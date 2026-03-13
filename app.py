"""
Kleine Terminliste - Berliner Veranstaltungskalender
für linke Subkultur und Politik
"""

import os
import re
import gc
import hashlib
import unicodedata
from html import unescape
from datetime import datetime, timedelta
from flask import Flask, render_template, request, session, jsonify, redirect, url_for
from flask_session import Session
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
import cloudscraper

# ─────────────────────────────────────────────────────────────────────────────
# Flask App Setup
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# Session Configuration
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "flask_session"
app.config["SESSION_PERMANENT"] = False
Session(app)

# ─────────────────────────────────────────────────────────────────────────────
# Datetime Helper
# ─────────────────────────────────────────────────────────────────────────────

def make_naive(dt: datetime) -> datetime:
    """Konvertiert timezone-aware datetime zu naive (entfernt tzinfo)."""
    if dt is None:
        return None
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


# ─────────────────────────────────────────────────────────────────────────────
# Slugify Helper
# ─────────────────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Konvertiert Text zu URL-freundlichem Slug."""
    if not text:
        return ""
    # Replace umlauts BEFORE normalization (NFKD decomposes them)
    replacements = {
        "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
        "Ä": "ae", "Ö": "oe", "Ü": "ue",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    # Normalize unicode
    text = unicodedata.normalize("NFKD", text)
    # Remove accents
    text = text.encode("ascii", "ignore").decode("ascii")
    # Lowercase and replace spaces/special chars
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Veranstalter (Quellen) - für Dropdown-Menü
# ─────────────────────────────────────────────────────────────────────────────

VERANSTALTER = {
    # Politische Bildung
    "rosa-luxemburg-stiftung": {"name": "Rosa-Luxemburg-Stiftung", "url": "https://www.rosalux.de"},
    "friedrich-ebert-stiftung": {"name": "Friedrich-Ebert-Stiftung", "url": "https://www.fes.de"},
    "berliner-landeszentrale-fuer-politische-bildung": {"name": "Berliner Landeszentrale für politische Bildung", "url": "https://www.berlin.de/politische-bildung"},
    "bundeszentrale-fuer-politische-bildung": {"name": "Bundeszentrale für politische Bildung", "url": "https://www.bpb.de"},
    "august-bebel-institut": {"name": "August Bebel Institut", "url": "https://august-bebel-institut.de"},
    # Theater & Performance
    "hau-hebbel-am-ufer": {"name": "HAU Hebbel am Ufer", "url": "https://www.hebbel-am-ufer.de"},
    "schaubuehne-berlin": {"name": "Schaubühne Berlin", "url": "https://www.schaubuehne.de"},
    "renaissance-theater": {"name": "Renaissance-Theater", "url": "https://renaissance-theater.de"},
    "rambazamba-theater": {"name": "RambaZamba Theater", "url": "https://www.rambazamba-theater.de"},
    "mehringhof-theater": {"name": "Mehringhof Theater", "url": "https://www.mehringhoftheater.de"},
    # Literatur & Lesungen
    "literaturforum-im-brecht-haus": {"name": "Literaturforum im Brecht-Haus", "url": "https://lfbrecht.de"},
    "literaturhaus-berlin": {"name": "Literaturhaus Berlin", "url": "https://li-be.de"},
    "lettretage": {"name": "Lettrétage", "url": "https://lettretage.de"},
    "haus-fuer-poesie": {"name": "Haus für Poesie", "url": "https://www.hausfuerpoesie.org"},
    # Buchhandlungen
    "pro-qm": {"name": "pro qm", "url": "https://pro-qm.de"},
    "zabriskie": {"name": "Zabriskie", "url": "https://zabriskie.de"},
    "buchbox": {"name": "Buchbox", "url": "https://www.buchboxberlin.de"},
    "ocelot": {"name": "Ocelot", "url": "https://www.genialokal.de/buchhandlung/berlin/ocelot/"},
    "schwarze-risse": {"name": "Schwarze Risse", "url": "https://schwarzerisse.de"},
    "b-books": {"name": "b_books", "url": "https://www.bbooks.de"},
    "zur-schwankenden-weltkugel": {"name": "Zur schwankenden Weltkugel", "url": "https://www.buchladen-weltkugel.de"},
    # Kinos
    "kino-central": {"name": "Kino Central", "url": "https://kino-central.de"},
    "lichtblick-kino": {"name": "Lichtblick Kino", "url": "https://lichtblick-kino.org"},
    "babylon-berlin": {"name": "Babylon Berlin", "url": "https://babylonberlin.eu"},
    "cinema-surreal": {"name": "Cinema Surreal", "url": "https://cinemasurreal.de"},
    # Clubs & Kulturzentren
    "baiz": {"name": "B.A.I.Z.", "url": "https://baiz.info"},
    "silent-green-kulturquartier": {"name": "Silent Green Kulturquartier", "url": "https://www.silent-green.net"},
    "acud-macht-neu": {"name": "ACUD macht neu", "url": "https://acudmachtneu.de"},
    "regenbogenfabrik": {"name": "Regenbogenfabrik", "url": "https://regenbogenfabrik.de"},
    "brotfabrik": {"name": "Brotfabrik", "url": "https://brotfabrik-berlin.de"},
    "so36": {"name": "SO36", "url": "https://so36.com"},
    "festsaal-kreuzberg": {"name": "Festsaal Kreuzberg", "url": "https://festsaal-kreuzberg.de"},
    "panke": {"name": "Panke", "url": "https://panke.gallery"},
    "peter-edel": {"name": "Peter Edel", "url": "https://www.peteredel.de"},
    "kubiz-wallenberg": {"name": "KuBiZ Wallenberg", "url": "https://www.kubiz-wallenberg.de"},
    "luftschloss-tempelhofer-feld": {"name": "Luftschloss Tempelhofer Feld", "url": "https://luftschloss-tempelhoferfeld.de"},
    "kreativhaus-berlin": {"name": "Kreativhaus Berlin", "url": "https://www.kreativhaus-berlin.de"},
    "flutgraben": {"name": "Flutgraben e.V.", "url": "https://flutgraben.org"},
    "alte-kantine-wedding": {"name": "Alte Kantine Wedding", "url": "https://alte-kantine.eu"},
    "frannz-club": {"name": "Frannz Club", "url": "https://frannz.eu"},
    "kesselhaus": {"name": "Kesselhaus", "url": "https://www.kesselhaus.net"},
    "panda-platforma": {"name": "Panda Platforma", "url": "https://panda-platforma.berlin"},
    # Museen & Ausstellungen
    "juedisches-museum-berlin": {"name": "Jüdisches Museum Berlin", "url": "https://www.jmberlin.de"},
    "deutsches-historisches-museum": {"name": "Deutsches Historisches Museum", "url": "https://www.dhm.de"},
    "humboldt-forum": {"name": "Humboldt Forum", "url": "https://www.humboldtforum.org"},
    "topographie-des-terrors": {"name": "Topographie des Terrors", "url": "https://www.topographie.de"},
    "anne-frank-zentrum": {"name": "Anne Frank Zentrum", "url": "https://www.annefrank.de"},
    "haus-der-wannsee-konferenz": {"name": "Haus der Wannsee-Konferenz", "url": "https://www.ghwk.de"},
    "dokumentationszentrum-flucht-vertreibung-versoehnung": {"name": "Dokumentationszentrum Flucht, Vertreibung, Versöhnung", "url": "https://www.flucht-vertreibung-versoehnung.de"},
    "traenenpalast": {"name": "Tränenpalast", "url": "https://www.hdg.de/traenenpalast"},
    "deutsches-technikmuseum": {"name": "Deutsches Technikmuseum", "url": "https://technikmuseum.berlin"},
    "deutsches-spionagemuseum": {"name": "Deutsches Spionagemuseum", "url": "https://www.deutsches-spionagemuseum.de"},
    "museum-fuer-kommunikation-berlin": {"name": "Museum für Kommunikation Berlin", "url": "https://www.mfk-berlin.de"},
    "bruecke-museum": {"name": "Brücke-Museum", "url": "https://www.bruecke-museum.de"},
    "kaethe-kollwitz-museum": {"name": "Käthe-Kollwitz-Museum Berlin", "url": "https://www.kaethe-kollwitz.berlin"},
    "mitte-museum": {"name": "Mitte Museum", "url": "https://www.mittemuseum.de"},
    "museum-charlottenburg-wilmersdorf": {"name": "Museum Charlottenburg-Wilmersdorf", "url": "https://www.villa-oppenheim-berlin.de"},
    "museum-reinickendorf": {"name": "Museum Reinickendorf", "url": "https://museum-reinickendorf.de"},
    # Kunst & Galerien
    "kw-institute-for-contemporary-art": {"name": "KW Institute for Contemporary Art", "url": "https://www.kw-berlin.de"},
    "gropius-bau": {"name": "Gropius Bau", "url": "https://www.berlinerfestspiele.de/gropiusbau"},
    "haus-am-waldsee": {"name": "Haus am Waldsee", "url": "https://www.hausamwaldsee.de"},
    "c-o-berlin": {"name": "C/O Berlin", "url": "https://co-berlin.org"},
    "ngbk": {"name": "nGbK", "url": "https://www.ngbk.de"},
    "nbk": {"name": "n.b.k. Neuer Berliner Kunstverein", "url": "https://www.nbk.org"},
    "kunstraum-kreuzberg-bethanien": {"name": "Kunstraum Kreuzberg/Bethanien", "url": "https://www.kunstraumkreuzberg.de"},
    "urban-nation": {"name": "Urban Nation Museum", "url": "https://urban-nation.com"},
    # Wissenschaft & Forschung
    "zois": {"name": "ZOiS – Zentrum für Osteuropa- und internationale Studien", "url": "https://www.zois-berlin.de"},
    "einstein-forum": {"name": "Einstein Forum", "url": "https://www.einsteinforum.de"},
    "leibniz-zentrum-fuer-zeithistorische-forschung": {"name": "Leibniz-Zentrum für Zeithistorische Forschung", "url": "https://zzf-potsdam.de"},
    "moses-mendelssohn-zentrum": {"name": "Moses Mendelssohn Zentrum", "url": "https://www.mmz-potsdam.de"},
    "critical-theory-berlin": {"name": "Critical Theory Berlin", "url": "https://criticaltheoryinberlin.de"},
    # Weitere Veranstaltungsorte
    "urania-berlin": {"name": "Urania Berlin", "url": "https://www.urania.de"},
    "zeiss-grossplanetarium": {"name": "Zeiss-Großplanetarium", "url": "https://www.planetarium.berlin"},
    "futurium": {"name": "Futurium", "url": "https://futurium.de"},
    "publix": {"name": "Publix", "url": "https://www.publix.de"},
    "mendelssohn-remise": {"name": "Mendelssohn-Remise", "url": "http://www.mendelssohn-remise.de"},
    "ffbiz": {"name": "FFBIZ", "url": "https://www.ffbiz.de"},
}


# ─────────────────────────────────────────────────────────────────────────────
# Dynamische Veranstaltungsorte (wird durch Scraper befüllt)
# ─────────────────────────────────────────────────────────────────────────────

# Basis-Venues (manuell gepflegt)
VENUES = {}

# Dynamisch entdeckte Venues (durch Scraper)
_DYNAMIC_VENUES: dict[str, dict] = {}


def get_all_venues() -> dict[str, dict]:
    """Gibt alle Venues zurück (statisch + dynamisch)."""
    all_venues = dict(VENUES)
    all_venues.update(_DYNAMIC_VENUES)
    return all_venues


def get_veranstalter() -> dict[str, dict]:
    """Gibt alle Veranstalter für das Dropdown zurück (alphabetisch sortiert)."""
    return dict(sorted(VERANSTALTER.items(), key=lambda x: x[1]["name"].lower()))


def get_bezirke_sorted() -> dict[str, str]:
    """Gibt Bezirke alphabetisch sortiert zurück."""
    return dict(sorted(BEZIRKE.items(), key=lambda x: x[1].lower()))


def get_event_types_sorted() -> dict[str, str]:
    """Gibt Event-Typen alphabetisch sortiert zurück."""
    return dict(sorted(EVENT_TYPES.items(), key=lambda x: x[1].lower()))


def get_or_create_venue(name: str, adresse: str = None, bezirk: str = None, url: str = None) -> str:
    """Holt existierenden Venue oder erstellt neuen. Gibt Slug zurück."""
    slug = slugify(name)
    if not slug:
        return "unbekannt"

    all_venues = get_all_venues()
    if slug in all_venues:
        return slug

    # Bezirk aus PLZ ermitteln falls nicht angegeben
    if not bezirk and adresse:
        bezirk = _bezirk_from_plz(adresse)

    _DYNAMIC_VENUES[slug] = {
        "name": name,
        "url": url,
        "bezirk": bezirk or "diverse",
        "adresse": adresse,
    }
    return slug


def _bezirk_from_plz(adresse: str) -> str:
    """Ermittelt Bezirk aus Postleitzahl in Adresse."""
    if not adresse:
        return "diverse"

    # PLZ-Mapping (vereinfacht)
    plz_match = re.search(r"\b(1\d{4})\b", adresse)
    if not plz_match:
        return "diverse"

    plz = plz_match.group(1)
    plz_prefix = plz[:3]

    # Grobe Zuordnung
    bezirk_map = {
        "101": "mitte",
        "102": "mitte",
        "103": "prenzlauer-berg",
        "104": "prenzlauer-berg",
        "105": "friedrichshain",
        "106": "kreuzberg",
        "107": "schoeneberg",
        "108": "mitte",
        "109": "kreuzberg",
        "120": "kreuzberg",
        "121": "neukoelln",
        "122": "treptow",
        "124": "treptow",
        "125": "neukoelln",
        "130": "weissensee",
        "131": "weissensee",
        "133": "wedding",
        "134": "wedding",
        "135": "reinickendorf",
        "136": "lichtenberg",
        "139": "pankow",
        "140": "charlottenburg",
        "141": "charlottenburg",
        "144": "potsdam",
        "145": "wilmersdorf",
        "146": "steglitz",
    }

    return bezirk_map.get(plz_prefix, "diverse")


# ─────────────────────────────────────────────────────────────────────────────
# Bezirke
# ─────────────────────────────────────────────────────────────────────────────

BEZIRKE = {
    "mitte": "Mitte",
    "kreuzberg": "Kreuzberg",
    "neukoelln": "Neukölln",
    "prenzlauer-berg": "Prenzlauer Berg",
    "friedrichshain": "Friedrichshain",
    "charlottenburg": "Charlottenburg",
    "schoeneberg": "Schöneberg",
    "wilmersdorf": "Wilmersdorf",
    "weissensee": "Weißensee",
    "wedding": "Wedding",
    "treptow": "Treptow",
    "lichtenberg": "Lichtenberg",
    "steglitz": "Steglitz",
    "reinickendorf": "Reinickendorf",
    "pankow": "Pankow",
    "potsdam": "Potsdam",
    "diverse": "Diverse",
}

# ─────────────────────────────────────────────────────────────────────────────
# Veranstaltungstypen
# ─────────────────────────────────────────────────────────────────────────────

EVENT_TYPES = {
    "lesung": "Lesung",
    "diskussion": "Diskussion & Vortrag",
    "film": "Film & Kino",
    "konzert": "Konzert & Musik",
    "party": "Party",
    "workshop": "Workshop",
    "theater": "Theater & Performance",
    "ausstellung": "Ausstellung",
    "politik": "Politik & Aktion",
    "sonstiges": "Sonstiges",
}

# ─────────────────────────────────────────────────────────────────────────────
# Venue Logos (filename in static/img/logos/)
# ─────────────────────────────────────────────────────────────────────────────

def get_venue_logo(veranstalter_slug: str) -> str | None:
    """Sucht automatisch nach Logo: static/img/logos/{slug}.svg"""
    logo_path = os.path.join(app.static_folder, "img", "logos", f"{veranstalter_slug}.svg")
    if os.path.exists(logo_path):
        return f"{veranstalter_slug}.svg"
    return None


@app.context_processor
def inject_venue_logos():
    """Make venue_logos function available in all templates."""
    # Scanne einmal alle verfügbaren Logos
    logos_dir = os.path.join(app.static_folder, "img", "logos")
    venue_logos = {}
    if os.path.exists(logos_dir):
        for filename in os.listdir(logos_dir):
            # Support svg, png, jpg, jpeg
            for ext in (".svg", ".png", ".jpg", ".jpeg"):
                if filename.endswith(ext):
                    slug = filename[:-len(ext)]
                    # Don't overwrite if svg already exists (prefer svg)
                    if slug not in venue_logos or filename.endswith(".svg"):
                        venue_logos[slug] = filename
                    break
    return {"venue_logos": venue_logos}


# ─────────────────────────────────────────────────────────────────────────────
# Zeitfenster für Suche
# ─────────────────────────────────────────────────────────────────────────────

TIME_SLOTS = {
    "10-12": "10–12 Uhr",
    "12-14": "12–14 Uhr",
    "14-16": "14–16 Uhr",
    "16-18": "16–18 Uhr",
    "18-20": "18–20 Uhr",
    "20-22": "20–22 Uhr",
    "22+": "Ab 22 Uhr",
}

# ─────────────────────────────────────────────────────────────────────────────
# In-Memory Event Cache
# ─────────────────────────────────────────────────────────────────────────────

_EVENT_CACHE: list[dict] = []
_CACHE_LOADING: bool = True  # Flag ob der Cache noch lädt


def is_cache_loading() -> bool:
    """Gibt True zurück wenn der Cache noch lädt."""
    return _CACHE_LOADING


def get_events() -> list[dict]:
    """Gibt alle gecachten Events zurück."""
    return _EVENT_CACHE


def get_events_by_date(date: datetime) -> list[dict]:
    """Filtert Events nach Datum."""
    return [e for e in _EVENT_CACHE if e.get("date") and e["date"].date() == date.date()]


def get_events_by_venue(venue_slug: str) -> list[dict]:
    """Filtert Events nach Veranstaltungsort."""
    return [e for e in _EVENT_CACHE if e.get("venue_slug") == venue_slug]


# Mapping von Veranstalter-Slug zu Source-ID
VERANSTALTER_SOURCE_MAP = {
    "rosa-luxemburg-stiftung": "rosalux",
    "hau-hebbel-am-ufer": "hau",
    "literaturforum-im-brecht-haus": "lfbrecht",
    "baiz": "baiz",
    "silent-green-kulturquartier": "silentgreen",
    "acud-macht-neu": "acud",
    "regenbogenfabrik": "regenbogenfabrik",
    "brotfabrik": "brotfabrik",
    "so36": "so36",
    "urania-berlin": "urania",
    "festsaal-kreuzberg": "festsaal",
    "panke": "panke",
    "kino-central": "kino-central",
    "lichtblick-kino": "lichtblick",
    "lettretage": "lettretage",
    "cinema-surreal": "cinemasurreal",
    "peter-edel": "peteredel",
    "kubiz-wallenberg": "kubiz",
    "zeiss-grossplanetarium": "planetarium",
    # "futurium": "futurium",  # PDF-Scraper noch nicht fertig
}


def get_events_by_veranstalter(veranstalter_slug: str) -> list[dict]:
    """Filtert Events nach Veranstalter (source)."""
    source_id = VERANSTALTER_SOURCE_MAP.get(veranstalter_slug)
    if source_id:
        return [e for e in _EVENT_CACHE if e.get("source") == source_id]
    # Fallback: nach venue_slug suchen
    return [e for e in _EVENT_CACHE if e.get("venue_slug") == veranstalter_slug]


def get_events_by_type(type_slug: str) -> list[dict]:
    """Filtert Events nach Typ."""
    return [e for e in _EVENT_CACHE if e.get("type") == type_slug]


def get_events_by_bezirk(bezirk_slug: str) -> list[dict]:
    """Filtert Events nach Bezirk."""
    return [e for e in _EVENT_CACHE if e.get("bezirk") == bezirk_slug]


# ─────────────────────────────────────────────────────────────────────────────
# Stressfaktor Scraper
# ─────────────────────────────────────────────────────────────────────────────

GERMAN_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}

GERMAN_MONTHS_DISPLAY = {
    1: "Januar", 2: "Februar", 3: "März", 4: "April",
    5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
    9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}

GERMAN_WEEKDAYS = {
    0: "Montag", 1: "Dienstag", 2: "Mittwoch", 3: "Donnerstag",
    4: "Freitag", 5: "Samstag", 6: "Sonntag",
}


@app.template_filter('german_date')
def german_date_filter(dt, fmt='full'):
    """Format datetime in German. fmt: 'full' = 'Montag, 05. März 2026', 'short' = '05. März 2026'"""
    if not dt:
        return ""
    day = dt.day
    month = GERMAN_MONTHS_DISPLAY.get(dt.month, "")
    year = dt.year
    weekday = GERMAN_WEEKDAYS.get(dt.weekday(), "")

    if fmt == 'short':
        return f"{day:02d}. {month} {year}"
    return f"{weekday}, {day:02d}. {month} {year}"


def _parse_german_date(text: str) -> datetime | None:
    """Parst deutsches Datum wie 'So., 1. März 2026'."""
    if not text:
        return None

    # Extrahiere Tag, Monat, Jahr
    match = re.search(r"(\d{1,2})\.\s*(\w+)\s*(\d{4})", text)
    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2).lower()
    year = int(match.group(3))

    month = GERMAN_MONTHS.get(month_name)
    if not month:
        return None

    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _classify_event_type(title: str, description: str = "") -> str:
    """Klassifiziert Event-Typ basierend auf Titel/Beschreibung."""
    text = (title + " " + description).lower()

    if any(w in text for w in ["lesung", "buchvorstellung", "autor", "literatur"]):
        return "lesung"
    if any(w in text for w in ["diskussion", "vortrag", "gespräch", "debatte", "panel", "podium"]):
        return "diskussion"
    if any(w in text for w in ["film", "kino", "screening", "dokumentar"]):
        return "film"
    if any(w in text for w in ["konzert", "musik", "live", "band", "dj"]):
        return "konzert"
    if any(w in text for w in ["party", "tanzen", "club", "rave"]):
        return "party"
    if any(w in text for w in ["workshop", "kurs", "seminar", "training"]):
        return "workshop"
    if any(w in text for w in ["theater", "performance", "bühne", "schauspiel"]):
        return "theater"
    if any(w in text for w in ["ausstellung", "vernissage", "galerie", "kunst"]):
        return "ausstellung"
    if any(w in text for w in ["demo", "kundgebung", "protest", "plenum", "versammlung", "aktion"]):
        return "politik"

    return "sonstiges"


def _detect_free_event(text: str) -> bool:
    """Erkennt ob ein Event kostenlos ist.

    Sucht nach typischen Formulierungen für kostenlose Veranstaltungen.
    """
    if not text:
        return False

    text_lower = text.lower()

    # Eindeutige Indikatoren für kostenlos
    free_patterns = [
        "eintritt frei",
        "eintritt: frei",
        "eintritt kostenlos",
        "kostenloser eintritt",
        "kostenfrei",
        "ohne eintritt",
        "freier eintritt",
        "0 €",
        "0€",
        "0,- €",
        "0,-€",
    ]

    for pattern in free_patterns:
        if pattern in text_lower:
            return True

    return False


