"""Optional AI operational briefing (Claude Messages API).

Turns the assembled Snapshot into a short, plain-language briefing for site
Ops/EHS managers. Same pattern as the FIRMS enrichment: the API key comes
from the sidebar, lives in session_state only, and is never logged or
persisted. Without a key — or on any API failure — the rest of the app
(rule-based tabs) is unaffected; the AI tab just shows guidance.

Layering: data layer. build_brief_payload is pure (snapshot -> prompt);
request_ai_brief does the HTTP call; sanitize_brief is the wording guardrail.
"""
from __future__ import annotations

import logging
import re

import requests

import config
from .models import Snapshot

log = logging.getLogger(__name__)


class AiBriefError(Exception):
    """Raised when the LLM call fails or returns no usable text."""


# 1-hr PM2.5 band -> plain label for the prompt (mirrors config thresholds).
BAND_LABELS = {1: "Normal", 2: "Elevated", 3: "High", 4: "Very High"}

# Wording guardrail: MOM's official guidance above PSI 300 is to MINIMISE
# outdoor work and postpone non-essential work — never "stop all work".
# Longest phrases first; English matched case-insensitively.
_BANNED_TO_MOM = [
    (re.compile(r"stop\s+all\s+(?:outdoor\s+)?work", re.IGNORECASE), "minimise outdoor work"),
    (re.compile(r"stop\s+work", re.IGNORECASE), "minimise outdoor work"),
    ("全面停止所有工作", "尽量减少户外作业"),
    ("全面停止工作", "尽量减少户外作业"),
    ("全面停工", "尽量减少户外作业"),
    ("停止一切户外工作", "尽量减少户外作业"),
    ("停止所有户外工作", "尽量减少户外作业"),
    ("停止户外工作", "尽量减少户外作业"),
    ("停工", "尽量减少户外作业"),
]

_SYSTEM_TEMPLATE = (
    "You are the operations briefing assistant for construction site managers in Singapore. "
    "Write a short, factual briefing based ONLY on the data provided by the user. "
    "Hard rules:\n"
    "- Never invent readings, forecasts, or hotspot counts.\n"
    "- Never tell the user to stop all work or shut down the site. The official MOM guidance "
    "for high PSI is to minimise outdoor work and postpone non-essential outdoor work — use that phrasing.\n"
    "- Keep the briefing under 200 words, in {lang}.\n"
    "- Use exactly three short sections with these headings: {h_today}, {h_actions}, {h_outlook}.\n"
    "- End with one line: {disclaimer}."
)


def build_brief_payload(snapshot: Snapshot, lang: str) -> dict[str, str]:
    """Snapshot -> (system, user) prompt pair. Pure; never contains the API key."""
    headings = (
        ("Today", "Actions", "Next 24 h", "Not official NEA/MOM guidance — check haze.gov.sg.")
        if lang == "en"
        else ("今日概况", "行动建议", "未来 24 小时展望", "非官方 NEA/MOM 指示——以 haze.gov.sg 为准。")
    )
    lang_name = "English" if lang == "en" else "Simplified Chinese (中文)"
    system = _SYSTEM_TEMPLATE.format(
        lang=lang_name, h_today=headings[0], h_actions=headings[1],
        h_outlook=headings[2], disclaimer=headings[3],
    )

    lines = [f"Mode: {snapshot.mode}", f"Data timestamp: {snapshot.fetched_at:%Y-%m-%d %H:%M SGT}"]
    for region, r in snapshot.pm25.items():
        p = snapshot.psi.get(region)
        w = snapshot.weather.get(region)
        parts = [
            f"PM2.5 1h {r.pm25_1h:.0f} ({BAND_LABELS.get(r.band, r.band)})",
            f"PSI 24h {p.psi_24h:.0f} (tier {p.tier})" if p else "PSI missing",
        ]
        if w is not None:
            wind = f"wind {w.wind_speed_kmh:.0f} km/h from {w.wind_dir_deg:.0f}°" \
                if w.wind_speed_kmh is not None else "wind unknown"
            parts.append(f"{wind}, rain {w.rainfall_mm:.1f} mm")
        lines.append(f"- {region}: {', '.join(parts)}")
    for source, hs in snapshot.hotspots.items():
        y = f" (yesterday {hs.yesterday_count})" if hs.yesterday_count is not None else ""
        lines.append(f"Hotspots {source}: {hs.count} today{y}")
    if snapshot.transport is not None:
        t = snapshot.transport
        lines.append(
            f"Transport risk: level {t.level}/4, upwind points {t.upwind_points}, "
            f"dominant source {t.dominant_source or 'none'}, wind available {t.wind_available}"
        )
    if snapshot.rss.level is not None:
        lines.append(f"ASMC alert level: {snapshot.rss.level}")
    if snapshot.analysis:
        worst = max(snapshot.analysis.values(), key=lambda a: a.mean)
        trend = (f"{worst.slope_per_day:+.2f}/day" if worst.slope_per_day is not None else "n/a")
        lines.append(f"14-day history: worst region {worst.region} "
                     f"(mean {worst.mean:.0f}, >55 {worst.pct_elevated:.0f}% of hours, trend {trend})")
    if snapshot.flags:
        lines.append(f"Data flags: {', '.join(snapshot.flags)}")
    return {"system": system, "user": "\n".join(lines)}


def request_ai_brief(
    payload: dict[str, str],
    api_key: str,
    session: requests.Session | None = None,
    timeout: float = config.ANTHROPIC_TIMEOUT_S,
) -> str:
    """One LLM call; returns the brief text or raises AiBriefError."""
    session = session or requests.Session()
    headers = {
        "x-api-key": api_key,
        "anthropic-version": config.ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    body = {
        "model": config.ANTHROPIC_MODEL,
        "max_tokens": config.ANTHROPIC_MAX_TOKENS,
        "system": payload["system"],
        "messages": [{"role": "user", "content": payload["user"]}],
    }
    try:
        resp = session.post(config.ANTHROPIC_URL, json=body, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        log.warning("ai brief request failed: %s", exc)
        raise AiBriefError(str(exc)) from exc
    if resp.status_code != 200:
        log.warning("ai brief HTTP %d: %s", resp.status_code, resp.text[:200])
        raise AiBriefError(f"HTTP {resp.status_code}")
    try:
        text = resp.json()["content"][0]["text"]
    except (ValueError, KeyError, IndexError) as exc:
        log.warning("ai brief unparseable response: %s", exc)
        raise AiBriefError("unparseable response") from exc
    text = text.strip()
    if not text:
        raise AiBriefError("empty response")
    return text


def sanitize_brief(text: str) -> tuple[str, bool]:
    """Replace any banned 'stop all work' phrasing with MOM-compliant wording.

    Returns (sanitized text, changed). The prompt already forbids the banned
    phrasing; this is the second line of defence for model output.
    """
    changed = False
    for pattern, replacement in _BANNED_TO_MOM:
        text, n = pattern.subn(replacement, text) if isinstance(pattern, re.Pattern) \
            else (text.replace(pattern, replacement), text.count(pattern))
        changed = changed or n > 0
    return text, changed
