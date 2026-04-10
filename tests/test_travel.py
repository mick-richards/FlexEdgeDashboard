"""Tests for services/travel.py — calendar travel detection and CO₂ calculation."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from services.travel import (
    match_route,
    classify_event,
    scan_events,
    calc_trip_co2,
    ONLINE_KEYWORDS,
)
from services.emissions import FACTORS


# ── match_route ──

class TestMatchRoute:
    ROUTES = [
        {"pattern": "den haag - leiden", "distance_km": 25, "mode": "Trein", "reverse": True},
        {"pattern": "amsterdam - rotterdam", "distance_km": 60, "mode": "Trein"},
    ]

    def test_exact_match(self):
        result = match_route("Den Haag - Leiden", self.ROUTES)
        assert result is not None
        assert result["distance_km"] == 25

    def test_case_insensitive(self):
        result = match_route("DEN HAAG - LEIDEN", self.ROUTES)
        assert result is not None

    def test_reverse_match(self):
        result = match_route("Leiden - Den Haag", self.ROUTES)
        assert result is not None
        assert result["distance_km"] == 25

    def test_no_reverse_when_disabled(self):
        result = match_route("Rotterdam - Amsterdam", self.ROUTES)
        assert result is None

    def test_forward_without_reverse(self):
        result = match_route("Amsterdam - Rotterdam", self.ROUTES)
        assert result is not None
        assert result["distance_km"] == 60

    def test_no_match(self):
        result = match_route("Utrecht - Eindhoven", self.ROUTES)
        assert result is None

    def test_partial_match_in_longer_subject(self):
        result = match_route("Reis: Den Haag - Leiden (meeting)", self.ROUTES)
        assert result is not None

    def test_empty_routes(self):
        assert match_route("Den Haag - Leiden", []) is None


# ── classify_event ──

class TestClassifyEvent:
    @patch("services.travel.load_known_routes", return_value=[])
    def test_online_meeting_skipped(self, _mock):
        event = {"subject": "Team standup", "onlineMeetingUrl": "https://teams.microsoft.com/123"}
        assert classify_event(event) is None

    @patch("services.travel.load_known_routes", return_value=[])
    def test_teams_keyword_in_location_skipped(self, _mock):
        event = {"subject": "Weekly sync", "location": "Microsoft Teams"}
        assert classify_event(event) is None

    @patch("services.travel.load_known_routes", return_value=[])
    def test_zoom_keyword_in_subject_skipped(self, _mock):
        event = {"subject": "Zoom call with client", "location": ""}
        assert classify_event(event) is None

    @patch("services.travel.load_known_routes", return_value=[])
    def test_travel_category_detected(self, _mock):
        event = {
            "subject": "Klantbezoek",
            "categories": ["Reizen"],
            "start": "2026-04-10T09:00:00",
            "end": "2026-04-10T10:00:00",
        }
        result = classify_event(event)
        assert result is not None
        assert result["date"] == "2026-04-10"
        assert result["source"] == "Agenda"

    @patch("services.travel.load_known_routes", return_value=[])
    def test_reistijd_category_detected(self, _mock):
        event = {"subject": "Reistijd", "categories": ["Reistijd"],
                 "start": "2026-04-10T08:00:00"}
        result = classify_event(event)
        assert result is not None

    @patch("services.travel.load_known_routes", return_value=[
        {"pattern": "den haag - amsterdam", "distance_km": 60, "mode": "Trein"}
    ])
    def test_city_pattern_with_known_route(self, _mock):
        event = {
            "subject": "Den Haag - Amsterdam",
            "start": "2026-04-10T07:30:00",
            "end": "2026-04-10T08:30:00",
        }
        result = classify_event(event)
        assert result is not None
        assert result["distance_km"] == 60
        assert result["mode"] == "Trein"
        assert result["matched_route"] is True
        assert result.get("needs_distance") is False

    @patch("services.travel.load_known_routes", return_value=[])
    def test_city_pattern_without_known_route(self, _mock):
        event = {
            "subject": "Utrecht - Eindhoven",
            "start": "2026-04-10T09:00:00",
        }
        result = classify_event(event)
        assert result is not None
        assert result["from_city"] == "Utrecht"
        assert result["to_city"] == "Eindhoven"
        assert result["needs_distance"] is True
        assert result["distance_km"] == 0

    @patch("services.travel.load_known_routes", return_value=[])
    def test_travel_keyword_in_subject(self, _mock):
        event = {"subject": "Trein naar klant", "start": "2026-04-10T06:00:00"}
        result = classify_event(event)
        assert result is not None

    @patch("services.travel.load_known_routes", return_value=[])
    def test_schiphol_keyword(self, _mock):
        event = {"subject": "Meeting at Schiphol", "start": "2026-04-10T12:00:00"}
        result = classify_event(event)
        assert result is not None

    @patch("services.travel.load_known_routes", return_value=[])
    def test_non_travel_event_skipped(self, _mock):
        event = {"subject": "Lunch met team", "location": "Kantoor"}
        assert classify_event(event) is None

    @patch("services.travel.load_known_routes", return_value=[])
    def test_long_subject_not_city_pattern(self, _mock):
        """Subject with separator but parts >30 chars should not be treated as city pair."""
        event = {"subject": "This is a very long meeting title - and another very long description here"}
        assert classify_event(event) is None


# ── scan_events ──

class TestScanEvents:
    @patch("services.travel.load_known_routes", return_value=[])
    def test_filters_travel_events(self, _mock):
        events = [
            {"subject": "Team standup", "onlineMeetingUrl": "https://teams.com/x"},
            {"subject": "Trein naar klant", "start": "2026-04-10T06:00:00"},
            {"subject": "Lunch", "location": "Kantoor"},
        ]
        results = scan_events(events)
        assert len(results) == 1
        assert results[0]["description"] == "Trein naar klant"


# ── calc_trip_co2 ──

class TestCalcTripCo2:
    def test_train(self):
        trip = {"distance_km": 60, "mode": "Trein"}
        assert calc_trip_co2(trip) == pytest.approx(60 * 0.008)

    def test_car_petrol(self):
        trip = {"distance_km": 100, "mode": "Auto (benzine)"}
        assert calc_trip_co2(trip) == pytest.approx(100 * 0.19)

    def test_short_flight(self):
        trip = {"distance_km": 500, "mode": "Vlucht (<800 km)"}
        assert calc_trip_co2(trip) == pytest.approx(500 * 0.18)

    def test_zero_distance(self):
        trip = {"distance_km": 0, "mode": "Trein"}
        assert calc_trip_co2(trip) == 0.0

    def test_unknown_mode_defaults_to_train(self):
        trip = {"distance_km": 50, "mode": "Raket"}
        assert calc_trip_co2(trip) == pytest.approx(50 * 0.008)
