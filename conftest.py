"""Pytest root conftest: sys.path, fast no-sleep fetcher, fakes for NEA/ASMC payloads."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from src.data import fetcher  # noqa: E402


@pytest.fixture(autouse=True)
def _fast_fetcher(monkeypatch):
    """No backoff sleeps in tests; effectively unlimited NEA rate limit."""
    monkeypatch.setattr(fetcher, "_sleep", lambda s: None)
    monkeypatch.setattr(fetcher, "NEA_LIMITER", fetcher.RateLimiter(1000, 10))


@pytest.fixture(autouse=True)
def _isolate_history(monkeypatch, tmp_path):
    """History CSV writes land in a per-test temp dir, never the repo data/."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "HISTORY_CSV", tmp_path / "history_pm25.csv")


class FakeResponse:
    def __init__(self, text="", status_code=200, headers=None, json_data=None):
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}
        self._json = json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self._json is not None:
            return self._json
        return json.loads(self.text)

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")


class FakeSession:
    """routes: {url: FakeResponse | callable() -> FakeResponse}; records calls."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls: list[tuple[str, str]] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("get", url))
        route = self.routes.get(url)
        if callable(route):
            return route()
        return route if route is not None else FakeResponse("", 404)

    def post(self, url, data=None, headers=None, timeout=None):
        self.calls.append(("post", url))
        route = self.routes.get(url)
        if callable(route):
            return route()
        return route if route is not None else FakeResponse("", 404)


# ---------------------------------------------------------------------------
# NEA payload builders (shapes verified live 2026-09-17)
# ---------------------------------------------------------------------------
def make_pm25_payload(values: dict[str, float], timestamp="2026-09-17T17:00:00+08:00") -> dict:
    return {
        "code": 0,
        "data": {
            "regionMetadata": [
                {"name": "north", "labelLocation": {"latitude": 1.41803, "longitude": 103.82}},
                {"name": "south", "labelLocation": {"latitude": 1.29587, "longitude": 103.82}},
                {"name": "east", "labelLocation": {"latitude": 1.35735, "longitude": 103.94}},
                {"name": "west", "labelLocation": {"latitude": 1.35735, "longitude": 103.70}},
                {"name": "central", "labelLocation": {"latitude": 1.35735, "longitude": 103.82}},
            ],
            "items": [
                {
                    "date": "2026-09-17",
                    "updatedTimestamp": "2026-09-17T17:15:55+08:00",
                    "timestamp": timestamp,
                    "readings": {"pm25_one_hourly": values},
                }
            ],
        },
        "errorMsg": "",
    }


def make_psi_payload(psi: dict[str, float], pm25_24h: dict[str, float] | None = None) -> dict:
    pm = pm25_24h or {r: v * 0.5 for r, v in psi.items()}
    return {
        "code": 0,
        "data": {
            "regionMetadata": [],
            "items": [
                {
                    "date": "2026-09-17",
                    "updatedTimestamp": "2026-09-17T17:15:55+08:00",
                    "timestamp": "2026-09-17T17:00:00+08:00",
                    "readings": {
                        "psi_twenty_four_hourly": psi,
                        "pm25_twenty_four_hourly": pm,
                    },
                }
            ],
        },
        "errorMsg": "",
    }


def make_weather_payload(stations: dict[str, tuple[float, float]], values: dict[str, float], timestamp="2026-09-17T17:14:00+08:00") -> dict:
    return {
        "code": 0,
        "data": {
            "stations": [
                {"id": sid, "deviceId": sid, "name": f"Station {sid}",
                 "location": {"latitude": lat, "longitude": lon}}
                for sid, (lat, lon) in stations.items()
            ],
            "readings": [
                {"timestamp": timestamp, "data": [
                    {"stationId": sid, "value": v} for sid, v in values.items()
                ]},
            ],
            "readingType": "T",
            "readingUnit": "u",
        },
        "errorMsg": "",
    }


ASMC_TEXT = """***** Hotspot Count Report *****
Created On: 2026, September 17, 16:10:57
Satellite: NOAA20
Date & Time: 2026/09/17 06:23:00
Total Hotspot Count: 3 (Daytime High Confidence)

S/No  Longitude  Latitude
==============================
1    105.3273    -4.4527
2    101.4500    0.5000
3    110.0000    -1.0000
"""