def scrape_stressfaktor() -> list[dict]:
    """Scraped Events von stressfaktor.squat.net.

    Nur Events von ausgewählten Venues werden übernommen.
    Stressfaktor aggregiert Events ohne Originallinks, daher wird
    auf die Stressfaktor-Seite verlinkt.
    """
    events = []

    # Nur diese Venues von Stressfaktor scrapen (lowercase für Vergleich)
    # Venues mit eigenem Scraper (wie Baiz) werden hier ausgeschlossen
    # Venue-Aliase: Stressfaktor-Namen -> kanonische Namen
    VENUE_ALIASES = {
        "kubiz": "kubiz-wallenberg",
    }

    ALLOWED_VENUES = {
        "kubiz-wallenberg": {
            "name": "KuBiZ Wallenberg",
            "adresse": "Bernkasteler Straße 78, 13088 Berlin",
            "bezirk": "weissensee",
            "url": "https://www.kubiz-wallenberg.de",
        },
        "k19": {
            "name": "K19",
            "adresse": "Kreutzigerstraße 19, 10247 Berlin",
            "bezirk": "friedrichshain",
            "url": None,
        },
        "køpi": {
            "name": "Køpi",
            "adresse": "Köpenicker Straße 137, 10179 Berlin",
            "bezirk": "kreuzberg",
            "url": "https://koepi137.net",
        },
        "zielona góra": {
            "name": "Zielona Góra",
            "adresse": "Grünberger Straße 73, 10245 Berlin",
            "bezirk": "friedrichshain",
            "url": "https://zielona-gora.de",
        },
        "supamolly": {
            "name": "SupaMolly",
            "adresse": "Jessnerstraße 41, 10247 Berlin",
            "bezirk": "friedrichshain",
            "url": "https://supamolly.de",
        },
    }

    try:
        resp = requests.get(
            "https://stressfaktor.squat.net/termine",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Stressfaktor] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    current_date = None

    # Iteriere durch alle relevanten Elemente
    for elem in soup.select("h3, .views-row"):
        # Datums-Header
        if elem.name == "h3":
            date_text = elem.get_text(strip=True)
            parsed_date = _parse_german_date(date_text)
            if parsed_date:
                current_date = parsed_date
            continue

        # Event-Row
        if "views-row" not in elem.get("class", []):
            continue

        if not current_date:
            continue

        # Ort zuerst prüfen (Filter!)
        venue_elem = elem.select_one(".views-field-nothing a")
        venue_name_raw = venue_elem.get_text(strip=True) if venue_elem else "Unbekannt"
        venue_key = venue_name_raw.lower()

        # Aliase anwenden (z.B. "kubiz" -> "kubiz-wallenberg")
        venue_key = VENUE_ALIASES.get(venue_key, venue_key)

        # Nur erlaubte Venues
        if venue_key not in ALLOWED_VENUES:
            continue

        venue_info = ALLOWED_VENUES[venue_key]

        # Titel
        title_elem = elem.select_one(".views-field-title h4 a")
        if not title_elem:
            continue

        title = title_elem.get_text(strip=True)
        link = title_elem.get("href", "")
        if link and not link.startswith("http"):
            link = "https://stressfaktor.squat.net" + link

        # Zeit
        time_elem = elem.select_one(".views-field-field-date-time time")
        time_str = ""
        if time_elem:
            time_str = time_elem.get_text(strip=True)
            # Auch datetime-Attribut nutzen falls vorhanden
            dt_attr = time_elem.get("datetime", "")
            if dt_attr and "T" in dt_attr:
                try:
                    dt_parsed = dateparser.parse(dt_attr)
                    if dt_parsed:
                        current_date = current_date.replace(
                            hour=dt_parsed.hour,
                            minute=dt_parsed.minute
                        )
                except Exception:
                    pass

        # Beschreibung
        desc_elem = elem.select_one(".views-field-body")
        description = desc_elem.get_text(strip=True) if desc_elem else ""

        # Venue registrieren mit korrekten Infos
        venue_slug = get_or_create_venue(
            name=venue_info["name"],
            adresse=venue_info["adresse"],
            bezirk=venue_info["bezirk"],
            url=venue_info["url"],
        )

        # Event-Typ klassifizieren
        event_type = _classify_event_type(title, description)

        # Event-ID generieren
        event_id = hashlib.md5(f"{link}{current_date.isoformat()}".encode()).hexdigest()[:12]

        # Link: Wenn Venue eigene Website hat, diese bevorzugen
        event_link = venue_info.get("url") or link

        events.append({
            "id": event_id,
            "title": title,
            "date": current_date,
            "time": time_str,
            "venue_slug": venue_slug,
            "venue_name": venue_info["name"],
            "venue_address": venue_info["adresse"],
            "bezirk": venue_info["bezirk"],
            "type": event_type,
            "description": description,
            "link": event_link,
            "source": "stressfaktor",
        })

    print(f"[Stressfaktor] {len(events)} Events geladen (gefiltert)")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Rosa Luxemburg Stiftung Scraper
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_rosalux_details(event_url: str) -> dict:
    """Holt Veranstaltungsdetails von RosaLux Event-Detailseite.

    Nutzt Schema.org Markup (itemprop) für zuverlässige Extraktion.
    Returns: dict mit venue_name, address, bezirk, event_type_original, is_free
    """
    result = {
        "venue_name": "",
        "address": "",
        "bezirk": "",
        "event_type_original": "",
        "is_free": False,
    }

    try:
        resp = requests.get(
            event_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=10,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Event-Typ aus intro__meta (z.B. "Tagung/Konferenz")
        intro_meta = soup.select_one(".intro__meta")
        if intro_meta:
            type_text = intro_meta.get_text(strip=True).rstrip(":")
            if type_text:
                result["event_type_original"] = type_text

        # Nutze Schema.org Markup für Venue
        venue_name = ""
        room_name = ""
        street = ""
        plz = ""
        city = ""

        location_elem = soup.select_one('[itemprop="location"]')
        if location_elem:
            name_elem = location_elem.select_one('[itemprop="name"]')
            if name_elem:
                venue_name = name_elem.get_text(strip=True)

            # Adresse aus itemprop="address"
            address_elem = location_elem.select_one('[itemprop="address"]')
            if address_elem:
                street_elem = address_elem.select_one('[itemprop="streetAddress"]')
                plz_elem = address_elem.select_one('[itemprop="postalCode"]')
                city_elem = address_elem.select_one('[itemprop="addressLocality"]')

                if street_elem:
                    # streetAddress kann mehrere Zeilen enthalten (Raum + Straße)
                    # getrennt durch <br/> Tags
                    street_parts = []
                    for content in street_elem.children:
                        if hasattr(content, 'name') and content.name == 'br':
                            continue
                        text = content.get_text(strip=True) if hasattr(content, 'get_text') else str(content).strip()
                        if text:
                            street_parts.append(text)

                    # Letzte Zeile mit Hausnummer ist die Straße
                    # Vorherige Zeilen sind Raumname
                    if street_parts:
                        # Finde die Zeile mit Hausnummer (Straße)
                        street_line = None
                        room_lines = []
                        for part in street_parts:
                            # Hat Hausnummer? (Zahl am Ende oder "Platz/Str." + Zahl)
                            if re.search(r'\d+[a-zA-Z]?\s*$', part) or re.search(r'(Platz|Straße|Str\.|Allee|Weg|Damm)\s*\d*\s*$', part, re.IGNORECASE):
                                street_line = part
                            else:
                                room_lines.append(part)

                        if street_line:
                            street = street_line
                            if room_lines:
                                room_name = ", ".join(room_lines)
                        else:
                            # Fallback: Alles als Straße
                            street = " ".join(street_parts)

                if plz_elem:
                    plz = plz_elem.get_text(strip=True)
                if city_elem:
                    city = city_elem.get_text(strip=True)

        # Preis-Info erkennen
        page_text = soup.get_text(" ", strip=True)
        result["is_free"] = _detect_free_event(page_text)

        if street and plz:
            # Kombiniere Venue-Name mit Raum falls vorhanden
            if room_name:
                full_venue = f"{venue_name}, {room_name}" if venue_name else room_name
            else:
                full_venue = venue_name

            result["venue_name"] = full_venue
            result["address"] = f"{street}, {plz} {city}".strip()
            result["bezirk"] = _bezirk_from_plz(result["address"])
            return result

        # Fallback: Alte Methode mit dt/dd
        for dt in soup.select("dt"):
            if "veranstaltungsort" in dt.get_text(strip=True).lower():
                dd = dt.find_next_sibling("dd")
                if dd:
                    raw_text = dd.get_text(" ", strip=True)
                    raw_text = re.split(r"Informationen|Weitere|Derzeit", raw_text)[0].strip()

                    plz_match = re.search(r"(\d{5})\s*Berlin", raw_text)
                    if plz_match:
                        result["venue_name"] = raw_text[:60]
                        result["address"] = raw_text
                        result["bezirk"] = _bezirk_from_plz(raw_text)
                        return result

    except Exception:
        pass

    return result


def scrape_rosalux() -> list[dict]:
    """Scraped Events von rosalux.de/veranstaltungen - nur Berlin Events.

    Lädt für jedes Event die Detailseite um den genauen Veranstaltungsort zu bekommen.
    """
    events = []

    # Default-Venue für Fallback
    default_venue_name = "Rosa-Luxemburg-Stiftung"
    default_address = "Franz-Mehring-Platz 1, 10243 Berlin"

    try:
        resp = requests.get(
            "https://www.rosalux.de/veranstaltungen",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[RosaLux] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Iteriere über Event-Teaser statt nur Links
    for teaser in soup.select(".teaser--event"):
        try:
            # Link und Titel
            link = teaser.select_one("a[href*='/veranstaltung/es_detail/']")
            if not link:
                continue

            href = link.get("href", "")
            if not href:
                continue

            # ORT PRÜFEN: Nur Berlin-Events behalten
            location_elem = teaser.select_one(".teaser__date-group--right span")
            if not location_elem:
                continue

            location = location_elem.get_text(strip=True).lower()
            # Nur Berlin oder Online Events
            if location not in ("berlin", "online"):
                continue

            # Titel extrahieren
            title_elem = teaser.select_one(".teaser__title-text")
            if not title_elem:
                continue
            title = title_elem.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            event_link = f"https://www.rosalux.de{href}" if href.startswith("/") else href

            # Datum aus Struktur extrahieren
            day_elem = teaser.select_one(".teaser__date-day")
            month_elem = teaser.select_one(".teaser__date-month")
            year_elem = teaser.select_one(".teaser__date-year")

            if not (day_elem and month_elem and year_elem):
                continue

            day = int(day_elem.get_text(strip=True))
            month_name = month_elem.get_text(strip=True).lower()
            year = int(year_elem.get_text(strip=True))

            month = GERMAN_MONTHS.get(month_name)
            if not month:
                continue

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            # Zeit extrahieren
            time_str = ""
            time_spans = teaser.select(".teaser__date-group--right span")
            for span in time_spans:
                text = span.get_text(strip=True)
                time_match = re.match(r"(\d{1,2}):(\d{2})", text)
                if time_match:
                    time_str = f"{time_match.group(1)}:{time_match.group(2)}"
                    break

            # Beschreibung
            description = ""
            desc_elem = teaser.select_one(".teaser__text")
            if desc_elem:
                description = desc_elem.get_text(strip=True)

            # Details von Detailseite holen (Venue, Adresse, Event-Typ, Preis)
            details = _fetch_rosalux_details(event_link)

            venue_name = details.get("venue_name") or default_venue_name
            address = details.get("address") or default_address
            bezirk = details.get("bezirk") or "friedrichshain"
            event_type_original = details.get("event_type_original", "")
            is_free = details.get("is_free", False)

            # Event-Typ für Filterung (Kategorie)
            event_type = "diskussion"
            type_lower = event_type_original.lower()
            if "film" in type_lower:
                event_type = "film"
            elif "konzert" in type_lower or "musik" in type_lower:
                event_type = "konzert"
            elif "ausstellung" in type_lower:
                event_type = "ausstellung"
            elif "workshop" in type_lower or "seminar" in type_lower:
                event_type = "workshop"
            elif "lesung" in type_lower:
                event_type = "lesung"

            # Online-Events markieren
            if location == "online":
                venue_name = f"{venue_name} (Online)" if venue_name else "Online"
                address = "Online"
                bezirk = "diverse"

            # Venue registrieren
            venue_slug = get_or_create_venue(
                name=venue_name,
                adresse=address,
                bezirk=bezirk,
                url="https://www.rosalux.de",
            )

            event_id = hashlib.md5(f"rosalux-{event_link}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": address,
                "bezirk": bezirk,
                "type": event_type,
                "type_display": event_type_original or "Diskussion & Vortrag",
                "description": description,
                "link": event_link,
                "source": "rosalux",
                "is_free": is_free,
            })
        except Exception:
            continue

    print(f"[RosaLux] {len(events)} Events geladen (nur Berlin)")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# HAU Hebbel am Ufer Scraper
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_hau_details(url: str) -> dict:
    """Fetch description and price info from HAU event detail page."""
    result = {"description": "", "is_free": False}
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Description is in .realContent
        # Try strong first, but only if it's a real description (not just a name)
        real_content = soup.select_one(".realContent")
        if real_content:
            strong_elem = real_content.select_one("strong")
            description = ""

            if strong_elem:
                strong_text = strong_elem.get_text(strip=True)
                # Only use strong if it's long enough to be a description
                # (short texts are often just artist names)
                if len(strong_text) > 30 and " " in strong_text:
                    description = strong_text

            # Fallback to first paragraph if strong wasn't useful
            if not description:
                p_elem = real_content.select_one("p")
                if p_elem:
                    description = p_elem.get_text(strip=True)

            result["description"] = description[:300] if description else ""

        # Check for free event
        page_text = soup.get_text(" ", strip=True)
        result["is_free"] = _detect_free_event(page_text)
    except Exception:
        pass
    return result


def scrape_hau() -> list[dict]:
    """Scraped Events von hebbel-am-ufer.de."""
    events = []

    # HAU venue addresses
    HAU_ADDRESSES = {
        "HAU1": "Stresemannstraße 29, 10963 Berlin",
        "HAU2": "Hallesches Ufer 34, 10963 Berlin",
        "HAU3": "Tempelhofer Ufer 10, 10963 Berlin",
        "WAU": "Hallesches Ufer 34, 10963 Berlin",
        "HAU3 Houseclub": "Tempelhofer Ufer 10, 10963 Berlin",
    }

    # Categories to block
    BLOCKED_CATEGORIES = {"tanz", "performance", "theater"}

    try:
        resp = requests.get(
            "https://www.hebbel-am-ufer.de/programm/spielplan-tickets",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[HAU] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    current_year = datetime.now().year
    current_month = None

    # Parse month headers and event items
    for month_div in soup.select("div.month"):
        # Extract month from header like "März 2026"
        month_header = month_div.select_one("h3")
        if month_header:
            month_text = month_header.get_text(strip=True).lower()
            for m_name, m_num in GERMAN_MONTHS.items():
                if m_name in month_text:
                    current_month = m_num
                    break

    # Process event items
    for item in soup.select("div.item, li.item"):
        try:
            # Titel aus h3 und h4 kombinieren
            h3_elem = item.select_one("h3")
            h4_elem = item.select_one("h4")
            if not h3_elem and not h4_elem:
                continue

            title_parts = []
            if h3_elem:
                title_parts.append(h3_elem.get_text(strip=True))
            if h4_elem:
                title_parts.append(h4_elem.get_text(strip=True))
            title = " – ".join(title_parts) if len(title_parts) > 1 else title_parts[0]

            if not title or len(title) < 3:
                continue

            # Extract categories from li.cat elements
            categories = []
            for cat_elem in item.select("li.cat"):
                cat_text = cat_elem.get_text(strip=True).lower()
                categories.append(cat_text)

            # Skip events with blocked categories
            if any(cat in BLOCKED_CATEGORIES for cat in categories):
                continue

            # Use first category as type_display
            type_display = ""
            if categories:
                type_display = item.select_one("li.cat").get_text(strip=True)

            # Link
            link_elem = item.select_one("a[href*='/programm/pdetail/']")
            if not link_elem:
                continue

            href = link_elem.get("href", "")
            event_link = f"https://www.hebbel-am-ufer.de{href}" if href.startswith("/") else href

            # Extract venue from data-venue attribute
            venue_elem = item.select_one("a[data-venue]")
            hau_venue = venue_elem.get("data-venue", "HAU1") if venue_elem else "HAU1"
            venue_address = HAU_ADDRESSES.get(hau_venue, HAU_ADDRESSES["HAU1"])
            venue_name = f"HAU Hebbel am Ufer ({hau_venue})"

            # Get date from parent day element
            day_parent = item.find_parent("li", class_="day")
            if not day_parent:
                # Try finding in sibling structure
                day_parent = item.find_parent("div", class_="ul-style")
                if day_parent:
                    day_parent = day_parent.find_parent("li", class_="day")

            day = None
            if day_parent:
                date_header = day_parent.select_one("h2.big")
                if date_header:
                    date_text = date_header.get_text(strip=True)
                    date_match = re.search(r"(\d{1,2})", date_text)
                    if date_match:
                        day = int(date_match.group(1))

            if not day:
                # Fallback: try to find date in item text
                text = item.get_text(" ", strip=True)
                date_match = re.search(r"(Mo|Di|Mi|Do|Fr|Sa|So)\s+(\d{1,2})", text)
                if date_match:
                    day = int(date_match.group(2))
                else:
                    continue

            # Get month from data-filterDate attribute or use current
            month = current_month or datetime.now().month
            if day_parent and day_parent.get("data-filterDate"):
                filter_date = day_parent.get("data-filterDate", "")
                date_parts = filter_date.split("-")
                if len(date_parts) == 2:
                    try:
                        month = int(date_parts[1])
                    except ValueError:
                        pass

            year = current_year
            if month < datetime.now().month:
                year += 1

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            # Zeit aus strong-Tag
            time_elem = item.select_one("strong")
            time_str = ""
            if time_elem:
                time_text = time_elem.get_text(strip=True)
                time_match = re.search(r"(\d{1,2}):(\d{2})", time_text)
                if time_match:
                    time_str = f"{time_match.group(1)}:{time_match.group(2)}"

            venue_slug = get_or_create_venue(
                name="HAU Hebbel am Ufer",
                adresse=venue_address,
                bezirk="kreuzberg",
                url="https://www.hebbel-am-ufer.de",
            )

            event_id = hashlib.md5(f"hau-{event_link}-{event_date.isoformat()}-{time_str}".encode()).hexdigest()[:12]

            # Determine internal type from categories
            event_type = "theater"
            if "musik" in categories:
                event_type = "konzert"
            elif "dialog" in categories:
                event_type = "diskussion"
            elif "film" in categories:
                event_type = "film"
            elif "ausstellung" in categories:
                event_type = "ausstellung"

            # Fetch description and price from detail page
            hau_details = _fetch_hau_details(event_link)
            description = hau_details.get("description", "")
            is_free = hau_details.get("is_free", False)

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "kreuzberg",
                "type": event_type,
                "type_display": type_display,
                "description": description,
                "link": event_link,
                "source": "hau",
                "is_free": is_free,
            })
        except Exception:
            continue

    print(f"[HAU] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Literaturforum im Brecht-Haus Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_lfbrecht() -> list[dict]:
    """Scraped Events von lfbrecht.de/events/."""
    events = []
    venue_name = "Literaturforum im Brecht-Haus"
    venue_address = "Chausseestraße 125, 10115 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://lfbrecht.de",
    )

    try:
        resp = requests.get(
            "https://lfbrecht.de/events/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[LFBrecht] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    seen_links = set()

    # Iteriere über article-Elemente (WordPress tribe_events)
    for article in soup.select("article.type-tribe_events"):
        try:
            # Link zum Event
            link_elem = article.select_one("a[href*='/event/']")
            if not link_elem:
                continue

            href = link_elem.get("href", "")
            if not href or href in seen_links:
                continue
            seen_links.add(href)

            event_link = href if href.startswith("http") else f"https://lfbrecht.de{href}"

            # Titel aus .list_infos
            title_elem = article.select_one(".list_infos a")
            title = title_elem.get_text(strip=True) if title_elem else ""
            if not title or len(title) < 5:
                continue

            # Datum und Zeit aus .duration
            duration_elem = article.select_one(".duration")
            if not duration_elem:
                continue

            duration_text = duration_elem.get_text(" ", strip=True)

            # Datum (Format: "Di. 03.03.")
            date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.?", duration_text)
            if not date_match:
                continue

            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = datetime.now().year
            # Jahreswechsel-Logik
            current_month = datetime.now().month
            if month < current_month and (current_month - month) > 2:
                year += 1

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            # Zeit (Format: "20:00")
            time_match = re.search(r"(\d{1,2}):(\d{2})", duration_text)
            time_str = f"{time_match.group(1)}:{time_match.group(2)}" if time_match else ""

            # Beschreibung
            desc_elem = article.select_one(".description")
            description = desc_elem.get_text(strip=True)[:200] if desc_elem else ""

            # Typ aus Kategorien ermitteln
            event_type = _classify_event_type(title, duration_text + " " + description)
            if event_type == "sonstiges":
                event_type = "lesung"  # Default für Literaturforum

            event_id = hashlib.md5(f"lfbrecht-{event_link}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "mitte",
                "type": event_type,
                "description": description,
                "link": event_link,
                "source": "lfbrecht",
            })
        except Exception:
            continue

    print(f"[LFBrecht] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Baiz Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_baiz() -> list[dict]:
    """Scraped Events von baiz.info/programm/."""
    events = []
    venue_name = "Baiz"
    venue_address = "Schönhauser Allee 26a, 10435 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="prenzlauer-berg",
        url="https://www.baiz.info",
    )

    try:
        resp = requests.get(
            "https://www.baiz.info/programm/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Baiz] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    current_year = datetime.now().year

    # Suche nach Event-Einträgen (Bold-Text mit Datum)
    for elem in soup.select("strong, b"):
        try:
            text = elem.get_text(strip=True)

            # Pattern: "Samstag, 14.02. 19:30 Kneipenquiz"
            match = re.search(r"(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),?\s*(\d{1,2})\.(\d{1,2})\.?\s*(\d{1,2}):(\d{2})\s+(.+)", text)
            if not match:
                continue

            day = int(match.group(2))
            month = int(match.group(3))
            hour = int(match.group(4))
            minute = int(match.group(5))
            title = match.group(6).strip()

            if not title:
                continue

            year = current_year
            # Nur ins nächste Jahr wechseln wenn Monat weit zurück liegt (nicht nur < aktueller Monat)
            current_month = datetime.now().month
            if month < current_month and (current_month - month) > 2:
                year += 1

            try:
                event_date = datetime(year, month, day, hour, minute)
            except ValueError:
                continue

            time_str = f"{hour:02d}:{minute:02d}"

            # Beschreibung aus folgendem Text
            description = ""
            next_elem = elem.find_next_sibling("p")
            if next_elem:
                description = next_elem.get_text(strip=True)[:200]

            event_id = hashlib.md5(f"baiz-{event_date.isoformat()}-{title}".encode()).hexdigest()[:12]
            event_type = _classify_event_type(title, description)

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "prenzlauer-berg",
                "type": event_type,
                "description": description,
                "link": "https://www.baiz.info/programm/",
                "source": "baiz",
            })
        except Exception:
            continue

    print(f"[Baiz] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Silent Green Scraper
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_silentgreen_details(url: str) -> dict:
    """Fetch details from Silent Green event detail page."""
    result = {"title": "", "description": "", "type_display": "", "is_free": False}
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Spitzmarke from h1 with itemprop="headline"
        h1 = soup.select_one("h1[itemprop='headline']")
        if h1:
            result["type_display"] = h1.get_text(strip=True)

        # Full title from h2 in ce-bodytext
        bodytext = soup.select_one(".ce-bodytext")
        if bodytext:
            h2 = bodytext.select_one("h2")
            if h2:
                result["title"] = h2.get_text(strip=True)

            # Description from first p tag after h2
            p = bodytext.select_one("p")
            if p:
                result["description"] = p.get_text(strip=True)

        # Check for free event
        page_text = soup.get_text(" ", strip=True)
        result["is_free"] = _detect_free_event(page_text)

    except Exception:
        pass
    return result


def scrape_silentgreen() -> list[dict]:
    """Scraped Events von silent-green.net/programm.

    Filtert normale Konzerte raus - nur Specials wie Film, Lesung, etc.
    """
    events = []
    venue_name = "Silent Green Kulturquartier"
    venue_address = "Gerichtstraße 35, 13347 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Gerichtstraße 35, 13347 Berlin",
        bezirk="wedding",
        url="https://www.silent-green.net",
    )

    try:
        resp = requests.get(
            "https://www.silent-green.net/programm",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[SilentGreen] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    seen_links = set()

    # Suche nach Event-Links mit /programm/detail/
    for link in soup.select("a[href*='/programm/detail/']"):
        try:
            href = link.get("href", "")
            if not href or href in seen_links:
                continue
            seen_links.add(href)

            # Titel aus Link-Text (vorläufig)
            link_title = link.get_text(strip=True)
            if not link_title or len(link_title) < 3:
                continue

            event_link = f"https://www.silent-green.net{href}" if href.startswith("/") else href

            # Datum aus URL-Parametern extrahieren (day, month, year in Query-String)
            day_match = re.search(r"day%5D=(\d+)", href) or re.search(r"day\]=(\d+)", href)
            month_match = re.search(r"month%5D=(\d+)", href) or re.search(r"month\]=(\d+)", href)
            year_match = re.search(r"year%5D=(\d+)", href) or re.search(r"year\]=(\d+)", href)

            if not (day_match and month_match and year_match):
                continue

            day = int(day_match.group(1))
            month = int(month_match.group(1))
            year = int(year_match.group(1))

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            # Zeit aus Parent-Container
            parent = link.find_parent("div") or link.find_parent("li")
            time_str = ""
            if parent:
                text = parent.get_text(" ", strip=True)
                time_match = re.search(r"(\d{1,2}):(\d{2})", text)
                if time_match:
                    time_str = f"{time_match.group(1)}:{time_match.group(2)}"

            # Konzerte rausfiltern - nur Specials behalten
            if link_title.lower().startswith("konzert"):
                continue

            # Fetch details from detail page
            details = _fetch_silentgreen_details(event_link)

            # Use detail page title if available, otherwise clean link title
            if details["title"]:
                title = details["title"]
            else:
                # Entferne Kategorieprefix aus Link-Titel
                title = re.sub(r"^(Konzert|Filmvorführung|Festival|Lesung|Installation|Performance|Ausstellung)\s*", "", link_title).strip()
                if not title:
                    title = link_title
            description = details["description"]
            type_display = details["type_display"]
            is_free = details.get("is_free", False)

            # Classify event type
            event_type = _classify_event_type(type_display or link_title, description)

            event_id = hashlib.md5(f"silentgreen-{event_link}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "wedding",
                "type": event_type,
                "type_display": type_display,
                "description": description,
                "link": event_link,
                "source": "silentgreen",
                "is_free": is_free,
            })
        except Exception:
            continue

    print(f"[SilentGreen] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Cinema Surreal (Sammlung Scharf-Gerstenberg) Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_cinema_surreal() -> list[dict]:
    """Scraped Events von smb.museum Cinema Surreal Filmreihe."""
    events = []
    venue_name = "Sammlung Scharf-Gerstenberg"
    venue_address = "Schloßstraße 70, 14059 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Schloßstraße 70, 14059 Berlin",
        bezirk="charlottenburg",
        url="https://www.smb.museum/museen-einrichtungen/sammlung-scharf-gerstenberg/",
    )

    try:
        resp = requests.get(
            "https://www.smb.museum/museen-einrichtungen/sammlung-scharf-gerstenberg/veranstaltungen/veranstaltungsreihe/cinema-surreal-2026/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[CinemaSurreal] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    for link in soup.select("a[href*='/veranstaltungen/detail/']"):
        try:
            title = link.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            href = link.get("href", "")
            event_link = f"https://www.smb.museum{href}" if href.startswith("/") else href

            # Parent für Datum
            parent = link.find_parent("div")
            if not parent:
                continue

            text = parent.get_text(" ", strip=True)

            # Datum (Format: "04.03.2026 18:00 Uhr")
            date_match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})\s+(\d{1,2}):(\d{2})", text)
            if not date_match:
                continue

            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = int(date_match.group(3))
            hour = int(date_match.group(4))
            minute = int(date_match.group(5))

            try:
                event_date = datetime(year, month, day, hour, minute)
            except ValueError:
                continue

            time_str = f"{hour:02d}:{minute:02d}"

            event_id = hashlib.md5(f"cinemasurreal-{event_link}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "charlottenburg",
                "type": "film",
                "description": "Cinema Surreal Filmreihe",
                "link": event_link,
                "source": "cinemasurreal",
            })
        except Exception:
            continue

    print(f"[CinemaSurreal] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Acud Macht Neu Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_acud() -> list[dict]:
    """Scraped Events von acudmachtneu.de."""
    events = []
    venue_name = "Acud Macht Neu"
    venue_address = "Veteranenstraße 21, 10119 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Veteranenstraße 21, 10119 Berlin",
        bezirk="mitte",
        url="https://acudmachtneu.de",
    )

    try:
        resp = requests.get(
            "https://acudmachtneu.de/programm/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Acud] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    current_year = datetime.now().year
    seen_links = set()

    # Suche nach Datumspattern "Mo 2.3 → Concert"
    for text_elem in soup.find_all(string=lambda t: t and any(day in str(t) for day in ["Mo ", "Di ", "Mi ", "Do ", "Fr ", "Sa ", "So "])):
        try:
            text = str(text_elem).strip()

            # Pattern: "Mo 2.3 → Concert" oder "Fr 6.3 — So 5.4 → Exhibition"
            date_match = re.search(r"(Mo|Di|Mi|Do|Fr|Sa|So)\s+(\d{1,2})\.(\d{1,2})", text)
            if not date_match:
                continue

            day = int(date_match.group(2))
            month = int(date_match.group(3))
            year = current_year
            current_month = datetime.now().month
            if month < current_month and (current_month - month) > 2:
                year += 1

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            # Event-Typ aus Text
            type_text = text.lower()
            if "concert" in type_text:
                event_type = "konzert"
            elif "club" in type_text:
                event_type = "party"
            elif "exhibition" in type_text:
                event_type = "ausstellung"
            elif "performance" in type_text:
                event_type = "theater"
            elif "film" in type_text or "screening" in type_text:
                event_type = "film"
            else:
                event_type = "sonstiges"

            # Finde nächsten Link für Titel
            parent = text_elem.find_parent()
            if not parent:
                continue

            next_link = parent.find_next("a", href=lambda h: h and "/events/" in h)
            if not next_link:
                continue

            href = next_link.get("href", "")
            if not href or href in seen_links:
                continue
            seen_links.add(href)

            title = next_link.get_text(strip=True)
            if not title or len(title) < 2:
                continue

            event_link = href if href.startswith("http") else f"https://acudmachtneu.de{href}"

            # Detailseite für Uhrzeit und Beschreibung laden
            time_str = ""
            description = ""
            try:
                detail_resp = requests.get(
                    event_link,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                    timeout=10,
                )
                detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

                # Beschreibung aus article p Tags
                paragraphs = detail_soup.select("article p")
                desc_parts = []
                for p in paragraphs:
                    p_text = p.get_text(" ", strip=True)
                    if p_text and len(p_text) > 20:
                        desc_parts.append(p_text)
                if desc_parts:
                    description = " ".join(desc_parts)[:300]

                # Uhrzeit aus Beschreibung extrahieren (z.B. "20H", "8pm", "20:00")
                page_text = detail_soup.get_text(" ", strip=True)
                time_match = re.search(r"(\d{1,2})[Hh](?:\s|,|$)", page_text)
                if time_match:
                    hour = int(time_match.group(1))
                    time_str = f"{hour:02d}:00"
                else:
                    time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*[Uu]hr", page_text)
                    if time_match:
                        hour = int(time_match.group(1))
                        minute = int(time_match.group(2)) if time_match.group(2) else 0
                        time_str = f"{hour:02d}:{minute:02d}"
                    else:
                        time_match = re.search(r"(\d{1,2})\s*pm", page_text.lower())
                        if time_match:
                            hour = int(time_match.group(1)) + 12
                            if hour == 24:
                                hour = 12
                            time_str = f"{hour:02d}:00"
            except Exception:
                pass

            event_id = hashlib.md5(f"acud-{event_link}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "mitte",
                "type": event_type,
                "description": description,
                "link": event_link,
                "source": "acud",
            })
        except Exception:
            continue

    print(f"[Acud] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Regenbogenfabrik Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_regenbogenfabrik() -> list[dict]:
    """Scraped Events von regenbogenfabrik.de."""
    events = []
    venue_name = "Regenbogenfabrik"
    venue_address = "Lausitzer Straße 22, 10999 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Lausitzer Straße 22, 10999 Berlin",
        bezirk="kreuzberg",
        url="https://regenbogenfabrik.de",
    )

    try:
        resp = requests.get(
            "https://regenbogenfabrik.de/veranstaltungen/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Regenbogenfabrik] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    seen_links = set()

    # Finde alle Event-Links
    for link in soup.select("a[href*='regenbogenfabrik.de/']"):
        try:
            href = link.get("href", "")
            # Filtere Navigations-Links
            if not href or href in seen_links:
                continue
            if any(x in href for x in ["/veranstaltungen/", "/category/", "/tag/", "/#", "/page/"]):
                continue
            if href.endswith("/"):
                href_clean = href.rstrip("/")
            else:
                href_clean = href

            # Nur Event-Links (nicht Home, Kontakt, etc.)
            if href_clean.count("/") < 3:
                continue

            seen_links.add(href)

            # Titel aus Link-Text oder nächstem Text
            title = link.get_text(strip=True)
            if title == "Weiterlesen ›" or not title or len(title) < 3:
                # Suche Titel im vorherigen Text
                prev = link.find_previous(string=True)
                if prev:
                    title = prev.strip()

            if not title or len(title) < 3 or title == "Weiterlesen ›":
                continue

            # Suche Datum im umgebenden Text
            parent = link.find_parent("article") or link.find_parent("div")
            if not parent:
                continue

            text = parent.get_text(" ", strip=True)

            # Finde das nächste Datum vor diesem Link
            # Format: "Donnerstag, 05.03.2026"
            date_matches = list(re.finditer(
                r"(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),\s*(\d{2})\.(\d{2})\.(\d{4})",
                text
            ))

            if not date_matches:
                continue

            # Finde das passende Datum für diesen Link (basierend auf Position im Text)
            link_text_pos = text.find(title)
            best_match = None
            for m in date_matches:
                if m.start() < link_text_pos:
                    best_match = m

            if not best_match:
                best_match = date_matches[0]

            day = int(best_match.group(1))
            month = int(best_match.group(2))
            year = int(best_match.group(3))

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            # Zeit (suche nach dem Datum)
            date_end = best_match.end()
            remaining_text = text[date_end:date_end+100]
            time_match = re.search(r"(\d{1,2}):(\d{2})", remaining_text)
            time_str = f"{time_match.group(1)}:{time_match.group(2)}" if time_match else ""

            event_id = hashlib.md5(f"regenbogenfabrik-{href}".encode()).hexdigest()[:12]
            event_type = _classify_event_type(title, text)

            # Fetch description from detail page
            description = ""
            try:
                detail_resp = requests.get(
                    href,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                    timeout=10,
                )
                if detail_resp.status_code == 200:
                    detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                    # Description is in p tags within the content
                    for p in detail_soup.select("article p, .entry-content p, .content p"):
                        p_text = p.get_text(strip=True)
                        if len(p_text) > 30:
                            description = p_text[:300]
                            break
            except Exception:
                pass

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "kreuzberg",
                "type": event_type,
                "description": description,
                "link": href,
                "source": "regenbogenfabrik",
            })
        except Exception:
            continue

    print(f"[Regenbogenfabrik] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Lettrétage Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_lettretage() -> list[dict]:
    """Scraped Events von lettretage.de."""
    events = []
    venue_name = "Lettrétage"
    venue_address = "Veteranenstraße 21, 10119 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Veteranenstraße 21, 10119 Berlin",
        bezirk="mitte",
        url="https://www.lettretage.de",
    )

    try:
        resp = requests.get(
            "https://www.lettretage.de/programm/aktuelles-programm/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Lettretage] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    current_year = datetime.now().year

    for item in soup.select("li.event"):
        try:
            text = item.get_text(" ", strip=True)

            # Datum (Format: "Mo. 02 März 2026")
            date_match = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", text)
            if not date_match:
                continue

            day = int(date_match.group(1))
            month_name = date_match.group(2).lower()
            year = int(date_match.group(3))

            month = GERMAN_MONTHS.get(month_name)
            if not month:
                continue

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            # Titel: Text nach Datum bis zur Uhrzeit
            title_match = re.search(r"\d{4}\s+(.+?)\s+\d{1,2}:\d{2}", text)
            if title_match:
                title = title_match.group(1).strip()
            else:
                continue

            if not title or len(title) < 3:
                continue

            # Zeit
            time_match = re.search(r"(\d{1,2}):(\d{2})", text)
            time_str = f"{time_match.group(1)}:{time_match.group(2)}" if time_match else ""

            # Beschreibung
            description = ""
            desc_match = re.search(r"Eintritt.*?€\s+(.+?)$", text)
            if desc_match:
                description = desc_match.group(1)[:150]

            event_id = hashlib.md5(f"lettretage-{event_date.isoformat()}-{title}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "mitte",
                "type": "lesung",
                "description": description,
                "link": "https://www.lettretage.de/programm/aktuelles-programm/",
                "source": "lettretage",
            })
        except Exception:
            continue

    print(f"[Lettretage] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Brotfabrik Scraper
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_brotfabrik_details(url: str) -> dict:
    """Fetch description and category from Brotfabrik event detail page."""
    result = {"description": "", "category": "", "is_free": False}
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Kategorie aus URL oder Menü erkennen
        if "/kino/" in url or "brot-menu-kino" in resp.text:
            result["category"] = "film"

        # Beschreibung aus p-Tags im Content-Bereich
        # Suche nach dem längsten zusammenhängenden Text
        paragraphs = soup.select("p")
        best_desc = ""
        for p in paragraphs:
            text = p.get_text(strip=True)
            # Ignoriere kurze Texte, Datums-/Zeitangaben, Footer-Texte
            if len(text) > 80 and not text.startswith("©") and "Kontakt" not in text[:20]:
                if "eingesperrt" in text or "Jahre" in text or len(text) > len(best_desc):
                    # Bevorzuge inhaltliche Beschreibungen
                    if not re.match(r"^\d+\.\d+\.\s*\|", text):  # Keine Datumszeilen
                        best_desc = text
                        break

        result["description"] = best_desc[:500] if best_desc else ""

        # Check for free event
        page_text = soup.get_text(" ", strip=True)
        result["is_free"] = _detect_free_event(page_text)

    except Exception:
        pass
    return result


def scrape_brotfabrik() -> list[dict]:
    """Scraped Events von brotfabrik-berlin.de via iCal-Feed.

    Filtert Kinderveranstaltungen aus.
    """
    # Blockliste für Titel (Kinderveranstaltungen)
    BLOCKED_TITLE_PATTERNS = [
        "für kinder", "kinder ab",
        "ab 3", "ab 4", "ab 5", "ab 6", "ab 7", "ab 8",
        "alle ab 3", "alle ab 4", "alle ab 5", "alle ab 6",
        "puppentheater", "kindertheater",
    ]

    events = []
    venue_name = "Brotfabrik"
    venue_address = "Caligariplatz 1, 13086 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="weissensee",
        url="https://brotfabrik-berlin.de",
    )

    # iCal-Feed nutzen (zuverlaessiger als HTML-Scraping)
    try:
        resp = requests.get(
            "https://brotfabrik-berlin.de/veranstaltungen/?ical=1",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Brotfabrik] Fehler beim Laden: {e}")
        return []

    # Kategorien-Mapping
    category_map = {
        "kino": "film",
        "buehne": "theater",
        "bühne": "theater",
        "galerie": "ausstellung",
        "ausstellung": "ausstellung",
        "literatur": "lesung",
        "kneipe": "sonstiges",
    }

    now = datetime.now()
    ical_text = resp.text

    # VEVENT-Bloecke parsen
    vevent_pattern = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.DOTALL)

    for match in vevent_pattern.finditer(ical_text):
        try:
            block = match.group(1)

            # Titel
            summary_match = re.search(r"SUMMARY:(.+?)(?:\r?\n(?! )|\Z)", block, re.DOTALL)
            if not summary_match:
                continue
            title = summary_match.group(1).strip()
            # iCal-Escaping rueckgaengig machen
            title = title.replace("\\,", ",").replace("\\n", " ").replace("\\;", ";")

            # Filter: Kinderveranstaltungen ausschließen
            title_lower = title.lower()
            if any(pattern in title_lower for pattern in BLOCKED_TITLE_PATTERNS):
                continue

            # Datum/Zeit
            dtstart_match = re.search(r"DTSTART(?:;[^:]+)?:(\d{8}T\d{6})", block)
            if not dtstart_match:
                continue
            dt_str = dtstart_match.group(1)
            event_date = datetime.strptime(dt_str, "%Y%m%dT%H%M%S")

            # Nur zukuenftige Events
            if event_date.date() < now.date():
                continue

            time_str = event_date.strftime("%H:%M")

            # URL
            url_match = re.search(r"URL:(.+?)(?:\r?\n(?! )|\Z)", block, re.DOTALL)
            event_link = url_match.group(1).strip() if url_match else "https://brotfabrik-berlin.de"

            # Beschreibung aus iCal für is_free Check
            desc_match = re.search(r"DESCRIPTION:(.+?)(?:\r?\n(?! )|\Z)", block, re.DOTALL)
            description = ""
            description_raw = ""  # Für is_free Check vor Bereinigung
            if desc_match:
                description_raw = desc_match.group(1).strip()
                description_raw = description_raw.replace("\\,", ",").replace("\\n", " ").replace("\\;", ";")
                description_raw = re.sub(r"\r?\n ", "", description_raw)

            # Beschreibung von Detailseite laden (bessere Qualität)
            try:
                detail_resp = requests.get(
                    event_link,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                    timeout=8,
                )
                detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

                # Beschreibung aus .tribe-events-single-event-description
                desc_div = detail_soup.select_one(".tribe-events-single-event-description, .tribe-events-content")
                if desc_div:
                    # Alle Paragraphen durchgehen
                    for p in desc_div.select("p"):
                        text = p.get_text(" ", strip=True)
                        # Überspringe zu kurze Texte
                        if len(text) < 30:
                            continue
                        # Überspringe Termine wie "6.3. | 21 Uhr" oder "20.2.26 | 19 Uhr"
                        if re.match(r"^\d+\.\d+\.?\d*\s*\|", text):
                            continue
                        # Überspringe Filminfo "F 2025 | 105 min"
                        if re.match(r"^[A-Z]{1,3}\s+\d{4}\s*\|", text):
                            continue
                        # Überspringe reine Uhrzeiten wie "Dienstag: 11-14 Uhr"
                        if re.match(r"^(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag)", text):
                            continue
                        # Überspringe generische Salon-Beschreibungen
                        if "monatliche" in text.lower() and "salon" in text.lower():
                            continue
                        # Überspringe Kontakt-Infos
                        if "@" in text or "kontakt:" in text.lower():
                            continue
                        # Überspringe "Einfache Sprache:" Überschriften
                        if text.lower().strip() in ["einfache sprache:", "einfache sprache"]:
                            continue
                        # Überspringe "Eintritt frei" als alleinstehend
                        if text.lower().strip() == "eintritt frei":
                            continue
                        # Ersten sinnvollen Absatz gefunden
                        # Nur ersten Satz nehmen wenn zu lang
                        if len(text) > 200:
                            # Am Satzende abschneiden
                            sentences = re.split(r'(?<=[.!?])\s+', text)
                            description = sentences[0] if sentences else text[:200]
                        else:
                            description = text
                        break
            except Exception:
                # Fallback: iCal-Beschreibung bereinigen
                if description_raw:
                    # Suche nach echtem Satzanfang
                    match = re.search(
                        r"((?:^|\s)(?:Der|Die|Das|Ein|Eine|Es|Sie|Er|Wir|Im|In|Mit|Hier)[^\n]{20,})",
                        description_raw
                    )
                    if match:
                        description = match.group(1).strip()[:200]
                    else:
                        description = description_raw[:200]

            # Kategorie
            cat_match = re.search(r"CATEGORIES:(.+?)(?:\r?\n(?! )|\Z)", block, re.DOTALL)
            event_type = "sonstiges"
            if cat_match:
                categories = cat_match.group(1).strip().lower()
                for cat_key, cat_type in category_map.items():
                    if cat_key in categories:
                        event_type = cat_type
                        break

            # Kostenlos? (prüfe auf Rohdaten vor Bereinigung)
            check_text = (description_raw or description).lower()
            is_free = "eintritt frei" in check_text or "kostenlos" in check_text

            # UID fuer eindeutige ID
            uid_match = re.search(r"UID:(.+?)(?:\r?\n|\Z)", block)
            uid = uid_match.group(1).strip() if uid_match else event_link
            event_id = hashlib.md5(f"brotfabrik-{uid}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "weissensee",
                "type": event_type,
                "description": description,
                "link": event_link,
                "source": "brotfabrik",
                "is_free": is_free,
            })
        except Exception:
            continue

    print(f"[Brotfabrik] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Mehringhof Theater Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_mehringhof() -> list[dict]:
    """Scraped Events von mehringhoftheater.de."""
    events = []
    venue_name = "Mehringhof Theater"
    venue_address = "Gneisenaustraße 2a, 10961 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Gneisenaustraße 2a, 10961 Berlin",
        bezirk="kreuzberg",
        url="https://www.mehringhoftheater.de",
    )

    try:
        resp = requests.get(
            "https://www.mehringhoftheater.de/programm/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Mehringhof] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    current_year = datetime.now().year

    for article in soup.select("article, .event, .programm-eintrag"):
        try:
            title_elem = article.select_one("h2 a, h3 a, a.title")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            href = title_elem.get("href", "")
            event_link = href if href.startswith("http") else f"https://www.mehringhoftheater.de{href}"

            text = article.get_text(" ", strip=True)

            date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})?", text)
            if not date_match:
                continue

            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = int(date_match.group(3)) if date_match.group(3) else current_year

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            time_match = re.search(r"(\d{1,2}):(\d{2})", text)
            time_str = f"{time_match.group(1)}:{time_match.group(2)}" if time_match else ""

            event_id = hashlib.md5(f"mehringhof-{event_link}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "kreuzberg",
                "type": "theater",
                "description": "",
                "link": event_link,
                "source": "mehringhof",
            })
        except Exception:
            continue

    print(f"[Mehringhof] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# SO36 Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_so36() -> list[dict]:
    """Scraped Special-Events von so36.com.

    Nur "Specials" wie Lesungen, Diskussionen, Filmabende, politische Events -
    keine normalen Konzerte und Partys (SO36 hat sehr viele davon).
    """
    events = []
    venue_name = "SO36"
    venue_address = "Oranienstraße 190, 10999 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Oranienstraße 190, 10999 Berlin",
        bezirk="kreuzberg",
        url="https://www.so36.com",
    )

    # Keywords für Special-Events (keine normalen Konzerte/Partys)
    SPECIAL_KEYWORDS = [
        "lesung", "diskussion", "vortrag", "talk", "film", "kino", "screening",
        "theater", "performance", "kabarett", "comedy", "slam", "quiz",
        "workshop", "ausstellung", "vernissage", "festival", "gala",
        "politik", "demo", "kundgebung", "soli", "benefiz",
    ]

    try:
        resp = requests.get(
            "https://www.so36.com/tickets",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[SO36] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    current_year = datetime.now().year

    for item in soup.select("article, .event, .ticket-item, li"):
        try:
            link_elem = item.select_one("a[href]")
            if not link_elem:
                continue

            href = link_elem.get("href", "")
            if not href:
                continue

            title = link_elem.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            event_link = href if href.startswith("http") else f"https://www.so36.com{href}"

            text = item.get_text(" ", strip=True)
            search_text = (title + " " + text).lower()

            # Nur Special-Events
            is_special = any(kw in search_text for kw in SPECIAL_KEYWORDS)
            if not is_special:
                continue

            date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})?", text)
            if not date_match:
                continue

            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = int(date_match.group(3)) if date_match.group(3) else current_year

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            time_match = re.search(r"(\d{1,2}):(\d{2})", text)
            time_str = f"{time_match.group(1)}:{time_match.group(2)}" if time_match else ""

            event_id = hashlib.md5(f"so36-{event_link}-{event_date.isoformat()}".encode()).hexdigest()[:12]
            event_type = _classify_event_type(title, text)

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "kreuzberg",
                "type": event_type,
                "description": "",
                "link": event_link,
                "source": "so36",
            })
        except Exception:
            continue

    print(f"[SO36] {len(events)} Special-Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Urania Scraper
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_urania_details(url: str) -> dict:
    """Fetch title, description and price info from Urania event detail page."""
    result = {"title": "", "description": "", "is_free": False}
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Titel aus h1
        h1 = soup.select_one("h1.c-event-article_content_title")
        if h1:
            result["title"] = h1.get_text(strip=True)

        # Beschreibung aus h2 intro
        h2 = soup.select_one("h2.c-event-article_content_intro")
        if h2:
            result["description"] = h2.get_text(strip=True)

        # Preis-Info: Suche nach Eintritt-Absatz
        page_text = soup.get_text(" ", strip=True)
        result["is_free"] = _detect_free_event(page_text)

    except Exception:
        pass
    return result


def scrape_urania() -> list[dict]:
    """Scraped Events von urania.de."""
    events = []
    venue_name = "Urania Berlin"
    venue_address = "An der Urania 17, 10787 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="An der Urania 17, 10787 Berlin",
        bezirk="schoeneberg",
        url="https://www.urania.de",
    )

    try:
        resp = requests.get(
            "https://www.urania.de/kalender/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Urania] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    current_year = datetime.now().year
    current_month = datetime.now().month
    seen_links = set()

    for link in soup.select("a[href*='urania.de/event/']"):
        try:
            href = link.get("href", "")
            if not href or href in seen_links or "reservix" in href:
                continue
            seen_links.add(href)

            # Titel aus Link-Text
            title = link.get_text(" ", strip=True)
            # Entferne "mehr Info" und ähnliches
            title = re.sub(r"\s*mehr\s*Info\s*$", "", title).strip()
            if not title or len(title) < 5:
                continue

            event_link = href

            # Finde Parent mit Datum und Zeit
            parent = link
            event_date = None
            time_str = ""

            for _ in range(10):
                parent = parent.find_parent()
                if not parent:
                    break

                text = parent.get_text(" ", strip=True)

                # Zeit (Format: "16:00 Uhr")
                if not time_str:
                    time_match = re.search(r"(\d{1,2}):(\d{2})\s*Uhr", text)
                    if time_match:
                        time_str = f"{time_match.group(1)}:{time_match.group(2)}"

                # Datum (Format: "08 So" = Tag 8, Sonntag)
                date_match = re.search(r"(\d{2})\s*(Mo|Di|Mi|Do|Fr|Sa|So)", text)
                if date_match and not event_date:
                    day = int(date_match.group(1))
                    # Monat aus aktuellem Monat ableiten (Urania zeigt ~4 Wochen)
                    month = current_month
                    year = current_year

                    # Wenn Tag < aktueller Tag, nächster Monat
                    if day < datetime.now().day - 7:
                        month += 1
                        if month > 12:
                            month = 1
                            year += 1

                    try:
                        event_date = datetime(year, month, day)
                    except ValueError:
                        pass
                    break

            if not event_date:
                continue

            # Fetch details from event page
            details = _fetch_urania_details(event_link)
            if details["title"]:
                title = details["title"]
            description = details["description"]
            is_free = details.get("is_free", False)

            event_id = hashlib.md5(f"urania-{event_link}".encode()).hexdigest()[:12]
            event_type = _classify_event_type(title, description)

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "schoeneberg",
                "type": event_type,
                "description": description,
                "link": event_link,
                "source": "urania",
                "is_free": is_free,
            })
        except Exception:
            continue

    print(f"[Urania] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Babylon Berlin Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_babylon() -> list[dict]:
    """Scraped Events von babylonberlin.eu (Stummfilme mit Orchester)."""
    events = []
    venue_name = "Babylon Berlin"
    venue_address = "Rosa-Luxemburg-Straße 30, 10178 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Rosa-Luxemburg-Straße 30, 10178 Berlin",
        bezirk="mitte",
        url="https://babylonberlin.eu",
    )

    try:
        resp = requests.get(
            "https://babylonberlin.eu/orchester",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Babylon] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    current_year = datetime.now().year

    for item in soup.select(".mix, article, .event-item"):
        try:
            link_elem = item.select_one("a[href*='/film/'], a[href*='/programm/']")
            if not link_elem:
                continue

            href = link_elem.get("href", "")
            event_link = f"https://babylonberlin.eu{href}" if href.startswith("/") else href

            # Titel
            title_elem = item.select_one("h3, h2, .title")
            title = title_elem.get_text(strip=True) if title_elem else link_elem.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            text = item.get_text(" ", strip=True)

            # Datum (Format: "Mo, 02.03. 17:00")
            date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.\s*(\d{1,2}):(\d{2})", text)
            if not date_match:
                continue

            day = int(date_match.group(1))
            month = int(date_match.group(2))
            hour = int(date_match.group(3))
            minute = int(date_match.group(4))

            year = current_year
            current_month = datetime.now().month
            if month < current_month and (current_month - month) > 2:
                year += 1

            try:
                event_date = datetime(year, month, day, hour, minute)
            except ValueError:
                continue

            time_str = f"{hour:02d}:{minute:02d}"

            event_id = hashlib.md5(f"babylon-{event_link}-{event_date.isoformat()}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "mitte",
                "type": "film",
                "description": "Stummfilm mit Live-Orchester",
                "link": event_link,
                "source": "babylon",
            })
        except Exception:
            continue

    print(f"[Babylon] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Literaturhaus Berlin Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_literaturhaus() -> list[dict]:
    """Scraped Events von li-be.de (Literaturhaus Berlin)."""
    events = []
    venue_name = "Literaturhaus Berlin"
    venue_address = "Fasanenstraße 23, 10719 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Fasanenstraße 23, 10719 Berlin",
        bezirk="charlottenburg",
        url="https://li-be.de",
    )

    try:
        resp = requests.get(
            "https://li-be.de/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Literaturhaus] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    current_year = datetime.now().year
    seen_links = set()

    # Suche nach h3-Titeln mit Event-Links
    for h3 in soup.select("h3"):
        try:
            link = h3.select_one("a[href*='li-be.de/programm/']")
            if not link:
                continue

            href = link.get("href", "")
            if not href or href in seen_links:
                continue
            seen_links.add(href)

            title = h3.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            event_link = href

            # Finde Parent mit Datum
            parent = h3
            event_date = None
            time_str = ""

            for _ in range(10):
                parent = parent.find_parent()
                if not parent:
                    break

                text = parent.get_text(" ", strip=True)

                # Datum (Format: "3.3.Di" = 3. März, Dienstag)
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(Mo|Di|Mi|Do|Fr|Sa|So)", text)
                if date_match:
                    day = int(date_match.group(1))
                    month = int(date_match.group(2))
                    year = current_year

                    try:
                        event_date = datetime(year, month, day)
                    except ValueError:
                        pass

                # Zeit
                time_match = re.search(r"(\d{1,2}):(\d{2})\s*Uhr", text)
                if time_match and not time_str:
                    time_str = f"{time_match.group(1)}:{time_match.group(2)}"

                if event_date:
                    break

            if not event_date:
                continue

            event_id = hashlib.md5(f"literaturhaus-{event_link}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "charlottenburg",
                "type": "lesung",
                "description": "",
                "link": event_link,
                "source": "literaturhaus",
            })
        except Exception:
            continue

    print(f"[Literaturhaus] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Friedrich-Ebert-Stiftung Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_fes() -> list[dict]:
    """Scraped Events von fes.de."""
    events = []
    venue_name = "Friedrich-Ebert-Stiftung"
    venue_address = "Hiroshimastraße 17, 10785 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Hiroshimastraße 17, 10785 Berlin",
        bezirk="mitte",
        url="https://www.fes.de",
    )

    try:
        resp = requests.get(
            "https://www.fes.de/veranstaltungen",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[FES] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    current_year = datetime.now().year

    for article in soup.select("article, .event, .veranstaltung"):
        try:
            link_elem = article.select_one("a[href]")
            if not link_elem:
                continue

            href = link_elem.get("href", "")
            event_link = f"https://www.fes.de{href}" if href.startswith("/") else href

            title_elem = article.select_one("h2, h3, .title")
            title = title_elem.get_text(strip=True) if title_elem else ""
            if not title or len(title) < 5:
                continue

            text = article.get_text(" ", strip=True)

            # Datum
            date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})?", text)
            if not date_match:
                continue

            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = int(date_match.group(3)) if date_match.group(3) else current_year

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            time_match = re.search(r"(\d{1,2}):(\d{2})", text)
            time_str = f"{time_match.group(1)}:{time_match.group(2)}" if time_match else ""

            # Nur Berlin-Events
            if "berlin" not in text.lower() and "online" not in text.lower():
                continue

            event_id = hashlib.md5(f"fes-{event_link}".encode()).hexdigest()[:12]
            event_type = _classify_event_type(title, text)

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "mitte",
                "type": event_type,
                "description": "",
                "link": event_link,
                "source": "fes",
            })
        except Exception:
            continue

    print(f"[FES] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Panke Culture Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_panke() -> list[dict]:
    """Scraped Events von pankeculture.com."""
    events = []
    venue_name = "Panke"
    venue_address = "Gerichtstraße 23, 13347 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Gerichtstraße 23, 13347 Berlin",
        bezirk="wedding",
        url="https://www.pankeculture.com",
    )

    try:
        resp = requests.get(
            "https://www.pankeculture.com/programme/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Panke] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    current_year = datetime.now().year

    for item in soup.select("article, .event, .programme-item, div[class*='event']"):
        try:
            link_elem = item.select_one("a[href]")
            if not link_elem:
                continue

            href = link_elem.get("href", "")
            # Vermeide Instagram-Links - nutze stattdessen Panke-Programmseite
            if "instagram" in href.lower():
                event_link = "https://www.pankeculture.com/programme/"
            elif href.startswith("http"):
                event_link = href
            else:
                event_link = f"https://www.pankeculture.com{href}"

            title_elem = item.select_one("h2, h3, .title")
            title = title_elem.get_text(strip=True) if title_elem else link_elem.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            text = item.get_text(" ", strip=True)

            date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})?", text)
            if not date_match:
                # Alternative: "March 5" oder "5 March"
                alt_match = re.search(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)", text, re.I)
                if alt_match:
                    day = int(alt_match.group(1))
                    month_names = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
                                   "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
                    month = month_names.get(alt_match.group(2).lower(), 0)
                    if month:
                        year = current_year
                        try:
                            event_date = datetime(year, month, day)
                        except ValueError:
                            continue
                    else:
                        continue
                else:
                    continue
            else:
                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3)) if date_match.group(3) else current_year
                try:
                    event_date = datetime(year, month, day)
                except ValueError:
                    continue

            time_match = re.search(r"(\d{1,2}):(\d{2})", text)
            time_str = f"{time_match.group(1)}:{time_match.group(2)}" if time_match else ""

            event_id = hashlib.md5(f"panke-{event_link}".encode()).hexdigest()[:12]
            event_type = _classify_event_type(title, text)
            if event_type == "sonstiges":
                event_type = "konzert"

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "wedding",
                "type": event_type,
                "description": "",
                "link": event_link,
                "source": "panke",
            })
        except Exception:
            continue

    print(f"[Panke] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Kino Central Scraper (nur Specials)
# ─────────────────────────────────────────────────────────────────────────────

def scrape_kino_central() -> list[dict]:
    """Scraped nur Special Events von Kino Central (Stummfilm, Livemusik, Previews, Gäste)."""
    events = []
    venue_name = "Kino Central"
    venue_address = "Rosenthaler Straße 39, 10178 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Rosenthaler Straße 39, 10178 Berlin",
        bezirk="mitte",
        url="https://kino-central.de",
    )

    try:
        resp = requests.get(
            "https://kino-central.de/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Kino Central] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Special-Indikatoren
    SPECIAL_KEYWORDS = [
        "livemusik", "stummfilm", "live", "konzert", "preview", "premiere",
        "zu gast", "anwesenheit", "q&a", "talk", "gespräch", "special",
        "sondervorstellung", "matinée", "matinee", "filmreihe",
    ]

    current_date = None

    for elem in soup.select(".program_date1, .program_entry"):
        try:
            # Datum-Header
            if "program_date1" in elem.get("class", []):
                date_text = elem.get_text(strip=True)
                # Format: "Dienstag, 24.03.2026"
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_text)
                if date_match:
                    day = int(date_match.group(1))
                    month = int(date_match.group(2))
                    year = int(date_match.group(3))
                    try:
                        current_date = datetime(year, month, day)
                    except ValueError:
                        current_date = None
                continue

            if not current_date:
                continue

            # Film-Eintrag
            link = elem.select_one('a[title="Information über den Film"]')
            if not link:
                continue

            text = link.get_text(strip=True)
            href = link.get("href", "")

            # Prüfe ob es ein Special ist
            text_lower = text.lower()
            is_special = any(kw in text_lower for kw in SPECIAL_KEYWORDS)

            if not is_special:
                continue

            # Zeit extrahieren (z.B. "19:30 Alraune - Stummfilm...")
            time_match = re.match(r"(\d{1,2}:\d{2})\s*(.+)", text)
            if time_match:
                time_str = time_match.group(1)
                title = time_match.group(2).strip()
            else:
                time_str = ""
                title = text

            if not title:
                continue

            event_date = current_date
            if time_match:
                try:
                    h, m = map(int, time_str.split(":"))
                    event_date = event_date.replace(hour=h, minute=m)
                except ValueError:
                    pass

            event_link = href if href.startswith("http") else f"https://kino-central.de{href}"
            event_id = hashlib.md5(f"kinocentral-{event_link}".encode()).hexdigest()[:12]

            # Beschreibung von Detailseite holen
            description = ""
            try:
                detail_resp = requests.get(
                    event_link,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                    timeout=10,
                )
                detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                wrapper = detail_soup.select_one(".movie-wrapper")
                if wrapper:
                    # Beschreibung ist nach Besetzung/Regie, vor englischer Version
                    for p in wrapper.select("p"):
                        text = p.get_text(" ", strip=True)
                        # Skip technische Infos und englische Beschreibung
                        if text.startswith(("Sprache:", "Regie:", "Besetzung:", "OmU =", "OV =", "OmeU =")):
                            continue
                        # Skip englische Beschreibung (meist kürzer, nach deutscher)
                        if len(text) > 50 and not description:
                            description = text[:300]
                            break
            except Exception:
                pass

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "mitte",
                "type": "film",
                "description": description,
                "link": event_link,
                "source": "kino-central",
            })
        except Exception:
            continue

    print(f"[Kino Central] {len(events)} Special-Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Lichtblick Kino Scraper (nur Specials/Filmreihen)
# ─────────────────────────────────────────────────────────────────────────────

ENGLISH_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def scrape_lichtblick() -> list[dict]:
    """Scraped nur Specials und Filmreihen von Lichtblick Kino."""
    events = []
    venue_name = "Lichtblick Kino"
    venue_address = "Kastanienallee 77, 10435 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Kastanienallee 77, 10435 Berlin",
        bezirk="prenzlauer-berg",
        url="https://lichtblick-kino.org",
    )

    try:
        resp = requests.get(
            "https://lichtblick-kino.org/programm/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Lichtblick] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Finde Specials-Block
    specials_block = soup.select_one(".block.specials")
    if not specials_block:
        print("[Lichtblick] Keine Specials gefunden")
        return []

    liste = specials_block.select_one(".liste")
    if not liste:
        return []

    # Sammle alle Special-URLs
    special_urls = []
    for eintrag in liste.select(".eintrag"):
        link = eintrag.select_one("a[href]")
        if link:
            href = link.get("href", "")
            if "/special/" in href or "/reihe/" in href:
                special_urls.append(href)

    # Lade jede Special-Seite für Datum
    for special_url in special_urls[:15]:  # Limit auf 15 Specials
        try:
            detail_resp = requests.get(
                special_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                timeout=20,
            )
            detail_resp.raise_for_status()
            detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

            # Finde Datum (Format: "Wednesday, 18 March, 7:45 pm")
            datum_elem = detail_soup.select_one("h4.datum")
            if not datum_elem:
                continue

            datum_text = datum_elem.get_text(strip=True)
            # Parse: "Wednesday, 18 March, 7:45 pm"
            date_match = re.search(
                r"(\d{1,2})\s+(\w+),?\s*(\d{1,2}):(\d{2})\s*(am|pm)?",
                datum_text,
                re.IGNORECASE
            )
            if not date_match:
                continue

            day = int(date_match.group(1))
            month_name = date_match.group(2).lower()
            hour = int(date_match.group(3))
            minute = int(date_match.group(4))
            ampm = date_match.group(5)

            month = ENGLISH_MONTHS.get(month_name)
            if not month:
                continue

            # AM/PM Konvertierung
            if ampm and ampm.lower() == "pm" and hour < 12:
                hour += 12
            elif ampm and ampm.lower() == "am" and hour == 12:
                hour = 0

            # Jahr bestimmen
            current_year = datetime.now().year
            current_month = datetime.now().month
            year = current_year
            if month < current_month - 2:
                year += 1

            try:
                event_date = datetime(year, month, day, hour, minute)
            except ValueError:
                continue

            # Titel
            titel_elem = detail_soup.select_one("h2.titel")
            haupttitel_elem = detail_soup.select_one("h2.special_haupttitel")

            title_parts = []
            if haupttitel_elem:
                title_parts.append(haupttitel_elem.get_text(strip=True))
            if titel_elem:
                title_parts.append(titel_elem.get_text(strip=True))

            title = ": ".join(title_parts) if title_parts else "Unbekannt"

            # Beschreibung
            description = ""
            intro_elem = detail_soup.select_one(".intro, .teaser")
            if intro_elem:
                description = intro_elem.get_text(strip=True)[:300]

            time_str = f"{hour:02d}:{minute:02d}"
            event_id = hashlib.md5(f"lichtblick-{special_url}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "prenzlauer-berg",
                "type": "film",
                "description": description,
                "link": special_url,
                "source": "lichtblick",
            })
        except Exception:
            continue

    print(f"[Lichtblick] {len(events)} Special-Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Festsaal Kreuzberg Scraper (via Wagtail API)
# ─────────────────────────────────────────────────────────────────────────────

def scrape_festsaal() -> list[dict]:
    """Scraped Special-Events von Festsaal Kreuzberg via API.

    Nur "Specials" wie Wrestling, Comedy, Shows - keine normalen Konzerte.
    """
    events = []
    venue_name = "Festsaal Kreuzberg"
    venue_address = "Skalitzer Straße 130, 10999 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Skalitzer Straße 130, 10999 Berlin",
        bezirk="kreuzberg",
        url="https://festsaal-kreuzberg.de",
    )

    # Keywords für Special-Events (keine normalen Konzerte)
    SPECIAL_KEYWORDS = [
        "wrestling", "comedy", "lesung", "talk", "kabarett", "theater",
        "performance", "vortrag", "diskussion", "slam", "quiz", "stand-up",
        "standup", "show", "gala", "preisverleihung", "festival", "messe",
        "convention", "con ", "fair", "markt",
    ]

    try:
        resp = requests.get(
            "https://admin.festsaal-kreuzberg.de/api/v2/pages/",
            params={
                "type": "home.EventPage",
                "fields": "*",
                "limit": 100,
            },
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Festsaal] Fehler beim Laden: {e}")
        return []

    today = datetime.now().date()

    for item in data.get("items", []):
        try:
            title = item.get("title", "")
            if not title:
                continue

            # Prüfe ob es ein Special ist
            sub_title = item.get("sub_title") or ""
            preview_text = item.get("preview_text") or ""
            search_text = (title + " " + sub_title + " " + preview_text).lower()

            is_special = any(kw in search_text for kw in SPECIAL_KEYWORDS)
            if not is_special:
                continue

            # Datum
            date_str = item.get("date")
            if not date_str:
                continue

            try:
                event_date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue

            # Nur zukünftige Events
            if event_date.date() < today:
                continue

            # Status prüfen (abgesagt etc.)
            status = item.get("status")
            if status in ["cancelled", "ABGESAGT"]:
                continue

            # Zeit (Start oder Doors)
            start_time = item.get("start") or item.get("doors")
            time_str = ""
            if start_time:
                # Format: "20:00:00"
                time_match = re.match(r"(\d{1,2}):(\d{2})", str(start_time))
                if time_match:
                    h, m = int(time_match.group(1)), int(time_match.group(2))
                    time_str = f"{h:02d}:{m:02d}"
                    event_date = event_date.replace(hour=h, minute=m)

            # URL
            url_path = item.get("url", "")
            event_link = f"https://festsaal-kreuzberg.de{url_path}" if url_path else "https://festsaal-kreuzberg.de"

            # Beschreibung aus layouts extrahieren falls preview_text leer
            description = preview_text
            if not description:
                layouts = item.get("layouts", [])
                for layout in layouts:
                    if layout.get("type") == "layout_simple":
                        for layout_item in layout.get("value", {}).get("items", []):
                            if layout_item.get("type") == "item_text":
                                html_text = layout_item.get("value", {}).get("text", "")
                                # HTML-Tags entfernen
                                text = re.sub(r"<[^>]+>", " ", html_text)
                                text = re.sub(r"\s+", " ", text).strip()
                                if text and len(text) > 50:
                                    description = text[:300]
                                    break
                    if description:
                        break

            # Titel mit Untertitel kombinieren falls vorhanden
            full_title = title
            if sub_title and sub_title.lower() not in title.lower():
                full_title = f"{title} - {sub_title}"

            # Event-Typ bestimmen
            event_type = "sonstiges"
            if "wrestling" in search_text:
                event_type = "theater"
            elif any(w in search_text for w in ["comedy", "kabarett", "stand-up", "standup"]):
                event_type = "theater"
            elif any(w in search_text for w in ["lesung", "vortrag", "diskussion", "talk"]):
                event_type = "diskussion"
            elif "quiz" in search_text or "slam" in search_text:
                event_type = "sonstiges"

            event_id = hashlib.md5(f"festsaal-{item.get('id', '')}".encode()).hexdigest()[:12]

            # HTML-Entities dekodieren
            clean_description = unescape(description[:300]) if description else ""

            events.append({
                "id": event_id,
                "title": full_title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "kreuzberg",
                "type": event_type,
                "description": clean_description,
                "link": event_link,
                "source": "festsaal",
            })
        except Exception:
            continue

    print(f"[Festsaal] {len(events)} Special-Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Schwarze Risse Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_schwarze_risse() -> list[dict]:
    """Scraped Events vom Buchladen Schwarze Risse."""
    events = []
    venue_name = "Schwarze Risse"
    venue_address = "Gneisenaustr. 2a, 10961 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Gneisenaustr. 2a, 10961 Berlin",
        bezirk="kreuzberg",
        url="https://schwarzerisse.de",
    )

    try:
        resp = requests.get(
            "https://schwarzerisse.de/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[SchwRisse] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    today = datetime.now().date()

    # Finde alle panel-grids mit Datum (h4 mit DD.MM.YYYY Format) und Titel (h3.widget-title)
    # Stoppe bei "Vergangene Veranstaltungen"
    found_vergangene = False

    for panel_grid in soup.find_all("div", class_="panel-grid"):
        # Prüfen ob wir bei "Vergangene Veranstaltungen" angelangt sind
        h1_check = panel_grid.find("h1")
        if h1_check and "vergangene" in h1_check.get_text(strip=True).lower():
            found_vergangene = True

        # Überspringe alles nach "Vergangene"
        if found_vergangene:
            continue

        # Datum/Zeit extrahieren (Format: "03.03.2026 // 20:00 Uhr")
        date_h4 = panel_grid.find("h4")
        if not date_h4:
            continue

        date_text = date_h4.get_text(strip=True)
        date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_text)
        time_match = re.search(r"(\d{1,2}):(\d{2})", date_text)

        if not date_match:
            continue

        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = int(date_match.group(3))

        try:
            event_date = datetime(year, month, day)
        except ValueError:
            continue

        # Nur zukünftige Events
        if event_date.date() < today:
            continue

        time_str = ""
        if time_match:
            h, m = int(time_match.group(1)), int(time_match.group(2))
            time_str = f"{h:02d}:{m:02d}"
            event_date = event_date.replace(hour=h, minute=m)

        # Titel aus widget-title h3 extrahieren
        title_elem = panel_grid.find("h3", class_="widget-title")
        if not title_elem:
            continue

        title = title_elem.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        # Beschreibung aus textwidget (das zweite textwidget, nicht das mit dem Datum)
        description = ""
        textwidgets = panel_grid.find_all("div", class_="textwidget")
        for tw in textwidgets:
            for p in tw.find_all("p"):
                p_text = p.get_text(strip=True)
                # Überspringe kurze Texte und Adress-Infos
                if p_text and len(p_text) > 50 and "Gneisenau" not in p_text and "Mehringdamm" not in p_text:
                    description = p_text[:400]
                    break
            if description:
                break

        event_id = hashlib.md5(f"schwarzerisse-{event_date.isoformat()}-{title[:30]}".encode()).hexdigest()[:12]

        events.append({
            "id": event_id,
            "title": title,
            "date": event_date,
            "time": time_str,
            "venue_slug": venue_slug,
            "venue_name": venue_name,
            "venue_address": venue_address,
            "bezirk": "kreuzberg",
            "type": "lesung",
            "description": description,
            "link": "https://schwarzerisse.de/",
            "source": "schwarzerisse",
        })

    print(f"[SchwRisse] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Buchladen Weltkugel Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_weltkugel() -> list[dict]:
    """Scraped Events vom Buchladen zur schwankenden Weltkugel."""
    events = []
    venue_name = "Zur schwankenden Weltkugel"
    venue_address = "Prenzlauer Allee 27, 10405 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Prenzlauer Allee 27, 10405 Berlin",
        bezirk="prenzlauer-berg",
        url="https://www.buchladen-weltkugel.de",
    )

    try:
        resp = requests.get(
            "https://www.buchladen-weltkugel.de/veranstaltungen",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Weltkugel] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    today = datetime.now().date()

    # Suche nach Event-Einträgen (Drupal-basierte Seite)
    # Format typischerweise: Veranstaltungstitel mit Datum
    for event_item in soup.select(".views-row, .event-item, article.event"):
        try:
            # Titel
            title_elem = event_item.select_one("h2, h3, .event-title, .views-field-title a")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            if not title:
                continue

            # Datum suchen
            date_elem = event_item.select_one(".date, .event-date, time, .views-field-field-date")
            if not date_elem:
                continue

            date_text = date_elem.get_text(strip=True)

            # Versuche verschiedene Datumsformate
            event_date = None

            # Format: DD.MM.YYYY
            date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_text)
            if date_match:
                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3))
                try:
                    event_date = datetime(year, month, day)
                except ValueError:
                    pass

            # Falls kein Datum gefunden, überspringen
            if not event_date:
                continue

            # Nur zukünftige Events
            if event_date.date() < today:
                continue

            # Zeit extrahieren
            time_str = ""
            time_match = re.search(r"(\d{1,2}):(\d{2})", date_text)
            if time_match:
                h, m = int(time_match.group(1)), int(time_match.group(2))
                time_str = f"{h:02d}:{m:02d}"
                event_date = event_date.replace(hour=h, minute=m)

            # Link
            link_elem = event_item.select_one("a[href]")
            link = "https://www.buchladen-weltkugel.de/veranstaltungen"
            if link_elem and link_elem.get("href"):
                href = link_elem.get("href")
                if href.startswith("/"):
                    link = f"https://www.buchladen-weltkugel.de{href}"
                elif href.startswith("http"):
                    link = href

            # Beschreibung
            desc_elem = event_item.select_one(".description, .event-description, .views-field-body")
            description = ""
            if desc_elem:
                description = desc_elem.get_text(strip=True)[:400]

            event_id = hashlib.md5(f"weltkugel-{event_date.isoformat()}-{title[:30]}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "prenzlauer-berg",
                "type": "lesung",
                "description": description,
                "link": link,
                "source": "weltkugel",
            })
        except Exception:
            continue

    print(f"[Weltkugel] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Peter Edel Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_peteredel() -> list[dict]:
    """Scraped Events von peteredel.de.

    Filtert unpassende Events raus (Party, Tango, Kinder, etc.),
    behält politische/kulturelle Veranstaltungen wie Lesungen, Diskussionen, Gespräche.
    """
    events = []
    venue_name = "Peter Edel"
    venue_address = "Berliner Allee 256, 13088 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Berliner Allee 256, 13088 Berlin",
        bezirk="weissensee",
        url="https://www.peteredel.de",
    )

    # Begriffe die auf unpassende Events hindeuten (werden lowercase verglichen)
    BLOCKED_KEYWORDS = [
        "tango", "tanztee", "tanzen", "tanzfest", "tanzt",
        "party", "disco", "80s", "90s", "schlager",
        "rudelsingen", "karaoke",
        "pittiplatsch", "kinderkino", "kindertheater", "hops", "hopsi", "hits für kids",
        "bootcamp", "yoga", "meditation",
        "sonntagsschön", "brunch",
        "liszt", "kammermusik", "klassik",
        "sip&smash", "juice",
        "ginverkostung", "weinverkostung", "whiskyverkostung",
        "after work", "video dome",
        " tour",  # Reine Konzerttouren (mit Leerzeichen davor)
        "shanderilan",  # Veljanov-Tour
    ]

    try:
        resp = requests.get(
            "https://www.peteredel.de/events/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[PeterEdel] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    today = datetime.now().date()
    current_year = datetime.now().year

    current_date = None

    # Alle h3-Elemente durchgehen
    for h3 in soup.find_all("h3"):
        text = h3.get_text(strip=True)

        # Datum erkennen (z.B. "FR | 06.03.")
        date_match = re.search(r"(MO|DI|MI|DO|FR|SA|SO)\s*\|\s*(\d{1,2})\.(\d{1,2})\.", text.upper())
        if date_match:
            day = int(date_match.group(2))
            month = int(date_match.group(3))
            try:
                year = current_year
                if month < datetime.now().month:
                    year += 1
                current_date = datetime(year, month, day)
            except ValueError:
                current_date = None
            continue

        # Event-Titel mit Link erkennen
        link_elem = h3.select_one("a")
        if link_elem and current_date:
            title_elem = link_elem.select_one("strong") or link_elem
            title = title_elem.get_text(strip=True)
            # Zeilenumbrüche entfernen
            title = re.sub(r"\s+", " ", title).strip()

            if not title or len(title) < 3:
                continue

            href = link_elem.get("href", "")
            if not href:
                continue

            event_link = f"https://www.peteredel.de{href}" if href.startswith("/") else href

            # Filter: Unpassende Events überspringen
            title_lower = title.lower()
            if any(keyword in title_lower for keyword in BLOCKED_KEYWORDS):
                continue

            # Beschreibung aus nachfolgendem p-Tag
            description = ""
            next_elem = h3.find_next_sibling()
            while next_elem and next_elem.name == "p":
                p_text = next_elem.get_text(strip=True)
                # Filtere Ticket-Infos und kurze Texte raus
                if p_text and len(p_text) > 50 and not p_text.startswith("Tickets"):
                    if "Einlass" not in p_text[:30] and "Euro" not in p_text[:30]:
                        description = p_text[:400]
                        break
                next_elem = next_elem.find_next_sibling()

            # Event-Typ klassifizieren
            event_type = _classify_event_type(title, description)

            event_id = hashlib.md5(f"peteredel-{current_date.isoformat()}-{title[:30]}".encode()).hexdigest()[:12]

            # Nur zukünftige Events
            if current_date.date() >= today:
                events.append({
                    "id": event_id,
                    "title": title,
                    "date": current_date,
                    "time": "",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "weissensee",
                    "type": event_type,
                    "description": description,
                    "link": event_link,
                    "source": "peteredel",
                })

    print(f"[PeterEdel] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# KuBiZ Wallenberg Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_kubiz() -> list[dict]:
    """Scraped Events von kubiz-wallenberg.de.

    Blockiert Jazz-Events.
    """
    events = []
    venue_name = "KuBiZ Wallenberg"
    venue_address = "Bernkasteler Straße 78, 13088 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Bernkasteler Straße 78, 13088 Berlin",
        bezirk="weissensee",
        url="https://www.kubiz-wallenberg.de",
    )

    try:
        resp = requests.get(
            "https://www.kubiz-wallenberg.de/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[KuBiZ] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    today = datetime.now().date()

    for article in soup.select("article.post"):
        try:
            # Titel aus h2.entry-title
            title_elem = article.select_one("h2.entry-title a")
            if not title_elem:
                continue

            raw_title = title_elem.get_text(strip=True)
            if not raw_title or len(raw_title) < 3:
                continue

            # Jazz-Events blockieren (im Titel oder in Tags)
            classes = article.get("class", [])
            class_str = " ".join(classes)
            if "tag-jazz" in class_str or "jazz" in raw_title.lower():
                continue

            event_link = title_elem.get("href", "")

            # Datum aus dem Titel extrahieren (z.B. "7.3.26 Jazzkonzert: ...")
            # Format: D.M.YY oder DD.MM.YY
            date_match = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})\s*(.+)", raw_title)
            if date_match:
                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3))
                if year < 100:
                    year += 2000
                title = date_match.group(4).strip()
                # Entferne führendes "Konzert:" etc.
                title = re.sub(r"^(Konzert|Film|Lesung|Workshop)[:\s]*", "", title, flags=re.IGNORECASE).strip()
            else:
                title = raw_title
                # Fallback: Datum aus time-Element
                time_elem = article.select_one("time.entry-date")
                if not time_elem:
                    continue
                datetime_attr = time_elem.get("datetime", "")
                if not datetime_attr:
                    continue
                try:
                    parsed_dt = datetime.fromisoformat(datetime_attr.replace("Z", "+00:00"))
                    day, month, year = parsed_dt.day, parsed_dt.month, parsed_dt.year
                except ValueError:
                    continue

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            # Nur zukünftige Events
            if event_date.date() < today:
                continue

            # Zeit aus h4 oder h2 (z.B. "20 Uhr, Aula")
            time_str = ""
            for heading in article.select("h4.wp-block-heading, h2.wp-block-heading"):
                time_text = heading.get_text(strip=True)
                time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*Uhr", time_text)
                if time_match:
                    h = int(time_match.group(1))
                    m = int(time_match.group(2)) if time_match.group(2) else 0
                    time_str = f"{h:02d}:{m:02d}"
                    break

            # Beschreibung aus dem Artikel-Content
            description = ""
            content_div = article.select_one(".entry-content")
            if content_div:
                for p in content_div.select("p"):
                    p_text = p.get_text(strip=True)
                    # Überspringe Zeit/Ort/Eintritt-Infos und kurze Texte
                    if p_text and len(p_text) > 50:
                        if not re.match(r"^\d+\s*Uhr", p_text) and "Eintritt" not in p_text[:20]:
                            description = p_text[:400]
                            break

            # Typ aus Tags
            event_type = "sonstiges"
            if "tag-film" in class_str or "tag-kino" in class_str:
                event_type = "film"
            elif "tag-konzert" in class_str:
                event_type = "konzert"
            elif "tag-lesung" in class_str:
                event_type = "lesung"
            elif "tag-workshop" in class_str:
                event_type = "workshop"

            event_id = hashlib.md5(f"kubiz-{event_date.isoformat()}-{title[:30]}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "weissensee",
                "type": event_type,
                "description": description,
                "link": event_link,
                "source": "kubiz",
            })
        except Exception:
            continue

    print(f"[KuBiZ] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Zeiss-Großplanetarium Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_planetarium() -> list[dict]:
    """Scraped Events von planetarium.berlin.

    Holt Lesungen/Hörspiele aus dem Programm (Erwachsene).
    """
    events = []
    venue_name = "Zeiss-Großplanetarium"
    venue_address = "Prenzlauer Allee 80, 10405 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="prenzlauer-berg",
        url="https://www.planetarium.berlin",
    )

    # Nur Lesungen/Hörspiele scrapen (passt zum Profil)
    categories = [
        ("hoerspiele-lesungen", "lesung"),
    ]

    # Kinderveranstaltungen überspringen
    BLOCKED_KEYWORDS = [
        "kinder", "kids", "ohrka", "familie", "traumzauberbaum",
        "ab 4 jahren", "ab 5 jahren", "ab 6 jahren", "ab 7 jahren", "ab 8 jahren",
    ]

    for cat_slug, event_type in categories:
        try:
            resp = requests.get(
                f"https://www.planetarium.berlin/veranstaltungsart/{cat_slug}",
                headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"[Planetarium] Fehler beim Laden {cat_slug}: {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # Events sind in article.event-page Elementen
        for article in soup.select("article.event-page"):
            try:
                link = article.select_one("a[href]")
                if not link:
                    continue

                href = link.get("href", "")
                if not href or "/veranstaltungsart/" in href:
                    continue

                event_link = f"https://www.planetarium.berlin{href}" if href.startswith("/") else href

                # Titel aus h4 oder Link-Text
                title_elem = article.select_one("h4 span")
                if title_elem:
                    title = title_elem.get_text(strip=True)
                else:
                    title = link.get_text(strip=True)

                if not title or len(title) < 3:
                    continue

                # Infos holen (z.B. "50 min | ab 4 Jahren")
                info_elem = article.select_one(".event__info, .field--name-field-infos")
                info_text = info_elem.get_text(strip=True) if info_elem else ""

                # Kinderveranstaltungen überspringen
                combined_text = f"{title} {info_text}".lower()
                if any(kw in combined_text for kw in BLOCKED_KEYWORDS):
                    continue

                # Event-Detailseite für Termine laden
                try:
                    detail_resp = requests.get(
                        event_link,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                        timeout=15,
                    )
                    detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

                    # Beschreibung extrahieren
                    description = ""
                    # Planetarium nutzt field--name-field-body-wo-summary für Beschreibungen
                    intro = detail_soup.select_one(".field--name-field-body-wo-summary, .field--name-field-intro, .field--name-body")
                    if intro:
                        description = intro.get_text(" ", strip=True)[:300]

                    # Planetarium-Events sind kostenpflichtig (Tickets 13-20€)
                    is_free = False

                    # Alle Termine aus event-date Artikeln extrahieren
                    for date_article in detail_soup.select("article.event-date"):
                        try:
                            # Datum aus data-event-time Attribut des Ticket-Buttons
                            ticket_btn = date_article.select_one("a[data-event-time]")
                            if ticket_btn:
                                dt_str = ticket_btn.get("data-event-time", "")
                                # Format: 2026-03-07T12:30:00
                                if dt_str:
                                    event_datetime = datetime.fromisoformat(dt_str)
                                    time_str = event_datetime.strftime("%H:%M")
                            else:
                                # Fallback: Datum aus Text
                                date_cell = date_article.select_one(".event-date__table-cell")
                                if not date_cell:
                                    continue
                                date_text = date_cell.get_text(" ", strip=True)
                                # Format: "Sa 07.03.2026"
                                date_match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", date_text)
                                if not date_match:
                                    continue
                                day = int(date_match.group(1))
                                month = int(date_match.group(2))
                                year = int(date_match.group(3))
                                event_datetime = datetime(year, month, day)

                                # Zeit aus zweiter Zelle
                                time_cells = date_article.select(".event-date__table-cell")
                                time_str = ""
                                if len(time_cells) >= 2:
                                    time_text = time_cells[1].get_text(strip=True)
                                    time_match = re.search(r"(\d{1,2}):(\d{2})", time_text)
                                    if time_match:
                                        time_str = f"{time_match.group(1)}:{time_match.group(2)}"

                            # Nur zukünftige Events
                            if event_datetime.date() < datetime.now().date():
                                continue

                            # Venue aus dritter Zelle (kann variieren)
                            location_elem = date_article.select_one(".field-location a")
                            if location_elem:
                                loc_name = location_elem.get_text(strip=True)
                                if "Zeiss-Großplanetarium" in loc_name:
                                    ev_venue = venue_name
                                    ev_address = venue_address
                                else:
                                    # Andere Stiftungsorte überspringen (Archenhold, etc.)
                                    continue
                            else:
                                ev_venue = venue_name
                                ev_address = venue_address

                            event_id = hashlib.md5(
                                f"planetarium-{event_link}-{event_datetime.isoformat()}".encode()
                            ).hexdigest()[:12]

                            events.append({
                                "id": event_id,
                                "title": title,
                                "date": event_datetime,
                                "time": time_str,
                                "venue_slug": venue_slug,
                                "venue_name": ev_venue,
                                "venue_address": ev_address,
                                "bezirk": "prenzlauer-berg",
                                "type": event_type,
                                "description": description,
                                "link": event_link,
                                "source": "planetarium",
                                "is_free": is_free,
                            })

                        except Exception:
                            continue

                except Exception:
                    continue

            except Exception:
                continue

    print(f"[Planetarium] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Publix Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_publix() -> list[dict]:
    """Scraped Events von publix.de (Haus des Journalismus)."""
    events = []
    venue_name = "Publix"
    venue_address = "Friedrichstraße 225, 10969 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="kreuzberg",
        url="https://www.publix.de",
    )

    try:
        resp = requests.get(
            "https://www.publix.de/veranstaltungen",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Publix] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    now = datetime.now()

    for link in soup.select('a[href*="/veranstaltungen/"]'):
        try:
            href = link.get("href", "")
            if "/archiv" in href or href.endswith("/veranstaltungen") or href.endswith("/veranstaltungen/"):
                continue

            text = link.get_text(" ", strip=True)
            if not text or len(text) < 10:
                continue

            # Datum extrahieren: "Dienstag 10.03. 18:30 – 20:00"
            date_match = re.search(r"(\d{1,2})\.(\d{2})\.\s*(\d{1,2}):(\d{2})", text)
            if not date_match:
                continue

            day = int(date_match.group(1))
            month = int(date_match.group(2))
            hour = int(date_match.group(3))
            minute = int(date_match.group(4))

            # Jahr bestimmen
            year = now.year
            event_date = datetime(year, month, day, hour, minute)
            if event_date < now - timedelta(days=30):
                event_date = datetime(year + 1, month, day, hour, minute)

            if event_date.date() < now.date():
                continue

            time_str = f"{hour:02d}:{minute:02d}"

            event_link = href if href.startswith("http") else f"https://www.publix.de{href}"

            # Detailseite für Titel und Beschreibung laden
            title = ""
            description = ""
            try:
                detail_resp = requests.get(
                    event_link,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                    timeout=10,
                )
                detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

                # Titel aus h1
                h1 = detail_soup.select_one("h1[itemprop='name'], h1")
                if h1:
                    title = h1.get_text(strip=True)

                # Beschreibung aus dem Content-Bereich (text-body-18/20/24 Paragraphen)
                for p in detail_soup.select("p.text-body-18, p.text-body-20, p.text-body-24"):
                    text = p.get_text(" ", strip=True)
                    # Überspringe kurze Texte und Sprecherlisten
                    if len(text) > 80 and not text.startswith("Mit ") and "ist " not in text[:50]:
                        description = text[:300]
                        break
            except Exception:
                pass

            # Fallback für Titel
            if not title:
                title_match = re.search(r"\d{2}:\d{2}\s+(?:Gastveranstaltung|Publix\s+\w+|Gemeinsam\s+\w+)?\s*(.+)", text)
                if title_match:
                    title = title_match.group(1).strip()
                else:
                    title_match = re.search(r"\d{2}:\d{2}\s+(.+)", text)
                    title = title_match.group(1).strip() if title_match else text

            # Kürzen wenn zu lang
            if len(title) > 100:
                title = title[:97] + "..."

            # Event-Typ bestimmen
            text_lower = text.lower()
            if "film" in text_lower or "screening" in text_lower:
                event_type = "film"
            elif "buchpremiere" in text_lower or "lesung" in text_lower:
                event_type = "lesung"
            elif "diskussion" in text_lower or "gespräch" in text_lower:
                event_type = "diskussion"
            elif "workshop" in text_lower or "kurs" in text_lower:
                event_type = "workshop"
            else:
                event_type = "diskussion"

            event_id = hashlib.md5(f"publix-{event_link}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "kreuzberg",
                "type": event_type,
                "description": description,
                "link": event_link,
                "source": "publix",
            })
        except Exception:
            continue

    # Duplikate entfernen (gleiche Links)
    seen = set()
    unique = []
    for e in events:
        if e["link"] not in seen:
            seen.add(e["link"])
            unique.append(e)

    print(f"[Publix] {len(unique)} Events geladen")
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# KW Institute for Contemporary Art Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_kw() -> list[dict]:
    """Scraped Events von KW Institute for Contemporary Art."""
    events = []
    venue_name = "KW Institute for Contemporary Art"
    venue_address = "Auguststraße 69, 10117 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://www.kw-berlin.de",
    )

    # Kinder/Familien-Veranstaltungen und Führungen ausfiltern
    BLOCKED_KEYWORDS = [
        "kinder", "familien", "kids", "0–6", "0-6",
        "führung", "einblicke in die", "überblicksführung",
        "somatische übungen", "kw, a hike", "kw, unboxed",
    ]

    try:
        resp = requests.get(
            "https://www.kw-berlin.de/de/veranstaltungen",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[KW] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    now = datetime.now()

    for link in soup.select('a[href*="/veranstaltungen/"]'):
        try:
            href = link.get("href", "")
            if href.endswith("/veranstaltungen") or href.endswith("/veranstaltungen/"):
                continue

            # Text enthält Datum und Titel: "Führung Sa, 07.03.26, 16:00–17:00 (de, en) Einblicke..."
            text = link.get_text(" ", strip=True)
            if not text or len(text) < 10:
                continue

            # Datum: "07.03.26" (2-stelliges Jahr)
            date_match = re.search(r"(\d{1,2})\.(\d{2})\.(\d{2})", text)
            if not date_match:
                continue

            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = 2000 + int(date_match.group(3))

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            if event_date.date() < now.date():
                continue

            # Zeit: "16:00–17:00" oder "16:00"
            time_str = ""
            time_match = re.search(r"(\d{1,2}):(\d{2})(?:–|$|\s)", text)
            if time_match:
                time_str = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"

            # Titel: Nach (de, en) oder nach der Zeit
            title = ""
            title_match = re.search(r"\((?:de|en|de,\s*en)\)\s*(.+)", text)
            if title_match:
                title = title_match.group(1).strip()
            else:
                # Fallback: Nach Zeitangabe
                title_match = re.search(r"\d{2}:\d{2}(?:–\d{2}:\d{2})?\s+(.+)", text)
                if title_match:
                    title = title_match.group(1).strip()

            if not title or len(title) < 5:
                continue

            # Kinder/Führungen filtern
            combined = f"{text} {title}".lower()
            if any(kw in combined for kw in BLOCKED_KEYWORDS):
                continue

            # Event-Typ aus erstem Wort
            first_word = text.split()[0].lower() if text else ""
            if "führung" in first_word:
                event_type = "workshop"
            elif "workshop" in first_word:
                event_type = "workshop"
            elif "gespräch" in first_word or "talk" in first_word:
                event_type = "diskussion"
            elif "konzert" in first_word or "performance" in first_word:
                event_type = "konzert"
            else:
                event_type = "ausstellung"

            # Kostenlos?
            is_free = "eintritt frei" in text.lower() or "free" in text.lower()

            event_link = href if href.startswith("http") else f"https://www.kw-berlin.de{href}"
            event_id = hashlib.md5(f"kw-{event_link}-{event_date.isoformat()}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "mitte",
                "type": event_type,
                "description": "",
                "link": event_link,
                "source": "kw",
                "is_free": is_free,
            })
        except Exception:
            continue

    # Duplikate entfernen
    seen = set()
    unique = []
    for e in events:
        key = f"{e['link']}-{e['date'].isoformat()}"
        if key not in seen:
            seen.add(key)
            unique.append(e)

    print(f"[KW] {len(unique)} Events geladen")
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# Topographie des Terrors Scraper
# ─────────────────────────────────────────────────────────────────────────────

