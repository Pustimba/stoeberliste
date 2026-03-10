#!/usr/bin/env python3
"""
Listet alle Veranstalter vom Museumsportal auf.
Öffnet Browser, du navigierst manuell zur Seite, dann extrahiert es die Namen.
"""

from playwright.sync_api import sync_playwright

def main():
    print("=" * 60)
    print("Museumsportal - Veranstalter auflisten")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Navigiere zur Startseite
        print("\nBrowser öffnet sich...")
        page.goto("https://www.museumsportal-berlin.de", timeout=30000)

        print("\n" + "=" * 60)
        print("ANLEITUNG:")
        print("1. Navigiere im Browser zu:")
        print("   https://www.museumsportal-berlin.de/de/programm?event_type=film&event_type=konzert&event_type=vortraglesunggesprach")
        print("2. Warte bis die Seite geladen ist")
        print("3. Scrolle ganz nach unten um alle Events zu laden")
        print("4. Komm hierher zurück und drücke ENTER")
        print("=" * 60)

        input("\nENTER drücken wenn fertig...")

        # Veranstalter extrahieren
        venues = set()
        cards = page.query_selector_all(".mp-card-location")
        for card in cards:
            try:
                name = card.inner_text().strip()
                if name:
                    venues.add(name)
            except:
                pass

        print(f"\n{'=' * 60}")
        print(f"GEFUNDENE VERANSTALTER ({len(venues)}):")
        print("=" * 60)
        for venue in sorted(venues):
            print(f"  - {venue}")

        print("\n" + "=" * 60)
        print("Jetzt zur 'Endet bald' Seite:")
        print("   https://www.museumsportal-berlin.de/de/programm?closing_soon=1")
        print("=" * 60)

        input("\nENTER drücken wenn fertig...")

        # Nochmal extrahieren
        cards = page.query_selector_all(".mp-card-location")
        for card in cards:
            try:
                name = card.inner_text().strip()
                if name:
                    venues.add(name)
            except:
                pass

        browser.close()

        print(f"\n{'=' * 60}")
        print(f"ALLE VERANSTALTER ({len(venues)}):")
        print("=" * 60)
        for venue in sorted(venues):
            print(f"  - {venue}")
        print("=" * 60)

if __name__ == "__main__":
    main()
