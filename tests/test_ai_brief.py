"""AI operational briefing: prompt building, wording guardrail, LLM call."""
from datetime import datetime, timedelta, timezone

import pytest
import requests

import config
from conftest import FakeResponse, FakeSession
from src.data import ai_brief
from src.data.ai_brief import AiBriefError, build_brief_payload, request_ai_brief, sanitize_brief
from src.data.models import (RSSStatus, RegionPM25, RegionPSI, RegionWeather,
                             Snapshot, SourceHotspots, TransportRisk)

SGT = timezone(timedelta(hours=8))


def _snapshot() -> Snapshot:
    return Snapshot(
        mode="demo",
        fetched_at=datetime(2026, 10, 1, 12, 0, tzinfo=SGT),
        freshness={},
        pm25={
            "central": RegionPM25(region="central", pm25_1h=64.0, band=2),
            "north": RegionPM25(region="north", pm25_1h=38.0, band=1),
        },
        psi={
            "central": RegionPSI(region="central", psi_24h=101.0, pm25_24h=76.0, tier=3),
            "north": RegionPSI(region="north", psi_24h=62.0, pm25_24h=40.0, tier=2),
        },
        weather={
            "central": RegionWeather(region="central", wind_speed_kmh=12.0,
                                     wind_dir_deg=250.0, rainfall_mm=0.0),
        },
        hotspots={
            "sumatra": SourceHotspots(source="sumatra", count=180, yesterday_count=90),
        },
        transport=TransportRisk(level=3, score=2.5, upwind_points=120,
                                dominant_source="sumatra", wind_available=True),
        advisories={},
        rss=RSSStatus(level=1),
        analysis={},
        flags=["flag_weather_partial"],
    )


# ---------------------------------------------------------------------------
# build_brief_payload
# ---------------------------------------------------------------------------
def test_payload_contains_rules_and_language():
    en = build_brief_payload(_snapshot(), "en")
    zh = build_brief_payload(_snapshot(), "zh")
    assert "based ONLY on the data provided" in en["system"]
    assert "Never tell the user to stop all work" in en["system"]
    assert "Today" in en["system"] and "English" in en["system"]
    assert "今日概况" in zh["system"] and "中文" in zh["system"]
    # The disclaimer line is demanded in both languages.
    assert "haze.gov.sg" in en["system"] and "haze.gov.sg" in zh["system"]


def test_payload_carries_snapshot_data_only():
    payload = build_brief_payload(_snapshot(), "en")
    user = payload["user"]
    assert "central: PM2.5 1h 64 (Elevated), PSI 24h 101 (tier 3)" in user
    assert "north: PM2.5 1h 38 (Normal)" in user
    assert "wind 12 km/h from 250" in user
    assert "Hotspots sumatra: 180 today (yesterday 90)" in user
    assert "Transport risk: level 3/4, upwind points 120" in user
    assert "Data flags: flag_weather_partial" in user
    # The API key must never appear in the payload (it is not even passed in).
    assert "sk-ant" not in user


# ---------------------------------------------------------------------------
# sanitize_brief — the wording guardrail
# ---------------------------------------------------------------------------
def test_sanitize_replaces_english_banned_phrasing():
    text, changed = sanitize_brief("The PSI is high. Please stop work immediately.")
    assert changed
    assert "stop work" not in text.lower()
    assert "minimise outdoor work" in text


def test_sanitize_english_case_insensitive():
    text, changed = sanitize_brief("Stop ALL Work on the rooftop.")
    assert changed
    assert "minimise outdoor work" in text


def test_sanitize_replaces_chinese_banned_phrasing():
    for banned in ("全面停工", "全面停止所有工作", "停止一切户外工作", "停工"):
        text, changed = sanitize_brief(f"建议{banned}半天。")
        assert changed, banned
        assert "停工" not in text
        assert "尽量减少户外作业" in text


def test_sanitize_leaves_compliant_text_untouched():
    text = "Minimise outdoor work and postpone non-essential work. 降雨停止后恢复作业。"
    out, changed = sanitize_brief(text)
    assert not changed
    assert out == text


def test_sanitize_does_not_touch_bare_stop_word():
    # "降雨停止" (rain stopped) must NOT be rewritten — only work-stopping phrases are banned.
    text = "降雨停止后可以恢复户外作业。"
    out, changed = sanitize_brief(text)
    assert not changed
    assert out == text


# ---------------------------------------------------------------------------
# request_ai_brief
# ---------------------------------------------------------------------------
def _ok_response(text: str) -> FakeResponse:
    return FakeResponse(json_data={"content": [{"text": text}]}, status_code=200)


def test_request_returns_text():
    session = FakeSession({config.ANTHROPIC_URL: _ok_response("  Brief text.  ")})
    assert request_ai_brief({"system": "s", "user": "u"}, "test-key", session=session) == "Brief text."
    assert ("post", config.ANTHROPIC_URL) in session.calls


def test_request_sends_workspace_header_only_when_given():
    class CaptureHeaders(FakeSession):
        def post(self, url, headers=None, **kwargs):
            self.last_headers = headers or {}
            return super().post(url, headers=headers, **kwargs)

    session = CaptureHeaders({config.ANTHROPIC_URL: _ok_response("ok")})
    request_ai_brief({"system": "s", "user": "u"}, "test-key", workspace_id="ws_123", session=session)
    assert session.last_headers.get("anthropic-workspace-id") == "ws_123"

    request_ai_brief({"system": "s", "user": "u"}, "test-key", session=session)
    assert "anthropic-workspace-id" not in session.last_headers


def test_request_http_error_raises():
    session = FakeSession({config.ANTHROPIC_URL: FakeResponse("nope", 401)})
    with pytest.raises(AiBriefError, match="401"):
        request_ai_brief({"system": "s", "user": "u"}, "test-key", session=session)


def test_request_error_includes_api_detail():
    body = FakeResponse(json_data={"error": {"type": "not_found_error",
                                             "message": "model: bad-name"}}, status_code=400)
    session = FakeSession({config.ANTHROPIC_URL: body})
    with pytest.raises(AiBriefError, match="not_found_error"):
        request_ai_brief({"system": "s", "user": "u"}, "test-key", session=session)
    with pytest.raises(AiBriefError, match="bad-name"):
        request_ai_brief({"system": "s", "user": "u"}, "test-key", session=session)


def test_request_unparseable_raises():
    session = FakeSession({config.ANTHROPIC_URL: FakeResponse(json_data={"content": []})})
    with pytest.raises(AiBriefError, match="unparseable"):
        request_ai_brief({"system": "s", "user": "u"}, "test-key", session=session)


def test_request_empty_text_raises():
    session = FakeSession({config.ANTHROPIC_URL: _ok_response("   ")})
    with pytest.raises(AiBriefError, match="empty"):
        request_ai_brief({"system": "s", "user": "u"}, "test-key", session=session)


def test_request_network_error_raises():
    class Boom(FakeSession):
        def post(self, url, **kwargs):
            raise requests.ConnectionError("down")

    with pytest.raises(AiBriefError, match="down"):
        request_ai_brief({"system": "s", "user": "u"}, "test-key", session=Boom())