GERMAN_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}


def scrape_topographie() -> list[dict]:
    """Scraped Events von Topographie des Terrors."""
    events = []
    venue_name = "Topographie des Terrors"
    venue_address = "Niederkirchnerstraße 8, 10963 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="kreuzberg",
        url="https://www.topographie.de",
    )

    try:
        resp = requests.get(
            "https://www.topographie.de/veranstaltungen/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Topographie] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    now = datetime.now()

    # Teaser-Elemente suchen
    for teaser in soup.select(".c-teaser--event"):
        try:
            link = teaser.select_one("a[href]")
            if not link:
                continue

            href = link.get("href", "")
            text = teaser.get_text(" ", strip=True)

            # Datum: "10 März" -> Tag + Monat
            date_match = re.search(r"(\d{1,2})\s+(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)", text, re.IGNORECASE)
            if not date_match:
                continue

            day = int(date_match.group(1))
            month_name = date_match.group(2).lower()
            month = GERMAN_MONTHS.get(month_name, 0)
            if not month:
                continue

            # Jahr: aktuelles Jahr, oder nächstes wenn Monat vergangen
            year = now.year
            if month < now.month or (month == now.month and day < now.day):
                year += 1

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            if event_date.date() < now.date():
                continue

            # Zeit: "19:00 Uhr"
            time_str = ""
            time_match = re.search(r"(\d{1,2}):(\d{2})", text)
            if time_match:
                time_str = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"

            # Titel: Nach "Format <Typ>" kommt der Titel
            title = ""
            title_match = re.search(r"(?:Buchpräsentation|Podiumsdiskussion|Vortrag|Lesung|Filmvorführung|Führung)\s+(.+)", text)
            if title_match:
                title = title_match.group(1).strip()
            else:
                # Fallback: Link-Text
                title = link.get_text(strip=True)

            if not title or len(title) < 5:
                continue

            # Event-Typ
            if "buchpräsentation" in text.lower():
                event_type = "lesung"
            elif "podiumsdiskussion" in text.lower() or "vortrag" in text.lower():
                event_type = "diskussion"
            elif "film" in text.lower():
                event_type = "film"
            elif "führung" in text.lower():
                event_type = "workshop"
            else:
                event_type = "diskussion"

            event_link = href if href.startswith("http") else f"https://www.topographie.de{href}"
            event_id = hashlib.md5(f"topographie-{event_link}-{event_date.isoformat()}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "kreuzberg",
                "type": event_type,
                "description": "",
                "link": event_link,
                "source": "topographie",
                "is_free": True,  # Eintritt immer frei
            })
        except Exception:
            continue

    print(f"[Topographie] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Jüdisches Museum Berlin Scraper
# ─────────────────────────────────────────────────────────────────────────────

GERMAN_MONTHS_SHORT = {
    "jan": 1, "feb": 2, "mär": 3, "apr": 4,
    "mai": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "okt": 10, "nov": 11, "dez": 12,
}


def scrape_jmberlin() -> list[dict]:
    """Scraped Events vom Jüdischen Museum Berlin."""
    events = []
    venue_name = "Jüdisches Museum Berlin"
    venue_address = "Lindenstraße 9-14, 10969 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="kreuzberg",
        url="https://www.jmberlin.de",
    )

    # Führungen, Kinder-Events und Standard-Angebote ausfiltern
    BLOCKED_KEYWORDS = [
        "führung", "highlights der dauerausstellung", "architektur, kunst und philosophie",
        "kinder", "familien", "anoha", "alte heimat – neue heimat",
        "bilder machen leute", "judentum erklingt", "heute geschlossen",
    ]

    try:
        resp = requests.get(
            "https://www.jmberlin.de/kalender",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[JMBerlin] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    now = datetime.now()

    for teaser in soup.select(".teaser"):
        try:
            link = teaser.select_one("a[href]")
            if not link:
                continue

            href = link.get("href", "")
            text = teaser.get_text(" ", strip=True)

            # Titel
            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # Filter anwenden
            combined = f"{text} {title}".lower()
            if any(kw in combined for kw in BLOCKED_KEYWORDS):
                continue

            # Datum: "Sa, 7. Mär 2026" oder "7. Mär 2026"
            date_match = re.search(r"(\d{1,2})\.\s*(Jan|Feb|Mär|Apr|Mai|Jun|Jul|Aug|Sep|Okt|Nov|Dez)\s*(\d{4})", text, re.IGNORECASE)
            if not date_match:
                continue

            day = int(date_match.group(1))
            month_name = date_match.group(2).lower()
            month = GERMAN_MONTHS_SHORT.get(month_name, 0)
            year = int(date_match.group(3))

            if not month:
                continue

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            if event_date.date() < now.date():
                continue

            # Zeit: "12–17 Uhr" oder "19 Uhr"
            time_str = ""
            time_match = re.search(r"(\d{1,2})(?:[–:]\d{1,2})?\s*Uhr", text)
            if time_match:
                hour = int(time_match.group(1))
                time_str = f"{hour:02d}:00"

            # Event-Typ
            text_lower = text.lower()
            if "führung" in text_lower:
                event_type = "workshop"
            elif "konzert" in text_lower:
                event_type = "konzert"
            elif "film" in text_lower:
                event_type = "film"
            elif "lesung" in text_lower:
                event_type = "lesung"
            elif "workshop" in text_lower:
                event_type = "workshop"
            elif "gespräch" in text_lower or "diskussion" in text_lower:
                event_type = "diskussion"
            else:
                event_type = "ausstellung"

            # Ausgebucht überspringen?
            if "ausgebucht" in text_lower:
                continue

            event_link = href if href.startswith("http") else f"https://www.jmberlin.de{href}"
            event_id = hashlib.md5(f"jmberlin-{event_link}-{event_date.isoformat()}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "kreuzberg",
                "type": event_type,
                "description": "",
                "link": event_link,
                "source": "jmberlin",
            })
        except Exception:
            continue

    # Duplikate entfernen
    seen = set()
    unique = []
    for e in events:
        key = f"{e['link']}-{e['date'].isoformat()}"
        if key not in seen:
            seen.add(key)
            unique.append(e)

    print(f"[JMBerlin] {len(unique)} Events geladen")
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# nGbK Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_ngbk() -> list[dict]:
    """Scraped Events von nGbK (neue Gesellschaft für bildende Kunst)."""
    events = []
    venue_name = "nGbK"
    venue_address = "Oranienstraße 25, 10999 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="kreuzberg",
        url="https://www.ngbk.de",
    )

    try:
        resp = requests.get(
            "https://www.ngbk.de/de/programm/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[nGbK] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    now = datetime.now()

    for teaser in soup.select(".teaser"):
        try:
            link = teaser.select_one("a[href]")
            if not link:
                continue

            href = link.get("href", "")
            text = teaser.get_text(" ", strip=True)

            # Titel: Erster Teil
            title = text.split(" Sa,")[0].split(" So,")[0].split(" Fr,")[0].split(" Do,")[0].split(" Mi,")[0].split(" Di,")[0].split(" Mo,")[0].strip()
            if not title or len(title) < 5:
                continue

            # Datum: "Sa, 28.3. – So, 28.6.26" -> Start-Datum
            date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(?:\s*–[^,]+,\s*\d{1,2}\.\d{1,2}\.)?(\d{2,4})?", text)
            if not date_match:
                continue

            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year_str = date_match.group(3)
            if year_str:
                year = int(year_str) if len(year_str) == 4 else 2000 + int(year_str)
            else:
                year = now.year

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            # Vergangene Events überspringen
            if event_date.date() < now.date():
                continue

            # Event-Typ
            text_lower = text.lower()
            if "ausstellung" in text_lower:
                event_type = "ausstellung"
            elif "buchpräsentation" in text_lower or "lesung" in text_lower:
                event_type = "lesung"
            elif "workshop" in text_lower:
                event_type = "workshop"
            elif "film" in text_lower:
                event_type = "film"
            else:
                event_type = "ausstellung"

            event_link = href if href.startswith("http") else f"https://www.ngbk.de{href}"
            event_id = hashlib.md5(f"ngbk-{event_link}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": "",
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "kreuzberg",
                "type": event_type,
                "description": "",
                "link": event_link,
                "source": "ngbk",
            })
        except Exception:
            continue

    # Duplikate entfernen
    seen = set()
    unique = []
    for e in events:
        if e["link"] not in seen:
            seen.add(e["link"])
            unique.append(e)

    print(f"[nGbK] {len(unique)} Events geladen")
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# Anne Frank Zentrum Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_annefrank() -> list[dict]:
    """Scraped Events vom Anne Frank Zentrum."""
    events = []
    venue_name = "Anne Frank Zentrum"
    venue_address = "Rosenthaler Straße 39, 10178 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://www.annefrank.de",
    )

    # Nur Veranstaltungen in Berlin, keine Wanderausstellungen oder Führungen
    BLOCKED_KEYWORDS = [
        "neuruppin", "wanderausstellung", "erfurt", "leipzig", "hamburg",
        "münchen", "köln", "frankfurt", "düsseldorf", "schulprojekt",
        "weimar", "arnsberg", "führung", "familienführung", "tandemführung",
        "gebärdensprache", "für familien",
    ]
    # Diese Keywords sind OK (Lesungen, Vorträge)
    ALLOWED_KEYWORDS = ["lesung", "vortrag", "gespräch", "diskussion", "podium"]

    try:
        resp = requests.get(
            "https://www.annefrank.de/termine",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[AnneFrank] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    now = datetime.now()

    for teaser in soup.select(".teaser"):
        try:
            link = teaser.select_one("a[href]")
            text = teaser.get_text(" ", strip=True)

            # Filter: Nur Berlin
            text_lower = text.lower()
            if any(kw in text_lower for kw in BLOCKED_KEYWORDS):
                continue

            # Datum: "11. 02. 2026 - 09. 03. 2026"
            date_match = re.search(r"(\d{1,2})\.\s*(\d{2})\.\s*(\d{4})", text)
            if not date_match:
                continue

            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = int(date_match.group(3))

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            if event_date.date() < now.date():
                continue

            # Titel: Nach Datum
            title_match = re.search(r"\d{4}\s+(.+?)(?:Das Anne Frank|$)", text)
            title = title_match.group(1).strip() if title_match else ""
            if not title or len(title) < 5:
                continue

            href = link.get("href", "") if link else ""
            event_link = href if href.startswith("http") else f"https://www.annefrank.de{href}"
            event_id = hashlib.md5(f"annefrank-{event_link}-{event_date.isoformat()}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": "",
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "mitte",
                "type": "ausstellung",
                "description": "",
                "link": event_link,
                "source": "annefrank",
            })
        except Exception:
            continue

    print(f"[AnneFrank] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Haus am Waldsee Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_hausamwaldsee() -> list[dict]:
    """Scraped Events vom Haus am Waldsee."""
    events = []
    venue_name = "Haus am Waldsee"
    venue_address = "Argentinische Allee 30, 14163 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="zehlendorf",
        url="https://www.hausamwaldsee.de",
    )

    # Kinder/Familien-Events ausfiltern
    BLOCKED_KEYWORDS = [
        "kinder", "familien", "familiensonntag", "workshop für kinder",
        "führung", "ausverkauft",
    ]

    try:
        resp = requests.get(
            "https://www.hausamwaldsee.de/programm/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[HausWaldsee] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    now = datetime.now()

    for event_elem in soup.select('[class*="event"]'):
        try:
            text = event_elem.get_text(" ", strip=True)
            link = event_elem.select_one("a[href]")

            # Filter
            text_lower = text.lower()
            if any(kw in text_lower for kw in BLOCKED_KEYWORDS):
                continue

            # Datum: "So, 8.3.2026"
            date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
            if not date_match:
                continue

            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = int(date_match.group(3))

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            if event_date.date() < now.date():
                continue

            # Titel: Nach Datum
            title_match = re.search(r"\d{4}\s+(.+)", text)
            title = title_match.group(1).strip() if title_match else ""
            if not title or len(title) < 5:
                continue

            # Zeit
            time_str = ""
            time_match = re.search(r"(\d{1,2})[:\.](\d{2})\s*Uhr", text)
            if time_match:
                time_str = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"

            # Event-Typ
            if "konzert" in text_lower:
                event_type = "konzert"
            elif "lesung" in text_lower or "gespräch" in text_lower:
                event_type = "lesung"
            elif "film" in text_lower:
                event_type = "film"
            else:
                event_type = "ausstellung"

            href = link.get("href", "") if link else "https://www.hausamwaldsee.de/programm/"
            event_link = href if href.startswith("http") else f"https://www.hausamwaldsee.de{href}"
            event_id = hashlib.md5(f"hausamwaldsee-{title}-{event_date.isoformat()}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title[:100],
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "zehlendorf",
                "type": event_type,
                "description": "",
                "link": event_link,
                "source": "hausamwaldsee",
            })
        except Exception:
            continue

    # Duplikate entfernen
    seen = set()
    unique = []
    for e in events:
        key = f"{e['title']}-{e['date'].isoformat()}"
        if key not in seen:
            seen.add(key)
            unique.append(e)

    print(f"[HausWaldsee] {len(unique)} Events geladen")
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# Dokumentationszentrum Flucht, Vertreibung, Versöhnung Scraper
# ─────────────────────────────────────────────────────────────────────────────

