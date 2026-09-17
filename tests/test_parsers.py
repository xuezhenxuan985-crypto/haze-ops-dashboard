"""Parsers: ASMC fixed-width text, KML, FIRMS CSV/errors, RSS, NEA payloads."""
from datetime import datetime

from conftest import ASMC_TEXT, FakeResponse, FakeSession, make_pm25_payload, make_psi_payload, make_weather_payload

import config
from src.data import hotspots, nea_pm25, nea_psi, nea_weather


# ---------------------------------------------------------------------------
# ASMC fixed-width text
# ---------------------------------------------------------------------------
def test_parse_asmc_text_full():
    count, points, created = hotspots.parse_asmc_text(ASMC_TEXT)
    assert count == 3
    assert points == [(105.3273, -4.4527), (101.45, 0.5), (110.0, -1.0)]
    assert created == datetime(2026, 9, 17, 16, 10, 57)


def test_parse_asmc_text_empty():
    assert hotspots.parse_asmc_text("") == (0, [], None)


def test_parse_asmc_text_no_header():
    text = "1  101.45  0.50\n2  110.0  -1.0\n"
    count, points, _ = hotspots.parse_asmc_text(text)
    assert count == 2  # falls back to len(points)
    assert len(points) == 2


def test_parse_asmc_text_malformed_rows_skipped():
    text = "Total Hotspot Count: 1 (Daytime High Confidence)\n\n1  101.45  0.50\nbad row here\n2  200.5  50.0\n3  not-a-float  1.0\n"
    count, points, _ = hotspots.parse_asmc_text(text)
    assert count == 1  # header is the authority
    assert points == [(101.45, 0.5)]  # out-of-box and non-numeric rows skipped


def test_parse_asmc_text_crlf_and_bom():
    count, points, _ = hotspots.parse_asmc_text("﻿" + ASMC_TEXT.replace("\n", "\r\n"))
    assert count == 3
    assert len(points) == 3


def test_parse_asmc_text_multiple_sections_sum():
    """Real files concatenate several VIIRS granules (own header each);
    counts sum across sections and overlapping coordinates are deduped."""
    section_b = """***** Hotspot Count Report *****
Created On: 2026, September 17, 16:10:57
Satellite: NOAA20
Date & Time: 2026/09/17 06:24:00
Total Hotspot Count: 3 (Daytime High Confidence)

S/No  Longitude  Latitude
==============================
1    101.4500    0.5000
2    104.1000    -0.9000
3    112.5000    -2.5000
"""
    count, points, created = hotspots.parse_asmc_text(ASMC_TEXT + section_b)
    assert count == 6  # 3 + 3 summed
    assert len(points) == 5  # (101.45, 0.5) appears in both — deduped
    assert created == datetime(2026, 9, 17, 16, 10, 57)  # first section's stamp


# ---------------------------------------------------------------------------
# ASMC KML
# ---------------------------------------------------------------------------
KML = """<?xml version="1.0"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
<Placemark>
<Point><coordinates>101.45,0.50,0</coordinates></Point>
<ExtendedData>
<Data name="satellite"><value>NOAA20</value></Data>
<Data name="region"><value>Sumatra</value></Data>
</ExtendedData>
</Placemark>
<Placemark>
<Point><coordinates>110.0,-1.0,0</coordinates></Point>
<ExtendedData><Data name="region"><value>Kalimantan</value></Data></ExtendedData>
</Placemark>
<Placemark>
<Point><coordinates>120.0,5.0,0</coordinates></Point>
</Placemark>
</Document>
</kml>"""


def test_parse_asmc_kml():
    out = hotspots.parse_asmc_kml(KML)
    assert out["sumatra"] == [(101.45, 0.5)]
    assert out["kalimantan"] == [(110.0, -1.0)]


# ---------------------------------------------------------------------------
# FIRMS
# ---------------------------------------------------------------------------
def test_classify_firms_point():
    assert hotspots._classify_firms_point(102.0, -1.0) == "sumatra"
    assert hotspots._classify_firms_point(115.0, 0.0) == "kalimantan"
    assert hotspots._classify_firms_point(103.0, 3.0) == "p_malaysia"
    assert hotspots._classify_firms_point(10.0, 10.0) is None


FIRMS_CSV = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n" \
            "0.5,101.45,330,1.0,1.0,2026-09-17,0622,NOAA-20,VIIRS,high,2.0,300,8.5,D\n" \
            "-1.0,110.0,320,1.0,1.0,2026-09-17,0622,NOAA-20,VIIRS,nominal,2.0,300,5.0,D\n" \
            "50.0,50.0,300,1.0,1.0,2026-09-17,0622,NOAA-20,VIIRS,low,2.0,300,1.0,D\n"


def test_fetch_firms_parses_and_classifies():
    session = FakeSession({config.FIRMS_CSV_URL_TEMPLATE.format(key="GOODKEY"): FakeResponse(FIRMS_CSV, 200)})
    points, flag = hotspots.fetch_firms("GOODKEY", session=session)
    assert flag is None
    assert len(points) == 2  # the (50,50) point is outside source bboxes
    assert points[0]["confidence"] == "high"
    assert points[0]["source"] == "sumatra"


