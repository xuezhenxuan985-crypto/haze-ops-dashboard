"""Central configuration for the haze ops dashboard.

Single source of truth for endpoints, thresholds, weights and mapping tables.
All layers may import this module; nothing else should define magic numbers.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
HISTORY_CSV = DATA_DIR / "history_pm25.csv"
HISTORY_HOURS = 48

# ---------------------------------------------------------------------------
# Regions (NEA 1-hr PM2.5 / 24-hr PSI reporting regions)
# ---------------------------------------------------------------------------
REGIONS = ["north", "south", "east", "west", "central"]

# Region anchors (NEA regionMetadata.labelLocation) — used as the reference
# point for auto-assigning rainfall stations to the nearest region. This is
# an approximation; see nea_weather.py.
REGION_ANCHORS = {
    "north": (1.41803, 103.82),
    "south": (1.29587, 103.82),
    "east": (1.35735, 103.94),
    "west": (1.35735, 103.70),
    "central": (1.35735, 103.82),
}

# Singapore reference point for transport risk geometry.
SINGAPORE_POINT = (1.35, 103.82)

# ---------------------------------------------------------------------------
# NEA endpoints (api-open.data.gov.sg v2 real-time; free, no key required)
# ---------------------------------------------------------------------------
NEA_BASE = "https://api-open.data.gov.sg/v2/real-time/api"
NEA_PM25_URL = f"{NEA_BASE}/pm25"
NEA_PSI_URL = f"{NEA_BASE}/psi"
NEA_WEATHER_URLS = {
    "rainfall": f"{NEA_BASE}/rainfall",
    "air_temperature": f"{NEA_BASE}/air-temperature",  # NOT "temperature" (403)
    "relative_humidity": f"{NEA_BASE}/relative-humidity",
    "wind_direction": f"{NEA_BASE}/wind-direction",
    "wind_speed": f"{NEA_BASE}/wind-speed",
}

# Anonymous v2 realtime API rate limit: 6 calls / 10 s (HTTP 429 above that).
NEA_RATE_LIMIT_CALLS = 6
NEA_RATE_LIMIT_WINDOW_S = 10
HTTP_RETRIES = 3
HTTP_BACKOFF_FACTOR = 1.5
USER_AGENT = "haze-ops-dashboard/1.0 (research tool; contact: site ops)"

# ---------------------------------------------------------------------------
# ASMC hotspot endpoints (no auth, no rate limits; verified 2026-09-17)
# ---------------------------------------------------------------------------
ASMC_HOTSPOT_TEXT_URL = "https://asmc.asean.org/files/msscommunity/hotspots/DailyJP1NOAA20.{region}.txt"
ASMC_HOTSPOT_REGIONS = {
    "sumatra": "sumatra",
    "kalimantan": "kalimantan",
    "p_malaysia": "p_malaysia",
}
ASMC_DAILY_COUNT_URL = (
    "https://asmc.asean.org/wp-content/themes/asmctheme/"
    "page-functions/functions-ajax-haze-daily-hotspot-count.php"
)
ASMC_KML_DISCOVERY_URL = (
    "https://asmc.asean.org/wp-content/themes/asmctheme/"
    "page-functions/functions-ajax-haze-hotspots.php"
)
ASMC_RSS_URL = "https://asmc.asean.org/feed/"

# ---------------------------------------------------------------------------
# NASA FIRMS (optional enrichment; free MAP_KEY via email registration)
# ---------------------------------------------------------------------------
FIRMS_CSV_URL_TEMPLATE = (
    "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_NOAA20_NRT/"
    "95.0,-6.0,120.0,8.0/1"
)

# Bounding boxes (west, south, east, north) for classifying FIRMS points
# into source regions. ASMC text files are already grouped by region.
# Order matters: p_malaysia is checked first because Sumatra's box extends
# to 6°N and would otherwise swallow points on the peninsula (lat >= 1°N).
SOURCE_BBOXES = {
    "p_malaysia": (99.5, 1.0, 105.0, 7.0),
    "sumatra": (95.0, -6.0, 106.0, 6.0),
    "kalimantan": (108.5, -4.5, 119.0, 5.0),
}

# ---------------------------------------------------------------------------
# Cache TTLs (seconds)
# ---------------------------------------------------------------------------
TTL_PM25 = 900          # NEA republishes hourly values ~every 15 min
TTL_PSI = 900
TTL_WEATHER = 300       # 1-5 min source cadence
TTL_HOTSPOTS = 900      # ASMC updates ~2x/day; poll cheaply
TTL_FIRMS = 1800
TTL_RSS = 1800
TTL_HISTORY = 300
TTL_SNAPSHOT = 300
FRAGMENT_REFRESH_S = 300

# ---------------------------------------------------------------------------
# Official band thresholds (haze.gov.sg / NEA; verified 2026-09-17)
# ---------------------------------------------------------------------------
# 1-hr PM2.5 bands: 1 Normal (0-55), 2 Elevated (56-150), 3 High (151-250),
# 4 Very High (>=251). NOTE: band 4 starts at 251 inclusive, not 250.
PM25_BAND_EDGES = (0, 55, 150, 250, 251)
# 24-hr PSI tiers: 1 Good (0-50), 2 Moderate (51-100), 3 Unhealthy (101-200),
# 4 Very unhealthy (201-300), 5 Hazardous (>300).
PSI_BAND_EDGES = (0, 50, 100, 200, 300, 301)

# ---------------------------------------------------------------------------
# Trend (µg/m³ per hour, last 3 hourly points)
# ---------------------------------------------------------------------------
TREND_WINDOW_POINTS = 3
TREND_STRONG_RISE = 10.0
TREND_MILD_RISE = 5.0
TREND_MILD_FALL = -5.0
TREND_STRONG_FALL = -10.0

# ---------------------------------------------------------------------------
# Transport risk (hotspots x wind sector)
# ---------------------------------------------------------------------------
SECTOR_HALF_WIDTH_DEG = 45.0
DISTANCE_BANDS_KM = ((400.0, 1.0), (700.0, 0.6))  # (upper bound, weight); else 0.3
WEIGHT_NO_WIND = 0.5
WEIGHT_SECTOR_MATCH = 1.0
WEIGHT_SECTOR_MISMATCH = 0.35
TRANSPORT_THRESHOLDS = (20.0, 80.0, 200.0)  # -> levels 1..4 (0 = none)
HOTSPOT_SURGE_FACTOR = 1.2   # applied when today's count >= 2x yesterday's
HOTSPOT_SURGE_RATIO = 2.0

# ---------------------------------------------------------------------------
# Regional risk score
# ---------------------------------------------------------------------------
TRANSPORT_LEVEL_ADDERS = {0: 0.0, 1: 0.5, 2: 1.0, 3: 1.5, 4: 1.5}
RAIN_SUPPRESSION_MM = 1.0
RAIN_SUPPRESSION_ADDER = -0.5
WIND_DISPERSION_KMH = 20.0
WIND_DISPERSION_ADDER = -0.5
RISK_LEVEL_CUTOFFS = (1.5, 2.5, 3.5)  # score -> level 1..4

# ---------------------------------------------------------------------------
# Station -> region mapping (curated; no official mapping exists)
# ---------------------------------------------------------------------------
# 18-station temp/RH network + Marina Barrage (wind only), assigned using
# official coordinates and NEA's town lists (see README). Unknown station
# IDs seen in live API responses are auto-assigned to the nearest
# REGION_ANCHORS entry at load time (logged).
STATION_REGION = {
    "S109": "central",   # Ang Mo Kio Avenue 5
    "S106": "east",      # Jalan Noordin, Pulau Ubin
    "S117": "west",      # Banyan Road, Jurong Island
    "S107": "east",      # East Coast Park
    "S104": "north",     # Woodlands Avenue 9
    "S115": "west",      # Tuas South Avenue 3
    "S116": "south",     # Pasir Panjang Terminal
    "S102": "west",      # Semakau Island
    "S80": "north",      # Sembawang Meteorological Station
    "S60": "south",      # Artillery Avenue, Sentosa
    "S50": "west",       # Clementi Road
    "S44": "west",       # Nanyang Avenue
    "S43": "east",       # Kim Chuan Road
    "S24": "east",       # Changi Meteorological Station
    "S23": "west",       # Tengah Meteorological Station
    "S06": "east",       # Paya Lebar Meteorological Station
    "S111": "south",     # Scotts Road
    "S121": "west",      # Old Choa Chu Kang Road
    "S108": "south",     # Marina Barrage (wind network only)
}

KNOTS_TO_KMH = 1.852

# ---------------------------------------------------------------------------
# Demo mode
# ---------------------------------------------------------------------------
DEMO_SCENARIOS = ["clear_day", "moderate_haze", "haze_episode"]
DEMO_SEEDS = {"clear_day": 11, "moderate_haze": 22, "haze_episode": 33}