ENGLISH_MONTHS_FULL = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def scrape_dokumentationszentrum() -> list[dict]:
    """Scraped Events vom Dokumentationszentrum Flucht, Vertreibung, Versöhnung."""
    events = []
    venue_name = "Dokumentationszentrum Flucht, Vertreibung, Versöhnung"
    venue_address = "Stresemannstraße 90, 10963 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="kreuzberg",
        url="https://www.flucht-vertreibung-versoehnung.de",
    )

    # Führungen ausfiltern
    BLOCKED_KEYWORDS = ["guided tour", "führung"]

    try:
        resp = requests.get(
            "https://www.flucht-vertreibung-versoehnung.de/de/besuchen/veranstaltungen",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[DokuZentrum] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    now = datetime.now()

    for article in soup.select("article"):
        try:
            text = article.get_text(" ", strip=True)
            link = article.select_one("a[href]")

            # Filter
            text_lower = text.lower()
            if any(kw in text_lower for kw in BLOCKED_KEYWORDS):
                continue

            # Englisches Datum: "Saturday, March 07, 2026"
            date_match = re.search(
                r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})",
                text, re.IGNORECASE
            )
            if not date_match:
                continue

            month_name = date_match.group(1).lower()
            month = ENGLISH_MONTHS_FULL.get(month_name, 0)
            day = int(date_match.group(2))
            year = int(date_match.group(3))

            if not month:
                continue

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            if event_date.date() < now.date():
                continue

            # Zeit: "2:00 – 5:00 PM" oder "6:30 – 8:00 PM"
            time_str = ""
            time_match = re.search(r"(\d{1,2}):(\d{2})\s*(?:–|-)?\s*\d*:?\d*\s*(AM|PM)", text, re.IGNORECASE)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))
                ampm = time_match.group(3).upper()
                if ampm == "PM" and hour != 12:
                    hour += 12
                elif ampm == "AM" and hour == 12:
                    hour = 0
                time_str = f"{hour:02d}:{minute:02d}"

            # Titel: Eventtyp + Titel
            # "book presentation and conversation Tuesday, March 24, 2026, 6:30 – 8:00 PM „Alte Wut" by Caro Matzko"
            title_match = re.search(r"(?:PM|AM)\s+(.+)", text)
            title = title_match.group(1).strip() if title_match else ""
            if not title:
                # Fallback: Erster Teil
                title_match = re.search(r"^([^\d]+)", text)
                title = title_match.group(1).strip() if title_match else ""

            if not title or len(title) < 5:
                continue

            # Event-Typ
            if "workshop" in text_lower:
                event_type = "workshop"
            elif "book presentation" in text_lower or "buchpräsentation" in text_lower:
                event_type = "lesung"
            elif "film" in text_lower:
                event_type = "film"
            elif "conversation" in text_lower or "gespräch" in text_lower:
                event_type = "diskussion"
            else:
                event_type = "diskussion"

            href = link.get("href", "") if link else ""
            event_link = href if href.startswith("http") else f"https://www.flucht-vertreibung-versoehnung.de{href}"
            event_id = hashlib.md5(f"dokuzentrum-{title}-{event_date.isoformat()}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title[:100],
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "kreuzberg",
                "type": event_type,
                "description": "",
                "link": event_link,
                "source": "dokumentationszentrum",
                "is_free": True,  # Eintritt frei
            })
        except Exception:
            continue

    # Duplikate entfernen
    seen = set()
    unique = []
    for e in events:
        key = f"{e['title']}-{e['date'].isoformat()}"
        if key not in seen:
            seen.add(key)
            unique.append(e)

    print(f"[DokuZentrum] {len(unique)} Events geladen")
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# Kunstraum Kreuzberg Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_kunstraumkreuzberg() -> list[dict]:
    """Scraped Ausstellungen vom Kunstraum Kreuzberg/Bethanien."""
    events = []
    venue_name = "Kunstraum Kreuzberg/Bethanien"
    venue_address = "Mariannenplatz 2, 10997 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="kreuzberg",
        url="https://www.kunstraumkreuzberg.de",
    )

    try:
        resp = requests.get(
            "https://www.kunstraumkreuzberg.de/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[KunstraumKreuzberg] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    now = datetime.now()

    for article in soup.select("article"):
        try:
            text = article.get_text(" ", strip=True)
            link = article.select_one("a[href]")

            if not link:
                continue

            href = link.get("href", "")

            # Nur Ausstellungen mit Datum: "Echoes of Tumult 24.1. – 22.3.26"
            date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.\s*[–-]\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})", text)
            if not date_match:
                continue

            # Start-Datum
            start_day = int(date_match.group(1))
            start_month = int(date_match.group(2))
            # End-Datum für Jahr
            end_day = int(date_match.group(3))
            end_month = int(date_match.group(4))
            year_str = date_match.group(5)
            year = int(year_str) if len(year_str) == 4 else 2000 + int(year_str)

            try:
                event_date = datetime(year, start_month, start_day)
            except ValueError:
                continue

            # Vergangene überspringen (aber laufende Ausstellungen zeigen)
            try:
                end_date = datetime(year, end_month, end_day)
                if end_date.date() < now.date():
                    continue
            except ValueError:
                pass

            # Titel: Alles vor dem Datum
            title = text.split(str(start_day) + ".")[0].strip()
            if not title or len(title) < 3:
                continue

            event_link = href if href.startswith("http") else f"https://www.kunstraumkreuzberg.de{href}"
            event_id = hashlib.md5(f"kunstraumkreuzberg-{event_link}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": "",
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address,
                "bezirk": "kreuzberg",
                "type": "ausstellung",
                "description": "",
                "link": event_link,
                "source": "kunstraumkreuzberg",
                "is_free": True,
            })
        except Exception:
            continue

    print(f"[KunstraumKreuzberg] {len(events)} Ausstellungen geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# ZOiS (Zentrum für Osteuropa- und internationale Studien) Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_zois() -> list[dict]:
    """Scraped Events von zois-berlin.de."""
    events = []
    venue_name = "ZOiS – Zentrum für Osteuropa- und internationale Studien"
    venue_address = "Anton-Wilhelm-Amo-Str. 60, 10117 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://www.zois-berlin.de",
    )

    try:
        resp = requests.get(
            "https://www.zois-berlin.de/veranstaltungen",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[ZOiS] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    now = datetime.now()

    for article in soup.select("article.eventTeaser"):
        try:
            # Link
            link_tag = article.select_one("a.eventTeaser__wrapper")
            if not link_tag:
                continue
            href = link_tag.get("href", "")
            event_link = f"https://www.zois-berlin.de{href}" if href.startswith("/") else href

            # Kategorie/SuperHeadline
            super_headline = article.select_one(".eventTeaser__superHeadline")
            category = super_headline.get_text(strip=True) if super_headline else ""

            # Titel
            title_tag = article.select_one(".eventTeaser__title")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)

            # Beschreibung
            desc_tag = article.select_one(".eventTeaser__main")
            description = desc_tag.get_text(" ", strip=True)[:250] if desc_tag else ""

            # Datum
            date_tag = article.select_one(".data__date")
            if not date_tag:
                continue
            date_str = date_tag.get_text(strip=True)  # z.B. "10.03.2026"
            try:
                event_date = datetime.strptime(date_str, "%d.%m.%Y")
            except ValueError:
                continue

            # Nur zukünftige Events
            if event_date.date() < now.date():
                continue

            # Uhrzeit
            time_tag = article.select_one(".eventInfo__data__start .data__time")
            time_str = time_tag.get_text(strip=True) if time_tag else ""

            # Ort (kann auch "Online" sein)
            location_tag = article.select_one(".eventInfo__section--location .data__html")
            location = ""
            is_online = False
            if location_tag:
                location = location_tag.get_text(" ", strip=True)
                if "online" in location.lower():
                    is_online = True

            # Event-Typ bestimmen
            cat_lower = (category + " " + title).lower()
            if "panel" in cat_lower or "discussion" in cat_lower or "diskussion" in cat_lower:
                event_type = "diskussion"
            elif "lecture" in cat_lower or "vortrag" in cat_lower:
                event_type = "diskussion"
            elif "exhibition" in cat_lower or "ausstellung" in cat_lower:
                event_type = "ausstellung"
            elif "film" in cat_lower:
                event_type = "film"
            elif "lesung" in cat_lower or "reading" in cat_lower:
                event_type = "lesung"
            else:
                event_type = "diskussion"

            # Titel mit Kategorie erweitern wenn sinnvoll
            if category and category not in title:
                full_title = f"{title}"
            else:
                full_title = title

            event_id = hashlib.md5(f"zois-{event_link}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": full_title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": venue_address if not is_online else "Online",
                "bezirk": "mitte",
                "type": event_type,
                "description": description,
                "link": event_link,
                "source": "zois",
            })
        except Exception:
            continue

    print(f"[ZOiS] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# LPB Berlin (Berliner Landeszentrale für politische Bildung) Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_lpb_berlin() -> list[dict]:
    """Scraped Events von der Berliner Landeszentrale für politische Bildung."""
    events = []
    venue_name = "Berliner Landeszentrale für politische Bildung"
    venue_address = "Hardenbergstraße 22-24, 10623 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="charlottenburg",
        url="https://www.berlin.de/politische-bildung",
    )

    base_url = "https://www.berlin.de"
    calendar_url = f"{base_url}/politische-bildung/veranstaltungen/veranstaltungen-der-berliner-landeszentrale/"

    try:
        resp = requests.get(
            calendar_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[LPB Berlin] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    now = datetime.now()

    # Events aus den Autoteaser-Listen extrahieren
    for li in soup.select(".modul-autoteaser ul.list--tablelist li"):
        try:
            # Datum
            date_cell = li.select_one(".cell.date")
            if not date_cell:
                continue
            date_str = date_cell.get_text(strip=True)  # z.B. "12.03.2026"
            try:
                event_date = datetime.strptime(date_str, "%d.%m.%Y")
            except ValueError:
                continue

            # Nur zukünftige Events
            if event_date.date() < now.date():
                continue

            # Titel und Link
            link_tag = li.select_one(".cell.text a")
            if not link_tag:
                continue
            title = link_tag.get_text(strip=True)
            href = link_tag.get("href", "")
            event_link = f"{base_url}{href}" if href.startswith("/") else href

            # Beschreibung von Detailseite laden
            description = ""
            event_time = ""
            event_address = venue_address
            try:
                detail_resp = requests.get(
                    event_link,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                    timeout=8,
                )
                detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

                # Beschreibung aus .textile p (berlin.de Struktur)
                for p in detail_soup.select(".textile p, .modul-text p, .article-content p"):
                    text = p.get_text(" ", strip=True)
                    if len(text) > 80:
                        # Ersten Satz nehmen wenn zu lang
                        if len(text) > 250:
                            sentences = re.split(r'(?<=[.!?])\s+', text)
                            description = sentences[0] if sentences else text[:250]
                        else:
                            description = text
                        break

                # Uhrzeit aus Metadaten oder Text
                time_match = re.search(r"(\d{1,2}[:.]\d{2})\s*(?:Uhr|–|-)", detail_resp.text)
                if time_match:
                    event_time = time_match.group(1).replace(".", ":")

                # Ort aus Metadaten
                location_tag = detail_soup.select_one(".location, .address, [itemprop='location']")
                if location_tag:
                    loc_text = location_tag.get_text(" ", strip=True)
                    if len(loc_text) > 10:
                        event_address = loc_text[:100]

            except Exception:
                pass

            # Event-Typ bestimmen
            title_lower = title.lower()
            if "film" in title_lower or "kino" in title_lower:
                event_type = "film"
            elif "lesung" in title_lower:
                event_type = "lesung"
            elif "workshop" in title_lower or "seminar" in title_lower:
                event_type = "workshop"
            elif "führung" in title_lower or "rundgang" in title_lower:
                event_type = "sonstiges"
            elif "ausstellung" in title_lower:
                event_type = "ausstellung"
            else:
                event_type = "diskussion"  # Default für politische Bildung

            event_id = hashlib.md5(f"lpb-berlin-{event_link}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": event_time,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": event_address,
                "bezirk": "charlottenburg",
                "type": event_type,
                "description": description,
                "link": event_link,
                "source": "lpb-berlin",
            })
        except Exception:
            continue

    # Duplikate entfernen
    seen = set()
    unique = []
    for e in events:
        if e["link"] not in seen:
            seen.add(e["link"])
            unique.append(e)

    print(f"[LPB Berlin] {len(unique)} Events geladen")
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# BPB (Bundeszentrale für politische Bildung) Scraper - nur Berlin Events
# ─────────────────────────────────────────────────────────────────────────────

