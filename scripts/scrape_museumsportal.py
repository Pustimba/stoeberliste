#!/usr/bin/env python3
"""
Manuelles Scraping-Skript für Museumsportal Berlin.

Verwendung:
1. pip install playwright
2. playwright install chromium
3. python scripts/scrape_museumsportal.py

Das Skript öffnet einen Browser, du kannst ggf. Captchas lösen,
dann extrahiert es die Events und speichert sie in data/museumsportal.json.
"""

import json
import re
import os
from datetime import datetime
from playwright.sync_api import sync_playwright

# Pfad zur JSON-Datei
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(SCRIPT_DIR, "..", "data", "museumsportal.json")


def scrape_events(page) -> list[dict]:
    """Scraped Events vom Museumsportal."""
    events = []
    now = datetime.now()

    url = "https://www.museumsportal-berlin.de/de/programm?event_type=film&event_type=konzert&event_type=vortraglesunggesprach"
    print(f"Lade Events von: {url}")
    print("(Warte auf Seite - kann etwas dauern...)")

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=120000)
    except Exception as e:
        print(f"Timeout beim Laden, aber Browser ist offen: {e}")

    # Warte auf User-Input falls Captcha oder langsames Laden
    input("\nDrücke ENTER wenn die Seite FERTIG geladen ist (ggf. Captcha lösen)...")

    # Scrollen um alle Events zu laden
    print("Scrolle durch die Seite...")
    for _ in range(5):
        page.evaluate("window.scrollBy(0, 1000)")
        page.wait_for_timeout(500)

    # Events extrahieren
    cards = page.query_selector_all("hylo-router-link.list-item")
    print(f"Gefunden: {len(cards)} Event-Karten")

    for card in cards:
        try:
            href = card.get_attribute("href") or ""
            if "veranstaltungen" not in href:
                continue

            # Titel
            title_elem = card.query_selector("h2")
            title = title_elem.inner_text().strip() if title_elem else ""
            if not title:
                continue

            # Typ
            type_elem = card.query_selector(".mp-card-type")
            event_type_text = type_elem.inner_text().strip().lower() if type_elem else ""

            # Location
            loc_elem = card.query_selector(".mp-card-location")
            venue_name = loc_elem.inner_text().strip() if loc_elem else "Museum Berlin"

            # Beschreibung
            subtitle_elem = card.query_selector("h3")
            description = subtitle_elem.inner_text().strip() if subtitle_elem else ""

            # Datum
            date_elem = card.query_selector(".mp-card-date")
            date_text = date_elem.inner_text().strip() if date_elem else ""

            event_date = None
            if date_text:
                # Format: "So 09.03. | 14:00" oder "09.03.2026"
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})?", date_text)
                time_match = re.search(r"(\d{1,2}):(\d{2})", date_text)

                if date_match:
                    day = int(date_match.group(1))
                    month = int(date_match.group(2))
                    year = int(date_match.group(3)) if date_match.group(3) else now.year
                    if month < now.month and not date_match.group(3):
                        year += 1

                    hour = int(time_match.group(1)) if time_match else 19
                    minute = int(time_match.group(2)) if time_match else 0

                    try:
                        event_date = datetime(year, month, day, hour, minute)
                    except ValueError:
                        continue

            if not event_date or event_date.date() < now.date():
                continue

            # Event-Typ bestimmen
            if "film" in event_type_text:
                event_type = "film"
            elif "konzert" in event_type_text:
                event_type = "konzert"
            elif "lesung" in event_type_text:
                event_type = "lesung"
            elif "gespräch" in event_type_text or "vortrag" in event_type_text:
                event_type = "diskussion"
            else:
                event_type = "vortrag"

            event_link = f"https://www.museumsportal-berlin.de{href}" if href.startswith("/") else href

            events.append({
                "title": title,
                "date": event_date.strftime("%Y-%m-%d %H:%M"),
                "venue_name": venue_name,
                "bezirk": "mitte",
                "type": event_type,
                "description": description[:300] if description else "",
                "link": event_link,
            })
            print(f"  + {title} ({event_date.strftime('%d.%m.%Y %H:%M')})")

        except Exception as e:
            print(f"  Fehler bei Karte: {e}")
            continue

    return events


def scrape_closing_soon(page) -> list[dict]:
    """Scraped 'Endet bald' Ausstellungen."""
    exhibitions = []
    now = datetime.now()

    url = "https://www.museumsportal-berlin.de/de/programm?closing_soon=1"
    print(f"\nLade 'Endet bald' von: {url}")

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=120000)
    except Exception as e:
        print(f"Timeout beim Laden: {e}")

    input("\nDrücke ENTER wenn die Seite FERTIG geladen ist...")

    # Scrollen
    for _ in range(3):
        page.evaluate("window.scrollBy(0, 1000)")
        page.wait_for_timeout(500)

    cards = page.query_selector_all("hylo-router-link.list-item")
    print(f"Gefunden: {len(cards)} Ausstellungen")

    for card in cards:
        try:
            href = card.get_attribute("href") or ""

            title_elem = card.query_selector("h2")
            title = title_elem.inner_text().strip() if title_elem else ""
            if not title:
                continue

            loc_elem = card.query_selector(".mp-card-location")
            venue_name = loc_elem.inner_text().strip() if loc_elem else "Museum Berlin"

            # Enddatum
            time_elem = card.query_selector("time span[aria-hidden]")
            date_text = time_elem.inner_text().strip() if time_elem else ""

            end_date = None
            if date_text:
                date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", date_text)
                if date_match:
                    day = int(date_match.group(1))
                    month = int(date_match.group(2))
                    year_str = date_match.group(3)
                    year = int(year_str) if len(year_str) == 4 else 2000 + int(year_str)
                    try:
                        end_date = datetime(year, month, day)
                    except ValueError:
                        continue

            if not end_date or end_date.date() < now.date():
                continue

            event_link = f"https://www.museumsportal-berlin.de{href}" if href.startswith("/") else href

            exhibitions.append({
                "title": title,
                "end_date": end_date.strftime("%Y-%m-%d"),
                "venue_name": venue_name,
                "bezirk": "mitte",
                "link": event_link,
            })
            print(f"  + {title} (endet {end_date.strftime('%d.%m.%Y')})")

        except Exception as e:
            print(f"  Fehler: {e}")
            continue

    return exhibitions


def main():
    print("=" * 60)
    print("Museumsportal Berlin Scraper")
    print("=" * 60)
    print()
    print("Das Skript öffnet einen Browser.")
    print("Falls ein Captcha erscheint, löse es manuell.")
    print()

    with sync_playwright() as p:
        # Browser NICHT headless, damit du Captchas lösen kannst
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Events scrapen
        events = scrape_events(page)

        # Closing soon scrapen
        closing_soon = scrape_closing_soon(page)

        browser.close()

    # JSON speichern
    data = {
        "events": events,
        "closing_soon": closing_soon,
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
    }

    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print(f"Fertig! {len(events)} Events und {len(closing_soon)} Ausstellungen gespeichert.")
    print(f"Datei: {JSON_PATH}")
    print()
    print("Jetzt committen und pushen:")
    print("  git add data/museumsportal.json")
    print("  git commit -m 'Update Museumsportal events'")
    print("  git push")
    print("=" * 60)


if __name__ == "__main__":
    main()
