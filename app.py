"""
Kleine Terminliste - Berliner Veranstaltungskalender
für linke Subkultur und Politik
"""

import os
import re
import hashlib
import unicodedata
from html import unescape
from datetime import datetime, timedelta
from flask import Flask, render_template, request, session, jsonify, redirect, url_for
from flask_session import Session
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

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
# Slugify Helper
# ─────────────────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Konvertiert Text zu URL-freundlichem Slug."""
    if not text:
        return ""
    # Normalize unicode
    text = unicodedata.normalize("NFKD", text)
    # Replace umlauts
    replacements = {
        "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
        "Ä": "ae", "Ö": "oe", "Ü": "ue",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
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
    "rosa-luxemburg-stiftung": {"name": "Rosa-Luxemburg-Stiftung", "url": "https://www.rosalux.de"},
    "hau-hebbel-am-ufer": {"name": "HAU Hebbel am Ufer", "url": "https://www.hebbel-am-ufer.de"},
    "literaturforum-im-brecht-haus": {"name": "Literaturforum im Brecht-Haus", "url": "https://lfbrecht.de"},
    "baiz": {"name": "B.A.I.Z.", "url": "https://baiz.info"},
    "silent-green-kulturquartier": {"name": "Silent Green Kulturquartier", "url": "https://www.silent-green.net"},
    "acud-macht-neu": {"name": "ACUD macht neu", "url": "https://acudmachtneu.de"},
    "regenbogenfabrik": {"name": "Regenbogenfabrik", "url": "https://regenbogenfabrik.de"},
    "brotfabrik": {"name": "Brotfabrik", "url": "https://brotfabrik-berlin.de"},
    "so36": {"name": "SO36", "url": "https://so36.com"},
    "urania-berlin": {"name": "Urania Berlin", "url": "https://www.urania.de"},
    "festsaal-kreuzberg": {"name": "Festsaal Kreuzberg", "url": "https://festsaal-kreuzberg.de"},
    "panke": {"name": "Panke", "url": "https://panke.gallery"},
    "kino-central": {"name": "Kino Central", "url": "https://kino-central.de"},
    "lichtblick-kino": {"name": "Lichtblick Kino", "url": "https://lichtblick-kino.org"},
    "lettretage": {"name": "Lettrétage", "url": "https://lettretage.de"},
    "cinema-surreal": {"name": "Cinema Surreal", "url": "https://cinemasurreal.de"},
    "peter-edel": {"name": "Peter Edel", "url": "https://www.peteredel.de"},
    "kubiz-wallenberg": {"name": "KuBiZ Wallenberg", "url": "https://www.kubiz-wallenberg.de"},
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
    """Gibt alle Veranstalter für das Dropdown zurück."""
    return VERANSTALTER


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
            if filename.endswith(".svg"):
                slug = filename[:-4]  # Remove .svg
                venue_logos[slug] = filename
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
    ALLOWED_VENUES = {
        "kubiz": {
            "name": "KuBiZ",
            "adresse": "Bernkasteler Straße 78, 13088 Berlin",
            "bezirk": "weissensee",
            "url": "https://kubiz-wallenberg.de",
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
        venue_name = venue_elem.get_text(strip=True) if venue_elem else "Unbekannt"
        venue_key = venue_name.lower()

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

        events.append({
            "id": event_id,
            "title": title,
            "date": current_date,
            "time": time_str,
            "venue_slug": venue_slug,
            "venue_name": venue_info["name"],
            "bezirk": venue_info["bezirk"],
            "type": event_type,
            "description": description,
            "link": link,
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

        # Description is in .realContent, first strong tag or first paragraph
        real_content = soup.select_one(".realContent")
        if real_content:
            strong_elem = real_content.select_one("strong")
            if strong_elem:
                result["description"] = strong_elem.get_text(strip=True)
            else:
                # Fallback to first paragraph
                p_elem = real_content.select_one("p")
                if p_elem:
                    result["description"] = p_elem.get_text(strip=True)

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
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Chausseestraße 125, 10115 Berlin",
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
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Schönhauser Allee 26a, 10435 Berlin",
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

            event_id = hashlib.md5(f"acud-{event_link}".encode()).hexdigest()[:12]

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": "",
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "bezirk": "mitte",
                "type": event_type,
                "description": "",
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

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "bezirk": "kreuzberg",
                "type": event_type,
                "description": "",
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

def scrape_brotfabrik() -> list[dict]:
    """Scraped Events von brotfabrik-berlin.de."""
    events = []
    venue_name = "Brotfabrik"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Caligariplatz 1, 13086 Berlin",
        bezirk="weissensee",
        url="https://brotfabrik-berlin.de",
    )

    try:
        resp = requests.get(
            "https://brotfabrik-berlin.de/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Brotfabrik] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    current_year = datetime.now().year

    for article in soup.select("article, .event-item, .programm-item"):
        try:
            title_elem = article.select_one("h2 a, h3 a, .title a")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            href = title_elem.get("href", "")
            event_link = href if href.startswith("http") else f"https://brotfabrik-berlin.de{href}"

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

            event_id = hashlib.md5(f"brotfabrik-{event_link}".encode()).hexdigest()[:12]
            event_type = _classify_event_type(title, text)

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "bezirk": "weissensee",
                "type": event_type,
                "description": "",
                "link": event_link,
                "source": "brotfabrik",
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
            event_link = href if href.startswith("http") else f"https://www.pankeculture.com{href}"

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

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "bezirk": "mitte",
                "type": "film",
                "description": "",
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
# Cache Refresh
# ─────────────────────────────────────────────────────────────────────────────

def refresh_cache():
    """Aktualisiert den Event-Cache von allen Quellen."""
    global _EVENT_CACHE

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

    # Sortieren nach Datum
    all_events.sort(key=lambda x: x.get("date", datetime.max))

    # Duplikate entfernen (nach ID)
    seen_ids = set()
    unique_events = []
    for event in all_events:
        if event["id"] not in seen_ids:
            seen_ids.add(event["id"])
            unique_events.append(event)

    _EVENT_CACHE = unique_events
    print(f"[Cache] {len(_EVENT_CACHE)} Events im Cache")


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Startseite - alle kommenden Events chronologisch."""
    now = datetime.now()
    events = sorted(
        [e for e in get_events() if e.get("date") and e["date"] >= now],
        key=lambda x: x["date"]
    )
    return render_template(
        "index.html",
        events=events,
        venues=get_veranstalter(),
        bezirke=BEZIRKE,
        event_types=EVENT_TYPES,
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
        bezirke=BEZIRKE,
        event_types=EVENT_TYPES,
    )


@app.route("/ort/<slug>")
def ort(slug: str):
    """Events für einen bestimmten Veranstalter."""
    veranstalter = get_veranstalter()

    if slug not in veranstalter:
        # Unbekannter Veranstalter
        return render_template(
            "ort.html",
            events=[],
            venue={"name": slug.replace("-", " ").title(), "adresse": None, "url": None},
            venue_slug=slug,
            venues=veranstalter,
            event_types=EVENT_TYPES,
            bezirke=BEZIRKE,
        )

    venue = veranstalter[slug]
    events = get_events_by_veranstalter(slug)
    events = sorted(events, key=lambda x: x.get("date", datetime.max))

    return render_template(
        "ort.html",
        events=events,
        venue=venue,
        venue_slug=slug,
        venues=veranstalter,
        event_types=EVENT_TYPES,
        bezirke=BEZIRKE,
    )


@app.route("/typ/<slug>")
def typ(slug: str):
    """Events eines bestimmten Typs."""
    if slug not in EVENT_TYPES:
        return redirect(url_for("index"))

    events = get_events_by_type(slug)
    events = sorted(events, key=lambda x: x.get("date", datetime.max))

    return render_template(
        "typ.html",
        events=events,
        event_type=EVENT_TYPES[slug],
        type_slug=slug,
        event_types=EVENT_TYPES,
        bezirke=BEZIRKE,
        venues=get_veranstalter(),
    )


@app.route("/bezirk/<slug>")
def bezirk(slug: str):
    """Events in einem bestimmten Bezirk."""
    if slug not in BEZIRKE:
        return redirect(url_for("index"))

    events = get_events_by_bezirk(slug)
    events = sorted(events, key=lambda x: x.get("date", datetime.max))

    return render_template(
        "bezirk.html",
        events=events,
        bezirk=BEZIRKE[slug],
        bezirk_slug=slug,
        bezirke=BEZIRKE,
        event_types=EVENT_TYPES,
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
        bezirke=BEZIRKE,
        event_types=EVENT_TYPES,
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

    events = sorted(events, key=lambda x: x.get("date", datetime.max))

    return render_template(
        "suche.html",
        events=events,
        query=query,
        bezirke=BEZIRKE,
        event_types=EVENT_TYPES,
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
    events = sorted(events, key=lambda x: x.get("date", datetime.max))

    return render_template(
        "merkliste.html",
        events=events,
        venues=get_veranstalter(),
        bezirke=BEZIRKE,
        event_types=EVENT_TYPES,
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

# Cache beim Start laden
print("[Startup] Lade Events...")
refresh_cache()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5001)