def scrape_bpb() -> list[dict]:
    """Scraped Events von bpb.de via RSS-Feed, gefiltert auf Berlin."""
    events = []
    venue_name = "Bundeszentrale für politische Bildung"
    venue_address = "Friedrichstraße 50, 10117 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://www.bpb.de",
    )

    rss_url = "https://www.bpb.de/rss-feed/133222.rss"

    try:
        resp = requests.get(
            rss_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[BPB] Fehler beim Laden: {e}")
        return []

    rss_text = resp.text
    now = datetime.now()

    # RSS mit Regex parsen (BeautifulSoup HTML-Parser funktioniert nicht gut mit RSS)
    item_pattern = re.compile(r"<item>(.*?)</item>", re.DOTALL)
    title_pattern = re.compile(r"<title><!\[CDATA\[(.*?)\]\]></title>")
    link_pattern = re.compile(r"<link>(https?://[^<]+)</link>")
    pubdate_pattern = re.compile(r"<pubDate>([^<]+)</pubDate>")
    desc_pattern = re.compile(r"<description><!\[CDATA\[(.*?)\]\]></description>")

    for item_match in item_pattern.finditer(rss_text):
        try:
            item = item_match.group(1)

            # Titel
            title_m = title_pattern.search(item)
            if not title_m:
                continue
            title = title_m.group(1)

            # Link
            link_m = link_pattern.search(item)
            if not link_m:
                continue
            event_link = link_m.group(1)

            # Beschreibung aus RSS
            desc_m = desc_pattern.search(item)
            rss_description = desc_m.group(1) if desc_m else ""

            # Datum aus pubDate
            pubdate_m = pubdate_pattern.search(item)
            if not pubdate_m:
                continue
            pub_date_str = pubdate_m.group(1).strip()
            # Format: "Thu, 26 Mar 2026 18:30:00 +0100"
            try:
                event_date = datetime.strptime(pub_date_str[:25], "%a, %d %b %Y %H:%M:%S")
            except ValueError:
                continue

            # Nur zukünftige Events
            if event_date.date() < now.date():
                continue

            time_str = event_date.strftime("%H:%M")

            # Detailseite laden um Ort zu prüfen
            is_berlin = False
            description = rss_description
            event_address = venue_address

            try:
                detail_resp = requests.get(
                    event_link,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                    timeout=10,
                )
                detail_text = detail_resp.text.lower()

                # Prüfen ob Berlin im Ort steht
                if "berlin" in detail_text:
                    # Genauer prüfen: Suche nach Adresse mit Berlin
                    detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

                    # Suche nach Ort-Metadaten
                    for selector in [".event-location", ".location", "[itemprop='location']", ".place"]:
                        loc = detail_soup.select_one(selector)
                        if loc:
                            loc_text = loc.get_text(" ", strip=True)
                            if "berlin" in loc_text.lower():
                                is_berlin = True
                                event_address = loc_text[:150]
                                break

                    # Fallback: Suche im gesamten Text nach "Berlin" als Ort
                    if not is_berlin:
                        berlin_match = re.search(r"(\d{5}\s+Berlin|Berlin[,\s]+\d{5})", detail_resp.text)
                        if berlin_match:
                            is_berlin = True

                    # Bessere Beschreibung von Detailseite
                    intro = detail_soup.select_one(".intro, .teaser-text, .article-intro")
                    if intro:
                        description = intro.get_text(" ", strip=True)[:250]

            except Exception:
                pass

            # Nur Berlin-Events speichern
            if not is_berlin:
                continue

            # Event-Typ bestimmen
            title_lower = title.lower()
            if "film" in title_lower or "kino" in title_lower:
                event_type = "film"
            elif "lesung" in title_lower:
                event_type = "lesung"
            elif "workshop" in title_lower or "seminar" in title_lower:
                event_type = "workshop"
            elif "tagung" in title_lower or "kongress" in title_lower:
                event_type = "diskussion"
            else:
                event_type = "diskussion"

            event_id = hashlib.md5(f"bpb-{event_link}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "venue_address": event_address,
                "bezirk": "mitte",
                "type": event_type,
                "description": description,
                "link": event_link,
                "source": "bpb",
            })
        except Exception:
            continue

    print(f"[BPB] {len(events)} Berlin-Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Futurium Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_futurium() -> list[dict]:
    """Scraped Events von futurium.de.

    Die Website ist React-basiert und erfordert PDF-Parsing.
    Benoetigt pdfplumber: pip install pdfplumber
    """
    try:
        import pdfplumber
    except ImportError:
        print("[Futurium] pdfplumber nicht installiert - ueberspringe (pip install pdfplumber)")
        return []

    import io

    events = []
    venue_name = "Futurium"
    venue_address = "Alexanderufer 2, 10117 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://futurium.de",
    )

    # Versuche aktuelle Programmflyer-URL zu finden
    # Das Futurium benennt sie nach Quartal: JAN-MAR, APR-JUN, etc.
    now = datetime.now()
    quarter_starts = [(1, "JAN-MAR"), (4, "APR-JUN"), (7, "JUL-SEP"), (10, "OKT-DEZ")]
    current_quarter = None
    for month, name in reversed(quarter_starts):
        if now.month >= month:
            current_quarter = name
            break
    if not current_quarter:
        current_quarter = "OKT-DEZ"

    year_short = str(now.year)[2:]
    pdf_url = f"https://futurium.de/uploads/documents/FUT_Programmflyer_{current_quarter}{year_short}_WEB.pdf"

    try:
        resp = requests.get(
            pdf_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Futurium] PDF nicht gefunden ({pdf_url}): {e}")
        return []

    try:
        pdf_bytes = io.BytesIO(resp.content)
        with pdfplumber.open(pdf_bytes) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() or ""

        # Events aus Text extrahieren (Format: "DD. MON HH:MM Titel")
        event_pattern = re.compile(
            r"(\d{1,2})\.\s*(JAN|FEB|MAR|APR|MAI|JUN|JUL|AUG|SEP|OKT|NOV|DEZ)\s+"
            r"(\d{1,2})[:\.](\d{2})\s*"
            r"([A-Z][^\n]{10,})",
            re.IGNORECASE
        )

        month_map = {
            "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAI": 5,
            "JUN": 6, "JUL": 7, "AUG": 8, "SEP": 9, "OKT": 10, "NOV": 11, "DEZ": 12
        }

        # Events filtern (keine Familien/Kinder-Events)
        SKIP_KEYWORDS = ["family", "familie", "kinder", "kids", "fuehrung"]

        for match in event_pattern.finditer(full_text):
            try:
                day = int(match.group(1))
                month_name = match.group(2).upper()
                hour = int(match.group(3))
                minute = int(match.group(4))
                title = match.group(5).strip()

                # Titel bereinigen
                title = re.sub(r'\s+', ' ', title)
                if len(title) > 100:
                    title = title[:100]

                # Kinder/Familien-Events skippen
                if any(kw in title.lower() for kw in SKIP_KEYWORDS):
                    continue

                month = month_map.get(month_name, 0)
                if not month:
                    continue

                year = now.year
                event_date = datetime(year, month, day, hour, minute)
                if event_date < now:
                    event_date = datetime(year + 1, month, day, hour, minute)

                if event_date.date() < now.date():
                    continue

                event_id = hashlib.md5(
                    f"futurium-{title}-{event_date.isoformat()}".encode()
                ).hexdigest()[:12]

                # Typ bestimmen
                title_lower = title.lower()
                if "quiz" in title_lower:
                    event_type = "sonstiges"
                elif "talk" in title_lower or "diskussion" in title_lower:
                    event_type = "diskussion"
                elif "open lab" in title_lower or "workshop" in title_lower:
                    event_type = "workshop"
                else:
                    event_type = "vortrag"

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "mitte",
                    "type": event_type,
                    "description": "",
                    "link": "https://futurium.de/de/veranstaltungen",
                    "source": "futurium",
                    "is_free": True,
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Futurium] Fehler beim PDF-Parsen: {e}")

    print(f"[Futurium] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# ZZF Potsdam Scraper (Leibniz-Zentrum für Zeithistorische Forschung)
# ─────────────────────────────────────────────────────────────────────────────

def scrape_zzf() -> list[dict]:
    """Scraped Events vom ZZF Potsdam."""
    events = []
    venue_name = "Leibniz-Zentrum für Zeithistorische Forschung"
    venue_address = "Am Neuen Markt 1, 14467 Potsdam"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="potsdam",
        url="https://zzf-potsdam.de",
    )

    url = "https://zzf-potsdam.de/wissenstransfer/veranstaltungen"
    now = datetime.now()

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events als Links zu Veranstaltungsseiten
        for link in soup.select("a[href*='/wissenstransfer/veranstaltungen/']"):
            try:
                href = link.get("href", "")
                if not href or href == "/wissenstransfer/veranstaltungen" or href.endswith("/veranstaltungen"):
                    continue

                event_link = href if href.startswith("http") else f"https://zzf-potsdam.de{href}"

                # Titel aus dem Link oder h3 extrahieren
                h3 = link.select_one("h3")
                if h3:
                    title = h3.get_text(strip=True)
                else:
                    title = link.get_text(strip=True)

                if not title or len(title) < 5:
                    continue

                # Datum aus dem Link-Text extrahieren
                link_text = link.get_text(" ", strip=True)
                date_match = re.search(r"(\d{1,2})\.\s*(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+(\d{4})", link_text)
                if not date_match:
                    # Alternatives Format: DD.MM.YYYY
                    date_match2 = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", link_text)
                    if date_match2:
                        day = int(date_match2.group(1))
                        month = int(date_match2.group(2))
                        year = int(date_match2.group(3))
                    else:
                        continue
                else:
                    day = int(date_match.group(1))
                    month_name = date_match.group(2)
                    year = int(date_match.group(3))
                    month_map = {
                        "Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6,
                        "Juli": 7, "August": 8, "September": 9, "Oktober": 10, "November": 11, "Dezember": 12
                    }
                    month = month_map.get(month_name, 1)

                # Uhrzeit aus Link-Text
                time_match = re.search(r"(\d{1,2}):(\d{2})\s*Uhr", link_text)
                if time_match:
                    hour, minute = int(time_match.group(1)), int(time_match.group(2))
                else:
                    hour, minute = 18, 0  # Default

                event_date = datetime(year, month, day, hour, minute)
                if event_date.date() < now.date():
                    continue

                time_str = f"{hour:02d}:{minute:02d}"

                # Detailseite laden
                description = ""
                event_address = venue_address

                try:
                    detail_resp = requests.get(
                        event_link,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                        timeout=10,
                    )
                    detail_resp.raise_for_status()
                    detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

                    # Ort aus Detailseite
                    page_text = detail_soup.get_text(" ", strip=True)
                    ort_match = re.search(r"Ort[:\s]+([^,]+,\s*[^,]+,\s*\d{5}\s*[A-Za-zäöüÄÖÜß]+)", page_text)
                    if ort_match:
                        event_address = ort_match.group(1).strip()
                    elif "potsdam" not in page_text.lower() and "berlin" not in page_text.lower():
                        # Event nicht in Potsdam/Berlin
                        pass

                    # Beschreibung
                    for p in detail_soup.select("p"):
                        text = p.get_text(" ", strip=True)
                        if len(text) > 80 and not text.startswith("Datum") and not text.startswith("Ort"):
                            description = text[:300]
                            break

                except Exception:
                    pass

                event_id = hashlib.md5(
                    f"zzf-{title}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                # Event-Typ bestimmen
                title_lower = title.lower()
                if "vortrag" in title_lower:
                    event_type = "vortrag"
                elif "lesung" in title_lower or "buchvorstellung" in title_lower:
                    event_type = "lesung"
                elif "diskussion" in title_lower or "gespräch" in title_lower:
                    event_type = "diskussion"
                elif "tagung" in title_lower or "konferenz" in title_lower:
                    event_type = "konferenz"
                elif "workshop" in title_lower or "seminar" in title_lower:
                    event_type = "workshop"
                elif "ausstellung" in title_lower:
                    event_type = "ausstellung"
                else:
                    event_type = "vortrag"

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": time_str,
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": event_address,
                    "bezirk": "potsdam",
                    "type": event_type,
                    "description": description,
                    "link": event_link,
                    "source": "zzf",
                })
            except Exception:
                continue

    except Exception as e:
        print(f"[ZZF] Fehler: {e}")

    # Duplikate entfernen (gleicher Titel)
    seen_titles = set()
    unique_events = []
    for event in events:
        if event["title"] not in seen_titles:
            seen_titles.add(event["title"])
            unique_events.append(event)

    print(f"[ZZF] {len(unique_events)} Events geladen")
    return unique_events


# ─────────────────────────────────────────────────────────────────────────────
# MMZ Potsdam Scraper (Moses Mendelssohn Zentrum)
# ─────────────────────────────────────────────────────────────────────────────

def scrape_mmz() -> list[dict]:
    """Scraped Events vom Moses Mendelssohn Zentrum Potsdam."""
    events = []
    venue_name = "Moses Mendelssohn Zentrum"
    venue_address = "Am Neuen Markt 8, 14467 Potsdam"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="potsdam",
        url="https://www.mmz-potsdam.de",
    )

    url = "https://www.mmz-potsdam.de/aktuelles/veranstaltungen"
    now = datetime.now()

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events sind als <p>Datum<br/><b><a>Title</a></b></p> strukturiert
        for p in soup.select("p"):
            try:
                link = p.select_one("a[href*='/aktuelles/veranstaltungen/']")
                if not link:
                    continue

                href = link.get("href", "")
                if not href or href.endswith("/veranstaltungen") or href.endswith("/veranstaltungen/"):
                    continue

                event_link = href if href.startswith("http") else f"https://www.mmz-potsdam.de{href}"
                title = link.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                # Datum aus dem <p>-Text extrahieren (Format: "DD.MM.YY")
                p_text = p.get_text(" ", strip=True)
                date_match = re.search(r"(\d{2})\.(\d{2})\.(\d{2})", p_text)
                if not date_match:
                    continue

                date_text = date_match.group(0)

                # Datum parsen (Format: DD.MM.YY)
                day, month, year = map(int, date_text.split("."))
                year = 2000 + year if year < 100 else year
                event_date = datetime(year, month, day, 19, 0)  # Default 19:00

                if event_date.date() < now.date():
                    continue

                # Detailseite laden für mehr Infos
                description = ""
                time_str = "19:00"
                event_address = venue_address

                try:
                    detail_resp = requests.get(
                        event_link,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                        timeout=10,
                    )
                    detail_resp.raise_for_status()
                    detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

                    # Beschreibung aus Paragraphen
                    for p in detail_soup.select("p"):
                        text = p.get_text(" ", strip=True)
                        if len(text) > 80 and not re.match(r"^\d{2}\.\d{2}\.\d{2}", text):
                            description = text[:300]
                            break

                    # Uhrzeit suchen
                    page_text = detail_soup.get_text(" ", strip=True)
                    time_match = re.search(r"(\d{1,2})[:\.](\d{2})\s*Uhr", page_text)
                    if time_match:
                        hour, minute = int(time_match.group(1)), int(time_match.group(2))
                        time_str = f"{hour:02d}:{minute:02d}"
                        event_date = event_date.replace(hour=hour, minute=minute)

                    # Prüfen ob Online-Event
                    if "videokonferenz" in page_text.lower() or "online" in page_text.lower():
                        event_address = "Online"

                except Exception:
                    pass

                event_id = hashlib.md5(
                    f"mmz-{title}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                # Event-Typ bestimmen
                title_lower = title.lower()
                if "vortrag" in title_lower or "vortragsreihe" in title_lower:
                    event_type = "vortrag"
                elif "lesung" in title_lower or "buchvorstellung" in title_lower:
                    event_type = "lesung"
                elif "diskussion" in title_lower or "gespräch" in title_lower:
                    event_type = "diskussion"
                elif "ausstellung" in title_lower:
                    event_type = "ausstellung"
                elif "workshop" in title_lower or "seminar" in title_lower:
                    event_type = "workshop"
                else:
                    event_type = "vortrag"

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": time_str,
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": event_address,
                    "bezirk": "potsdam",
                    "type": event_type,
                    "description": description,
                    "link": event_link,
                    "source": "mmz",
                })
            except Exception:
                continue

    except Exception as e:
        print(f"[MMZ] Fehler: {e}")

    print(f"[MMZ] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Renaissance-Theater Berlin Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_renaissance_theater() -> list[dict]:
    """Scraped Events vom Renaissance-Theater Berlin.

    Nur Specials: Lesungen, Gespräche, Poetry Slam, Sonderveranstaltungen.
    Reguläres Theaterprogramm wird ignoriert.
    """
    events = []
    venue_name = "Renaissance-Theater"
    venue_address = "Knesebeckstraße 100, 10623 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="charlottenburg-wilmersdorf",
        url="https://renaissance-theater.de",
    )

    url = "https://renaissance-theater.de/spielplan/"
    now = datetime.now()

    # Kategorien die wir wollen
    WANTED_CATEGORIES = {"lesung", "gespräch", "poetry slam", "sonderveranstaltung"}

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Aktueller Monat/Jahr für Datumsberechnung
        current_month = None
        current_year = now.year

        month_map = {
            "Januar": 1, "Februar": 2, "März": 3, "April": 4,
            "Mai": 5, "Juni": 6, "Juli": 7, "August": 8,
            "September": 9, "Oktober": 10, "November": 11, "Dezember": 12
        }

        # Alle Monatsüberschriften und Events durchgehen
        for element in soup.select("h1, div.rt-spielplan-day"):
            # Monatsüberschrift (h1 nicht h2)
            if element.name == "h1":
                month_text = element.get_text(strip=True)
                if month_text in month_map:
                    current_month = month_map[month_text]
                    # Jahr anpassen wenn Monat in der Vergangenheit
                    if current_month < now.month:
                        current_year = now.year + 1
                continue

            if not current_month:
                continue

            # Event-Tag
            day_elem = element.select_one(".rt-sp-day")
            if not day_elem:
                continue

            try:
                day = int(day_elem.get_text(strip=True))
            except ValueError:
                continue

            # Alle Events an diesem Tag
            for event_div in element.select(".rt-sp-date"):
                try:
                    # Kategorie prüfen
                    special_div = event_div.select_one(".special-premiere")
                    if not special_div:
                        continue

                    category = special_div.get_text(strip=True).lower()
                    if category not in WANTED_CATEGORIES:
                        continue

                    # Zeit
                    time_elem = event_div.select_one(".rt-sp-time")
                    if not time_elem:
                        continue
                    time_text = time_elem.get_text(strip=True)
                    time_match = re.match(r"(\d{1,2})\.(\d{2})", time_text)
                    if time_match:
                        hour, minute = int(time_match.group(1)), int(time_match.group(2))
                    else:
                        hour, minute = 19, 30

                    # Titel
                    title_elem = event_div.select_one("h4")
                    if not title_elem:
                        continue
                    title = title_elem.get_text(" ", strip=True)
                    # Span mit Zusatzinfo entfernen
                    span = title_elem.select_one("span")
                    if span:
                        title = title.replace(span.get_text(" ", strip=True), "").strip()

                    if not title:
                        continue

                    # Link
                    link_elem = event_div.select_one("a[href*='/produktion/']")
                    if link_elem:
                        event_link = link_elem.get("href", "")
                    else:
                        event_link = url

                    # Beschreibung
                    desc_elem = event_div.select_one("p")
                    description = desc_elem.get_text(strip=True) if desc_elem else ""

                    # Datum zusammenbauen
                    event_date = datetime(current_year, current_month, day, hour, minute)
                    if event_date.date() < now.date():
                        continue

                    time_str = f"{hour:02d}:{minute:02d}"

                    event_id = hashlib.md5(
                        f"renaissance-{title}-{event_date.strftime('%Y-%m-%d-%H%M')}".encode()
                    ).hexdigest()[:12]

                    # Event-Typ mappen
                    if "lesung" in category:
                        event_type = "lesung"
                    elif "gespräch" in category or "salon" in category.lower():
                        event_type = "diskussion"
                    elif "poetry" in category or "slam" in category:
                        event_type = "literatur"
                    else:
                        event_type = "sonstiges"

                    events.append({
                        "id": event_id,
                        "title": title,
                        "date": event_date,
                        "time": time_str,
                        "venue_slug": venue_slug,
                        "venue_name": venue_name,
                        "venue_address": venue_address,
                        "bezirk": "charlottenburg-wilmersdorf",
                        "type": event_type,
                        "description": description,
                        "link": event_link,
                        "source": "renaissance-theater",
                    })
                except Exception:
                    continue

    except Exception as e:
        print(f"[Renaissance] Fehler: {e}")

    print(f"[Renaissance] {len(events)} Special-Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Flutgraben Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_flutgraben() -> list[dict]:
    """Scraped Events von Flutgraben e.V.

    Lädt Detailseiten um Datum aus Fließtext zu extrahieren.
    """
    events = []
    venue_name = "Flutgraben e.V."
    venue_address = "Am Flutgraben 3, 12435 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="treptow-koepenick",
        url="https://flutgraben.org",
    )

    url = "https://flutgraben.org/aktuell/filter/events/"
    now = datetime.now()

    month_map = {
        "januar": 1, "februar": 2, "märz": 3, "april": 4,
        "mai": 5, "juni": 6, "juli": 7, "august": 8,
        "september": 9, "oktober": 10, "november": 11, "dezember": 12
    }

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for article in soup.select("article.posts_item"):
            try:
                link = article.select_one("a.posts_item_link")
                if not link:
                    continue

                href = link.get("href", "")
                if not href:
                    continue

                title_elem = article.select_one("h3.posts_item_title")
                title = title_elem.get_text(strip=True) if title_elem else ""
                if not title:
                    continue

                # Detailseite laden für Datum
                detail_resp = requests.get(
                    href,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                    timeout=10,
                )
                detail_resp.raise_for_status()
                detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                text = detail_soup.get_text(" ", strip=True)

                # Datum suchen
                event_date = None

                # Format: "13. bis 16. August" oder "14. März 2026"
                match = re.search(
                    r"(\d{1,2})\.\s*(?:bis\s*\d{1,2}\.)?\s*(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)(?:\s*(\d{4}))?",
                    text, re.IGNORECASE
                )
                if match:
                    day = int(match.group(1))
                    month = month_map.get(match.group(2).lower(), 1)
                    year = int(match.group(3)) if match.group(3) else now.year
                    # Wenn Monat in der Vergangenheit, nächstes Jahr
                    if not match.group(3) and month < now.month:
                        year = now.year + 1
                    event_date = datetime(year, month, day, 19, 0)

                # Format: "14.03.2026"
                if not event_date:
                    match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
                    if match:
                        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                        event_date = datetime(year, month, day, 19, 0)

                if not event_date or event_date.date() < now.date():
                    continue

                # Beschreibung
                desc_elem = article.select_one("p.posts_item_text")
                description = desc_elem.get_text(strip=True) if desc_elem else ""

                event_id = hashlib.md5(
                    f"flutgraben-{title}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": "19:00",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "treptow-koepenick",
                    "type": "sonstiges",
                    "description": description,
                    "link": href,
                    "source": "flutgraben",
                })
            except Exception:
                continue

    except Exception as e:
        print(f"[Flutgraben] Fehler: {e}")

    print(f"[Flutgraben] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Einstein Forum Scraper (iCal)
# ─────────────────────────────────────────────────────────────────────────────

def load_museumsportal_from_json() -> list[dict]:
    """Lädt Museumsportal-Events aus manuell gepflegter JSON-Datei."""
    import json
    events = []
    now = datetime.now()
    json_path = os.path.join(os.path.dirname(__file__), "data", "museumsportal.json")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Events laden
        for item in data.get("events", []):
            try:
                event_date = datetime.strptime(item["date"], "%Y-%m-%d %H:%M")
                if event_date.date() < now.date():
                    continue

                venue_slug = get_or_create_venue(
                    name=item.get("venue_name", "Museum Berlin"),
                    adresse="Berlin",
                    bezirk=item.get("bezirk", "mitte"),
                    url="https://www.museumsportal-berlin.de",
                )

                event_id = hashlib.md5(
                    f"museumsportal-{item['title']}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": item["title"],
                    "date": event_date,
                    "time": event_date.strftime("%H:%M"),
                    "venue_slug": venue_slug,
                    "venue_name": item.get("venue_name", "Museum Berlin"),
                    "venue_address": "Berlin",
                    "bezirk": item.get("bezirk", "mitte"),
                    "type": item.get("type", "vortrag"),
                    "description": item.get("description", ""),
                    "link": item.get("link", ""),
                    "source": "museumsportal",
                })
            except Exception:
                continue

        # "Endet bald" Ausstellungen laden
        for item in data.get("closing_soon", []):
            try:
                end_date = datetime.strptime(item["end_date"], "%Y-%m-%d")
                if end_date.date() < now.date():
                    continue

                venue_slug = get_or_create_venue(
                    name=item.get("venue_name", "Museum Berlin"),
                    adresse="Berlin",
                    bezirk=item.get("bezirk", "mitte"),
                    url="https://www.museumsportal-berlin.de",
                )

                # Für jeden Tag von heute bis zum Enddatum ein Event
                current_date = now.replace(hour=18, minute=0, second=0, microsecond=0)
                while current_date.date() <= end_date.date():
                    event_id = hashlib.md5(
                        f"closing-{item['title']}-{current_date.strftime('%Y-%m-%d')}".encode()
                    ).hexdigest()[:12]

                    days_left = (end_date.date() - current_date.date()).days
                    if days_left == 0:
                        prefix = "LETZTER TAG:"
                    elif days_left == 1:
                        prefix = "ENDET MORGEN:"
                    else:
                        prefix = f"ENDET in {days_left} Tagen:"

                    events.append({
                        "id": event_id,
                        "title": f"{prefix} {item['title']}",
                        "date": current_date,
                        "time": "18:00",
                        "venue_slug": venue_slug,
                        "venue_name": item.get("venue_name", "Museum Berlin"),
                        "venue_address": "Berlin",
                        "bezirk": item.get("bezirk", "mitte"),
                        "type": "ausstellung",
                        "description": f"Ausstellung endet am {end_date.strftime('%d.%m.%Y')}",
                        "link": item.get("link", ""),
                        "source": "museumsportal",
                    })
                    current_date += timedelta(days=1)
            except Exception:
                continue

        print(f"[Museumsportal] {len(events)} Events aus JSON geladen")

    except FileNotFoundError:
        print("[Museumsportal] JSON-Datei nicht gefunden")
    except Exception as e:
        print(f"[Museumsportal] Fehler beim Laden: {e}")

    return events


def scrape_spionagemuseum() -> list[dict]:
    """Scraped Events vom Deutschen Spionagemuseum."""
    events = []
    now = datetime.now()

    venue_name = "Deutsches Spionagemuseum"
    venue_address = "Leipziger Platz 9, 10117 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://www.deutsches-spionagemuseum.de",
    )

    try:
        resp = requests.get(
            "https://www.deutsches-spionagemuseum.de/events/aktuell",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events sind in Elementor-Widgets
        for article in soup.select("article, .elementor-post, .elementor-widget-container"):
            try:
                # Titel finden
                title_elem = article.select_one("h2, h3, .elementor-heading-title")
                if not title_elem:
                    continue
                title = title_elem.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                # Datum finden (Format: DD.MM.YYYY oder ähnlich)
                text = article.get_text(" ", strip=True)
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
                if not date_match:
                    continue

                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3))

                # Uhrzeit finden
                time_match = re.search(r"(\d{1,2}):(\d{2})", text)
                hour = int(time_match.group(1)) if time_match else 19
                minute = int(time_match.group(2)) if time_match else 0

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Link finden
                link_elem = article.select_one("a[href*='event'], a[href*='veranstaltung']")
                if not link_elem:
                    link_elem = article.find_parent("a") or article.select_one("a")
                event_link = link_elem.get("href", "") if link_elem else ""
                if event_link and not event_link.startswith("http"):
                    event_link = f"https://www.deutsches-spionagemuseum.de{event_link}"
                if not event_link:
                    event_link = "https://www.deutsches-spionagemuseum.de/events/aktuell"

                event_id = hashlib.md5(
                    f"spionagemuseum-{title}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "mitte",
                    "type": "diskussion",
                    "description": "",
                    "link": event_link,
                    "source": "spionagemuseum",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Spionagemuseum] Fehler: {e}")

    print(f"[Spionagemuseum] {len(events)} Events geladen")
    return events


def scrape_museum_reinickendorf() -> list[dict]:
    """Scraped Events vom Museum Reinickendorf."""
    events = []
    now = datetime.now()

    venue_name = "Museum Reinickendorf"
    venue_address = "Alt-Hermsdorf 35, 13467 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="reinickendorf",
        url="https://museum-reinickendorf.de",
    )

    try:
        resp = requests.get(
            "https://museum-reinickendorf.de/kulturkalender/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events sind als Links strukturiert
        for link in soup.select("a[href*='/termine/']"):
            try:
                href = link.get("href", "")
                if not href or "/termine/" not in href:
                    continue

                text = link.get_text(" ", strip=True)
                if not text or len(text) < 10:
                    continue

                # Datum extrahieren (Format: DD.MM.YYYY oder DD.MM.YYYY–DD.MM.YYYY)
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
                if not date_match:
                    continue

                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3))

                # Uhrzeit finden (Format: HH:MM Uhr)
                time_match = re.search(r"(\d{1,2}):(\d{2})", text)
                hour = int(time_match.group(1)) if time_match else 19
                minute = int(time_match.group(2)) if time_match else 0

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Titel ist meist am Ende des Texts (nach Datum/Typ)
                # Format: "Typ | Ort | Datum Titel"
                title = text
                # Versuche Titel zu isolieren
                title_parts = text.split("\n")
                if len(title_parts) > 1:
                    title = title_parts[-1].strip()
                else:
                    # Entferne Datum und Uhrzeit vom Text
                    title = re.sub(r"\d{1,2}\.\d{1,2}\.\d{4}(–\d{1,2}\.\d{1,2}\.\d{4})?", "", title)
                    title = re.sub(r"\d{1,2}:\d{2}\s*Uhr", "", title)
                    title = re.sub(r"\s+", " ", title).strip()

                if not title or len(title) < 5:
                    continue

                # Event-Typ bestimmen
                text_lower = text.lower()
                if "lesung" in text_lower or "liest" in text_lower:
                    event_type = "lesung"
                elif "führung" in text_lower:
                    event_type = "diskussion"
                elif "ausstellung" in text_lower:
                    event_type = "ausstellung"
                elif "spaziergang" in text_lower or "unterwegs" in text_lower:
                    event_type = "workshop"
                elif "workshop" in text_lower:
                    event_type = "workshop"
                elif "vortrag" in text_lower or "gespräch" in text_lower:
                    event_type = "diskussion"
                else:
                    event_type = "diskussion"

                event_link = href if href.startswith("http") else f"https://museum-reinickendorf.de{href}"

                event_id = hashlib.md5(
                    f"reinickendorf-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title[:200],
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "reinickendorf",
                    "type": event_type,
                    "description": "",
                    "link": event_link,
                    "source": "museum_reinickendorf",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Museum Reinickendorf] Fehler: {e}")

    print(f"[Museum Reinickendorf] {len(events)} Events geladen")
    return events


def scrape_kollwitz_museum() -> list[dict]:
    """Scraped Events vom Käthe-Kollwitz-Museum Berlin."""
    events = []
    now = datetime.now()

    venue_name = "Käthe-Kollwitz-Museum Berlin"
    venue_address = "Fasanenstraße 24, 10719 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="charlottenburg-wilmersdorf",
        url="https://www.kaethe-kollwitz.berlin",
    )

    try:
        resp = requests.get(
            "https://www.kaethe-kollwitz.berlin/aktuelles/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events sind in article-Elementen
        for article in soup.select("article"):
            try:
                # Titel
                title_elem = article.select_one(".entry-title, h2, h3")
                if not title_elem:
                    continue
                title = title_elem.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                # Link
                link_elem = title_elem.find("a") or article.select_one("a")
                event_link = link_elem.get("href", "") if link_elem else ""
                if not event_link:
                    event_link = "https://www.kaethe-kollwitz.berlin/aktuelles/"

                # Text für Datumssuche
                text = article.get_text(" ", strip=True)

                # Datum extrahieren (verschiedene Formate)
                # Format: "31. März 2026" oder "15. März 2026, 11:30 Uhr"
                months = {
                    "januar": 1, "februar": 2, "märz": 3, "april": 4,
                    "mai": 5, "juni": 6, "juli": 7, "august": 8,
                    "september": 9, "oktober": 10, "november": 11, "dezember": 12
                }

                date_match = re.search(r"(\d{1,2})\.\s*(\w+)\s*(\d{4})", text.lower())
                if date_match:
                    day = int(date_match.group(1))
                    month_name = date_match.group(2)
                    year = int(date_match.group(3))
                    month = months.get(month_name, 0)
                    if month == 0:
                        continue
                else:
                    # Alternatives Format: DD.MM.YYYY
                    date_match2 = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
                    if date_match2:
                        day = int(date_match2.group(1))
                        month = int(date_match2.group(2))
                        year = int(date_match2.group(3))
                    else:
                        continue

                # Uhrzeit
                time_match = re.search(r"(\d{1,2}):(\d{2})", text)
                hour = int(time_match.group(1)) if time_match else 16
                minute = int(time_match.group(2)) if time_match else 0

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Event-Typ bestimmen
                text_lower = text.lower()
                if "führung" in text_lower:
                    event_type = "diskussion"
                elif "ausstellung" in text_lower:
                    event_type = "ausstellung"
                elif "vortrag" in text_lower or "gespräch" in text_lower:
                    event_type = "diskussion"
                elif "workshop" in text_lower:
                    event_type = "workshop"
                elif "lesung" in text_lower:
                    event_type = "lesung"
                else:
                    event_type = "ausstellung"

                event_id = hashlib.md5(
                    f"kollwitz-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title[:200],
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "charlottenburg-wilmersdorf",
                    "type": event_type,
                    "description": "",
                    "link": event_link,
                    "source": "kollwitz_museum",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Käthe-Kollwitz-Museum] Fehler: {e}")

    print(f"[Käthe-Kollwitz-Museum] {len(events)} Events geladen")
    return events


def scrape_smb_museen() -> list[dict]:
    """Scraped Events von den Staatlichen Museen zu Berlin (SMB).

    Filtert Events nach Typ - blockt:
    - Führung / Mit den Kurator*innen / Tandemführung
    - Workshop / Werkstatt
    - Ausstellungsgespräch
    - Aktionstag
    - Kinder / Jugendliche / Familien
    """
    events = []
    now = datetime.now()

    # Blockliste für Event-Typen die wir nicht wollen
    BLOCKED_TYPES = [
        "führung", "kurator", "tandemführung",
        "workshop", "werkstatt",
        "ausstellungsgespräch",
        "aktionstag",
        "kinder", "jugendliche", "familien"
    ]

    # Mapping von SMB-Museen zu Bezirken
    MUSEUM_BEZIRKE = {
        "humboldt forum": "mitte",
        "pergamonmuseum": "mitte",
        "neues museum": "mitte",
        "altes museum": "mitte",
        "alte nationalgalerie": "mitte",
        "bode-museum": "mitte",
        "james-simon-galerie": "mitte",
        "gemäldegalerie": "tiergarten",
        "kunstgewerbemuseum": "tiergarten",
        "kupferstichkabinett": "tiergarten",
        "neue nationalgalerie": "tiergarten",
        "musikinstrumenten-museum": "tiergarten",
        "kulturforum": "tiergarten",
        "hamburger bahnhof": "moabit",
        "museum berggruen": "charlottenburg-wilmersdorf",
        "sammlung scharf-gerstenberg": "charlottenburg-wilmersdorf",
        "schloss charlottenburg": "charlottenburg-wilmersdorf",
        "museum für fotografie": "charlottenburg-wilmersdorf",
        "schloss köpenick": "treptow-koepenick",
        "friedrichswerdersche kirche": "mitte",
    }

    try:
        resp = requests.get(
            "https://www.smb.museum/veranstaltungen/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events finden - suche nach Event-Links
        for link in soup.select("a[href*='/veranstaltungen/detail/']"):
            try:
                # Event-Container finden (Elternelement)
                container = link.find_parent("article") or link.find_parent("div")
                if not container:
                    container = link

                text = container.get_text(" ", strip=True).lower()

                # Prüfe ob Event geblockt werden soll
                should_block = False
                for blocked in BLOCKED_TYPES:
                    if blocked in text:
                        should_block = True
                        break
                if should_block:
                    continue

                # Titel extrahieren
                title_elem = container.select_one("h2, h3, strong, b")
                if title_elem:
                    title = title_elem.get_text(strip=True)
                else:
                    # Fallback: Link-Text
                    title = link.get_text(strip=True)

                if not title or len(title) < 5:
                    continue

                # Venue/Museum extrahieren
                venue_name = "Staatliche Museen zu Berlin"
                bezirk = "mitte"

                # Suche nach Museumsnamen im Text
                full_text = container.get_text(" ", strip=True)
                for museum, museum_bezirk in MUSEUM_BEZIRKE.items():
                    if museum in full_text.lower():
                        venue_name = museum.title()
                        bezirk = museum_bezirk
                        break

                # Datum extrahieren (Format: "Mi 11.03.2026 11:00 Uhr")
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", full_text)
                if not date_match:
                    continue

                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3))

                # Uhrzeit
                time_match = re.search(r"(\d{1,2}):(\d{2})", full_text)
                hour = int(time_match.group(1)) if time_match else 19
                minute = int(time_match.group(2)) if time_match else 0

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Event-Link
                href = link.get("href", "")
                event_link = href if href.startswith("http") else f"https://www.smb.museum{href}"

                # Event-Typ bestimmen
                text_lower = full_text.lower()
                if "konzert" in text_lower or "musik" in text_lower:
                    event_type = "konzert"
                elif "film" in text_lower or "kino" in text_lower:
                    event_type = "film"
                elif "lesung" in text_lower:
                    event_type = "lesung"
                elif "vortrag" in text_lower or "gespräch" in text_lower or "diskussion" in text_lower:
                    event_type = "diskussion"
                elif "performance" in text_lower or "theater" in text_lower:
                    event_type = "theater"
                else:
                    event_type = "ausstellung"

                # Venue-Slug erstellen
                venue_slug = get_or_create_venue(
                    name=venue_name,
                    adresse="",  # SMB-Museen haben verschiedene Adressen
                    bezirk=bezirk,
                    url="https://www.smb.museum",
                )

                event_id = hashlib.md5(
                    f"smb-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title[:200],
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": "",
                    "bezirk": bezirk,
                    "type": event_type,
                    "description": "",
                    "link": event_link,
                    "source": "smb_museen",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[SMB Museen] Fehler: {e}")

    print(f"[SMB Museen] {len(events)} Events geladen")
    return events


def scrape_museum_charlottenburg() -> list[dict]:
    """Scraped Events vom Museum Charlottenburg-Wilmersdorf (Villa Oppenheim)."""
    events = []
    now = datetime.now()

    venue_name = "Museum Charlottenburg-Wilmersdorf"
    venue_address = "Schloßstraße 55, 14059 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="charlottenburg-wilmersdorf",
        url="https://www.villa-oppenheim-berlin.de",
    )

    try:
        resp = requests.get(
            "https://www.villa-oppenheim-berlin.de/veranstaltungen/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events in Artikeln oder Containern
        for container in soup.select("article, .event, .veranstaltung, section"):
            try:
                text = container.get_text(" ", strip=True)
                if len(text) < 20:
                    continue

                # Datum extrahieren (Format: "Sa, 14.03.2026, 11 Uhr")
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
                if not date_match:
                    continue

                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3))

                # Uhrzeit (Format: "11 Uhr" oder "14:00")
                time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*Uhr", text, re.IGNORECASE)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2)) if time_match.group(2) else 0
                else:
                    hour, minute = 19, 0

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Titel finden
                title_elem = container.select_one("h2, h3, h4, strong, b")
                if title_elem:
                    title = title_elem.get_text(strip=True)
                else:
                    # Fallback: erster Teil des Texts nach dem Datum
                    title = text.split("–")[0].strip() if "–" in text else text[:100]

                # Entferne Datum vom Titel
                title = re.sub(r"^[A-Za-z]{2},?\s*\d{1,2}\.\d{1,2}\.\d{4},?\s*\d{1,2}(?::\d{2})?\s*Uhr\s*", "", title)
                title = title.strip(" –-")

                if not title or len(title) < 5:
                    continue

                # Link finden
                link_elem = container.select_one("a[href]")
                event_link = link_elem.get("href", "") if link_elem else ""
                if event_link and not event_link.startswith("http"):
                    event_link = f"https://www.villa-oppenheim-berlin.de{event_link}"
                if not event_link:
                    event_link = "https://www.villa-oppenheim-berlin.de/veranstaltungen/"

                # Event-Typ bestimmen
                text_lower = text.lower()
                if "lesung" in text_lower:
                    event_type = "lesung"
                elif "film" in text_lower:
                    event_type = "film"
                elif "gespräch" in text_lower or "diskussion" in text_lower or "vortrag" in text_lower:
                    event_type = "diskussion"
                elif "konzert" in text_lower or "musik" in text_lower:
                    event_type = "konzert"
                elif "stadtrundgang" in text_lower or "stadttour" in text_lower or "spaziergang" in text_lower:
                    event_type = "workshop"
                elif "ausstellung" in text_lower:
                    event_type = "ausstellung"
                else:
                    event_type = "diskussion"

                # Beschreibung aus .vrst-content p (nach der Headline)
                description = ""
                vrst_content = container.select_one(".vrst-content")
                if vrst_content:
                    # Nimm alle p-Elemente nach der Headline
                    paragraphs = vrst_content.select("p")
                    for p in paragraphs:
                        p_text = p.get_text(strip=True)
                        # Überspringe kurze/leere oder reine strong-Tags
                        if len(p_text) > 30:
                            description = p_text[:300]
                            break

                event_id = hashlib.md5(
                    f"charlottenburg-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title[:200],
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "charlottenburg-wilmersdorf",
                    "type": event_type,
                    "description": description,
                    "link": event_link,
                    "source": "museum_charlottenburg",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Museum Charlottenburg-Wilmersdorf] Fehler: {e}")

    print(f"[Museum Charlottenburg-Wilmersdorf] {len(events)} Events geladen")
    return events


