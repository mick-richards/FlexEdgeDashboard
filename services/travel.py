"""Travel scanner — detects travel events from calendar and calculates emissions.

Scans Outlook calendar events for travel patterns (city-to-city subjects,
location-based keywords, Travel/Reizen categories) and matches against
known routes for distance estimation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from services.emissions import FACTORS, TRAVEL_MODES

DATA_DIR = Path(__file__).parent.parent / "data"

# ── Travel detection patterns ──

# Subject patterns that indicate travel (e.g., "Leiden - Den Haag", "Den Haag → Rotterdam")
CITY_SEPARATOR_RE = re.compile(
    r"^(.+?)\s*[-–→>]\s*(.+?)$"
)

# Keywords in subject or location that suggest travel
TRAVEL_KEYWORDS = [
    "reizen", "travel", "trein", "vlucht", "flight", "rijden",
    "station", "airport", "schiphol", "centraal", "intercity",
]

# Location keywords that indicate physical presence (not online)
PHYSICAL_KEYWORDS = [
    "kantoor", "office", "straat", "weg", "laan", "plein", "gracht",
    "building", "gebouw", "etage", "verdieping",
]

# Online meeting indicators (NOT travel)
ONLINE_KEYWORDS = [
    "teams", "zoom", "meet.google", "webex", "online",
    "microsoft teams", "teams-vergadering",
]


# ── Known routes ──

def load_known_routes() -> list[dict]:
    path = DATA_DIR / "known_routes.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("routes", [])
    return []


def save_known_routes(routes: list[dict]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / "known_routes.json"
    path.write_text(
        json.dumps({"routes": routes}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def match_route(subject: str, routes: list[dict]) -> dict | None:
    """Try to match a calendar subject against known routes."""
    subject_lower = subject.lower().strip()
    for route in routes:
        pattern = route["pattern"].lower()
        if pattern in subject_lower:
            return route
        # Try reverse if enabled
        if route.get("reverse"):
            parts = pattern.split(" - ")
            if len(parts) == 2:
                reverse_pattern = f"{parts[1]} - {parts[0]}"
                if reverse_pattern in subject_lower:
                    return route
    return None


# ── Event classification ──

def classify_event(event: dict) -> dict | None:
    """Classify a calendar event as travel or not.

    Returns a travel dict if it's a travel event, None otherwise.
    Event structure from Outlook MCP:
    {subject, start, end, location, categories, attendees, organizer, ...}
    """
    subject = event.get("subject", "")
    location = event.get("location", "")
    categories = event.get("categories", [])
    meeting_url = event.get("onlineMeetingUrl", "") or event.get("meetingUrl", "")

    subject_lower = subject.lower()
    location_lower = location.lower() if location else ""

    # Skip online meetings
    if meeting_url:
        return None
    for kw in ONLINE_KEYWORDS:
        if kw in location_lower or kw in subject_lower:
            return None

    # Check 1: Categories contain Travel/Reizen
    is_tagged = any(
        cat.lower() in ("travel", "reizen", "reis", "reistijd")
        for cat in (categories or [])
    )

    # Check 2: Subject matches city-to-city pattern
    city_match = CITY_SEPARATOR_RE.match(subject.strip())
    is_city_pattern = False
    from_city = ""
    to_city = ""
    if city_match:
        from_city = city_match.group(1).strip()
        to_city = city_match.group(2).strip()
        # Sanity: both parts should be short (city names, not full sentences)
        if len(from_city) < 30 and len(to_city) < 30:
            is_city_pattern = True

    # Check 3: Travel keywords in subject
    has_travel_keyword = any(kw in subject_lower for kw in TRAVEL_KEYWORDS)

    # Determine if this is travel
    if not (is_tagged or is_city_pattern or has_travel_keyword):
        return None

    # Extract date from event
    start = event.get("start", "")
    event_date = start[:10] if start else ""

    # Try to match known route
    routes = load_known_routes()
    route = match_route(subject, routes)

    result = {
        "date": event_date,
        "description": subject,
        "distance_km": route["distance_km"] if route else 0,
        "mode": route.get("mode", "Trein") if route else "Trein",
        "source": "Agenda",
        "matched_route": bool(route),
        "event_start": start,
        "event_end": event.get("end", ""),
    }

    if is_city_pattern and not route:
        result["from_city"] = from_city
        result["to_city"] = to_city
        result["needs_distance"] = True
    else:
        result["needs_distance"] = result["distance_km"] == 0

    return result


def scan_events(events: list[dict]) -> list[dict]:
    """Scan a list of calendar events and return detected travel events."""
    travel_events = []
    for event in events:
        result = classify_event(event)
        if result:
            travel_events.append(result)
    return travel_events


def calc_trip_co2(trip: dict) -> float:
    """Calculate CO₂e for a single trip."""
    km = trip.get("distance_km", 0)
    mode = trip.get("mode", "Trein")
    mode_key = TRAVEL_MODES.get(mode, "travel_train")
    factor = FACTORS.get(mode_key, 0.008)
    return km * factor
