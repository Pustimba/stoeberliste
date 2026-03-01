"""
Kleine Terminliste - Berliner Veranstaltungskalender
für linke Subkultur und Politik
"""

import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, session, jsonify, redirect, url_for
from flask_session import Session

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
# Veranstaltungsorte
# ─────────────────────────────────────────────────────────────────────────────

VENUES = {
    "urania": {
        "name": "Urania",
        "url": "https://www.urania.de/kalender/",
        "bezirk": "schoeneberg",
        "adresse": "An der Urania 17, 10787 Berlin",
    },
    "zois": {
        "name": "ZOiS",
        "url": "https://www.zois-berlin.de/veranstaltungen",
        "bezirk": "mitte",
        "adresse": "Mohrenstraße 60, 10117 Berlin",
    },
    "publix": {
        "name": "Publix",
        "url": "https://www.publix.de/veranstaltungen",
        "bezirk": "neukoelln",
        "adresse": "Karl-Marx-Straße 83, 12043 Berlin",
    },
    "akademie-der-kuenste": {
        "name": "Akademie der Künste",
        "url": "https://adk.de/programm/veranstaltungskalender",
        "bezirk": "mitte",
        "adresse": "Pariser Platz 4, 10117 Berlin",
    },
    "haus-der-demokratie": {
        "name": "Haus der Demokratie",
        "url": "https://www.hausderdemokratie.de/veranstaltung",
        "bezirk": "prenzlauer-berg",
        "adresse": "Greifswalder Straße 4, 10405 Berlin",
    },
    "literaturforum-brecht-haus": {
        "name": "Literaturforum im Brecht-Haus",
        "url": "https://lfbrecht.de/events/",
        "bezirk": "mitte",
        "adresse": "Chausseestraße 125, 10115 Berlin",
    },
    "literaturhaus-berlin": {
        "name": "Literaturhaus Berlin",
        "url": "https://li-be.de/",
        "bezirk": "wilmersdorf",
        "adresse": "Fasanenstraße 23, 10719 Berlin",
    },
    "brotfabrik": {
        "name": "Brotfabrik",
        "url": "https://brotfabrik-berlin.de/",
        "bezirk": "weissensee",
        "adresse": "Caligariplatz 1, 13086 Berlin",
    },
    "z-bar": {
        "name": "Z-Bar",
        "url": "https://zbarberlin.com/kulturprogramm/",
        "bezirk": "mitte",
        "adresse": "Bergstraße 2, 10115 Berlin",
    },
    "flutgraben": {
        "name": "Flutgraben",
        "url": "https://flutgraben.org/aktuell/filter/events/",
        "bezirk": "kreuzberg",
        "adresse": "Am Flutgraben 3, 12435 Berlin",
    },
    "haus-der-statistik": {
        "name": "Haus der Statistik / Sinema Transtopia",
        "url": "https://hausderstatistik.org/programm/",
        "bezirk": "mitte",
        "adresse": "Karl-Marx-Allee 1, 10178 Berlin",
    },
    "renaissance-theater": {
        "name": "Renaissance-Theater",
        "url": "https://renaissance-theater.de/spielplan/",
        "bezirk": "charlottenburg",
        "adresse": "Knesebeckstraße 100, 10623 Berlin",
    },
    "einstein-forum": {
        "name": "Einstein Forum",
        "url": "https://www.einsteinforum.de/programm/",
        "bezirk": "potsdam",
        "adresse": "Am Neuen Markt 7, 14467 Potsdam",
    },
    "stressfaktor": {
        "name": "Stressfaktor",
        "url": "https://stressfaktor.squat.net/termine",
        "bezirk": "diverse",
        "adresse": None,
    },
}

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
# In-Memory Event Cache (wird durch Scraper befüllt)
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
        venues=VENUES,
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
        venues=VENUES,
        bezirke=BEZIRKE,
    )


@app.route("/ort/<slug>")
def ort(slug: str):
    """Events für einen bestimmten Veranstaltungsort."""
    if slug not in VENUES:
        return redirect(url_for("index"))

    venue = VENUES[slug]
    events = get_events_by_venue(slug)
    events = sorted(events, key=lambda x: x.get("date", datetime.max))

    return render_template(
        "ort.html",
        events=events,
        venue=venue,
        venue_slug=slug,
        venues=VENUES,
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
        venues=VENUES,
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
        venues=VENUES,
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
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5001)