def scrape_humboldt_forum() -> list[dict]:
    """Scraped Events vom Humboldt Forum via REST API.

    Filtert nach relevanten Genres (Konzerte, Theater, Lesungen, Gespräche, etc.)
    Genre IDs: 392,564,729,823,523,423,827,390,393,943,820,930,1078,829
    """
    events = []
    now = datetime.now()

    venue_name = "Humboldt Forum"
    venue_address = "Schloßplatz, 10178 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://www.humboldtforum.org",
    )

    # Relevante Genre-IDs (aus dem URL-Filter)
    genres = "392,564,729,823,523,423,827,390,393,943,820,930,1078,829"

    try:
        resp = requests.get(
            f"https://www.humboldtforum.org/wp-json/humboldt/v1/event/items?genre={genres}",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for item in data:
            try:
                title = item.get("title", "")
                if not title:
                    continue

                slug = item.get("slug", "")
                post_id = item.get("postId", "")

                # Event-Link
                event_link = f"https://www.humboldtforum.org/de/programm/veranstaltung/{slug}-{post_id}/"

                # Zeiten aus ACF-Feld
                acf = item.get("acf", {})
                times = acf.get("times", [])

                if not times:
                    continue

                # Jede Zeit als separates Event
                for time_slot in times:
                    try:
                        # Format: "20260313 18:30"
                        start_str = time_slot.get("start", "")
                        if not start_str:
                            continue

                        # Parse Datum
                        start_match = re.match(r"(\d{4})(\d{2})(\d{2})\s*(\d{2}):(\d{2})", start_str)
                        if not start_match:
                            continue

                        year = int(start_match.group(1))
                        month = int(start_match.group(2))
                        day = int(start_match.group(3))
                        hour = int(start_match.group(4))
                        minute = int(start_match.group(5))

                        try:
                            event_date = datetime(year, month, day, hour, minute)
                        except ValueError:
                            continue

                        if event_date.date() < now.date():
                            continue

                        # Event-Typ bestimmen aus genre
                        genre_ids = item.get("genre", [])
                        event_type = "diskussion"  # Default

                        # Genre-Mapping (basierend auf typischen IDs)
                        # 390 = Konzert, 392 = Vortrag, 393 = Gespräch, 423 = Lesung
                        # 523 = Theater/Performance, 564 = Film
                        if 390 in genre_ids or 820 in genre_ids:
                            event_type = "konzert"
                        elif 564 in genre_ids:
                            event_type = "film"
                        elif 423 in genre_ids:
                            event_type = "lesung"
                        elif 523 in genre_ids or 827 in genre_ids:
                            event_type = "theater"
                        elif 392 in genre_ids or 393 in genre_ids:
                            event_type = "diskussion"

                        event_id = hashlib.md5(
                            f"humboldtforum-{post_id}-{event_date.strftime('%Y-%m-%d-%H%M')}".encode()
                        ).hexdigest()[:12]

                        events.append({
                            "id": event_id,
                            "title": title[:200],
                            "date": event_date,
                            "time": f"{hour:02d}:{minute:02d}",
                            "venue_slug": venue_slug,
                            "venue_name": venue_name,
                            "venue_address": venue_address,
                            "bezirk": "mitte",
                            "type": event_type,
                            "description": item.get("excerpt", "")[:300],
                            "link": event_link,
                            "source": "humboldt_forum",
                        })

                    except Exception:
                        continue

            except Exception:
                continue

    except Exception as e:
        print(f"[Humboldt Forum] Fehler: {e}")

    print(f"[Humboldt Forum] {len(events)} Events geladen")
    return events


def scrape_mitte_museum() -> list[dict]:
    """Scraped Events vom Mitte Museum."""
    events = []
    now = datetime.now()

    venue_name = "Mitte Museum"
    venue_address = "Pankstraße 47, 13357 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://www.mittemuseum.de",
    )

    try:
        resp = requests.get(
            "https://www.mittemuseum.de/de/veranstaltung",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events in Links suchen
        for link in soup.select("a[href*='/veranstaltung/']"):
            try:
                href = link.get("href", "")
                if not href or "/veranstaltung/" not in href:
                    continue

                # Container für Text
                container = link.find_parent("article") or link.find_parent("div") or link
                text = container.get_text(" ", strip=True)

                if len(text) < 15:
                    continue

                # Titel finden
                title_elem = container.select_one("h2, h3, h4, strong")
                if title_elem:
                    title = title_elem.get_text(strip=True)
                else:
                    title = link.get_text(strip=True)

                if not title or len(title) < 5:
                    continue

                # Datum extrahieren
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
                if not date_match:
                    # Versuche deutsches Datumsformat: "15. März 2026"
                    months = {
                        "januar": 1, "februar": 2, "märz": 3, "april": 4,
                        "mai": 5, "juni": 6, "juli": 7, "august": 8,
                        "september": 9, "oktober": 10, "november": 11, "dezember": 12
                    }
                    date_match2 = re.search(r"(\d{1,2})\.\s*(\w+)\s*(\d{4})", text.lower())
                    if date_match2:
                        day = int(date_match2.group(1))
                        month_name = date_match2.group(2)
                        year = int(date_match2.group(3))
                        month = months.get(month_name, 0)
                        if month == 0:
                            continue
                    else:
                        continue
                else:
                    day = int(date_match.group(1))
                    month = int(date_match.group(2))
                    year = int(date_match.group(3))

                # Uhrzeit
                time_match = re.search(r"(\d{1,2}):(\d{2})", text)
                hour = int(time_match.group(1)) if time_match else 19
                minute = int(time_match.group(2)) if time_match else 0

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Event-Link
                event_link = href if href.startswith("http") else f"https://www.mittemuseum.de{href}"

                # Event-Typ
                text_lower = text.lower()
                if "vernissage" in text_lower or "eröffnung" in text_lower:
                    event_type = "ausstellung"
                elif "finissage" in text_lower:
                    event_type = "ausstellung"
                elif "lesung" in text_lower:
                    event_type = "lesung"
                elif "vortrag" in text_lower or "gespräch" in text_lower:
                    event_type = "diskussion"
                elif "führung" in text_lower:
                    event_type = "diskussion"
                else:
                    event_type = "ausstellung"

                event_id = hashlib.md5(
                    f"mittemuseum-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title[:200],
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "mitte",
                    "type": event_type,
                    "description": "",
                    "link": event_link,
                    "source": "mitte_museum",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Mitte Museum] Fehler: {e}")

    print(f"[Mitte Museum] {len(events)} Events geladen")
    return events


def scrape_mendelssohn_remise() -> list[dict]:
    """Scraped Events von der Mendelssohn-Remise.

    Die Website läuft nur über HTTP (kein HTTPS).
    """
    events = []
    now = datetime.now()

    venue_name = "Mendelssohn-Remise"
    venue_address = "Jägerstraße 51, 10117 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="http://www.mendelssohn-remise.de",
    )

    try:
        # Website nutzt nur HTTP, kein HTTPS
        resp = requests.get(
            "http://www.mendelssohn-remise.de/gesellschaft/veranstaltungen",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events sind in div.event Elementen
        for event_div in soup.select("div.event"):
            try:
                # Prüfe ob vergangenes Event (past_event Klasse)
                if "past_event" in event_div.get("class", []):
                    continue

                # Event-Typ (Konzert, Vortrag, etc.)
                type_elem = event_div.select_one(".column_e_s.red_font")
                event_type_text = type_elem.get_text(strip=True).lower() if type_elem else ""

                # Titel
                title_elem = event_div.select_one(".event_title")
                if not title_elem:
                    continue
                title = title_elem.get_text(strip=True)
                if not title:
                    continue

                # Datum (Format: "Do., 8.1." oder "Sa., 10.1.")
                datum_elem = event_div.select_one(".datum")
                if not datum_elem:
                    continue
                datum_text = datum_elem.get_text(strip=True)

                # Uhrzeit
                time_elem = event_div.select_one(".FSeXS.ph")
                time_text = time_elem.get_text(strip=True) if time_elem else "19:00"

                # Parse Datum
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.", datum_text)
                if not date_match:
                    continue

                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = now.year
                # Wenn Monat vor aktuellem Monat, dann nächstes Jahr
                if month < now.month:
                    year += 1

                # Uhrzeit parsen
                time_match = re.search(r"(\d{1,2}):(\d{2})", time_text)
                hour = int(time_match.group(1)) if time_match else 19
                minute = int(time_match.group(2)) if time_match else 0

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Link aus onclick extrahieren
                onclick_elem = event_div.select_one("[onclick*='loadLayer']")
                event_link = ""
                if onclick_elem:
                    onclick = onclick_elem.get("onclick", "")
                    link_match = re.search(r"loadLayer\('([^']+)'\)", onclick)
                    if link_match:
                        event_link = link_match.group(1)
                if not event_link:
                    event_link = "http://www.mendelssohn-remise.de/gesellschaft/veranstaltungen"

                # Event-Typ bestimmen
                if "konzert" in event_type_text:
                    event_type = "konzert"
                elif "lesung" in event_type_text:
                    event_type = "lesung"
                elif "vortrag" in event_type_text or "gespräch" in event_type_text:
                    event_type = "diskussion"
                elif "führung" in event_type_text:
                    event_type = "diskussion"
                elif "ausstellung" in event_type_text:
                    event_type = "ausstellung"
                else:
                    event_type = "konzert"  # Default für Mendelssohn-Remise

                # Beschreibung aus .shorttext p
                description = ""
                shorttext = event_div.select_one(".shorttext")
                if shorttext:
                    desc_p = shorttext.select_one("p")
                    if desc_p:
                        description = desc_p.get_text(strip=True)[:300]

                event_id = hashlib.md5(
                    f"mendelssohn-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title[:200],
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "mitte",
                    "type": event_type,
                    "description": description,
                    "link": event_link,
                    "source": "mendelssohn_remise",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Mendelssohn-Remise] Fehler: {e}")

    print(f"[Mendelssohn-Remise] {len(events)} Events geladen")
    return events


def scrape_dhm() -> list[dict]:
    """Scraped Events vom Deutschen Historischen Museum."""
    events = []
    now = datetime.now()

    venue_name = "Deutsches Historisches Museum"
    venue_address = "Unter den Linden 2, 10117 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://www.dhm.de",
    )

    try:
        resp = requests.get(
            "https://www.dhm.de/programm/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events in Links suchen
        for link in soup.select("a[href*='/veranstaltung/'], a[href*='/programm/']"):
            try:
                href = link.get("href", "")
                if not href:
                    continue

                # Container für Text
                container = link.find_parent("article") or link.find_parent("div") or link
                text = container.get_text(" ", strip=True)

                if len(text) < 15:
                    continue

                # Titel finden
                title_elem = container.select_one("h2, h3, h4, strong")
                if title_elem:
                    title = title_elem.get_text(strip=True)
                else:
                    title = link.get_text(strip=True)

                if not title or len(title) < 5:
                    continue

                # Datum extrahieren (Format: "17. März 2026")
                months = {
                    "januar": 1, "februar": 2, "märz": 3, "april": 4,
                    "mai": 5, "juni": 6, "juli": 7, "august": 8,
                    "september": 9, "oktober": 10, "november": 11, "dezember": 12
                }

                date_match = re.search(r"(\d{1,2})\.\s*(\w+)\s*(\d{4})", text.lower())
                if date_match:
                    day = int(date_match.group(1))
                    month_name = date_match.group(2)
                    year = int(date_match.group(3))
                    month = months.get(month_name, 0)
                    if month == 0:
                        # Versuche numerisches Format
                        date_match2 = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
                        if date_match2:
                            day = int(date_match2.group(1))
                            month = int(date_match2.group(2))
                            year = int(date_match2.group(3))
                        else:
                            continue
                else:
                    date_match2 = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
                    if date_match2:
                        day = int(date_match2.group(1))
                        month = int(date_match2.group(2))
                        year = int(date_match2.group(3))
                    else:
                        continue

                # Uhrzeit
                time_match = re.search(r"(\d{1,2}):(\d{2})", text)
                hour = int(time_match.group(1)) if time_match else 18
                minute = int(time_match.group(2)) if time_match else 0

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Event-Link
                event_link = href if href.startswith("http") else f"https://www.dhm.de{href}"

                # Event-Typ
                text_lower = text.lower()
                if "finissage" in text_lower or "vernissage" in text_lower:
                    event_type = "ausstellung"
                elif "vortrag" in text_lower or "gespräch" in text_lower or "diskussion" in text_lower:
                    event_type = "diskussion"
                elif "führung" in text_lower or "tandem" in text_lower:
                    event_type = "diskussion"
                elif "konzert" in text_lower or "musik" in text_lower:
                    event_type = "konzert"
                elif "lesung" in text_lower:
                    event_type = "lesung"
                elif "film" in text_lower:
                    event_type = "film"
                elif "tagung" in text_lower or "symposium" in text_lower:
                    event_type = "diskussion"
                else:
                    event_type = "diskussion"

                event_id = hashlib.md5(
                    f"dhm-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title[:200],
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "mitte",
                    "type": event_type,
                    "description": "",
                    "link": event_link,
                    "source": "dhm",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[DHM] Fehler: {e}")

    print(f"[DHM] {len(events)} Events geladen")
    return events


def scrape_nbk() -> list[dict]:
    """Scraped Events vom Neuen Berliner Kunstverein (n.b.k.)."""
    events = []
    now = datetime.now()

    venue_name = "n.b.k. Neuer Berliner Kunstverein"
    venue_address = "Chausseestraße 128/129, 10115 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://www.nbk.org",
    )

    try:
        resp = requests.get(
            "https://www.nbk.org/de/diskursprogramm",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Der gesamte Text der Seite durchsuchen
        text = resp.text

        # Finde alle Datum-Muster mit umgebendem Kontext
        # Format: "13.03.2026 - Titel"
        pattern = r'(\d{1,2})\.(\d{2})\.(\d{4})\s*[-–]\s*([^<"\n]{5,100})'
        matches = re.findall(pattern, text)

        seen_titles = set()
        for match in matches:
            try:
                day = int(match[0])
                month = int(match[1])
                year = int(match[2])
                title = match[3].strip()

                # Bereinige Titel
                title = re.sub(r'\s+', ' ', title)
                title = title.strip(' ,-–')

                if not title or len(title) < 5:
                    continue

                # Duplikate vermeiden
                title_key = f"{title[:30]}-{day}-{month}"
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)

                # Standard-Uhrzeit für Events
                hour, minute = 19, 0

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Event-Typ bestimmen
                title_lower = title.lower()
                if "eröffnung" in title_lower or "ausstellung" in title_lower:
                    event_type = "ausstellung"
                elif "book launch" in title_lower or "lesung" in title_lower:
                    event_type = "lesung"
                elif "rundgang" in title_lower or "führung" in title_lower:
                    event_type = "diskussion"
                elif "vortrag" in title_lower or "talk" in title_lower:
                    event_type = "diskussion"
                elif "screening" in title_lower or "film" in title_lower:
                    event_type = "film"
                else:
                    event_type = "ausstellung"

                event_id = hashlib.md5(
                    f"nbk-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title[:200],
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "mitte",
                    "type": event_type,
                    "description": "",
                    "link": "https://www.nbk.org/de/diskursprogramm",
                    "source": "nbk",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[n.b.k.] Fehler: {e}")

    print(f"[n.b.k.] {len(events)} Events geladen")
    return events


def scrape_kreativhaus() -> list[dict]:
    """Scraped Events vom Kreativhaus Berlin via REST API (The Events Calendar).

    Filtert Familien-/Kinderveranstaltungen aus.
    """
    events = []
    now = datetime.now()

    # Blockliste für Titel (Familien-/Kinderveranstaltungen, Kurse, Senioren)
    BLOCKED_TITLE_PATTERNS = [
        # Kinder/Familie
        "kinder", "kids", "familie", "familien", "eltern",
        "baby", "krabbel", "spiel-raum", "spiel-bau",
        "mitmach-märchen", "puppentheater", "1-4 jahre", "1-6 jahre",
        "ab 4 jahr", "ab 3 jahr", "für kinder",
        "tiny dancer", "mutter-kind", "vater-kind",
        # Senioren
        "silver dancer", "seniorinnen", "senioren", "junggeblieben",
        "locker vom hocker",
        # Kurse/Sport
        "deutschkurs", "deutsch lernen", "spielend deutsch", "sprachcafe",
        "yoga", "pilates", "gymnastik", "fitness", "aerobic",
        "let's dance", "lets dance",
        # Beratung
        "clearing", "beratung",
        # Handarbeit
        "nähkurs", "strickkurs",
        # Technik-Hilfe
        "digital-treff", "digitaltreff",
    ]

    venue_name = "Kreativhaus Berlin"
    venue_address = "Fischerinsel 3, 10179 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://www.kreativhaus-berlin.de",
    )

    try:
        # The Events Calendar REST API
        resp = requests.get(
            "https://www.kreativhaus-berlin.de/wp-json/tribe/events/v1/events",
            params={"per_page": 50, "start_date": now.strftime("%Y-%m-%d")},
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("events", []):
            try:
                title = item.get("title", "")
                if not title:
                    continue

                # Filter: Familien-/Kinderveranstaltungen ausschließen
                title_lower = title.lower()
                if any(pattern in title_lower for pattern in BLOCKED_TITLE_PATTERNS):
                    continue

                # Datum parsen
                start_date_str = item.get("start_date", "")
                if not start_date_str:
                    continue

                # Format: "2026-03-11 09:00:00"
                try:
                    event_date = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Event-Link
                event_link = item.get("url", "https://www.kreativhaus-berlin.de/veranstaltungen/")

                # Kategorien für Event-Typ
                categories = item.get("categories", [])
                category_names = [c.get("name", "").lower() for c in categories]
                category_text = " ".join(category_names)

                if "konzert" in category_text or "musik" in category_text:
                    event_type = "konzert"
                elif "film" in category_text or "kino" in category_text:
                    event_type = "film"
                elif "lesung" in category_text or "literatur" in category_text:
                    event_type = "lesung"
                elif "theater" in category_text or "performance" in category_text:
                    event_type = "theater"
                elif "workshop" in category_text or "kurs" in category_text:
                    event_type = "workshop"
                elif "vortrag" in category_text or "diskussion" in category_text:
                    event_type = "diskussion"
                elif "party" in category_text or "tanz" in category_text:
                    event_type = "party"
                else:
                    event_type = "diskussion"

                # Beschreibung (bereinigt) - excerpt bevorzugen, sonst description
                excerpt = item.get("excerpt", "")
                if not excerpt:
                    excerpt = item.get("description", "")
                if excerpt:
                    # HTML entfernen
                    excerpt = re.sub(r"<[^>]+>", " ", excerpt)
                    excerpt = re.sub(r"\s+", " ", excerpt).strip()
                    excerpt = excerpt[:300]

                event_id = hashlib.md5(
                    f"kreativhaus-{item.get('id', '')}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title[:200],
                    "date": event_date,
                    "time": event_date.strftime("%H:%M"),
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "mitte",
                    "type": event_type,
                    "description": excerpt,
                    "link": event_link,
                    "source": "kreativhaus",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Kreativhaus] Fehler: {e}")

    print(f"[Kreativhaus] {len(events)} Events geladen")
    return events


def scrape_newsletter_rss() -> list[dict]:
    """Scraped Events aus Newsletter-RSS-Feed (Kill the Newsletter).

    Extrahiert Events aus HTML-Newslettern von Urban Nation.
    Format: Titel in font-size:20px div, Beschreibung in font-size:14px div,
    Datum bei "Wann:", Ort bei "Wo:", Link bei "Mehr erfahren".
    """
    events = []
    now = datetime.now()

    # Monatsnamen für Parsing
    MONTHS = {
        "januar": 1, "februar": 2, "märz": 3, "april": 4,
        "mai": 5, "juni": 6, "juli": 7, "august": 8,
        "september": 9, "oktober": 10, "november": 11, "dezember": 12
    }

    try:
        resp = requests.get(
            "https://kill-the-newsletter.com/feeds/du5hw4itlnha39i0cmv2.xml",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()

        # Atom-Feed parsen
        soup = BeautifulSoup(resp.text, "xml")

        for entry in soup.find_all("entry"):
            try:
                entry_title_elem = entry.find("title")
                if not entry_title_elem:
                    continue
                newsletter_title = entry_title_elem.get_text(strip=True).lower()

                # Nur Urban Nation Newsletter verarbeiten
                if "urban nation" not in newsletter_title:
                    continue

                # HTML-Content des Newsletters
                content_elem = entry.find("content")
                if not content_elem:
                    continue
                html_content = content_elem.get_text()

                # HTML parsen
                content_soup = BeautifulSoup(html_content, "html.parser")

                # Events finden: Titel in 20px font, Beschreibung in 14px font
                # Suche nach allen divs mit font-size:20px (Titel)
                title_divs = content_soup.find_all("div", style=lambda s: s and "font-size:20px" in s)

                for title_div in title_divs:
                    try:
                        title = title_div.get_text(strip=True)
                        if not title or len(title) < 5:
                            continue

                        # Überspringe englische Titel (nur deutsch)
                        # Einfacher Check: enthält deutsche Wörter?
                        # Wir akzeptieren alle, da Urban Nation oft englische Titel hat

                        # Suche Beschreibungs-div (14px) nach dem Titel
                        description = ""
                        event_link = ""
                        event_date = None
                        location = ""
                        is_free = False

                        # Nächstes Geschwister-Element oder Parent durchsuchen
                        next_elem = title_div.find_next_sibling()
                        if not next_elem:
                            next_elem = title_div.parent.find_next_sibling() if title_div.parent else None

                        # Suche im umgebenden Bereich nach Infos
                        parent = title_div.parent
                        search_area = parent.parent if parent else title_div
                        if search_area:
                            area_text = search_area.get_text(" ", strip=True)

                            # Datum extrahieren: "Wann: 13. März 2026, 19–21 Uhr"
                            wann_match = re.search(
                                r"Wann[:\s]*(\d{1,2})\.\s*(\w+)\s*(\d{4})[,\s]*(\d{1,2})(?:[–\-:](\d{1,2}))?\s*Uhr",
                                area_text, re.IGNORECASE
                            )
                            if wann_match:
                                day = int(wann_match.group(1))
                                month_name = wann_match.group(2).lower()
                                year = int(wann_match.group(3))
                                hour = int(wann_match.group(4))
                                month = MONTHS.get(month_name, 0)
                                if month > 0:
                                    try:
                                        event_date = datetime(year, month, day, hour, 0)
                                    except ValueError:
                                        pass

                            # Ort extrahieren: "Wo: Martha Cooper Library..."
                            wo_match = re.search(r"Wo[:\s]*([^<\n]+?)(?:Eintritt|Mehr erfahren|$)", area_text)
                            if wo_match:
                                location = wo_match.group(1).strip()

                            # Eintritt frei?
                            if "eintritt" in area_text.lower() and "frei" in area_text.lower():
                                is_free = True

                            # Link extrahieren
                            mehr_link = search_area.find("a", string=re.compile(r"Mehr erfahren", re.IGNORECASE))
                            if mehr_link:
                                event_link = mehr_link.get("href", "")

                            # Beschreibung: Text zwischen Titel und "Wann"
                            desc_div = search_area.find("div", style=lambda s: s and "font-size:14px" in s)
                            if desc_div:
                                desc_text = desc_div.get_text(" ", strip=True)
                                # Kürze bei "Wann:" oder "Mehr erfahren"
                                for cutoff in ["Wann:", "Wann ", "Mehr erfahren"]:
                                    if cutoff in desc_text:
                                        desc_text = desc_text.split(cutoff)[0]
                                description = desc_text[:500].strip()

                        if not event_date:
                            continue

                        if event_date.date() < now.date():
                            continue

                        # Venue
                        venue_name = "Urban Nation Museum"
                        venue_address = "Bülowstraße 7, 10783 Berlin"
                        venue_slug = get_or_create_venue(
                            name=venue_name,
                            adresse=venue_address,
                            bezirk="schoeneberg",
                            url="https://urban-nation.com",
                        )

                        # Event-Typ
                        title_lower = title.lower()
                        if "ausstellung" in title_lower or "exhibition" in title_lower:
                            event_type = "ausstellung"
                        elif "book launch" in title_lower or "buchvorstellung" in title_lower:
                            event_type = "lesung"
                        elif "talk" in title_lower or "gespräch" in title_lower or "diskussion" in title_lower:
                            event_type = "diskussion"
                        elif "film" in title_lower or "screening" in title_lower:
                            event_type = "film"
                        elif "konzert" in title_lower or "concert" in title_lower or "music" in title_lower:
                            event_type = "konzert"
                        else:
                            event_type = "ausstellung"

                        event_id = hashlib.md5(
                            f"urban-nation-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                        ).hexdigest()[:12]

                        events.append({
                            "id": event_id,
                            "title": title[:200],
                            "date": event_date,
                            "time": event_date.strftime("%H:%M"),
                            "venue_slug": venue_slug,
                            "venue_name": venue_name,
                            "venue_address": venue_address,
                            "bezirk": "schoeneberg",
                            "type": event_type,
                            "description": description,
                            "link": event_link if event_link else "https://urban-nation.com",
                            "source": "newsletter_urban_nation",
                            "is_free": is_free,
                        })

                    except Exception:
                        continue

            except Exception:
                continue

    except Exception as e:
        print(f"[Newsletter RSS] Fehler: {e}")

    # Duplikate entfernen (nach Titel + Datum)
    seen = set()
    unique_events = []
    for ev in events:
        key = f"{ev['title'][:50]}-{ev['date'].strftime('%Y-%m-%d')}"
        if key not in seen:
            seen.add(key)
            unique_events.append(ev)

    print(f"[Newsletter RSS] {len(unique_events)} Events geladen")
    return unique_events


def scrape_luftschloss() -> list[dict]:
    """Scraped Events vom Luftschloss Tempelhofer Feld via REST API."""
    events = []
    now = datetime.now()

    venue_name = "Luftschloss Tempelhofer Feld"
    venue_address = "Tempelhofer Feld, Eingang Oderstraße, 12051 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="tempelhof-schoeneberg",
        url="https://luftschloss-tempelhoferfeld.de",
    )

    api_url = "https://luftschloss-tempelhoferfeld.de/wp-json/atze-events/v1/events/filtered"

    try:
        resp = requests.get(
            api_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # Data format: {"2026-05": {"2026-05-20": [event, ...]}}
        for month_key, days in data.items():
            if not isinstance(days, dict):
                continue
            for date_key, day_events in days.items():
                if not isinstance(day_events, list):
                    continue
                for ev in day_events:
                    try:
                        # Parse date from datetimeISO
                        dt_iso = ev.get("datetimeISO", "")
                        if not dt_iso:
                            continue
                        event_date = datetime.fromisoformat(dt_iso)

                        if event_date.date() < now.date():
                            continue

                        title = ev.get("name", "")
                        if not title:
                            continue

                        time_str = ev.get("time", "20:00")
                        description = ev.get("excerpt", "")[:300]
                        link = ev.get("repertoire_link", "https://luftschloss-tempelhoferfeld.de/programm/")

                        # Typ bestimmen aus tags/category
                        tags = ev.get("tags", "").lower()
                        category = ev.get("category", "").lower()
                        if "konzert" in tags or "musik" in tags:
                            event_type = "konzert"
                        elif "theater" in category or "schauspiel" in tags:
                            event_type = "theater"
                        elif "lesung" in tags:
                            event_type = "lesung"
                        else:
                            event_type = "konzert"  # Default für Luftschloss

                        event_id = hashlib.md5(
                            f"luftschloss-{ev.get('id', '')}-{event_date.strftime('%Y-%m-%d')}".encode()
                        ).hexdigest()[:12]

                        events.append({
                            "id": event_id,
                            "title": title,
                            "date": event_date,
                            "time": time_str,
                            "venue_slug": venue_slug,
                            "venue_name": venue_name,
                            "venue_address": venue_address,
                            "bezirk": "tempelhof-schoeneberg",
                            "type": event_type,
                            "description": description,
                            "link": link,
                            "source": "luftschloss",
                        })
                    except Exception:
                        continue

    except Exception as e:
        print(f"[Luftschloss] Fehler: {e}")

    print(f"[Luftschloss] {len(events)} Events geladen")
    return events


def scrape_schaubuehne() -> list[dict]:
    """Scraped Events von der Schaubühne Berlin (Diskurs, Lesung, Premiere)."""
    events = []
    now = datetime.now()

    # Typen die wir wollen: 29=Diskurs, 28=Lesung, 6=Premiere
    wanted_types = {"29", "28", "6"}

    venue_name = "Schaubühne Berlin"
    venue_address = "Kurfürstendamm 153, 10709 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="charlottenburg-wilmersdorf",
        url="https://www.schaubuehne.de",
    )

    try:
        # AJAX Endpunkt laden
        page = 0
        last_termin = 0
        all_html = ""

        while True:
            resp = requests.get(
                f"https://www.schaubuehne.de/de/spielplan/programm.html?ajax=1&offset={page}&letzterTermin={last_termin}",
                headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                timeout=15,
            )
            if resp.status_code != 200 or "ende erreicht" in resp.text.lower():
                break

            content = resp.text
            all_html += content

            # Letzten Termin extrahieren
            termin_match = re.search(r'class="d-none letzterTermin">(\d+)</div>', content)
            if termin_match:
                last_termin = int(termin_match.group(1))
            else:
                break

            page += 1
            if page > 10:
                break

        soup = BeautifulSoup(all_html, "html.parser")

        for vorstellung in soup.select("div.vorstellung"):
            try:
                classes = " ".join(vorstellung.get("class", []))

                # Prüfen ob der Typ gewünscht ist
                is_wanted = False
                event_type = "theater"
                for t in wanted_types:
                    if f"typ-{t}" in classes:
                        is_wanted = True
                        if t == "29":
                            event_type = "diskussion"
                        elif t == "28":
                            event_type = "lesung"
                        elif t == "6":
                            event_type = "theater"
                        break

                if not is_wanted:
                    continue

                # Datum aus data-date (Format: 080326 = 08.03.26)
                data_date = vorstellung.get("data-date", "")
                if len(data_date) == 6:
                    day = int(data_date[0:2])
                    month = int(data_date[2:4])
                    year = 2000 + int(data_date[4:6])
                else:
                    continue

                # Uhrzeit
                time_elem = vorstellung.select_one("div.col-6, div.col-weekday ~ div")
                time_text = ""
                for div in vorstellung.select("div"):
                    text = div.get_text(strip=True)
                    if re.match(r"\d{1,2}\.\d{2}", text):
                        time_text = text
                        break

                if time_text:
                    time_match = re.match(r"(\d{1,2})\.(\d{2})", time_text)
                    if time_match:
                        hour = int(time_match.group(1))
                        minute = int(time_match.group(2))
                    else:
                        hour, minute = 19, 30
                else:
                    hour, minute = 19, 30

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Titel
                title_link = vorstellung.select_one("a.no-underline")
                title = title_link.get_text(strip=True) if title_link else ""
                if not title:
                    continue

                href = title_link.get("href", "") if title_link else ""
                event_link = f"https://www.schaubuehne.de/de/{href}" if href else "https://www.schaubuehne.de"

                # Beschreibung
                desc_elem = vorstellung.select_one("div.col-xl-7.fs-4")
                description = desc_elem.get_text(strip=True)[:200] if desc_elem else ""

                time_str = f"{hour:02d}:{minute:02d}"

                event_id = hashlib.md5(
                    f"schaubuehne-{title}-{event_date.strftime('%Y-%m-%d-%H%M')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": time_str,
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "charlottenburg-wilmersdorf",
                    "type": event_type,
                    "description": description,
                    "link": event_link,
                    "source": "schaubuehne",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Schaubühne] Fehler: {e}")

    print(f"[Schaubühne] {len(events)} Events geladen (Diskurs/Lesung/Premiere)")
    return events


def scrape_einstein_forum() -> list[dict]:
    """Scraped Events vom Einstein Forum Potsdam via iCal-Feed."""
    events = []
    venue_name = "Einstein Forum"
    venue_address = "Am Neuen Markt 7, 14467 Potsdam"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="potsdam",
        url="https://www.einsteinforum.de",
    )

    ical_url = "https://www.einsteinforum.de/programm/?feed=ical_feed_saison"
    now = datetime.now()

    try:
        resp = requests.get(
            ical_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        ical_text = resp.text

        # iCal Events parsen (VEVENT Blöcke)
        vevent_pattern = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.DOTALL)

        for match in vevent_pattern.finditer(ical_text):
            try:
                vevent = match.group(1)

                # DTSTART
                dtstart_match = re.search(r"DTSTART[^:]*:(\d{8}T?\d{0,6})", vevent)
                if not dtstart_match:
                    continue
                dtstart = dtstart_match.group(1)
                if len(dtstart) >= 8:
                    year = int(dtstart[0:4])
                    month = int(dtstart[4:6])
                    day = int(dtstart[6:8])
                    hour = int(dtstart[9:11]) if len(dtstart) > 8 else 19
                    minute = int(dtstart[11:13]) if len(dtstart) > 11 else 0
                    event_date = datetime(year, month, day, hour, minute)
                else:
                    continue

                if event_date.date() < now.date():
                    continue

                # SUMMARY
                summary_match = re.search(r"SUMMARY[^:]*:(.*?)(?:\r?\n[A-Z]|\r?\nEND)", vevent, re.DOTALL)
                title = summary_match.group(1).strip().replace("\r\n ", "").replace("\n ", "") if summary_match else ""
                if not title:
                    continue

                # DESCRIPTION
                desc_match = re.search(r"DESCRIPTION[^:]*:(.*?)(?:\r?\n[A-Z]|\r?\nEND)", vevent, re.DOTALL)
                description = desc_match.group(1).strip().replace("\r\n ", "").replace("\n ", "").replace("\\n", " ")[:300] if desc_match else ""

                # URL
                url_match = re.search(r"URL[^:]*:(.*?)(?:\r?\n|$)", vevent)
                event_link = url_match.group(1).strip() if url_match else "https://www.einsteinforum.de/programm/"

                # LOCATION
                loc_match = re.search(r"LOCATION[^:]*:(.*?)(?:\r?\n[A-Z]|\r?\nEND)", vevent)
                event_address = loc_match.group(1).strip().replace("\r\n ", "") if loc_match else venue_address

                time_str = f"{hour:02d}:{minute:02d}"

                event_id = hashlib.md5(
                    f"einstein-{title}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": time_str,
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": event_address,
                    "bezirk": "potsdam",
                    "type": "vortrag",
                    "description": description,
                    "link": event_link,
                    "source": "einstein-forum",
                })
            except Exception:
                continue

    except Exception as e:
        print(f"[Einstein] Fehler: {e}")

    print(f"[Einstein] {len(events)} Events geladen")
    return events


def scrape_mfk_berlin() -> list[dict]:
    """Scraped Events vom Museum für Kommunikation Berlin via JSON-LD."""
    events = []
    now = datetime.now()

    venue_name = "Museum für Kommunikation Berlin"
    venue_address = "Leipziger Straße 16, 10117 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://www.mfk-berlin.de",
    )

    # Filter für unerwünschte Events
    BLOCKED_PATTERNS = [
        "führung", "tour", "highlight-führung",
        "kinder", "familien", "kids",
        "workshop", "werkstatt",
    ]

    try:
        resp = requests.get(
            "https://www.mfk-berlin.de/?format=list",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        html = resp.text

        # JSON-LD Blöcke extrahieren
        soup = BeautifulSoup(html, "html.parser")
        json_ld_scripts = soup.find_all("script", type="application/ld+json")

        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                # Kann ein Array oder einzelnes Objekt sein
                if isinstance(data, list):
                    items = data
                else:
                    items = [data]

                for item in items:
                    if item.get("@type") != "Event":
                        continue

                    title = item.get("name", "")
                    if not title:
                        continue

                    # Filter anwenden
                    title_lower = title.lower()
                    if any(p in title_lower for p in BLOCKED_PATTERNS):
                        continue

                    # Datum parsen
                    start_date_str = item.get("startDate", "")
                    if not start_date_str:
                        continue

                    try:
                        # ISO-Format: 2026-03-01T15:00:00+01:00
                        event_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
                        # Konvertiere zu naive datetime
                        event_date = event_date.replace(tzinfo=None)
                    except ValueError:
                        continue

                    if event_date.date() < now.date():
                        continue

                    # Beschreibung (HTML-Tags entfernen)
                    description = item.get("description", "")
                    if description:
                        desc_soup = BeautifulSoup(description, "html.parser")
                        description = desc_soup.get_text(" ", strip=True)[:300]

                    # Link
                    event_link = item.get("url", "https://www.mfk-berlin.de/")

                    # Event-Typ
                    if "vortrag" in title_lower or "talk" in title_lower:
                        event_type = "vortrag"
                    elif "lesung" in title_lower:
                        event_type = "lesung"
                    elif "konzert" in title_lower:
                        event_type = "konzert"
                    elif "film" in title_lower:
                        event_type = "film"
                    elif "ausstellung" in title_lower:
                        event_type = "ausstellung"
                    else:
                        event_type = "vortrag"

                    time_str = event_date.strftime("%H:%M")

                    event_id = hashlib.md5(
                        f"mfk-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                    ).hexdigest()[:12]

                    events.append({
                        "id": event_id,
                        "title": title,
                        "date": event_date,
                        "time": time_str,
                        "venue_slug": venue_slug,
                        "venue_name": venue_name,
                        "venue_address": venue_address,
                        "bezirk": "mitte",
                        "type": event_type,
                        "description": description,
                        "link": event_link,
                        "source": "mfk-berlin",
                    })

            except (json.JSONDecodeError, Exception):
                continue

    except Exception as e:
        print(f"[MfK Berlin] Fehler: {e}")

    print(f"[MfK Berlin] {len(events)} Events geladen")
    return events


def scrape_co_berlin() -> list[dict]:
    """Scraped Events von C/O Berlin."""
    events = []
    now = datetime.now()

    venue_name = "C/O Berlin"
    venue_address = "Hardenbergstraße 22-24, 10623 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="charlottenburg-wilmersdorf",
        url="https://co-berlin.org",
    )

    # Filter: nur relevante Event-Typen
    WANTED_TYPES = ["artist talk", "gespräch", "vortrag", "lesung", "film", "diskussion", "symposium"]
    BLOCKED_PATTERNS = ["führung", "tour", "workshop", "kinder", "familien", "schüler"]

    try:
        resp = requests.get(
            "https://co-berlin.org/de/programm/kalender",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events aus der Kalender-Seite extrahieren
        event_links = soup.select("a[href*='/de/veranstaltungen/']")

        for link in event_links:
            try:
                href = link.get("href", "")
                if not href or "/de/veranstaltungen/" not in href:
                    continue

                # Titel aus dem Link-Text oder h3
                title_elem = link.find(["h2", "h3", "h4"]) or link
                title = title_elem.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                title_lower = title.lower()

                # Filter
                if any(p in title_lower for p in BLOCKED_PATTERNS):
                    continue

                # Datum finden (im Parent oder Geschwister)
                parent = link.parent
                if parent:
                    parent = parent.parent
                date_text = ""
                if parent:
                    date_elem = parent.find(string=re.compile(r"\d{1,2}\.\s*\w+\s*\d{4}|\d{1,2}\.\s*(Jan|Feb|Mär|Apr|Mai|Jun|Jul|Aug|Sep|Okt|Nov|Dez)", re.IGNORECASE))
                    if date_elem:
                        date_text = str(date_elem)

                if not date_text:
                    # Suche in der ganzen Link-Umgebung
                    container = link.find_parent(class_=re.compile(r"event|item|card", re.IGNORECASE))
                    if container:
                        text = container.get_text(" ", strip=True)
                        date_match = re.search(r"(\d{1,2})\.\s*(\w+)\s*(\d{4})?", text)
                        if date_match:
                            date_text = date_match.group(0)

                # Datum parsen
                event_date = None
                if date_text:
                    MONTHS = {
                        "jan": 1, "feb": 2, "mär": 3, "mar": 3, "apr": 4,
                        "mai": 5, "jun": 6, "jul": 7, "aug": 8,
                        "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12
                    }
                    match = re.search(r"(\d{1,2})\.\s*(\w{3,})\s*(\d{4})?", date_text, re.IGNORECASE)
                    if match:
                        day = int(match.group(1))
                        month_name = match.group(2).lower()[:3]
                        year = int(match.group(3)) if match.group(3) else now.year
                        month = MONTHS.get(month_name, 0)
                        if month > 0:
                            try:
                                event_date = datetime(year, month, day, 19, 0)
                            except ValueError:
                                pass

                if not event_date or event_date.date() < now.date():
                    continue

                # Event-Typ
                if "film" in title_lower or "screening" in title_lower:
                    event_type = "film"
                elif "talk" in title_lower or "gespräch" in title_lower:
                    event_type = "diskussion"
                elif "lesung" in title_lower:
                    event_type = "lesung"
                else:
                    event_type = "vortrag"

                event_link = f"https://co-berlin.org{href}" if href.startswith("/") else href

                # Fetch description from detail page
                description = ""
                try:
                    detail_resp = requests.get(
                        event_link,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                        timeout=10,
                    )
                    if detail_resp.status_code == 200:
                        detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                        # Subtitle field contains the best description
                        subtitle = detail_soup.select_one(".field--name-field-subtitle")
                        if subtitle:
                            description = subtitle.get_text(strip=True)[:300]
                except Exception:
                    pass

                event_id = hashlib.md5(
                    f"co-berlin-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": "19:00",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "charlottenburg-wilmersdorf",
                    "type": event_type,
                    "description": description,
                    "link": event_link,
                    "source": "co-berlin",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[C/O Berlin] Fehler: {e}")

    # Duplikate entfernen
    seen = set()
    unique_events = []
    for ev in events:
        key = f"{ev['title'][:30]}-{ev['date'].strftime('%Y-%m-%d')}"
        if key not in seen:
            seen.add(key)
            unique_events.append(ev)

    print(f"[C/O Berlin] {len(unique_events)} Events geladen")
    return unique_events


def scrape_technikmuseum() -> list[dict]:
    """Scraped Events vom Deutschen Technikmuseum Berlin."""
    events = []
    now = datetime.now()

    venue_name = "Deutsches Technikmuseum"
    venue_address = "Trebbiner Straße 9, 10963 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="friedrichshain-kreuzberg",
        url="https://technikmuseum.berlin",
    )

    # Filter
    BLOCKED_PATTERNS = [
        "führung", "tour",
        "kinder", "familien", "kids", "schüler",
        "workshop", "werkstatt",
    ]

    try:
        # Kalender-API probieren
        resp = requests.get(
            "https://technikmuseum.berlin/kalender/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Suche nach Event-Elementen
        event_items = soup.select(".event-item, .calendar-event, article.event, .veranstaltung")

        for item in event_items:
            try:
                title_elem = item.find(["h2", "h3", "h4", "a"])
                title = title_elem.get_text(strip=True) if title_elem else ""
                if not title:
                    continue

                title_lower = title.lower()
                if any(p in title_lower for p in BLOCKED_PATTERNS):
                    continue

                # Datum
                date_text = item.get_text(" ", strip=True)
                event_date = None
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_text)
                if date_match:
                    day = int(date_match.group(1))
                    month = int(date_match.group(2))
                    year = int(date_match.group(3))
                    try:
                        event_date = datetime(year, month, day, 19, 0)
                    except ValueError:
                        pass

                if not event_date or event_date.date() < now.date():
                    continue

                # Link
                link_elem = item.find("a", href=True)
                href = link_elem.get("href", "") if link_elem else ""
                event_link = f"https://technikmuseum.berlin{href}" if href.startswith("/") else (href or "https://technikmuseum.berlin/kalender/")

                event_id = hashlib.md5(
                    f"technikmuseum-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": "19:00",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "friedrichshain-kreuzberg",
                    "type": "vortrag",
                    "description": "",
                    "link": event_link,
                    "source": "technikmuseum",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Technikmuseum] Fehler: {e}")

    print(f"[Technikmuseum] {len(events)} Events geladen")
    return events


def scrape_gropius_bau() -> list[dict]:
    """Scraped Events vom Gropius Bau (Berliner Festspiele)."""
    events = []
    now = datetime.now()

    venue_name = "Gropius Bau"
    venue_address = "Niederkirchnerstraße 7, 10963 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="friedrichshain-kreuzberg",
        url="https://www.berlinerfestspiele.de/gropiusbau",
    )

    # Filter
    BLOCKED_PATTERNS = [
        "führung", "tour",
        "kinder", "familien", "kids", "schüler",
        "workshop",
    ]

    try:
        # Programm-Seite mit Filter auf Gropius Bau
        resp = requests.get(
            "https://www.berlinerfestspiele.de/de/gropiusbau/programm/kalender.html",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # JSON-LD oder Event-Elemente suchen
        json_ld = soup.find("script", type="application/ld+json")
        if json_ld:
            try:
                data = json.loads(json_ld.string)
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "Event":
                            title = item.get("name", "")
                            if not title:
                                continue
                            title_lower = title.lower()
                            if any(p in title_lower for p in BLOCKED_PATTERNS):
                                continue

                            start_date = item.get("startDate", "")
                            if start_date:
                                try:
                                    event_date = datetime.fromisoformat(start_date.replace("Z", "+00:00")).replace(tzinfo=None)
                                    if event_date.date() >= now.date():
                                        event_id = hashlib.md5(f"gropius-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()).hexdigest()[:12]
                                        events.append({
                                            "id": event_id,
                                            "title": title,
                                            "date": event_date,
                                            "time": event_date.strftime("%H:%M"),
                                            "venue_slug": venue_slug,
                                            "venue_name": venue_name,
                                            "venue_address": venue_address,
                                            "bezirk": "friedrichshain-kreuzberg",
                                            "type": "ausstellung",
                                            "description": item.get("description", "")[:300],
                                            "link": item.get("url", "https://www.berlinerfestspiele.de/gropiusbau"),
                                            "source": "gropius-bau",
                                        })
                                except ValueError:
                                    pass
            except json.JSONDecodeError:
                pass

        # Fallback: Event-Elemente parsen
        event_cards = soup.select(".event-card, .program-item, article.event")
        for card in event_cards:
            try:
                title_elem = card.find(["h2", "h3", "h4"])
                title = title_elem.get_text(strip=True) if title_elem else ""
                if not title:
                    continue

                title_lower = title.lower()
                if any(p in title_lower for p in BLOCKED_PATTERNS):
                    continue

                # Weitere Verarbeitung falls nötig
            except Exception:
                continue

    except Exception as e:
        print(f"[Gropius Bau] Fehler: {e}")

    print(f"[Gropius Bau] {len(events)} Events geladen")
    return events


def scrape_wannseekonferenz() -> list[dict]:
    """Scraped Events vom Haus der Wannsee-Konferenz."""
    events = []
    now = datetime.now()

    venue_name = "Haus der Wannsee-Konferenz"
    venue_address = "Am Großen Wannsee 56-58, 14109 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="steglitz-zehlendorf",
        url="https://www.ghwk.de",
    )

    MONTHS = {
        "januar": 1, "februar": 2, "märz": 3, "april": 4,
        "mai": 5, "juni": 6, "juli": 7, "august": 8,
        "september": 9, "oktober": 10, "november": 11, "dezember": 12
    }

    try:
        resp = requests.get(
            "https://www.ghwk.de/de/termine",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events in h4 > a Struktur
        event_links = soup.select("h4 a[href*='/de/termine/']")

        for link in event_links:
            try:
                title = link.get_text(strip=True)
                if not title:
                    continue

                href = link.get("href", "")
                event_link = f"https://www.ghwk.de{href}" if href.startswith("/") else href

                # Datum im nächsten p-Element
                parent = link.find_parent("h4")
                if not parent:
                    continue

                next_p = parent.find_next_sibling("p")
                if not next_p:
                    continue

                date_text = next_p.get_text(strip=True)
                # Format: "14. März 2026 · 13:00 Uhr - 14:30 Uhr"
                date_match = re.search(r"(\d{1,2})\.\s*(\w+)\s*(\d{4})\s*·?\s*(\d{1,2}):(\d{2})", date_text)
                if not date_match:
                    continue

                day = int(date_match.group(1))
                month_name = date_match.group(2).lower()
                year = int(date_match.group(3))
                hour = int(date_match.group(4))
                minute = int(date_match.group(5))

                month = MONTHS.get(month_name, 0)
                if month == 0:
                    continue

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Beschreibung
                desc_p = next_p.find_next_sibling("p")
                description = desc_p.get_text(strip=True)[:300] if desc_p else ""

                event_id = hashlib.md5(
                    f"wannsee-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "steglitz-zehlendorf",
                    "type": "vortrag",
                    "description": description,
                    "link": event_link,
                    "source": "wannseekonferenz",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Wannseekonferenz] Fehler: {e}")

    print(f"[Wannseekonferenz] {len(events)} Events geladen")
    return events


def scrape_bruecke_museum() -> list[dict]:
    """Scraped Events vom Brücke-Museum."""
    events = []
    now = datetime.now()

    venue_name = "Brücke-Museum"
    venue_address = "Bussardsteig 9, 14195 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="steglitz-zehlendorf",
        url="https://www.bruecke-museum.de",
    )

    MONTHS = {
        "januar": 1, "februar": 2, "märz": 3, "april": 4,
        "mai": 5, "juni": 6, "juli": 7, "august": 8,
        "september": 9, "oktober": 10, "november": 11, "dezember": 12
    }

    # Filter
    BLOCKED_PATTERNS = ["führung", "rundgang", "kinder", "familien", "workshop"]

    try:
        resp = requests.get(
            "https://www.bruecke-museum.de/de/programm/veranstaltungen",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Event-Titel sind verlinkt, Datum in Text darunter
        # Format: "15. März 2026, 12.00 Uhr"
        text = soup.get_text(" ", strip=True)

        # Alle Links zu Veranstaltungen
        event_links = soup.select("a[href*='/de/programm/veranstaltungen/']")

        for link in event_links:
            try:
                href = link.get("href", "")
                # Skip iCal and Google Calendar links
                if href.endswith(".ics") or href.endswith(".google"):
                    continue

                title = link.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                # Skip calendar link texts
                title_lower = title.lower()
                if title_lower in ("ical", "google calendar", "google\ncalendar"):
                    continue

                if any(p in title_lower for p in BLOCKED_PATTERNS):
                    continue
                event_link = f"https://www.bruecke-museum.de{href}" if href.startswith("/") else href

                # Datum im umgebenden Text suchen
                parent = link.find_parent()
                if parent:
                    parent = parent.find_parent()
                if not parent:
                    continue

                area_text = parent.get_text(" ", strip=True)
                date_match = re.search(r"(\d{1,2})\.\s*(\w+)\s*(\d{4}),?\s*(\d{1,2})[\.:]\s*(\d{2})\s*Uhr", area_text)
                if not date_match:
                    continue

                day = int(date_match.group(1))
                month_name = date_match.group(2).lower()
                year = int(date_match.group(3))
                hour = int(date_match.group(4))
                minute = int(date_match.group(5))

                month = MONTHS.get(month_name, 0)
                if month == 0:
                    continue

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Fetch description from detail page
                description = ""
                try:
                    detail_resp = requests.get(
                        event_link,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
                        timeout=10,
                    )
                    if detail_resp.status_code == 200:
                        detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                        for p in detail_soup.select("main p, article p, .content p"):
                            p_text = p.get_text(strip=True)
                            if len(p_text) > 50:
                                description = p_text[:300]
                                break
                except Exception:
                    pass

                event_id = hashlib.md5(
                    f"bruecke-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "steglitz-zehlendorf",
                    "type": "vortrag",
                    "description": description,
                    "link": event_link,
                    "source": "bruecke-museum",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Brücke-Museum] Fehler: {e}")

    # Duplikate entfernen
    seen = set()
    unique = []
    for ev in events:
        key = f"{ev['title'][:30]}-{ev['date'].strftime('%Y-%m-%d')}"
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    print(f"[Brücke-Museum] {len(unique)} Events geladen")
    return unique


def scrape_traenenpalast() -> list[dict]:
    """Scraped Events vom Tränenpalast (Stiftung Haus der Geschichte)."""
    events = []
    now = datetime.now()

    venue_name = "Tränenpalast"
    venue_address = "Reichstagufer 17, 10117 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://www.hdg.de/traenenpalast",
    )

    # Filter: keine Führungen
    BLOCKED_PATTERNS = ["führung", "ausstellungsbegleitung"]

    try:
        resp = requests.get(
            "https://www.hdg.de/traenenpalast/veranstaltungen",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events in h4 Elementen, Datum in strong
        event_titles = soup.select("h4")

        for title_elem in event_titles:
            try:
                title = title_elem.get_text(strip=True)
                if not title:
                    continue

                title_lower = title.lower()
                if any(p in title_lower for p in BLOCKED_PATTERNS):
                    continue

                # Typ aus h6 davor
                prev_h6 = title_elem.find_previous("h6")
                event_type_text = prev_h6.get_text(strip=True).lower() if prev_h6 else ""
                if any(p in event_type_text for p in BLOCKED_PATTERNS):
                    continue

                # Datum suchen in der Umgebung
                parent = title_elem.find_parent()
                if parent:
                    parent = parent.find_parent()

                event_date = None
                if parent:
                    strongs = parent.find_all("strong")
                    for strong in strongs:
                        text = strong.get_text(strip=True)
                        # Format: "21. März 2026" oder "15:00 Uhr"
                        date_match = re.search(r"(\d{1,2})\.\s*(\w+)\s*(\d{4})", text)
                        time_match = re.search(r"(\d{1,2}):(\d{2})", text)

                        if date_match:
                            MONTHS = {
                                "januar": 1, "februar": 2, "märz": 3, "april": 4,
                                "mai": 5, "juni": 6, "juli": 7, "august": 8,
                                "september": 9, "oktober": 10, "november": 11, "dezember": 12
                            }
                            day = int(date_match.group(1))
                            month_name = date_match.group(2).lower()
                            year = int(date_match.group(3))
                            month = MONTHS.get(month_name, 0)
                            if month > 0:
                                try:
                                    event_date = datetime(year, month, day, 15, 0)
                                except ValueError:
                                    pass

                        if time_match and event_date:
                            event_date = event_date.replace(
                                hour=int(time_match.group(1)),
                                minute=int(time_match.group(2))
                            )

                if not event_date or event_date.date() < now.date():
                    continue

                # Link
                link_elem = title_elem.find("a") or title_elem.find_next("a")
                href = link_elem.get("href", "") if link_elem else ""
                event_link = f"https://www.hdg.de{href}" if href.startswith("/") else (href or "https://www.hdg.de/traenenpalast/veranstaltungen")

                event_id = hashlib.md5(
                    f"traenenpalast-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": event_date.strftime("%H:%M"),
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "mitte",
                    "type": "vortrag",
                    "description": "",
                    "link": event_link,
                    "source": "traenenpalast",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Tränenpalast] Fehler: {e}")

    print(f"[Tränenpalast] {len(events)} Events geladen")
    return events


def scrape_haus_fuer_poesie() -> list[dict]:
    """Scraped Events vom Haus für Poesie."""
    events = []
    now = datetime.now()

    venue_name = "Haus für Poesie"
    venue_address = "Kulturbrauerei, Knaackstraße 97, 10435 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="pankow",
        url="https://www.hausfuerpoesie.org",
    )

    # Filter
    BLOCKED_PATTERNS = ["kinder", "jugend", "schüler"]

    try:
        resp = requests.get(
            "https://www.hausfuerpoesie.org/de/programm/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events auf der Programm-Seite
        event_items = soup.select("article, .event-item, .program-item")

        for item in event_items:
            try:
                title_elem = item.find(["h2", "h3", "h4"])
                title = title_elem.get_text(strip=True) if title_elem else ""
                if not title:
                    continue

                title_lower = title.lower()
                if any(p in title_lower for p in BLOCKED_PATTERNS):
                    continue

                # Datum: Format "24.3.2026 Di, 19:00"
                text = item.get_text(" ", strip=True)
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})[^,]*,?\s*(\d{1,2}):(\d{2})", text)
                if not date_match:
                    continue

                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3))
                hour = int(date_match.group(4))
                minute = int(date_match.group(5))

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Link
                link_elem = item.find("a", href=True)
                href = link_elem.get("href", "") if link_elem else ""
                event_link = f"https://www.hausfuerpoesie.org{href}" if href.startswith("/") else (href or "https://www.hausfuerpoesie.org/de/programm/")

                # Event-Typ
                if "lesung" in title_lower:
                    event_type = "lesung"
                elif "gespräch" in title_lower or "diskussion" in title_lower:
                    event_type = "diskussion"
                elif "workshop" in title_lower:
                    event_type = "workshop"
                else:
                    event_type = "lesung"

                event_id = hashlib.md5(
                    f"poesie-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "pankow",
                    "type": event_type,
                    "description": "",
                    "link": event_link,
                    "source": "haus-fuer-poesie",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Haus für Poesie] Fehler: {e}")

    print(f"[Haus für Poesie] {len(events)} Events geladen")
    return events


