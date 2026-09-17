"""i18n: key parity across languages, every template formats, fallbacks."""
import re

import pytest

from src.i18n import STRINGS, tr

_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")

# Sample values for every named placeholder used anywhere in STRINGS.
SAMPLES = {
    "value": "78.0",
    "slope": "5.0",
    "points": "120",
    "upwind": "120",
    "band": "2",
    "level": "3",
    "refresh": "300",
    "region": "North",
    "band_name": "Elevated",
    "tier_name": "Unhealthy",
    "source": "Sumatra",
    "dir": "250",
    "speed": "12.0",
    "n": "25",
}


def test_language_key_sets_match():
    assert set(STRINGS["en"]) == set(STRINGS["zh"])


def test_no_unknown_languages():
    assert tr("app_title", "xx") == STRINGS["en"]["app_title"]  # falls back to en


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_all_templates_format(lang):
    for key, template in STRINGS[lang].items():
        placeholders = _PLACEHOLDER.findall(template)
        fmt = {p: SAMPLES.get(p, "X") for p in placeholders}
        out = tr(key, lang, **fmt)
        assert not out.startswith("["), f"{key} ({lang}): {out}"


def test_nested_keys_render_in_zh():
    # factor args carry i18n keys (band_name / source) — translated twice.
    args = {"value": "78.0", "band": "2", "band_name": tr("band_2", "zh")}
    out = tr("factor_pm25_band", "zh", **args)
    assert "偏高" in out  # band_2 zh translation


def test_missing_key_marker():
    assert tr("does_not_exist") == "[does_not_exist]"


def test_format_failure_marker():
    assert tr("factor_pm25_band") == "[factor_pm25_band:fmt]"


def test_wording_rule_spotcheck():
    # MOM >300 tier must minimise, never stop (full sweep in test_advisory).
    for lang in ("en", "zh"):
        text = tr("psi_action_4", lang).lower()
        assert "minimis" in text or "减少" in text or "尽量" in text
