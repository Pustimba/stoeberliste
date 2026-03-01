# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Kleine Terminliste is a Berlin event calendar aggregator for left-wing subculture and politics. It scrapes event data from various venues and presents them in a unified, searchable interface.

## Development Commands

### Running the Application

Development server:
```bash
python app.py
```

Production server with Gunicorn:
```bash
gunicorn -c gunicorn.conf.py app:app
```

### Dependencies

Install dependencies:
```bash
pip install -r requirements.txt
```

## Architecture

### Data Flow

1. **Event Scraping** - Scrapers fetch events from venue websites
2. **Event Normalization** - Extract title, date, time, description, type
3. **Caching** - Store in `_EVENT_CACHE` (in-memory) and optionally persist to JSON
4. **Display** - Render via Flask templates with filtering

### Key Data Structures

**Event dict:**
```python
{
    "id": "urania-2026-03-15-example-event",
    "title": "Example Event",
    "date": datetime(2026, 3, 15, 19, 0),
    "time": "19:00",
    "venue_slug": "urania",
    "venue_name": "Urania",
    "bezirk": "schoeneberg",
    "type": "diskussion",
    "description": "...",
    "link": "https://...",
}
```

### Routes

- `/` - All upcoming events
- `/tag/<datum>` - Events for a specific day (heute, morgen, YYYY-MM-DD)
- `/ort/<slug>` - Events at a specific venue
- `/typ/<slug>` - Events of a specific type
- `/bezirk/<slug>` - Events in a specific district
- `/woche` - Week overview
- `/suche` - Full-text search with filters
- `/merkliste` - Saved events

### Venue Configuration

Venues are defined in `VENUES` dict with:
- `name` - Display name
- `url` - Calendar page URL
- `bezirk` - District slug
- `adresse` - Physical address

### Event Types

- lesung, diskussion, film, konzert, party, workshop, theater, ausstellung, politik

## Scraper Guidelines

When adding a new venue scraper:

1. Add venue to `VENUES` dict
2. Create scraper function `_scrape_<venue_slug>()`
3. Return list of event dicts with required fields
4. Handle date parsing with `python-dateutil`
5. Add to scraper dispatch in refresh function

## Related Project

This project is related to [kleinestoeberkiste](https://github.com/Pustimba/rss-filter) - an RSS feed aggregator for political journalism.