def scrape_panda_platforma() -> list[dict]:
    """Scraped Events von Panda Platforma."""
    events = []
    now = datetime.now()

    venue_name = "Panda Platforma"
    venue_address = "Knaackstraße 97, 10435 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="pankow",
        url="https://panda-platforma.berlin",
    )

    try:
        resp = requests.get(
            "https://panda-platforma.berlin/veranstaltungen-in-berlin/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events: Datum DD/MM/YY, Zeit HH:MM, Titel als Link
        event_links = soup.select("a[href*='/events/']")

        for link in event_links:
            try:
                title = link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                href = link.get("href", "")
                event_link = href if href.startswith("http") else f"https://panda-platforma.berlin{href}"

                # Datum/Zeit im Text davor
                prev = link.find_previous(string=True)
                if not prev:
                    continue

                # Suche nach DD/MM/YY und HH:MM
                parent_text = ""
                parent = link.find_parent()
                if parent:
                    parent_text = parent.get_text(" ", strip=True)

                date_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2})\s+(\d{1,2}):(\d{2})", parent_text)
                if not date_match:
                    continue

                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = 2000 + int(date_match.group(3))
                hour = int(date_match.group(4))
                minute = int(date_match.group(5))

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                event_id = hashlib.md5(
                    f"panda-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "pankow",
                    "type": "konzert",
                    "description": "",
                    "link": event_link,
                    "source": "panda-platforma",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Panda Platforma] Fehler: {e}")

    # Duplikate entfernen
    seen = set()
    unique = []
    for ev in events:
        key = f"{ev['title'][:30]}-{ev['date'].strftime('%Y-%m-%d')}"
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    print(f"[Panda Platforma] {len(unique)} Events geladen")
    return unique


def scrape_alte_kantine() -> list[dict]:
    """Scraped Events von Alte Kantine Wedding."""
    events = []
    now = datetime.now()

    venue_name = "Alte Kantine Wedding"
    venue_address = "Uferstraße 8-11, 13357 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://alte-kantine.eu",
    )

    try:
        resp = requests.get(
            "https://alte-kantine.eu/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events in h6 oder als Links
        event_items = soup.select("h6 a, .event-item a, article a")

        for link in event_items:
            try:
                title = link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                href = link.get("href", "")
                event_link = href if href.startswith("http") else f"https://alte-kantine.eu{href}"

                # Datum im umgebenden Text: DD.MM Format
                parent = link.find_parent()
                if parent:
                    parent = parent.find_parent()
                if not parent:
                    continue

                text = parent.get_text(" ", strip=True)

                # Format: "12.03" oder "12.03.2026"
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.?(\d{4})?", text)
                time_match = re.search(r"(\d{1,2}):(\d{2})\s*Uhr", text)

                if not date_match:
                    continue

                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3)) if date_match.group(3) else now.year
                if month < now.month and not date_match.group(3):
                    year += 1

                hour = int(time_match.group(1)) if time_match else 22
                minute = int(time_match.group(2)) if time_match else 0

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                event_id = hashlib.md5(
                    f"altekantine-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "mitte",
                    "type": "konzert",
                    "description": "",
                    "link": event_link,
                    "source": "alte-kantine",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Alte Kantine] Fehler: {e}")

    # Duplikate entfernen
    seen = set()
    unique = []
    for ev in events:
        key = f"{ev['title'][:30]}-{ev['date'].strftime('%Y-%m-%d')}"
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    print(f"[Alte Kantine] {len(unique)} Events geladen")
    return unique


def scrape_kesselhaus() -> list[dict]:
    """Scraped Events vom Kesselhaus (ohne Konzert, Theater, Party)."""
    events = []
    now = datetime.now()

    venue_name = "Kesselhaus"
    venue_address = "Knaackstraße 97, 10435 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="pankow",
        url="https://www.kesselhaus.net",
    )

    # Nur bestimmte Kategorien
    BLOCKED_CATEGORIES = ["konzert", "party", "theater", "tanz", "comedy"]

    try:
        resp = requests.get(
            "https://www.kesselhaus.net/de/calendar",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events in der Angular-App - versuche Textextraktion
        text = soup.get_text(" ", strip=True)

        # Events aus Links extrahieren
        event_links = soup.select("a[href*='/de/calendar/']")

        for link in event_links:
            try:
                title = link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                # Kategorie prüfen
                title_lower = title.lower()
                parent = link.find_parent()
                parent_text = parent.get_text(" ", strip=True).lower() if parent else ""

                if any(cat in title_lower or cat in parent_text for cat in BLOCKED_CATEGORIES):
                    continue

                href = link.get("href", "")
                event_link = f"https://www.kesselhaus.net{href}" if href.startswith("/") else href

                # Datum aus dem umgebenden Text
                if parent:
                    parent = parent.find_parent()
                if not parent:
                    continue

                area_text = parent.get_text(" ", strip=True)

                # Verschiedene Datumsformate versuchen
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", area_text)
                if not date_match:
                    date_match = re.search(r"(\d{1,2})\.\s*(\w{3,})", area_text)

                if not date_match:
                    continue

                if len(date_match.groups()) >= 3:
                    day = int(date_match.group(1))
                    month = int(date_match.group(2))
                    year = int(date_match.group(3))
                else:
                    continue

                try:
                    event_date = datetime(year, month, day, 20, 0)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                event_id = hashlib.md5(
                    f"kesselhaus-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": "20:00",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "pankow",
                    "type": "vortrag",
                    "description": "",
                    "link": event_link,
                    "source": "kesselhaus",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Kesselhaus] Fehler: {e}")

    print(f"[Kesselhaus] {len(events)} Events geladen")
    return events


def scrape_frannz() -> list[dict]:
    """Scraped Events vom Frannz Club."""
    events = []
    now = datetime.now()

    venue_name = "Frannz Club"
    venue_address = "Schönhauser Allee 36, 10435 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="pankow",
        url="https://frannz.eu",
    )

    MONTHS = {
        "januar": 1, "februar": 2, "märz": 3, "april": 4,
        "mai": 5, "juni": 6, "juli": 7, "august": 8,
        "september": 9, "oktober": 10, "november": 11, "dezember": 12,
        "jan": 1, "feb": 2, "mär": 3, "apr": 4, "mai": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dez": 12
    }

    # Filter - nur Lesungen/Kulturelles, keine reinen Partys
    WANTED_TYPES = ["lesung", "reading", "literatur", "gespräch", "vortrag", "theater", "show"]

    try:
        resp = requests.get(
            "https://frannz.eu/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events in der Seite finden
        # Struktur: Datum-Header, dann Event-Details
        text = soup.get_text("\n", strip=True)

        # Suche nach Event-Blöcken mit Datum
        event_links = soup.select("a[href*='frannz.eu']")

        for link in event_links:
            try:
                href = link.get("href", "")
                title = link.get_text(strip=True)

                if not title or len(title) < 5:
                    continue

                # Nur kulturelle Events
                title_lower = title.lower()
                parent = link.find_parent()
                parent_text = parent.get_text(" ", strip=True).lower() if parent else ""

                is_cultural = any(t in title_lower or t in parent_text for t in WANTED_TYPES)
                if not is_cultural:
                    continue

                # Datum suchen
                if parent:
                    parent = parent.find_parent()
                if not parent:
                    continue

                area_text = parent.get_text(" ", strip=True)

                # Format: "Donnerstag, 12. März 2026" oder "12.03.2026"
                date_match = re.search(r"(\d{1,2})\.?\s*(\w+)\s*(\d{4})", area_text)
                if not date_match:
                    date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", area_text)

                if not date_match:
                    continue

                day = int(date_match.group(1))
                month_str = date_match.group(2)
                year = int(date_match.group(3))

                if month_str.isdigit():
                    month = int(month_str)
                else:
                    month = MONTHS.get(month_str.lower()[:3], 0)
                    if month == 0:
                        continue

                # Zeit suchen
                time_match = re.search(r"Beginn[:\s]*(\d{1,2}):(\d{2})", area_text)
                if not time_match:
                    time_match = re.search(r"(\d{1,2}):(\d{2})", area_text)

                hour = int(time_match.group(1)) if time_match else 20
                minute = int(time_match.group(2)) if time_match else 0

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                event_link = href if href.startswith("http") else f"https://frannz.eu{href}"

                event_id = hashlib.md5(
                    f"frannz-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "pankow",
                    "type": "lesung",
                    "description": "",
                    "link": event_link,
                    "source": "frannz",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Frannz] Fehler: {e}")

    # Duplikate entfernen
    seen = set()
    unique = []
    for ev in events:
        key = f"{ev['title'][:30]}-{ev['date'].strftime('%Y-%m-%d')}"
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    print(f"[Frannz] {len(unique)} Events geladen")
    return unique


def scrape_rambazamba() -> list[dict]:
    """Scraped Premieren vom RambaZamba Theater."""
    events = []
    now = datetime.now()

    venue_name = "RambaZamba Theater"
    venue_address = "Schönhauser Allee 36, 10435 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="pankow",
        url="https://www.rambazamba-theater.de",
    )

    MONTHS = {
        "januar": 1, "februar": 2, "märz": 3, "april": 4,
        "mai": 5, "juni": 6, "juli": 7, "august": 8,
        "september": 9, "oktober": 10, "november": 11, "dezember": 12,
        "jan": 1, "feb": 2, "mär": 3, "apr": 4, "mai": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dez": 12
    }

    try:
        resp = requests.get(
            "https://www.rambazamba-theater.de/de/premieren",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Premieren als Links mit Datum "Premiere am:"
        premiere_links = soup.select("a[href*='/de/spielzeiten/']")

        for link in premiere_links:
            try:
                title = link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                href = link.get("href", "")
                event_link = f"https://www.rambazamba-theater.de{href}" if href.startswith("/") else href

                # Datum suchen in "Premiere am: Mi 29.04.26"
                parent = link.find_parent()
                if parent:
                    parent = parent.find_parent()
                if not parent:
                    continue

                area_text = parent.get_text(" ", strip=True)

                # Format: "Premiere am: Mi 29.04.26" oder "Premiere am: Do 05.06.2026"
                date_match = re.search(r"Premiere\s+am[:\s]*\w+\s+(\d{1,2})\.(\d{1,2})\.(\d{2,4})", area_text)
                if not date_match:
                    continue

                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year_str = date_match.group(3)
                year = int(year_str) if len(year_str) == 4 else 2000 + int(year_str)

                try:
                    event_date = datetime(year, month, day, 19, 30)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Regie und Autor extrahieren
                regie_match = re.search(r"Regie:\s*([^\n]+)", area_text)
                autor_match = re.search(r"Von:\s*([^\n]+)", area_text)

                description = ""
                if autor_match:
                    description += f"Von: {autor_match.group(1).strip()}"
                if regie_match:
                    if description:
                        description += " | "
                    description += f"Regie: {regie_match.group(1).strip()}"

                event_id = hashlib.md5(
                    f"rambazamba-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": f"Premiere: {title}",
                    "date": event_date,
                    "time": "19:30",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "pankow",
                    "type": "theater",
                    "description": description[:300],
                    "link": event_link,
                    "source": "rambazamba",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[RambaZamba] Fehler: {e}")

    print(f"[RambaZamba] {len(events)} Events geladen")
    return events


def scrape_bbooks() -> list[dict]:
    """Scraped Events von b_books."""
    events = []
    now = datetime.now()

    venue_name = "b_books"
    venue_address = "Lübbener Straße 14, 10997 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="friedrichshain-kreuzberg",
        url="https://www.bbooks.de",
    )

    MONTHS = {
        "januar": 1, "february": 2, "februar": 2, "march": 3, "märz": 3,
        "april": 4, "may": 5, "mai": 5, "june": 6, "juni": 6,
        "july": 7, "juli": 7, "august": 8, "september": 9,
        "october": 10, "oktober": 10, "november": 11, "december": 12, "dezember": 12
    }

    try:
        resp = requests.get(
            "https://www.bbooks.de/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # montagsPRAXIS Events - Datumsformat: "Wednesday, March 4, 2026"
        text = soup.get_text(" ", strip=True)

        # Suche nach Events mit Datum
        event_links = soup.select("a[href*='montagspraxis'], a[href*='unterproduktionen']")

        for link in event_links:
            try:
                title = link.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                href = link.get("href", "")
                event_link = f"https://www.bbooks.de{href}" if href.startswith("/") else href

                # Datum im umgebenden Text
                parent = link.find_parent()
                if parent:
                    parent = parent.find_parent()
                if not parent:
                    continue

                area_text = parent.get_text(" ", strip=True)

                # Format: "Wednesday, March 4, 2026" oder "Mittwoch, 4. März 2026"
                date_match = re.search(r"(\w+day),?\s*(\w+)\s+(\d{1,2}),?\s*(\d{4})", area_text, re.IGNORECASE)
                if not date_match:
                    date_match = re.search(r"(\d{1,2})\.?\s*(\w+)\s*(\d{4})", area_text)

                if not date_match:
                    continue

                if len(date_match.groups()) == 4:
                    month_name = date_match.group(2).lower()
                    day = int(date_match.group(3))
                    year = int(date_match.group(4))
                else:
                    day = int(date_match.group(1))
                    month_name = date_match.group(2).lower()
                    year = int(date_match.group(3))

                month = MONTHS.get(month_name, 0)
                if month == 0:
                    continue

                # Zeit suchen
                time_match = re.search(r"(\d{1,2}):(\d{2})\s*(pm|am)?", area_text, re.IGNORECASE)
                hour = 19
                minute = 0
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2))
                    if time_match.group(3) and time_match.group(3).lower() == "pm" and hour < 12:
                        hour += 12

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                event_id = hashlib.md5(
                    f"bbooks-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "friedrichshain-kreuzberg",
                    "type": "diskussion",
                    "description": "",
                    "link": event_link,
                    "source": "bbooks",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[b_books] Fehler: {e}")

    print(f"[b_books] {len(events)} Events geladen")
    return events


def scrape_pro_qm() -> list[dict]:
    """Scraped Events von pro qm.

    Website nutzt .event__listitem mit h2.event__title und .event__subtitle.
    Datum kommt aus <time datetime="..."> im .event__date.
    """
    events = []
    now = datetime.now()

    venue_name = "pro qm"
    venue_address = "Almstadtstraße 48-50, 10119 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://pro-qm.de",
    )

    try:
        resp = requests.get(
            "https://pro-qm.de/events",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events in .event__listitem Elementen
        event_items = soup.select(".event__listitem")

        for item in event_items:
            try:
                # Überspringe vergangene Events
                if "date-ago" in item.get("class", []):
                    continue

                # Datum aus time-Element
                time_elem = item.select_one(".event__date time")
                if not time_elem:
                    continue

                dt_attr = time_elem.get("datetime", "")
                if not dt_attr:
                    continue

                try:
                    event_date = dateparser.parse(dt_attr)
                    if not event_date:
                        continue
                except Exception:
                    continue

                if event_date.date() < now.date():
                    continue

                # Titel aus h2.event__title a
                title_elem = item.select_one(".event__title a")
                title = title_elem.get_text(strip=True) if title_elem else ""

                if not title or len(title) < 5:
                    continue

                # Link
                href = title_elem.get("href", "") if title_elem else ""
                event_link = f"https://pro-qm.de{href}" if href.startswith("/") else (href or "https://pro-qm.de/events")

                # Beschreibung aus .event__subtitle
                desc_elem = item.select_one(".event__subtitle")
                description = desc_elem.get_text(strip=True)[:300] if desc_elem else ""

                event_id = hashlib.md5(
                    f"proqm-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": event_date.strftime("%H:%M"),
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "mitte",
                    "type": "lesung",
                    "description": description,
                    "link": event_link,
                    "source": "pro-qm",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[pro qm] Fehler: {e}")

    print(f"[pro qm] {len(events)} Events geladen")
    return events


def scrape_august_bebel() -> list[dict]:
    """Scraped Events vom August Bebel Institut."""
    events = []
    now = datetime.now()

    venue_name = "August Bebel Institut"
    venue_address = "Müllerstraße 163, 13353 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://august-bebel-institut.de",
    )

    MONTHS = {
        "januar": 1, "februar": 2, "märz": 3, "april": 4,
        "mai": 5, "juni": 6, "juli": 7, "august": 8,
        "september": 9, "oktober": 10, "november": 11, "dezember": 12
    }

    try:
        resp = requests.get(
            "https://august-bebel-institut.de/events/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events in Karten-Format
        event_cards = soup.select("article, .event-card, .tribe-events-calendar-list__event")

        for card in event_cards:
            try:
                # Titel
                title_elem = card.find(["h2", "h3", "h4"])
                title = title_elem.get_text(strip=True) if title_elem else ""
                if not title or len(title) < 5:
                    continue

                # Datum: "Sa. 21. März 2026" oder "11:30 – 13:30 Uhr"
                text = card.get_text(" ", strip=True)
                date_match = re.search(r"(\d{1,2})\.?\s*(\w+)\s*(\d{4})", text)
                if not date_match:
                    continue

                day = int(date_match.group(1))
                month_name = date_match.group(2).lower()
                year = int(date_match.group(3))

                month = MONTHS.get(month_name, 0)
                if month == 0:
                    continue

                # Zeit
                time_match = re.search(r"(\d{1,2}):(\d{2})\s*(?:–|Uhr)", text)
                hour = int(time_match.group(1)) if time_match else 18
                minute = int(time_match.group(2)) if time_match else 0

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Link
                link_elem = card.find("a", href=True)
                href = link_elem.get("href", "") if link_elem else ""
                event_link = href if href.startswith("http") else f"https://august-bebel-institut.de{href}"

                event_id = hashlib.md5(
                    f"bebel-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "mitte",
                    "type": "workshop",
                    "description": "",
                    "link": event_link,
                    "source": "august-bebel",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[August Bebel] Fehler: {e}")

    # Duplikate entfernen
    seen = set()
    unique = []
    for ev in events:
        key = f"{ev['title'][:30]}-{ev['date'].strftime('%Y-%m-%d')}"
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    print(f"[August Bebel] {len(unique)} Events geladen")
    return unique


def scrape_ffbiz() -> list[dict]:
    """Scraped Events vom FFBIZ (Frauenforschungs-, -bildungs- und -informationszentrum)."""
    events = []
    now = datetime.now()

    venue_name = "FFBIZ"
    venue_address = "Eldenaer Straße 35, 10247 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="friedrichshain-kreuzberg",
        url="https://www.ffbiz.de",
    )

    MONTHS = {
        "januar": 1, "februar": 2, "märz": 3, "april": 4,
        "mai": 5, "juni": 6, "juli": 7, "august": 8,
        "september": 9, "oktober": 10, "november": 11, "dezember": 12
    }

    try:
        resp = requests.get(
            "https://www.ffbiz.de/aktivitaeten/veranstaltungen",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events in article.event
        event_articles = soup.select("article.event, li.event, .event")

        for article in event_articles:
            try:
                # Titel
                title_elem = article.find(["h2", "h3"])
                title = title_elem.get_text(strip=True) if title_elem else ""
                if not title or len(title) < 5:
                    continue

                # Datum/Zeit in span.time
                time_elem = article.find("span", class_="time")
                text = time_elem.get_text(" ", strip=True) if time_elem else article.get_text(" ", strip=True)

                date_match = re.search(r"(\d{1,2})\.?\s*(\w+)\s*(\d{4})", text)
                if not date_match:
                    continue

                day = int(date_match.group(1))
                month_name = date_match.group(2).lower()
                year = int(date_match.group(3))

                month = MONTHS.get(month_name, 0)
                if month == 0:
                    continue

                time_match = re.search(r"(\d{1,2}):(\d{2})", text)
                hour = int(time_match.group(1)) if time_match else 18
                minute = int(time_match.group(2)) if time_match else 0

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Link
                link_elem = article.find("a", href=True)
                href = link_elem.get("href", "") if link_elem else ""
                event_link = f"https://www.ffbiz.de{href}" if href.startswith("/") else (href or "https://www.ffbiz.de/aktivitaeten/veranstaltungen")

                event_id = hashlib.md5(
                    f"ffbiz-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "friedrichshain-kreuzberg",
                    "type": "workshop",
                    "description": "",
                    "link": event_link,
                    "source": "ffbiz",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[FFBIZ] Fehler: {e}")

    print(f"[FFBIZ] {len(events)} Events geladen")
    return events


def scrape_zabriskie() -> list[dict]:
    """Scraped Events von Zabriskie Buchladen."""
    events = []
    now = datetime.now()

    venue_name = "Zabriskie"
    venue_address = "Reichenberger Str. 150, 10999 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="friedrichshain-kreuzberg",
        url="https://zabriskie.de",
    )

    MONTHS = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }

    try:
        # Die Events sind auf der Hauptseite im Veranstaltungen-Abschnitt
        resp = requests.get(
            "https://zabriskie.de",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Finde die Veranstaltungen-Sektion
        veranstaltungen_section = None
        for section in soup.find_all("section"):
            h2 = section.find("h2")
            if h2 and "Veranstaltungen" in h2.get_text():
                veranstaltungen_section = section
                break

        if not veranstaltungen_section:
            print("[Zabriskie] Veranstaltungen-Sektion nicht gefunden")
            return events

        # Event-Karten sind .article-card-wrapper
        cards = veranstaltungen_section.select(".article-card-wrapper")
        seen_titles = set()

        for card in cards:
            try:
                # Titel
                title_elem = card.find(["h2", "h3"])
                title = title_elem.get_text(strip=True) if title_elem else ""
                if not title or len(title) < 5:
                    continue

                # Deduplizieren
                if title in seen_titles:
                    continue
                seen_titles.add(title)

                # Datum: "START →Sat, Mar 14, 2026 at 7:00 PM"
                text = card.get_text(" ", strip=True)

                # Überspringe beendete Events
                if "Event finished" in text or "finished" in text.lower():
                    continue

                date_match = re.search(r"(\w{3}),?\s*(\w{3})\s*(\d{1,2}),?\s*(\d{4})\s*at\s*(\d{1,2}):(\d{2})\s*(PM|AM)?", text, re.IGNORECASE)
                if not date_match:
                    continue

                month_name = date_match.group(2).lower()
                day = int(date_match.group(3))
                year = int(date_match.group(4))
                hour = int(date_match.group(5))
                minute = int(date_match.group(6))
                ampm = date_match.group(7)

                month = MONTHS.get(month_name, 0)
                if month == 0:
                    continue

                if ampm and ampm.upper() == "PM" and hour < 12:
                    hour += 12

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Link
                link_elem = card.find("a", href=True)
                href = link_elem.get("href", "") if link_elem else ""
                event_link = f"https://zabriskie.de{href}" if href.startswith("/") else (href or "https://zabriskie.de")

                # Beschreibung aus .article-card__excerpt
                description = ""
                excerpt_elem = card.select_one(".article-card__excerpt")
                if excerpt_elem:
                    description = excerpt_elem.get_text(strip=True)[:300]

                event_id = hashlib.md5(
                    f"zabriskie-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "friedrichshain-kreuzberg",
                    "type": "lesung",
                    "description": description,
                    "link": event_link,
                    "source": "zabriskie",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Zabriskie] Fehler: {e}")

    print(f"[Zabriskie] {len(events)} Events geladen")
    return events


def scrape_buchbox() -> list[dict]:
    """Scraped Events von Buchbox Berlin."""
    events = []
    now = datetime.now()

    venue_name = "Buchbox"
    venue_address = "Wörther Straße 16, 10405 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="pankow",
        url="https://www.buchboxberlin.de",
    )

    try:
        resp = requests.get(
            "https://www.buchboxberlin.de/veranstaltungen",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events mit Datum "12.03.2026 | 20:00 Uhr"
        event_cards = soup.select(".veranstaltungbuchbox.overview")

        for card in event_cards:
            try:
                text = card.get_text(" ", strip=True)

                # Datum und Zeit
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s*\|?\s*(\d{1,2}):(\d{2})", text)
                if not date_match:
                    continue

                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3))
                hour = int(date_match.group(4))
                minute = int(date_match.group(5))

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Titel
                title_elem = card.find(["h2", "h3", "h4"])
                if not title_elem:
                    link_elem = card.find("a")
                    title = link_elem.get_text(strip=True) if link_elem else ""
                else:
                    title = title_elem.get_text(strip=True)

                if not title or len(title) < 5:
                    continue

                # Link
                link_elem = card.find("a", href=True)
                href = link_elem.get("href", "") if link_elem else ""
                event_link = f"https://www.buchboxberlin.de{href}" if href.startswith("/") else (href or "https://www.buchboxberlin.de/veranstaltungen")

                # Beschreibung aus .text.js-ellipsis
                description = ""
                desc_elem = card.select_one(".text.js-ellipsis")
                if desc_elem:
                    description = desc_elem.get_text(strip=True)[:300]

                event_id = hashlib.md5(
                    f"buchbox-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "pankow",
                    "type": "lesung",
                    "description": description,
                    "link": event_link,
                    "source": "buchbox",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Buchbox] Fehler: {e}")

    print(f"[Buchbox] {len(events)} Events geladen")
    return events


def scrape_geistesblueten() -> list[dict]:
    """Scraped Events von Geistesblüten Buchhandlung."""
    events = []
    now = datetime.now()

    venue_name = "Geistesblüten"
    venue_address = "Mommsensstraße 45, 10629 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="charlottenburg-wilmersdorf",
        url="https://geistesblueten.com",
    )

    DAYS = {"montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3, "freitag": 4, "samstag": 5, "sonntag": 6}

    try:
        resp = requests.get(
            "https://geistesblueten.com/events/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events mit Datum "Donnerstag, 12.03.2026" und Zeit "19:00"
        event_cards = soup.select("article, .event, .veranstaltung, div")

        for card in event_cards:
            try:
                text = card.get_text(" ", strip=True)

                # Datum: "Donnerstag, 12.03.2026" oder "12.03.2026"
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
                if not date_match:
                    continue

                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3))

                # Zeit
                time_match = re.search(r"(\d{1,2}):(\d{2})", text)
                hour = int(time_match.group(1)) if time_match else 19
                minute = int(time_match.group(2)) if time_match else 0

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Titel - suche nach Autorname und Buchtitel
                title_elem = card.find(["h2", "h3", "h4"])
                title = title_elem.get_text(strip=True) if title_elem else ""

                if not title or len(title) < 5:
                    continue

                # Link
                link_elem = card.find("a", href=True)
                href = link_elem.get("href", "") if link_elem else ""
                event_link = href if href.startswith("http") else f"https://geistesblueten.com{href}"

                event_id = hashlib.md5(
                    f"geistesblueten-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "charlottenburg-wilmersdorf",
                    "type": "lesung",
                    "description": "",
                    "link": event_link,
                    "source": "geistesblueten",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Geistesblüten] Fehler: {e}")

    # Duplikate entfernen
    seen = set()
    unique = []
    for ev in events:
        key = f"{ev['title'][:30]}-{ev['date'].strftime('%Y-%m-%d')}"
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    print(f"[Geistesblüten] {len(unique)} Events geladen")
    return unique