def test_fetch_firms_invalid_key():
    session = FakeSession({config.FIRMS_CSV_URL_TEMPLATE.format(key="BADKEY"): FakeResponse("Invalid MAP_KEY.", 400)})
    points, flag = hotspots.fetch_firms("BADKEY", session=session)
    assert points is None
    assert flag == "invalid_key"


def test_fetch_firms_missing_key():
    assert hotspots.fetch_firms("") == (None, None)


# ---------------------------------------------------------------------------
# RSS
# ---------------------------------------------------------------------------
RSS_XML = """<?xml version="1.0"?><rss version="2.0"><channel>
<title>ASMC</title>
<item><title>Subseasonal Weather Outlook (14-27 September 2026)</title><link>https://asmc.asean.org/x</link></item>
<item><title>Alert20260826 - Activation of Alert Level 3 for the Southern ASEAN Region</title><link>https://asmc.asean.org/y</link></item>
</channel></rss>"""


def test_fetch_rss_parses_alert_level():
    session = FakeSession({config.ASMC_RSS_URL: FakeResponse(RSS_XML, 200)})
    status = hotspots.fetch_rss(session=session)
    assert status.level == 3
    assert "Subseasonal" in status.title
    assert status.fetched_at is not None


def test_fetch_rss_failure_is_graceful():
    class Boom(FakeSession):
        def get(self, url, params=None, headers=None, timeout=None):
            raise ConnectionError("down")
    status = hotspots.fetch_rss(session=Boom())
    assert status.level is None
    assert status.fetched_at is None


# ---------------------------------------------------------------------------
# NEA loaders against fake sessions
# ---------------------------------------------------------------------------
def test_fetch_pm25_uses_region_names_not_order():
    values = {"central": 78.0, "north": 46.0, "south": 55.0, "west": 55.0, "east": 47.0}
    session = FakeSession({config.NEA_PM25_URL: FakeResponse(json_data=make_pm25_payload(values))})
    regions, updated = nea_pm25.fetch_pm25(session=session)
    assert set(regions) == set(config.REGIONS)
    assert regions["central"].pm25_1h == 78.0
    assert regions["north"].pm25_1h == 46.0
    assert updated.tzinfo is not None


def test_fetch_psi():
    session = FakeSession({config.NEA_PSI_URL: FakeResponse(json_data=make_psi_payload(
        {"north": 68.0, "south": 66.0, "west": 87.0, "east": 77.0, "central": 93.0},
    ))})
    regions, _ = nea_psi.fetch_psi(session=session)
    assert regions["central"].psi_24h == 93.0
    assert regions["central"].pm25_24h == 46.5


def test_fetch_weather_aggregates():
    # Wind stations both east (S24 Changi, S107 East Coast Park); S104 is north.
    session = FakeSession({
        config.NEA_WEATHER_URLS["rainfall"]: FakeResponse(json_data=make_weather_payload(
            {"S104": (1.44, 103.79)}, {"S104": 0.4})),
        config.NEA_WEATHER_URLS["air_temperature"]: FakeResponse(json_data=make_weather_payload(
            {"S104": (1.44, 103.79), "S24": (1.37, 103.98)}, {"S104": 30.0, "S24": 32.0})),
        config.NEA_WEATHER_URLS["relative_humidity"]: FakeResponse(json_data=make_weather_payload(
            {"S104": (1.44, 103.79), "S24": (1.37, 103.98)}, {"S104": 60.0, "S24": 70.0})),
        config.NEA_WEATHER_URLS["wind_speed"]: FakeResponse(json_data=make_weather_payload(
            {"S24": (1.37, 103.98), "S107": (1.30, 103.95)}, {"S24": 5.0, "S107": 7.0})),
        config.NEA_WEATHER_URLS["wind_direction"]: FakeResponse(json_data=make_weather_payload(
            {"S24": (1.37, 103.98), "S107": (1.30, 103.95)}, {"S24": 180.0, "S107": 200.0})),
    })
    weather, ts = nea_weather.fetch_weather(session=session)
    assert weather["north"].temp_c == 30.0
    assert weather["east"].temp_c == 32.0
    assert weather["north"].rainfall_mm == 0.4  # S104 curated -> north
    assert weather["east"].wind_speed_kmh == round(6.0 * config.KNOTS_TO_KMH, 1)
    # circular mean of 180 and 200 -> 190
    assert weather["east"].wind_dir_deg == 190.0


def test_fetch_weather_unknown_station_falls_back_to_nearest_anchor():
    # S999 not curated, located near Tuas (west).
    session = FakeSession({
        config.NEA_WEATHER_URLS["rainfall"]: FakeResponse(json_data=make_weather_payload({}, {})),
        config.NEA_WEATHER_URLS["air_temperature"]: FakeResponse(json_data=make_weather_payload(
            {"S999": (1.30, 103.65)}, {"S999": 28.0})),
        config.NEA_WEATHER_URLS["relative_humidity"]: FakeResponse(json_data=make_weather_payload({}, {})),
        config.NEA_WEATHER_URLS["wind_speed"]: FakeResponse(json_data=make_weather_payload({}, {})),
        config.NEA_WEATHER_URLS["wind_direction"]: FakeResponse(json_data=make_weather_payload({}, {})),
    })
    weather, _ = nea_weather.fetch_weather(session=session)
    assert weather["west"].temp_c == 28.0
