"""
Kleine Terminliste - Berliner Veranstaltungskalender
für linke Subkultur und Politik
"""

import os
import re
import hashlib
import unicodedata
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
        "schokoladen": {
            "name": "Schokoladen",
            "adresse": "Ackerstraße 169, 10115 Berlin",
            "bezirk": "mitte",
            "url": "https://schokoladen-mitte.de",
        },
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

def scrape_rosalux() -> list[dict]:
    """Scraped Events von rosalux.de/veranstaltungen."""
    events = []
    venue_name = "Rosa-Luxemburg-Stiftung"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Franz-Mehring-Platz 1, 10243 Berlin",
        bezirk="friedrichshain",
        url="https://www.rosalux.de",
    )

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
    seen_links = set()

    for link in soup.select("a[href*='/veranstaltung/es_detail/']"):
        try:
            href = link.get("href", "")
            if not href or href in seen_links:
                continue
            seen_links.add(href)

            raw_title = link.get_text(strip=True)
            if not raw_title or len(raw_title) < 3:
                continue

            event_link = f"https://www.rosalux.de{href}" if href.startswith("/") else href

            # Titel enthält Datum: "Event-Name, 20 Februar 2026" oder "Event-Name, 20 Februar 2026 - 23 März 2026"
            # Trenne Titel vom Datum
            title_date_match = re.match(r"^(.+?),\s*(\d{1,2})\s+(\w+)\s+(\d{4})", raw_title)
            if title_date_match:
                title = title_date_match.group(1).strip()
                day = int(title_date_match.group(2))
                month_name = title_date_match.group(3).lower()
                year = int(title_date_match.group(4))
            else:
                # Fallback: Titel ohne Datum-Suffix
                title = re.sub(r",\s*\d{1,2}\s+\w+.*$", "", raw_title).strip()
                day, month_name, year = None, None, None

            if not title or len(title) < 3:
                continue

            # Finde Parent-Container für Metadaten
            parent = link.find_parent("div") or link.find_parent("li")
            if not parent:
                continue

            full_text = parent.get_text(" ", strip=True)

            # Falls Datum nicht aus Titel extrahiert, aus full_text
            if not day:
                date_match = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", full_text)
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

            # Zeit extrahieren (Format: "19:30 Uhr" oder nur "19:30")
            time_match = re.search(r"(\d{1,2}):(\d{2})(?:\s*Uhr)?", full_text)
            time_str = f"{time_match.group(1)}:{time_match.group(2)}" if time_match else ""

            # Beschreibung: Text nach Uhrzeit oder Ort
            # Typisches Format: "01 März 2026 Berlin 19:30 Uhr Beschreibungstext"
            description = ""
            # Suche nach Text nach "Uhr"
            desc_match = re.search(r"\d{1,2}:\d{2}\s*Uhr\s+(.+?)$", full_text)
            if desc_match:
                desc_text = desc_match.group(1).strip()
                # Entferne Kategorien/Reihen am Anfang
                desc_text = re.sub(r"^(Diskussion/Vortrag|Ausstellung/Kultur|Film|Konzert|Workshop|Seminar|ausgebucht)\s*", "", desc_text)
                if len(desc_text) > 5:
                    description = desc_text

            event_id = hashlib.md5(f"rosalux-{event_link}".encode()).hexdigest()[:12]

            # Typ klassifizieren
            event_type = _classify_event_type(title, full_text)

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "bezirk": "friedrichshain",
                "type": event_type,
                "description": description,
                "link": event_link,
                "source": "rosalux",
            })
        except Exception:
            continue

    print(f"[RosaLux] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# HAU Hebbel am Ufer Scraper
# ─────────────────────────────────────────────────────────────────────────────

def scrape_hau() -> list[dict]:
    """Scraped Events von hebbel-am-ufer.de."""
    events = []

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

    for item in soup.select("li"):
        try:
            # Titel aus h3 oder h4
            title_elem = item.select_one("h3, h4")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            # Link
            link_elem = item.select_one("a[href*='/programm/pdetail/']")
            if not link_elem:
                continue

            href = link_elem.get("href", "")
            event_link = f"https://www.hebbel-am-ufer.de{href}" if href.startswith("/") else href

            # Datum aus strong-Tags (Format: "So 01" = Sonntag, 1.)
            text = item.get_text(" ", strip=True)

            # Suche nach Datum-Pattern wie "So 01" oder "Mi 04"
            date_match = re.search(r"(Mo|Di|Mi|Do|Fr|Sa|So)\s+(\d{1,2})", text)
            if not date_match:
                continue

            day = int(date_match.group(2))

            # Monat aus Kontext ermitteln (März = 3)
            month_match = re.search(r"(januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)", text.lower())
            if month_match:
                month = GERMAN_MONTHS.get(month_match.group(1), datetime.now().month)
            else:
                month = datetime.now().month

            year = current_year
            if month < datetime.now().month:
                year += 1

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            # Zeit (Format: "17:00" oder "20:00")
            time_match = re.search(r"(\d{1,2}):(\d{2})", text)
            time_str = f"{time_match.group(1)}:{time_match.group(2)}" if time_match else ""

            # Venue - immer HAU Hebbel am Ufer (nicht HAU1/2/3 unterscheiden)
            venue_name = "HAU Hebbel am Ufer"
            venue_slug = get_or_create_venue(
                name=venue_name,
                adresse="Stresemannstraße 29, 10963 Berlin",
                bezirk="kreuzberg",
                url="https://www.hebbel-am-ufer.de",
            )

            event_id = hashlib.md5(f"hau-{event_link}-{event_date.isoformat()}".encode()).hexdigest()[:12]

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
                "source": "hau",
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

def scrape_silentgreen() -> list[dict]:
    """Scraped Events von silent-green.net/programm."""
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

            # Titel aus Link-Text
            title = link.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            # Entferne Kategorieprefix (Konzert, Filmvorführung, etc.)
            clean_title = re.sub(r"^(Konzert|Filmvorführung|Festival|Lesung|Installation|Performance|Ausstellung)", "", title).strip()
            if clean_title:
                title = clean_title

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

            # Typ aus Kategorie (Konzert, Filmvorführung, Lesung)
            original_text = link.get_text(strip=True)
            event_type = _classify_event_type(original_text, "")

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
                "description": "",
                "link": event_link,
                "source": "silentgreen",
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
    """Scraped Events von so36.com."""
    events = []
    venue_name = "SO36"
    venue_slug = get_or_create_venue(
        name=venue_name,
        adresse="Oranienstraße 190, 10999 Berlin",
        bezirk="kreuzberg",
        url="https://www.so36.com",
    )

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
            if event_type == "sonstiges":
                event_type = "konzert"

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

    print(f"[SO36] {len(events)} Events geladen")
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Urania Scraper
# ─────────────────────────────────────────────────────────────────────────────

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

            event_id = hashlib.md5(f"urania-{event_link}".encode()).hexdigest()[:12]
            event_type = _classify_event_type(title, "")

            events.append({
                "id": event_id,
                "title": title,
                "date": event_date,
                "time": time_str,
                "venue_slug": venue_slug,
                "venue_name": venue_name,
                "bezirk": "schoeneberg",
                "type": event_type,
                "description": "",
                "link": event_link,
                "source": "urania",
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
            "https://li-be.de/programm/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KleineTerminliste/1.0)"},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Literaturhaus] Fehler beim Laden: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    current_year = datetime.now().year

    for link in soup.select("a[href*='li-be.de']"):
        try:
            href = link.get("href", "")
            if not href or "/programm/" not in href or href.endswith("/programm/"):
                continue

            # Nur Event-Links
            title_elem = link.select_one("h3, h2")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            event_link = href if href.startswith("http") else f"https://li-be.de{href}"

            # Datum aus Parent
            parent = link.find_parent("div") or link.find_parent("article")
            if not parent:
                continue

            text = parent.get_text(" ", strip=True)

            # Datum (Format: "3.3.Di" = 3. März, Dienstag)
            date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(Mo|Di|Mi|Do|Fr|Sa|So)", text)
            if not date_match:
                continue

            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = current_year

            try:
                event_date = datetime(year, month, day)
            except ValueError:
                continue

            # Zeit
            time_match = re.search(r"(\d{1,2}):(\d{2})\s*Uhr", text)
            time_str = f"{time_match.group(1)}:{time_match.group(2)}" if time_match else ""

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

    # Babylon Berlin
    all_events.extend(scrape_babylon())

    # Literaturhaus Berlin
    all_events.extend(scrape_literaturhaus())

    # Friedrich-Ebert-Stiftung
    all_events.extend(scrape_fes())

    # Panke
    all_events.extend(scrape_panke())

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
        venues=get_all_venues(),
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
        venues=get_all_venues(),
        bezirke=BEZIRKE,
        event_types=EVENT_TYPES,
    )


@app.route("/ort/<slug>")
def ort(slug: str):
    """Events für einen bestimmten Veranstaltungsort."""
    all_venues = get_all_venues()
    if slug not in all_venues:
        # Vielleicht existiert der Venue noch nicht - 404 statt redirect
        return render_template(
            "ort.html",
            events=[],
            venue={"name": slug.replace("-", " ").title(), "adresse": None, "url": None},
            venue_slug=slug,
            venues=all_venues,
            event_types=EVENT_TYPES,
            bezirke=BEZIRKE,
        )

    venue = all_venues[slug]
    events = get_events_by_venue(slug)
    events = sorted(events, key=lambda x: x.get("date", datetime.max))

    return render_template(
        "ort.html",
        events=events,
        venue=venue,
        venue_slug=slug,
        venues=all_venues,
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
        venues=get_all_venues(),
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
        venues=get_all_venues(),
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
        venues=get_all_venues(),
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
        venues=get_all_venues(),
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
        venues=get_all_venues(),
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