def scrape_nicolaische() -> list[dict]:
    """Scraped Events von Nicolaische Buchhandlung."""
    events = []
    now = datetime.now()

    venue_name = "Nicolaische Buchhandlung"
    venue_address = "Rheinstraße 65, 12159 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="tempelhof-schoeneberg",
        url="https://nicolaische-buchhandlung.buchhandlung.de",
    )

    try:
        resp = requests.get(
            "https://nicolaische-buchhandlung.buchhandlung.de/shop/magazine/131407/veranstaltungen.html",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # JSON-Daten oder Event-Module
        event_modules = soup.select(".event, .mod_event_teaser_single, article")

        for module in event_modules:
            try:
                text = module.get_text(" ", strip=True)

                # Datum: ISO oder deutsches Format
                date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
                if not date_match:
                    date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
                    if date_match:
                        day = int(date_match.group(1))
                        month = int(date_match.group(2))
                        year = int(date_match.group(3))
                    else:
                        continue
                else:
                    year = int(date_match.group(1))
                    month = int(date_match.group(2))
                    day = int(date_match.group(3))

                # Zeit
                time_match = re.search(r"(\d{1,2}):(\d{2})\s*Uhr", text)
                hour = int(time_match.group(1)) if time_match else 19
                minute = int(time_match.group(2)) if time_match else 30

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Titel
                title_elem = module.find(["h2", "h3", "h4"])
                title = title_elem.get_text(strip=True) if title_elem else ""
                if not title or len(title) < 5:
                    continue

                # Link
                link_elem = module.find("a", href=True)
                href = link_elem.get("href", "") if link_elem else ""
                event_link = href if href.startswith("http") else f"https://nicolaische-buchhandlung.buchhandlung.de{href}"

                event_id = hashlib.md5(
                    f"nicolaische-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "tempelhof-schoeneberg",
                    "type": "lesung",
                    "description": "",
                    "link": event_link,
                    "source": "nicolaische",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Nicolaische] Fehler: {e}")

    print(f"[Nicolaische] {len(events)} Events geladen")
    return events


def scrape_ocelot() -> list[dict]:
    """Scraped Events von Ocelot Buchhandlung."""
    events = []
    now = datetime.now()

    venue_name = "Ocelot"
    venue_address = "Brunnenstraße 181, 10119 Berlin"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse=venue_address,
        bezirk="mitte",
        url="https://www.genialokal.de/buchhandlung/berlin/ocelot/",
    )

    try:
        resp = requests.get(
            "https://www.genialokal.de/buchhandlung/berlin/ocelot/Veranstaltungen/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events mit Datum "14.03.2026 19:30 Uhr"
        # Einzelne Events sind in .row innerhalb von .retailerEvent
        event_sections = soup.select(".retailerEvent .col-12.col-md-10")

        for section in event_sections:
            try:
                text = section.get_text(" ", strip=True)

                # Datum und Zeit
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})", text)
                if not date_match:
                    continue

                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3))
                hour = int(date_match.group(4))
                minute = int(date_match.group(5))

                try:
                    event_date = datetime(year, month, day, hour, minute)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Titel
                title_elem = section.find(["h2", "h3", "h4"])
                title = title_elem.get_text(strip=True) if title_elem else ""
                if not title or len(title) < 5:
                    # Versuche ersten starken Text
                    strong = section.find("strong")
                    title = strong.get_text(strip=True) if strong else ""

                if not title or len(title) < 5:
                    continue

                # Link
                link_elem = section.find("a", href=True)
                href = link_elem.get("href", "") if link_elem else ""
                event_link = href if href.startswith("http") else f"https://www.genialokal.de{href}"

                event_id = hashlib.md5(
                    f"ocelot-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": f"{hour:02d}:{minute:02d}",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": "mitte",
                    "type": "lesung",
                    "description": "",
                    "link": event_link,
                    "source": "ocelot",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Ocelot] Fehler: {e}")

    # Duplikate entfernen
    seen = set()
    unique = []
    for ev in events:
        key = f"{ev['title'][:30]}-{ev['date'].strftime('%Y-%m-%d')}"
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    print(f"[Ocelot] {len(unique)} Events geladen")
    return unique


def scrape_motto_berlin() -> list[dict]:
    """Scraped Events von Motto Berlin."""
    events = []
    now = datetime.now()

    # Motto hat mehrere Standorte
    venues = {
        "motto xberg": ("Motto Berlin Kreuzberg", "Skalitzer Straße 68, 10997 Berlin", "friedrichshain-kreuzberg"),
        "motto berlin": ("Motto Berlin", "Skalitzer Straße 68, 10997 Berlin", "friedrichshain-kreuzberg"),
        "motto wedding": ("Motto Berlin Wedding", "Gerichtstraße 35, 13347 Berlin", "mitte"),
    }

    default_venue = venues["motto berlin"]

    try:
        resp = requests.get(
            "https://www.mottodistribution.com/site/?page_id=31943",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Events: "29.03.2026: Artist @ Venue"
        text = soup.get_text("\n", strip=True)
        lines = text.split("\n")

        for line in lines:
            try:
                # Format: "29.03.2026: Name @ Motto Xberg"
                match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4}):\s*(.+?)(?:\s*@\s*(.+))?$", line)
                if not match:
                    continue

                day = int(match.group(1))
                month = int(match.group(2))
                year = int(match.group(3))
                title = match.group(4).strip()
                location = match.group(5).strip().lower() if match.group(5) else "motto berlin"

                if not title or len(title) < 3:
                    continue

                # Nur Berlin-Veranstaltungen
                if "paris" in location:
                    continue

                try:
                    event_date = datetime(year, month, day, 20, 0)
                except ValueError:
                    continue

                if event_date.date() < now.date():
                    continue

                # Venue bestimmen
                venue_info = default_venue
                for key, info in venues.items():
                    if key in location:
                        venue_info = info
                        break

                venue_name, venue_address, bezirk = venue_info
                venue_slug = get_or_create_venue(
                    name=venue_name,
                    adresse=venue_address,
                    bezirk=bezirk,
                    url="https://www.mottodistribution.com",
                )

                event_id = hashlib.md5(
                    f"motto-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": "20:00",
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": bezirk,
                    "type": "konzert",
                    "description": "",
                    "link": "https://www.mottodistribution.com/site/?page_id=31943",
                    "source": "motto-berlin",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Motto Berlin] Fehler: {e}")

    print(f"[Motto Berlin] {len(events)} Events geladen")
    return events


def scrape_criticaltheory() -> list[dict]:
    """Scraped Events von Critical Theory Berlin (KTB)."""
    events = []
    now = datetime.now()

    # Month name mapping for English and German date format
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "januar": 1, "februar": 2, "märz": 3, "april": 4, "mai": 5,
        "juni": 6, "juli": 7, "august": 8, "september": 9,
        "oktober": 10, "november": 11, "dezember": 12,
    }

    try:
        resp = requests.get(
            "https://criticaltheoryinberlin.de/events/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Each event is in a .box_events_expanded_wrapper
        event_boxes = soup.select(".box_events_expanded_wrapper")

        for box in event_boxes:
            try:
                # Title from h2 > a
                title_link = box.select_one("h2 a.event_snippet_heading_a")
                if not title_link:
                    continue
                title = title_link.get_text(strip=True)
                if not title:
                    continue
                event_link = title_link.get("href", "")

                # Details from ul.event_datails_in_box li
                details = box.select("ul.event_datails_in_box li span")

                date_text = ""
                time_text = ""
                location = ""

                for detail in details:
                    text = detail.get_text(strip=True)
                    if not text:
                        continue

                    # Check for date pattern: "April 17, 2026" or "4.-5. Juni 2026" or "März 10, 2026"
                    # English format: Month DD, YYYY
                    date_match_en = re.search(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", text)
                    # German format: DD.-DD. Month YYYY or DD. Month YYYY
                    date_match_de = re.search(r"(\d{1,2})(?:\.-\d{1,2})?\.?\s+(\w+)\s+(\d{4})", text)
                    if date_match_en or date_match_de:
                        date_text = text
                        continue

                    # Check for time pattern: "18:00 » 20:00" or just "18:00"
                    time_match = re.search(r"(\d{1,2}):(\d{2})", text)
                    if time_match and ("»" in text or re.match(r"^\d{1,2}:\d{2}", text)):
                        time_text = text
                        continue

                    # Otherwise it's likely the location
                    if not location and len(text) > 3:
                        location = text

                # Parse date
                event_date = None
                if date_text:
                    # Try English format first: "April 17, 2026" or "März 10, 2026"
                    date_match_en = re.search(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", date_text)
                    # German format: "4.-5. Juni 2026" or "10. März 2026"
                    date_match_de = re.search(r"(\d{1,2})(?:\.-\d{1,2})?\.?\s+(\w+)\s+(\d{4})", date_text)

                    if date_match_en:
                        month_name = date_match_en.group(1).lower()
                        day = int(date_match_en.group(2))
                        year = int(date_match_en.group(3))
                    elif date_match_de:
                        day = int(date_match_de.group(1))
                        month_name = date_match_de.group(2).lower()
                        year = int(date_match_de.group(3))
                    else:
                        continue

                    month = months.get(month_name)
                    if month:
                        # Parse time
                        hour, minute = 19, 0  # Default
                        if time_text:
                            time_match = re.search(r"(\d{1,2}):(\d{2})", time_text)
                            if time_match:
                                hour = int(time_match.group(1))
                                minute = int(time_match.group(2))
                        try:
                            event_date = datetime(year, month, day, hour, minute)
                        except ValueError:
                            continue

                if not event_date or event_date.date() < now.date():
                    continue

                # Create venue
                venue_name = "Critical Theory Berlin"
                venue_address = ""
                bezirk = "mitte"

                # If location mentions HU or Humboldt, use specific address
                if location and ("humboldt" in location.lower() or "hu berlin" in location.lower()):
                    venue_address = "Unter den Linden 6, 10117 Berlin"
                elif location and "fu berlin" in location.lower():
                    venue_address = "Habelschwerdter Allee 45, 14195 Berlin"
                    bezirk = "steglitz-zehlendorf"
                elif location and "grimm" in location.lower():
                    venue_address = "Geschwister-Scholl-Straße 1, 10117 Berlin"

                venue_slug = get_or_create_venue(
                    name=venue_name,
                    adresse=venue_address,
                    bezirk=bezirk,
                    url="https://criticaltheoryinberlin.de",
                )

                event_id = hashlib.md5(
                    f"ktb-{title[:50]}-{event_date.strftime('%Y-%m-%d')}".encode()
                ).hexdigest()[:12]

                # Determine event type based on title/content
                event_type = "diskussion"
                title_lower = title.lower()
                if "buchpräsentation" in title_lower or "lesung" in title_lower:
                    event_type = "lesung"
                elif "film" in title_lower:
                    event_type = "film"
                elif "workshop" in title_lower:
                    event_type = "workshop"
                elif "summer school" in title_lower:
                    event_type = "workshop"

                events.append({
                    "id": event_id,
                    "title": title,
                    "date": event_date,
                    "time": event_date.strftime("%H:%M"),
                    "venue_slug": venue_slug,
                    "venue_name": venue_name,
                    "venue_address": venue_address,
                    "bezirk": bezirk,
                    "type": event_type,
                    "description": location if location else "",
                    "link": event_link,
                    "source": "critical-theory-berlin",
                })

            except Exception:
                continue

    except Exception as e:
        print(f"[Critical Theory Berlin] Fehler: {e}")

    print(f"[Critical Theory Berlin] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Cache Refresh
# ─────────────────────────────────────────────────────────────────────────────

def refresh_cache():
    """Aktualisiert den Event-Cache von allen Quellen."""
    global _EVENT_CACHE, _CACHE_LOADING

    all_events = []

    # Stressfaktor
    all_events.extend(scrape_stressfaktor())

    # Rosa Luxemburg Stiftung
    all_events.extend(scrape_rosalux())

    # HAU Hebbel am Ufer
    all_events.extend(scrape_hau())

    # Literaturforum im Brecht-Haus
    all_events.extend(scrape_lfbrecht())

    # Baiz
    all_events.extend(scrape_baiz())

    # Silent Green
    all_events.extend(scrape_silentgreen())

    # Cinema Surreal
    all_events.extend(scrape_cinema_surreal())

    # Acud Macht Neu
    all_events.extend(scrape_acud())

    # Regenbogenfabrik
    all_events.extend(scrape_regenbogenfabrik())

    # Lettrétage
    all_events.extend(scrape_lettretage())

    # Brotfabrik
    all_events.extend(scrape_brotfabrik())

    # Mehringhof Theater
    all_events.extend(scrape_mehringhof())

    # SO36
    all_events.extend(scrape_so36())

    # Urania
    all_events.extend(scrape_urania())

    # Babylon, Literaturhaus, FES - Scraper vorbereitet aber deaktiviert (komplexe Strukturen)
    # all_events.extend(scrape_babylon())
    # all_events.extend(scrape_literaturhaus())
    # all_events.extend(scrape_fes())

    # Panke
    all_events.extend(scrape_panke())

    # Kino Central (nur Specials)
    all_events.extend(scrape_kino_central())

    # Lichtblick Kino (nur Specials/Filmreihen)
    all_events.extend(scrape_lichtblick())

    # Festsaal Kreuzberg
    all_events.extend(scrape_festsaal())

    # Schwarze Risse (Buchladen)
    all_events.extend(scrape_schwarze_risse())

    # Buchladen Weltkugel
    all_events.extend(scrape_weltkugel())

    # Peter Edel
    all_events.extend(scrape_peteredel())

    # KuBiZ Wallenberg
    all_events.extend(scrape_kubiz())

    # Zeiss-Großplanetarium
    all_events.extend(scrape_planetarium())

    # Publix (Haus des Journalismus)
    all_events.extend(scrape_publix())

    # KW Institute for Contemporary Art
    all_events.extend(scrape_kw())

    # Topographie des Terrors
    all_events.extend(scrape_topographie())

    # Jüdisches Museum Berlin
    all_events.extend(scrape_jmberlin())

    # nGbK (neue Gesellschaft für bildende Kunst)
    all_events.extend(scrape_ngbk())

    # Anne Frank Zentrum (Lesungen, Vorträge - keine Führungen/Wanderausstellungen)
    all_events.extend(scrape_annefrank())

    # Haus am Waldsee
    all_events.extend(scrape_hausamwaldsee())

    # Dokumentationszentrum Flucht, Vertreibung, Versöhnung
    all_events.extend(scrape_dokumentationszentrum())

    # Kunstraum Kreuzberg/Bethanien
    all_events.extend(scrape_kunstraumkreuzberg())

    # ZOiS
    all_events.extend(scrape_zois())

    # LPB Berlin
    all_events.extend(scrape_lpb_berlin())

    # BPB (nur Berlin-Events)
    all_events.extend(scrape_bpb())

    # Futurium (PDF-Layout zu komplex, vorerst deaktiviert)
    # all_events.extend(scrape_futurium())

    # MMZ Potsdam
    all_events.extend(scrape_mmz())

    # ZZF Potsdam
    all_events.extend(scrape_zzf())

    # Renaissance-Theater (nur Specials)
    all_events.extend(scrape_renaissance_theater())

    # Flutgraben
    all_events.extend(scrape_flutgraben())

    # Einstein Forum (iCal)
    all_events.extend(scrape_einstein_forum())

    # Museum für Kommunikation Berlin
    all_events.extend(scrape_mfk_berlin())

    # C/O Berlin
    all_events.extend(scrape_co_berlin())

    # Deutsches Technikmuseum
    all_events.extend(scrape_technikmuseum())

    # Gropius Bau
    all_events.extend(scrape_gropius_bau())

    # Haus der Wannsee-Konferenz
    all_events.extend(scrape_wannseekonferenz())

    # Brücke-Museum
    all_events.extend(scrape_bruecke_museum())

    # Tränenpalast
    all_events.extend(scrape_traenenpalast())

    # Haus für Poesie
    all_events.extend(scrape_haus_fuer_poesie())

    # Panda Platforma
    all_events.extend(scrape_panda_platforma())

    # Alte Kantine Wedding
    all_events.extend(scrape_alte_kantine())

    # Kesselhaus (ohne Konzert, Theater, Party)
    all_events.extend(scrape_kesselhaus())

    # Frannz Club (kulturelle Events)
    all_events.extend(scrape_frannz())

    # RambaZamba Theater (Premieren)
    all_events.extend(scrape_rambazamba())

    # Buchhandlungen und Archive
    all_events.extend(scrape_bbooks())
    all_events.extend(scrape_pro_qm())
    all_events.extend(scrape_august_bebel())
    all_events.extend(scrape_ffbiz())
    all_events.extend(scrape_zabriskie())
    all_events.extend(scrape_buchbox())
    # all_events.extend(scrape_geistesblueten())  # Domain existiert nicht mehr
    # all_events.extend(scrape_nicolaische())  # Braucht JavaScript
    all_events.extend(scrape_ocelot())
    all_events.extend(scrape_motto_berlin())

    # Deutsches Spionagemuseum
    all_events.extend(scrape_spionagemuseum())

    # Museum Reinickendorf
    all_events.extend(scrape_museum_reinickendorf())

    # Käthe-Kollwitz-Museum Berlin
    all_events.extend(scrape_kollwitz_museum())

    # Staatliche Museen zu Berlin (SMB) - filtert Führungen, Workshops, Kinderevents
    all_events.extend(scrape_smb_museen())

    # Museum Charlottenburg-Wilmersdorf (Villa Oppenheim)
    all_events.extend(scrape_museum_charlottenburg())

    # Humboldt Forum (via REST API)
    all_events.extend(scrape_humboldt_forum())

    # Mitte Museum
    all_events.extend(scrape_mitte_museum())

    # Mendelssohn-Remise
    all_events.extend(scrape_mendelssohn_remise())

    # Deutsches Historisches Museum
    all_events.extend(scrape_dhm())

    # n.b.k. Neuer Berliner Kunstverein
    all_events.extend(scrape_nbk())

    # Kreativhaus Berlin
    all_events.extend(scrape_kreativhaus())

    # Newsletter RSS (Urban Nation)
    all_events.extend(scrape_newsletter_rss())

    # Museumsportal Berlin (aus manuell gepflegter JSON-Datei)
    all_events.extend(load_museumsportal_from_json())

    # Schaubühne (Diskurs, Lesung, Premiere)
    all_events.extend(scrape_schaubuehne())

    # Luftschloss Tempelhofer Feld
    all_events.extend(scrape_luftschloss())

    # Critical Theory Berlin (KTB)
    all_events.extend(scrape_criticaltheory())

    # Speicher freigeben
    gc.collect()

    # Sortieren nach Datum (timezone-aware -> naive für Vergleich)
    def _sort_key(event):
        dt = event.get("date", datetime.max)
        # Falls timezone-aware, zu naive konvertieren (lokale Zeit)
        if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    all_events.sort(key=_sort_key)

    # Duplikate entfernen (nach ID)
    seen_ids = set()
    unique_events = []
    for event in all_events:
        if event["id"] not in seen_ids:
            seen_ids.add(event["id"])
            unique_events.append(event)

    global _CACHE_LOADING
    _EVENT_CACHE = unique_events
    _CACHE_LOADING = False
    print(f"[Cache] {len(_EVENT_CACHE)} Events im Cache")


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Startseite - alle kommenden Events chronologisch."""
    now = datetime.now()
    events = sorted(
        [e for e in get_events() if e.get("date") and make_naive(e["date"]) >= now],
        key=lambda x: make_naive(x["date"])
    )
    return render_template(
        "index.html",
        events=events,
        venues=get_veranstalter(),
        bezirke=get_bezirke_sorted(),
        event_types=get_event_types_sorted(),
        cache_loading=is_cache_loading(),
    )


@app.route("/tag/<datum>")
def tag(datum: str):
    """Events für einen bestimmten Tag."""
    if datum == "heute":
        target_date = datetime.now()
    elif datum == "morgen":
        target_date = datetime.now() + timedelta(days=1)
    else:
        try:
            target_date = datetime.strptime(datum, "%Y-%m-%d")
        except ValueError:
            return redirect(url_for("index"))

    events = get_events_by_date(target_date)
    events = sorted(events, key=lambda x: x.get("time", "00:00"))

    return render_template(
        "tag.html",
        events=events,
        datum=target_date,
        venues=get_veranstalter(),
        bezirke=get_bezirke_sorted(),
        event_types=get_event_types_sorted(),
    )


@app.route("/ort/<slug>")
def ort(slug: str):
    """Events für einen bestimmten Veranstalter."""
    veranstalter = get_veranstalter()
    all_venues = get_all_venues()

    # Prüfen ob Venue existiert (in VERANSTALTER oder dynamisch erstellt)
    if slug in veranstalter:
        venue = veranstalter[slug]
    elif slug in all_venues:
        # Dynamisch erstellter Venue (z.B. aus Museumsportal)
        venue = all_venues[slug]
    else:
        # Unbekannter Veranstalter
        return render_template(
            "ort.html",
            events=[],
            venue={"name": slug.replace("-", " ").title(), "adresse": None, "url": None},
            venue_slug=slug,
            venues=veranstalter,
            event_types=get_event_types_sorted(),
            bezirke=get_bezirke_sorted(),
        )

    events = get_events_by_veranstalter(slug)
    events = sorted(events, key=lambda x: make_naive(x.get("date")) or datetime.max)

    return render_template(
        "ort.html",
        events=events,
        venue=venue,
        venue_slug=slug,
        venues=veranstalter,
        event_types=get_event_types_sorted(),
        bezirke=get_bezirke_sorted(),
    )


@app.route("/typ/<slug>")
def typ(slug: str):
    """Events eines bestimmten Typs."""
    if slug not in EVENT_TYPES:
        return redirect(url_for("index"))

    events = get_events_by_type(slug)
    events = sorted(events, key=lambda x: make_naive(x.get("date")) or datetime.max)

    return render_template(
        "typ.html",
        events=events,
        event_type=EVENT_TYPES[slug],
        type_slug=slug,
        event_types=get_event_types_sorted(),
        bezirke=get_bezirke_sorted(),
        venues=get_veranstalter(),
    )


@app.route("/bezirk/<slug>")
def bezirk(slug: str):
    """Events in einem bestimmten Bezirk."""
    if slug not in BEZIRKE:
        return redirect(url_for("index"))

    events = get_events_by_bezirk(slug)
    events = sorted(events, key=lambda x: make_naive(x.get("date")) or datetime.max)

    return render_template(
        "bezirk.html",
        events=events,
        bezirk=BEZIRKE[slug],
        bezirk_slug=slug,
        bezirke=get_bezirke_sorted(),
        event_types=get_event_types_sorted(),
        venues=get_veranstalter(),
    )


@app.route("/woche")
def woche():
    """Wochenübersicht."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_events = {}

    for i in range(7):
        day = today + timedelta(days=i)
        day_events = get_events_by_date(day)
        day_events = sorted(day_events, key=lambda x: x.get("time", "00:00"))
        week_events[day] = day_events

    return render_template(
        "woche.html",
        week_events=week_events,
        venues=get_veranstalter(),
        bezirke=get_bezirke_sorted(),
        event_types=get_event_types_sorted(),
    )


@app.route("/suche")
def suche():
    """Volltextsuche mit Filtern."""
    query = request.args.get("q", "").strip()
    bezirk_filter = request.args.getlist("bezirk")
    typ_filter = request.args.getlist("typ")
    zeit_filter = request.args.get("zeit", "")

    events = get_events()

    # Textsuche
    if query:
        query_lower = query.lower()
        events = [
            e for e in events
            if query_lower in e.get("title", "").lower()
            or query_lower in e.get("description", "").lower()
            or query_lower in e.get("venue_name", "").lower()
        ]

    # Bezirk-Filter
    if bezirk_filter:
        events = [e for e in events if e.get("bezirk") in bezirk_filter]

    # Typ-Filter
    if typ_filter:
        events = [e for e in events if e.get("type") in typ_filter]

    # Zeit-Filter
    if zeit_filter and zeit_filter in TIME_SLOTS:
        start_hour, end_hour = _parse_time_slot(zeit_filter)
        events = [
            e for e in events
            if _event_in_time_range(e, start_hour, end_hour)
        ]

    events = sorted(events, key=lambda x: make_naive(x.get("date")) or datetime.max)

    return render_template(
        "suche.html",
        events=events,
        query=query,
        bezirke=get_bezirke_sorted(),
        event_types=get_event_types_sorted(),
        venues=get_veranstalter(),
        time_slots=TIME_SLOTS,
        selected_bezirke=bezirk_filter,
        selected_types=typ_filter,
        selected_zeit=zeit_filter,
    )


@app.route("/merkliste")
def merkliste():
    """Gespeicherte Events."""
    saved_ids = session.get("saved_events", [])
    events = [e for e in get_events() if e.get("id") in saved_ids]
    events = sorted(events, key=lambda x: make_naive(x.get("date")) or datetime.max)

    return render_template(
        "merkliste.html",
        events=events,
        venues=get_veranstalter(),
        bezirke=get_bezirke_sorted(),
        event_types=get_event_types_sorted(),
    )


@app.route("/toggle_merkliste", methods=["POST"])
def toggle_merkliste():
    """Event zur Merkliste hinzufügen/entfernen."""
    event_id = request.form.get("event_id")
    if not event_id:
        return jsonify({"error": "Keine Event-ID"}), 400

    saved = session.get("saved_events", [])

    if event_id in saved:
        saved.remove(event_id)
        added = False
    else:
        saved.append(event_id)
        added = True

    session["saved_events"] = saved
    return jsonify({"added": added, "count": len(saved)})


@app.route("/refresh")
def refresh():
    """Manuelles Cache-Refresh (für Entwicklung)."""
    refresh_cache()
    return redirect(url_for("index"))


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def _parse_time_slot(slot: str) -> tuple[int, int]:
    """Parst Zeitfenster-String zu Start/End-Stunde."""
    if slot == "22+":
        return 22, 24
    parts = slot.split("-")
    return int(parts[0]), int(parts[1])


def _event_in_time_range(event: dict, start_hour: int, end_hour: int) -> bool:
    """Prüft ob Event in Zeitfenster fällt."""
    time_str = event.get("time", "")
    if not time_str:
        return False
    try:
        hour = int(time_str.split(":")[0])
        return start_hour <= hour < end_hour
    except (ValueError, IndexError):
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────────────────────────────────────

# Cache im Hintergrund laden, damit der Server sofort starten kann
import threading

def _background_refresh():
    print("[Startup] Lade Events im Hintergrund...")
    refresh_cache()
    print("[Startup] Events geladen!")

# Starte das Scraping in einem separaten Thread
_cache_thread = threading.Thread(target=_background_refresh, daemon=True)
_cache_thread.start()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5001)
