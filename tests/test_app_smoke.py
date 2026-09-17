"""Smoke-test the whole app via Streamlit's AppTest harness (demo mode).

Boots app.py in a fake runtime, switches to demo, and checks the page
renders without exceptions, in both languages.
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def at() -> AppTest:
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    app.run()
    assert not app.exception, app.exception
    app.sidebar.radio[0].set_value("demo").run()
    assert not app.exception, app.exception
    return app


def test_demo_page_renders(at: AppTest):
    assert at.session_state["mode"] == "demo"
    # KPI metrics present (5 of them).
    assert len(at.metric) >= 5
    # Tabs exist.
    assert len(at.tabs) == 3
    # Region cards / markdown rendered.
    assert at.markdown
    # Demo note flag shown (rendered as an info banner, not markdown).
    infos = " ".join(i.value for i in at.info)
    assert "Demo data" in infos or "演示数据" in infos


def test_zh_language_switch(at: AppTest):
    at.sidebar.segmented_control[0].set_value("中文").run()
    assert not at.exception, at.exception
    texts = " ".join(m.value for m in at.markdown)
    assert "雾霾运营台" in texts


def test_scenario_switch_changes_data(at: AppTest):
    def peak_pm25() -> float:
        values = [float(m.value) for m in at.metric if m.value.replace(".", "").isdigit()]
        return values[0] if values else 0.0

    at.sidebar.radio[0].set_value("demo").run()
    at.sidebar.selectbox[0].set_value("clear_day").run()
    clear = peak_pm25()
    at.sidebar.selectbox[0].set_value("haze_episode").run()
    episode = peak_pm25()
    assert episode > clear
