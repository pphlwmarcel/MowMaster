"""Constants for the MowMaster integration."""
from homeassistant.const import Platform

DOMAIN = "mowmaster"
PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
]

# Config flow & Options
CONF_MOWER_ENTITY = "mower_entity"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_LAWN_AREA = "lawn_area"
CONF_MOWER_TYPE = "mower_type"
CONF_MOWER_CAPACITY = "mower_capacity"
CONF_CONFIGURE_PRO = "configure_pro"

# Mower types
MOWER_TYPE_CHAOS = "chaos"
MOWER_TYPE_SYSTEMATIC = "systematic"

# Sensor Overrides & Physical Model Sources (Pro Settings)
CONF_SENSOR_TEMP = "sensor_temp"
CONF_SENSOR_HUMIDITY = "sensor_humidity"
CONF_SENSOR_DEW_POINT = "sensor_dew_point"
CONF_SENSOR_RAIN = "sensor_rain"
CONF_SENSOR_MOWER_RAIN = "sensor_mower_rain"
CONF_SENSOR_RAIN_RADAR = "sensor_rain_radar"
CONF_SENSOR_MOISTURE_SCORE = "sensor_moisture_score"
CONF_SENSOR_WIND = "sensor_wind"
CONF_SENSOR_SOLAR = "sensor_solar"
CONF_SENSOR_SOLAR_DIFF = "sensor_solar_diff"
CONF_SENSOR_SOIL = "sensor_soil"
CONF_SENSOR_BATTERY = "sensor_battery"

# Thresholds & Constraints
CONF_DEW_SPREAD_MIN = "dew_spread_min"
CONF_MIN_TEMP = "min_temp"
CONF_HEAT_LIMIT = "heat_limit"
CONF_MOISTURE_THRESHOLD = "moisture_threshold"
CONF_RADAR_RAIN_BUFFER = "radar_rain_buffer"
CONF_WILDLIFE_ENABLED = "wildlife_enabled"
CONF_WILDLIFE_SUNRISE_OFFSET = "wildlife_sunrise_offset"
CONF_WILDLIFE_SUNSET_OFFSET = "wildlife_sunset_offset"
CONF_QUIET_HOURS_START = "quiet_hours_start"
CONF_QUIET_HOURS_END = "quiet_hours_end"
CONF_MIN_BATTERY_LEVEL = "min_battery_level"
CONF_MAX_RUN_TIME = "max_run_time"
CONF_MULTI_CYCLE = "multi_cycle"
CONF_EDGE_CUT_INTERVAL = "edge_cut_interval"
CONF_EDGE_CUT_SERVICE = "edge_cut_service"
CONF_EDGE_CUT_DATA = "edge_cut_data"

# Defaults
DEFAULT_LAWN_AREA = 250.0  # m²
DEFAULT_MOWER_TYPE = MOWER_TYPE_CHAOS
DEFAULT_CAPACITY_CHAOS = 50.0  # m²/h
DEFAULT_CAPACITY_SYSTEMATIC = 120.0  # m²/h
DEFAULT_DEW_SPREAD_MIN = 2.5  # °C
DEFAULT_MIN_TEMP = 9.0  # °C (safe grass cutting minimum)
DEFAULT_HEAT_LIMIT = 28.0  # °C
DEFAULT_MOISTURE_THRESHOLD = 3.0  # pts (below 3 pts is dry)
DEFAULT_RADAR_RAIN_BUFFER = 60  # minutes ahead for rain radar
DEFAULT_MIN_BATTERY = 80  # %
DEFAULT_WILDLIFE_SUNRISE = 60  # minutes after sunrise
DEFAULT_WILDLIFE_SUNSET = 90  # minutes before sunset
DEFAULT_QUIET_HOURS_START = "20:00"
DEFAULT_QUIET_HOURS_END = "08:00"
DEFAULT_MAX_RUN_TIME = 0  # 0 = unlimited / normal battery depletion
DEFAULT_MULTI_CYCLE = True
DEFAULT_EDGE_CUT_INTERVAL = 0  # 0 = disabled

# Storage keys
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_data"

# Service / Event Names
ATTR_REASONS = "blocking_reasons"
ATTR_MOISTURE_SCORE = "moisture_score"
ATTR_DEW_POINT = "dew_point"
ATTR_DEW_SPREAD = "dew_spread"
ATTR_GROWTH_INDEX = "growth_index"
ATTR_GDD = "growing_degree_days"
ATTR_DAYS_SINCE_FERTILIZED = "days_since_fertilized"
ATTR_TARGET_MINUTES = "target_daily_minutes"
ATTR_MOWED_MINUTES = "mowed_minutes_today"
ATTR_REMAINING_MINUTES = "remaining_minutes_today"
ATTR_RUNS_COUNT = "total_runs_count"
ATTR_DRYING_RATE = "drying_rate"
ATTR_WETTING_RATE = "wetting_rate"

