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
    """Scraped Events von stressfaktor.squat.net."""
    events = []

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

        # Ort
        venue_elem = elem.select_one(".views-field-nothing a")
        venue_name = venue_elem.get_text(strip=True) if venue_elem else "Unbekannt"

        # Adresse
        adresse_elem = elem.select_one(".location .address")
        adresse = ""
        if adresse_elem:
            # Extrahiere Adresse aus den span-Elementen
            parts = []
            street = adresse_elem.select_one(".address-line1")
            if street:
                parts.append(street.get_text(strip=True))
            plz = adresse_elem.select_one(".postal-code")
            city = adresse_elem.select_one(".locality")
            if plz and city:
                parts.append(f"{plz.get_text(strip=True)} {city.get_text(strip=True)}")
            adresse = ", ".join(parts)

        # Beschreibung
        desc_elem = elem.select_one(".views-field-body")
        description = desc_elem.get_text(strip=True) if desc_elem else ""

        # Venue registrieren/holen
        venue_slug = get_or_create_venue(
            name=venue_name,
            adresse=adresse,
            url=f"https://stressfaktor.squat.net{venue_elem.get('href', '')}" if venue_elem else None,
        )

        # Event-Typ klassifizieren
        event_type = _classify_event_type(title, description)

        # Event-ID generieren
        event_id = hashlib.md5(f"{link}{current_date.isoformat()}".encode()).hexdigest()[:12]

        # Bezirk vom Venue holen
        all_venues = get_all_venues()
        bezirk = all_venues.get(venue_slug, {}).get("bezirk", "diverse")

        events.append({
            "id": event_id,
            "title": title,
            "date": current_date,
            "time": time_str,
            "venue_slug": venue_slug,
            "venue_name": venue_name,
            "bezirk": bezirk,
            "type": event_type,
            "description": description,
            "link": link,
            "source": "stressfaktor",
        })

    print(f"[Stressfaktor] {len(events)} Events geladen, {len(_DYNAMIC_VENUES)} Venues")
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

    # TODO: Weitere Scraper hier hinzufügen

    # Sortieren nach Datum
    all_events.sort(key=lambda x: x.get("date", datetime.max))

    _EVENT_CACHE = all_events
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
    )


@app.route("/ort/<slug>")
def ort(slug: str):
    """Events für einen bestimmten Veranstaltungsort."""
    all_venues = get_all_venues()
    if slug not in all_venues:
        return redirect(url_for("index"))

    venue = all_venues[slug]
    events = get_events_by_venue(slug)
    events = sorted(events, key=lambda x: x.get("date", datetime.max))

    return render_template(
        "ort.html",
        events=events,
        venue=venue,
        venue_slug=slug,
        venues=all_venues,
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
