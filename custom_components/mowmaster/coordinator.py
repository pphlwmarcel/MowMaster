"""DataUpdateCoordinator for the MowMaster integration."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    ATTR_TEMPERATURE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import homeassistant.util.dt as dt_util

from .config_flow import discover_companion_sensors
from .const import (
    CONF_CLEARED_SENSORS,
    CONF_DEW_SPREAD_MIN,
    CONF_EDGE_CUT_DATA,
    CONF_EDGE_CUT_INTERVAL,
    CONF_EDGE_CUT_SERVICE,
    CONF_HEAT_LIMIT,
    CONF_LAWN_AREA,
    CONF_LAWN_IRRIGATED,
    CONF_MAX_RUN_TIME,
    CONF_MIN_BATTERY_LEVEL,
    CONF_MIN_TEMP,
    CONF_MOISTURE_THRESHOLD,
    CONF_MOWER_CAPACITY,
    CONF_MOWER_ENTITY,
    CONF_MOWER_TYPE,
    CONF_MULTI_CYCLE,
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    CONF_RADAR_RAIN_BUFFER,
    CONF_SENSOR_BATTERY,
    CONF_SENSOR_DEW_POINT,
    CONF_SENSOR_HUMIDITY,
    CONF_SENSOR_MOISTURE_SCORE,
    CONF_SENSOR_MOWER_RAIN,
    CONF_SENSOR_RAIN,
    CONF_SENSOR_RAIN_RADAR,
    CONF_SENSOR_SOIL,
    CONF_SENSOR_SOLAR,
    CONF_SENSOR_SOLAR_BINARY,
    CONF_SENSOR_SOLAR_DIFF,
    CONF_SENSOR_TEMP,
    CONF_SENSOR_WIND,
    CONF_SOLAR_DIFF_THRESHOLD,
    CONF_WEATHER_ENTITY,
    CONF_WILDLIFE_ENABLED,
    CONF_WILDLIFE_SUNRISE_OFFSET,
    CONF_WILDLIFE_SUNSET_OFFSET,
    DEFAULT_DEW_SPREAD_MIN,
    DEFAULT_HEAT_LIMIT,
    DEFAULT_LAWN_AREA,
    DEFAULT_LAWN_IRRIGATED,
    DEFAULT_MIN_BATTERY,
    DEFAULT_MIN_TEMP,
    DEFAULT_MOISTURE_THRESHOLD,
    DEFAULT_MOWER_TYPE,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_RADAR_RAIN_BUFFER,
    DEFAULT_SOLAR_DIFF_THRESHOLD,
    DEFAULT_WILDLIFE_SUNRISE,
    DEFAULT_WILDLIFE_SUNSET,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .engine import (
    MoistureStatus,
    calculate_daily_target_minutes,
    calculate_dew_point,
    calculate_drying_rate,
    calculate_fertilizer_factor,
    calculate_gdd,
    calculate_growth_index,
    calculate_soil_factor,
    calculate_wetting_rate,
    evaluate_slot,
    is_surface_dry,
)

_LOGGER = logging.getLogger(__name__)

MOWING_STATES = {"mowing", "cutting", "mow", "edgecut", "border_cut", "zoning"}
DOCKED_STATES = {"docked", "charging", "idle", "standby"}


class MowMasterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinates updates and state for MowMaster."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"MowMaster ({entry.title})",
            update_interval=timedelta(minutes=5),
        )
        self.entry = entry
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")

        # Persistent state
        self.last_fertilized_date: str | None = None
        self.mowed_minutes_today: float = 0.0
        self.last_reset_date: str = dt_util.now().date().isoformat()
        self.total_runs_count: int = 0
        self.edge_cut_next: bool = False
        self.auto_mow_enabled: bool = False
        self.internal_moisture_score: float = 0.0
        self._moisture_initialized: bool = False
        self._last_moisture_update: datetime = dt_util.now()

        # Cached forecast & daily observed temperatures
        self._cached_t_max: float | None = None
        self._cached_t_min: float | None = None
        self._observed_t_max: float | None = None
        self._observed_t_min: float | None = None
        self._last_forecast_fetch: datetime | None = None

        # Live session tracking & command debounce
        self._session_start_time: datetime | None = None
        self._last_mower_state: str | None = None
        self._last_auto_cmd_time: datetime | None = None
        self._unsub_trackers: list[CALLBACK_TYPE] = []

    async def async_setup(self) -> None:
        """Load stored data, auto-discover companion sensors, and register state change listeners."""
        now = dt_util.now()
        today_str = now.date().isoformat()

        # Auto-discover companion sensors and populate options if not already set or cleared
        discovered = discover_companion_sensors(
            self.hass,
            self._get_opt(CONF_MOWER_ENTITY),
            self._get_opt(CONF_WEATHER_ENTITY),
        )
        if discovered:
            current_opts = dict(self.entry.options)
            cleared = list(current_opts.get(CONF_CLEARED_SENSORS, []))
            updated_opts = False
            for k, v in discovered.items():
                if k not in current_opts and k not in cleared:
                    current_opts[k] = v
                    updated_opts = True
            if updated_opts:
                self.hass.config_entries.async_update_entry(self.entry, options=current_opts)

        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self.last_fertilized_date = stored.get("last_fertilized_date")
            self.mowed_minutes_today = float(stored.get("mowed_minutes_today", 0.0))
            self.last_reset_date = stored.get("last_reset_date", today_str)
            self.total_runs_count = int(stored.get("total_runs_count", 0))
            self.edge_cut_next = bool(stored.get("edge_cut_next", False))
            self.auto_mow_enabled = bool(stored.get("auto_mow_enabled", False))
            if "internal_moisture_score" in stored:
                self.internal_moisture_score = float(stored["internal_moisture_score"])
                self._moisture_initialized = True

            if stored.get("observed_t_max") is not None:
                self._observed_t_max = float(stored["observed_t_max"])
            if stored.get("observed_t_min") is not None:
                self._observed_t_min = float(stored["observed_t_min"])

            raw_sess = stored.get("session_start_time")
            if isinstance(raw_sess, str):
                parsed_sess = dt_util.parse_datetime(raw_sess)
                if parsed_sess and parsed_sess.date().isoformat() == today_str:
                    self._session_start_time = parsed_sess

        if self.last_reset_date != today_str:
            self.mowed_minutes_today = 0.0
            self._observed_t_max = None
            self._observed_t_min = None
            self._session_start_time = None
            self.last_reset_date = today_str
            await self._async_save()

        mower_entity = self._get_opt(CONF_MOWER_ENTITY)
        if mower_entity:
            # Check if mower is already mowing right now (e.g. after HA restart)
            st = self.hass.states.get(mower_entity)
            if st and (st.state or "").lower() in MOWING_STATES:
                self._last_mower_state = st.state.lower()
                if self._session_start_time is None:
                    self._session_start_time = now
                    await self._async_save()

            self._unsub_trackers.append(
                async_track_state_change_event(
                    self.hass, [mower_entity], self._handle_mower_state_change
                )
            )

        watch_list = [
            self._get_opt(CONF_WEATHER_ENTITY),
            self._get_opt(CONF_SENSOR_RAIN_RADAR),
            self._get_opt(CONF_SENSOR_RAIN),
            self._get_opt(CONF_SENSOR_MOWER_RAIN),
            self._get_opt(CONF_SENSOR_MOISTURE_SCORE),
        ]
        entities_to_watch = [e for e in watch_list if e]
        if entities_to_watch:
            self._unsub_trackers.append(
                async_track_state_change_event(
                    self.hass, entities_to_watch, self._handle_environment_change
                )
            )

    async def async_unload(self) -> None:
        """Unload listeners and save state."""
        for unsub in self._unsub_trackers:
            unsub()
        self._unsub_trackers.clear()
        await self._async_save()

    async def _async_save(self) -> None:
        """Save state to storage."""
        data = {
            "last_fertilized_date": self.last_fertilized_date,
            "mowed_minutes_today": round(self.mowed_minutes_today, 1),
            "last_reset_date": self.last_reset_date,
            "total_runs_count": self.total_runs_count,
            "edge_cut_next": self.edge_cut_next,
            "auto_mow_enabled": self.auto_mow_enabled,
            "internal_moisture_score": round(self.internal_moisture_score, 1),
            "session_start_time": (
                self._session_start_time.isoformat() if self._session_start_time else None
            ),
            "observed_t_max": self._observed_t_max,
            "observed_t_min": self._observed_t_min,
        }
        await self._store.async_save(data)

    def _get_opt(self, key: str, default: Any = None) -> Any:
        """Get an option from options dict, falling back to entry data."""
        if key in self.entry.options:
            return self.entry.options[key]
        return self.entry.data.get(key, default)

    @callback
    def _handle_mower_state_change(self, event: Event) -> None:
        """Handle real-time state changes of the robot mower."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if not new_state:
            return

        new_val = (new_state.state or "").lower()
        old_val = (old_state.state if old_state else "").lower()
        now = dt_util.now()

        if new_val in MOWING_STATES and old_val not in MOWING_STATES:
            _LOGGER.info("MowMaster: Mower started mowing session at %s", now)
            self._session_start_time = now
            self.total_runs_count += 1
            if self.edge_cut_next:
                self.edge_cut_next = False
            self.hass.async_create_task(self._async_save())

        elif old_val in MOWING_STATES and new_val not in MOWING_STATES:
            if self._session_start_time:
                duration_min = max(0.0, (now - self._session_start_time).total_seconds() / 60.0)
                self.mowed_minutes_today += duration_min
                _LOGGER.info(
                    "MowMaster: Session finished. Duration: %.1f min. Today: %.1f min",
                    duration_min,
                    self.mowed_minutes_today,
                )
                self._session_start_time = None
                self.hass.async_create_task(self._async_save())

        self._last_mower_state = new_val
        self.async_set_updated_data(self._calculate_all())

    @callback
    def _handle_environment_change(self, event: Event) -> None:
        """Handle real-time environmental changes (rain, radar, moisture score)."""
        data = self._calculate_all()
        self.async_set_updated_data(data)

        # Immediately recall mower if acute rain, heat, or wildlife hazard occurs while mowing
        if (
            self.auto_mow_enabled
            and data.get("current_mower_state") in MOWING_STATES
            and (
                data.get("rain_blocked")
                or data.get("heat_blocked")
                or data.get("wildlife_blocked")
            )
        ):
            self.hass.async_create_task(self._async_manage_auto_mow(data))

    def _get_sun_times(self, now: datetime) -> tuple[datetime | None, datetime | None, float, bool]:
        """Get sunrise, sunset, elevation and horizon status."""
        sunrise: datetime | None = None
        sunset: datetime | None = None
        elevation: float = 10.0
        above_horizon: bool = True

        try:
            from homeassistant.helpers import sun

            sr = sun.get_astral_event_date(self.hass, "sunrise", now.date())
            ss = sun.get_astral_event_date(self.hass, "sunset", now.date())
            if sr and ss:
                sunrise, sunset = sr, ss
        except Exception:
            pass

        sun_state = self.hass.states.get("sun.sun")
        if sun_state:
            above_horizon = sun_state.state.lower() != "below_horizon"
            if sun_state.attributes:
                if "elevation" in sun_state.attributes:
                    try:
                        elevation = float(sun_state.attributes["elevation"])
                    except (ValueError, TypeError):
                        pass
                if not sunrise and "next_rising" in sun_state.attributes:
                    sunrise = dt_util.parse_datetime(sun_state.attributes["next_rising"])
                if not sunset and "next_setting" in sun_state.attributes:
                    sunset = dt_util.parse_datetime(sun_state.attributes["next_setting"])

        return sunrise, sunset, elevation, above_horizon

    async def _async_fetch_forecast(self, weather_entity: str | None) -> None:
        """Fetch daily or hourly max/min forecast using HA weather.get_forecasts service."""
        now = dt_util.now()
        if (
            self._last_forecast_fetch
            and (now - self._last_forecast_fetch).total_seconds() < 1800
            and self._cached_t_max is not None
        ):
            return

        candidates = [weather_entity] if weather_entity else []
        candidates.extend(["weather.forecast_home", "weather.openweathermap"])

        for ent in [c for c in candidates if c]:
            st = self.hass.states.get(ent)
            if not st or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue

            # Try daily forecast first, then hourly fallback
            for fc_type in ("daily", "hourly"):
                try:
                    res = await self.hass.services.async_call(
                        "weather",
                        "get_forecasts",
                        {"entity_id": ent, "type": fc_type},
                        blocking=True,
                        return_response=True,
                    )
                    if isinstance(res, dict) and ent in res:
                        fc_list = res[ent].get("forecast")
                        if isinstance(fc_list, list) and len(fc_list) > 0:
                            if fc_type == "daily":
                                first = fc_list[0]
                                if "temperature" in first and first["temperature"] is not None:
                                    self._cached_t_max = float(first["temperature"])
                                    low = first.get("templow")
                                    self._cached_t_min = (
                                        float(low) if low is not None else self._cached_t_max - 6.0
                                    )
                                    self._last_forecast_fetch = now
                                    return
                            else:
                                temps = [
                                    float(item["temperature"])
                                    for item in fc_list[:24]
                                    if isinstance(item, dict) and item.get("temperature") is not None
                                ]
                                if temps:
                                    self._cached_t_max = max(temps)
                                    self._cached_t_min = min(temps)
                                    self._last_forecast_fetch = now
                                    return
                except Exception as err:
                    _LOGGER.debug("Could not get %s forecast from %s: %s", fc_type, ent, err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch updated data and execute autonomous decision checks."""
        now = dt_util.now()
        today_str = now.date().isoformat()
        if self.last_reset_date != today_str:
            if self._session_start_time:
                self._session_start_time = now
            self.mowed_minutes_today = 0.0
            self._observed_t_max = None
            self._observed_t_min = None
            self.last_reset_date = today_str
            await self._async_save()

        # Fetch latest daily forecast from weather service
        weather_entity = self._get_opt(CONF_WEATHER_ENTITY)
        await self._async_fetch_forecast(weather_entity)

        data = self._calculate_all()
        await self._async_save()
        await self._async_manage_auto_mow(data)
        return data

    def _calculate_all(self) -> dict[str, Any]:
        """Perform all mathematical, physical rate and status evaluations."""
        now = dt_util.now()

        # 0. Astronomical location (latitude & day of year)
        latitude: float = 50.0
        if hasattr(self.hass, "config") and self.hass.config.latitude is not None:
            try:
                latitude = float(self.hass.config.latitude)
            except (ValueError, TypeError):
                pass
        day_of_year = now.timetuple().tm_yday

        # 1. Temperature: Prioritize local temperature sensor
        current_temp: float | None = None
        temp_sensor = self._get_opt(CONF_SENSOR_TEMP)
        if temp_sensor:
            st = self.hass.states.get(temp_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    current_temp = float(st.state)
                except ValueError:
                    pass

        # 2. Weather entity reading
        weather_entity = self._get_opt(CONF_WEATHER_ENTITY)
        weather_state = self.hass.states.get(weather_entity) if weather_entity else None

        if not weather_state or weather_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            for alt_w in ["weather.forecast_home", "weather.openweathermap"]:
                alt_st = self.hass.states.get(alt_w)
                if alt_st and alt_st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    weather_state = alt_st
                    break

        current_humidity: float = 70.0
        weather_cond: str = "sunny"

        if weather_state and weather_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            weather_cond = weather_state.state
            attrs = weather_state.attributes
            if current_temp is None and ATTR_TEMPERATURE in attrs and attrs[ATTR_TEMPERATURE] is not None:
                current_temp = float(attrs[ATTR_TEMPERATURE])
            if "humidity" in attrs and attrs["humidity"] is not None:
                current_humidity = float(attrs["humidity"])

        if current_temp is None:
            current_temp = 10.0

        # Track actual observed daily min and max temperatures
        if self._observed_t_max is None or current_temp > self._observed_t_max:
            self._observed_t_max = current_temp
        if self._observed_t_min is None or current_temp < self._observed_t_min:
            self._observed_t_min = current_temp

        # Override humidity with local sensor if configured
        hum_sensor = self._get_opt(CONF_SENSOR_HUMIDITY)
        if hum_sensor:
            st = self.hass.states.get(hum_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    current_humidity = float(st.state)
                except ValueError:
                    pass

        # 3. Forecast & Observed T_max and T_min for biological GDD
        if self._cached_t_max is not None and self._cached_t_min is not None:
            t_max = max(self._cached_t_max, self._observed_t_max)
            t_min = min(self._cached_t_min, self._observed_t_min)
        else:
            t_max = self._observed_t_max if self._observed_t_max is not None else current_temp
            t_min = (
                self._observed_t_min
                if self._observed_t_min is not None and self._observed_t_min < t_max
                else (current_temp - 4.0)
            )

        # 4. Dew point calculation or measurement
        dew_point: float
        dew_sensor = self._get_opt(CONF_SENSOR_DEW_POINT)
        if dew_sensor:
            st = self.hass.states.get(dew_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    dew_point = float(st.state)
                except ValueError:
                    dew_point = calculate_dew_point(current_temp, current_humidity)
            else:
                dew_point = calculate_dew_point(current_temp, current_humidity)
        else:
            dew_point = calculate_dew_point(current_temp, current_humidity)

        dew_spread = round(current_temp - dew_point, 2)

        # Rain rate sensor
        rain_sensor = self._get_opt(CONF_SENSOR_RAIN)
        rain_rate: float = 0.0
        if rain_sensor:
            st = self.hass.states.get(rain_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    rain_rate = float(st.state)
                except ValueError:
                    if st.state.lower() in ("on", "true", "wet"):
                        rain_rate = 1.0

        # Mower hardware rain sensor (e.g. binary_sensor.bobbi_regensensor)
        mower_rain_active = False
        mower_rain_sensor = self._get_opt(CONF_SENSOR_MOWER_RAIN)
        if mower_rain_sensor:
            st = self.hass.states.get(mower_rain_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                mower_rain_active = st.state.lower() in ("on", "true", "wet")

        # Wind sensor
        wind_sensor = self._get_opt(CONF_SENSOR_WIND)
        wind_speed: float = 0.0
        if wind_sensor:
            st = self.hass.states.get(wind_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    wind_speed = float(st.state)
                except ValueError:
                    pass

        # Solar difference (e.g. sensor.garten_sonnensensor_temperatur_ch3)
        solar_diff_sensor = self._get_opt(CONF_SENSOR_SOLAR_DIFF)
        diff_sonne: float = 0.0
        if solar_diff_sensor:
            st = self.hass.states.get(solar_diff_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    diff_sonne = float(st.state)
                except ValueError:
                    pass

        # Solar pyranometer (W/m² or lx)
        solar_sensor = self._get_opt(CONF_SENSOR_SOLAR)
        solar_rad: float = 0.0
        if solar_sensor:
            st = self.hass.states.get(solar_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    solar_rad = float(st.state)
                except ValueError:
                    pass

        # Binary sun sensor (on/off fallback)
        solar_bin_sensor = self._get_opt(CONF_SENSOR_SOLAR_BINARY)
        solar_binary_on: bool = False
        if solar_bin_sensor:
            st = self.hass.states.get(solar_bin_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                solar_binary_on = st.state.lower() in ("on", "true", "sunny", "1")

        solar_diff_threshold = float(
            self._get_opt(CONF_SOLAR_DIFF_THRESHOLD, DEFAULT_SOLAR_DIFF_THRESHOLD)
        )

        # Rain radar sensor (smart parsing of timestamp, mm, %, or minutes countdown)
        rain_radar_sensor = self._get_opt(CONF_SENSOR_RAIN_RADAR)
        radar_minutes: float | None = None
        radar_sum: float | None = None
        if rain_radar_sensor:
            st = self.hass.states.get(rain_radar_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                attrs = st.attributes or {}
                for sum_attr in ("sum", "precipitation", "rain"):
                    if sum_attr in attrs and attrs[sum_attr] is not None:
                        try:
                            radar_sum = float(attrs[sum_attr])
                            break
                        except (ValueError, TypeError):
                            pass

                parsed_time = dt_util.parse_datetime(st.state)
                if parsed_time:
                    diff_min = (parsed_time - now).total_seconds() / 60.0
                    # Ignore stale timestamps more than 2 minutes in the past
                    if -2.0 <= diff_min <= 1440.0:
                        radar_minutes = max(0.1, round(diff_min, 1))
                else:
                    try:
                        val = float(st.state)
                        unit = str(attrs.get("unit_of_measurement", "")).strip().lower()
                        if unit in ("mm", "l/m²", "l/m2", "mm/h", "in"):
                            radar_sum = val
                        elif unit == "%":
                            if val >= 65.0:
                                radar_sum = max(radar_sum or 0.0, 0.5)
                        else:
                            if unit in ("s", "sec", "seconds"):
                                val = val / 60.0
                            # Only treat positive values > 0 as a countdown in minutes
                            if val > 0.0:
                                radar_minutes = round(val, 1)
                    except ValueError:
                        pass

        # Sun astronomical position
        sunrise, sunset, elevation, above_horizon = self._get_sun_times(now)

        # 5. Biological Growth & GDD (including location-based photoperiod & irrigation)
        gdd = calculate_gdd(t_max=t_max, t_min=t_min)
        days_since_fert: int | None = None
        if self.last_fertilized_date:
            try:
                fert_d = date.fromisoformat(self.last_fertilized_date)
                days_since_fert = (now.date() - fert_d).days
            except Exception:
                pass

        soil_sensor = self._get_opt(CONF_SENSOR_SOIL)
        soil_pct: float | None = None
        if soil_sensor:
            st = self.hass.states.get(soil_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    soil_pct = float(st.state)
                except ValueError:
                    pass

        lawn_irrigated = bool(self._get_opt(CONF_LAWN_IRRIGATED, DEFAULT_LAWN_IRRIGATED))
        fert_factor = calculate_fertilizer_factor(days_since_fert)
        soil_factor = calculate_soil_factor(
            soil_moisture_percent=soil_pct,
            lawn_irrigated=lawn_irrigated,
            gdd=gdd,
        )
        growth_index, season_factor, daylight_hours = calculate_growth_index(
            gdd=gdd,
            latitude=latitude,
            day_of_year=day_of_year,
            fertilizer_factor=fert_factor,
            soil_factor=soil_factor,
        )

        # 6. Physical Drying & Wetting Rate Model (using local daylight hours)
        drying_rate = calculate_drying_rate(
            temp_c=current_temp,
            dew_c=dew_point,
            wind_kmh=wind_speed,
            diff_sonne=diff_sonne,
            solar_rad_wm2=solar_rad,
            solar_binary_on=solar_binary_on,
            solar_diff_threshold=solar_diff_threshold,
            rain_mm=rain_rate,
            mower_wet=mower_rain_active,
            weather_condition=weather_cond,
            sun_elevation=elevation,
            sun_below_horizon=not above_horizon,
            daylight_hours=daylight_hours,
        )

        wetting_rate = calculate_wetting_rate(
            temp_c=current_temp,
            dew_c=dew_point,
            humidity_percent=current_humidity,
            wind_kmh=wind_speed,
            diff_sonne=diff_sonne,
            rain_mm=rain_rate,
            mower_wet=mower_rain_active,
            weather_condition=weather_cond,
            sun_elevation=elevation,
        )

        # Moisture score determination (external helper or internal physical integration)
        score_sensor = self._get_opt(CONF_SENSOR_MOISTURE_SCORE)
        moisture_score: float
        if score_sensor:
            st = self.hass.states.get(score_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    moisture_score = float(st.state)
                except ValueError:
                    moisture_score = self.internal_moisture_score
            else:
                moisture_score = self.internal_moisture_score
        else:
            elapsed_sec = max(0.0, (now - self._last_moisture_update).total_seconds())
            delta_hours = min(1.0, elapsed_sec / 3600.0)
            self._last_moisture_update = now

            rain_active = (
                rain_rate > 0.0
                or mower_rain_active
                or any(
                    rc in weather_cond.lower()
                    for rc in ["rainy", "pouring", "lightning-rainy", "hail", "snowy", "snowy-rainy"]
                )
            )

            # Smart cold-start initialization if no saved state exists yet
            if not self._moisture_initialized:
                sun_shining = (
                    diff_sonne >= solar_diff_threshold
                    or solar_rad >= 120.0
                    or solar_binary_on
                )
                if rain_active:
                    self.internal_moisture_score = 75.0
                elif "fog" in weather_cond.lower() or current_humidity >= 88.0 or dew_spread < 1.5:
                    self.internal_moisture_score = 50.0
                elif current_humidity >= 75.0 and (elevation < 25.0 or not sun_shining):
                    self.internal_moisture_score = 35.0
                elif current_humidity >= 68.0:
                    self.internal_moisture_score = 15.0
                else:
                    self.internal_moisture_score = 0.0
                self._moisture_initialized = True
                _LOGGER.info(
                    "MowMaster: Seeded initial lawn moisture score to %.1f (humidity=%.0f%%, spread=%.1f°C)",
                    self.internal_moisture_score,
                    current_humidity,
                    dew_spread,
                )

            if rain_rate > 0.0 or mower_rain_active:
                self.internal_moisture_score = max(self.internal_moisture_score, 15.0)

            delta = (wetting_rate - drying_rate) * delta_hours
            ziel_max = 100.0 if rain_active else max(self.internal_moisture_score, 55.0)
            self.internal_moisture_score = round(
                min(ziel_max, max(0.0, self.internal_moisture_score + delta)), 1
            )
            moisture_score = self.internal_moisture_score

        moisture_threshold = float(self._get_opt(CONF_MOISTURE_THRESHOLD, DEFAULT_MOISTURE_THRESHOLD))
        dew_spread_min = float(self._get_opt(CONF_DEW_SPREAD_MIN, DEFAULT_DEW_SPREAD_MIN))
        is_dry, _ = is_surface_dry(
            moisture_score=moisture_score,
            moisture_threshold=moisture_threshold,
            dew_spread=dew_spread,
            dew_spread_threshold=dew_spread_min,
            mower_rain_sensor=mower_rain_active,
            sun_elevation=elevation,
        )

        if rain_rate > 0.0 or mower_rain_active:
            desc = "Regen / Mähersensor nass"
        elif moisture_score >= 10.0:
            desc = "Nass / Feuchtes Rasenkonto"
        elif not is_dry:
            desc = "Abtrocknend / Morgentau"
        else:
            desc = "Trocken"

        moisture_status = MoistureStatus(
            dew_point=dew_point,
            dew_spread=dew_spread,
            moisture_score=moisture_score,
            is_dry=is_dry,
            state_description=desc,
            drying_rate=drying_rate,
            wetting_rate=wetting_rate,
        )

        # 7. Daily Mowing Budget
        lawn_area = float(self._get_opt(CONF_LAWN_AREA, DEFAULT_LAWN_AREA))
        mower_type = self._get_opt(CONF_MOWER_TYPE, DEFAULT_MOWER_TYPE)
        custom_cap = self._get_opt(CONF_MOWER_CAPACITY)

        target_minutes = calculate_daily_target_minutes(
            lawn_area_m2=lawn_area,
            mower_type=mower_type,
            growth_index=growth_index,
            custom_capacity_m2h=custom_cap,
        )

        elapsed_today = self.mowed_minutes_today
        if self._session_start_time:
            ongoing_min = max(0.0, (now - self._session_start_time).total_seconds() / 60.0)
            elapsed_today += ongoing_min

        remaining_minutes = max(0, int(round(target_minutes - elapsed_today)))

        # 8. Mower & Battery status
        mower_entity = self._get_opt(CONF_MOWER_ENTITY)
        mower_state = self.hass.states.get(mower_entity) if mower_entity else None
        current_mower_state = (mower_state.state or "unknown").lower() if mower_state else "unknown"

        battery_level: float | None = None
        batt_sensor = self._get_opt(CONF_SENSOR_BATTERY)
        if batt_sensor:
            st = self.hass.states.get(batt_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    battery_level = float(st.state)
                except ValueError:
                    pass
        elif mower_state and mower_state.attributes:
            b_val = mower_state.attributes.get(ATTR_BATTERY_LEVEL) or mower_state.attributes.get("battery")
            if b_val is not None:
                try:
                    battery_level = float(b_val)
                except ValueError:
                    pass

        # 9. Slot Evaluation
        min_temp = float(self._get_opt(CONF_MIN_TEMP, DEFAULT_MIN_TEMP))
        heat_limit = float(self._get_opt(CONF_HEAT_LIMIT, DEFAULT_HEAT_LIMIT))
        radar_buffer = int(self._get_opt(CONF_RADAR_RAIN_BUFFER, DEFAULT_RADAR_RAIN_BUFFER))

        slot = evaluate_slot(
            now=now,
            current_temp=current_temp,
            humidity=current_humidity,
            dew_point=dew_point,
            weather_condition=weather_cond,
            moisture_score=moisture_score,
            moisture_threshold=moisture_threshold,
            rain_rate_mmh=rain_rate,
            mower_rain_sensor=mower_rain_active,
            rain_radar_minutes=radar_minutes,
            rain_radar_sum=radar_sum,
            radar_buffer_minutes=radar_buffer,
            battery_level=battery_level,
            sunrise=sunrise,
            sunset=sunset,
            sun_elevation=elevation,
            sun_above_horizon=above_horizon,
            growth_index=growth_index,
            daylight_hours=daylight_hours,
            dew_spread_threshold=dew_spread_min,
            min_temp=min_temp,
            heat_limit=heat_limit,
            wildlife_enabled=bool(self._get_opt(CONF_WILDLIFE_ENABLED, True)),
            wildlife_sunrise_offset=int(self._get_opt(CONF_WILDLIFE_SUNRISE_OFFSET, DEFAULT_WILDLIFE_SUNRISE)),
            wildlife_sunset_offset=int(self._get_opt(CONF_WILDLIFE_SUNSET_OFFSET, DEFAULT_WILDLIFE_SUNSET)),
            quiet_start=str(self._get_opt(CONF_QUIET_HOURS_START, DEFAULT_QUIET_HOURS_START)),
            quiet_end=str(self._get_opt(CONF_QUIET_HOURS_END, DEFAULT_QUIET_HOURS_END)),
            min_battery=int(self._get_opt(CONF_MIN_BATTERY_LEVEL, DEFAULT_MIN_BATTERY)),
            remaining_minutes_today=remaining_minutes,
            target_daily_minutes=target_minutes,
        )

        return {
            "mowing_permitted": slot.permitted,
            "blocking_reasons": slot.blocking_reasons,
            "rain_blocked": slot.rain_blocked,
            "dew_blocked": slot.dew_blocked,
            "heat_blocked": slot.heat_blocked,
            "cold_blocked": slot.cold_blocked,
            "wildlife_blocked": slot.wildlife_blocked,
            "quiet_hours_blocked": slot.quiet_hours_blocked,
            "battery_blocked": slot.battery_blocked,
            "seasonal_time_blocked": slot.seasonal_time_blocked,
            "growth_dormant_blocked": slot.growth_dormant_blocked,
            "urgency_score": slot.urgency_score,
            "moisture_status": moisture_status,
            "growth_index": growth_index,
            "season_factor": season_factor,
            "daylight_hours": daylight_hours,
            "latitude": latitude,
            "gdd": gdd,
            "days_since_fertilized": days_since_fert,
            "target_daily_minutes": target_minutes,
            "mowed_minutes_today": round(elapsed_today, 1),
            "remaining_minutes_today": remaining_minutes,
            "total_runs_count": self.total_runs_count,
            "edge_cut_next": self.edge_cut_next,
            "auto_mow_enabled": self.auto_mow_enabled,
            "current_mower_state": current_mower_state,
            "battery_level": battery_level,
            "temperature": current_temp,
            "humidity": current_humidity,
            "dew_point": dew_point,
            "dew_spread": dew_spread,
            "drying_rate": drying_rate,
            "wetting_rate": wetting_rate,
        }

    async def _async_manage_auto_mow(self, data: dict[str, Any]) -> None:
        """Autonomously dispatch or recall mower if auto_mow is enabled."""
        if not self.auto_mow_enabled:
            return

        mower_entity = self._get_opt(CONF_MOWER_ENTITY)
        if not mower_entity:
            return

        now = dt_util.now()
        # Prevent duplicate command spam within 45 seconds
        if self._last_auto_cmd_time and (now - self._last_auto_cmd_time).total_seconds() < 45:
            return

        current_state = data.get("current_mower_state", "unknown")
        is_permitted = data.get("mowing_permitted", False)
        remaining_min = data.get("remaining_minutes_today", 0)

        # Mower is active - check limits and acute weather changes
        if current_state in MOWING_STATES:
            max_run = int(self._get_opt(CONF_MAX_RUN_TIME, 0))
            if max_run > 0 and self._session_start_time:
                ongoing_min = (now - self._session_start_time).total_seconds() / 60.0
                if ongoing_min >= max_run:
                    _LOGGER.info("MowMaster: Max session limit reached (%.1f min). Recalling.", ongoing_min)
                    self._last_auto_cmd_time = now
                    await self.async_dock_mower()
                    return

            if remaining_min <= 0:
                _LOGGER.info("MowMaster: Daily budget finished. Recalling mower to dock.")
                self._last_auto_cmd_time = now
                await self.async_dock_mower()
                return

            if data.get("rain_blocked") or data.get("heat_blocked") or data.get("wildlife_blocked"):
                _LOGGER.warning(
                    "MowMaster: Unsafe condition (%s). Calling mower home immediately.",
                    data.get("blocking_reasons"),
                )
                self._last_auto_cmd_time = now
                await self.async_dock_mower()
                return

        # Mower is docked - check if conditions are green
        elif current_state in DOCKED_STATES:
            multi_cycle = bool(self._get_opt(CONF_MULTI_CYCLE, True))
            if is_permitted and remaining_min >= 15:
                if self.mowed_minutes_today == 0 or multi_cycle:
                    _LOGGER.info(
                        "MowMaster: Optimal slot! Remaining: %d min. Dispatching mower.",
                        remaining_min,
                    )
                    self._last_auto_cmd_time = now
                    await self.async_start_mowing()

    async def async_start_mowing(self) -> None:
        """Trigger mower start, executing edge-cutting service if scheduled."""
        mower_entity = self._get_opt(CONF_MOWER_ENTITY)
        if not mower_entity:
            return

        edge_interval = int(self._get_opt(CONF_EDGE_CUT_INTERVAL, 0))
        next_run_number = self.total_runs_count + 1
        should_cut_edge = self.edge_cut_next or (
            edge_interval > 0 and (next_run_number % edge_interval == 0)
        )

        edge_service = self._get_opt(CONF_EDGE_CUT_SERVICE)
        if should_cut_edge and edge_service and "." in str(edge_service):
            domain, svc = str(edge_service).split(".", 1)
            raw_data = self._get_opt(CONF_EDGE_CUT_DATA)
            call_data: dict[str, Any] = {"entity_id": mower_entity}
            if raw_data:
                try:
                    if isinstance(raw_data, str):
                        parsed = json.loads(raw_data)
                        if isinstance(parsed, dict):
                            call_data.update(parsed)
                except Exception as err:
                    _LOGGER.warning("Could not parse edge cut service data: %s", err)

            _LOGGER.info("MowMaster: Calling edge cut service %s with %s", edge_service, call_data)
            await self.hass.services.async_call(domain, svc, call_data, blocking=True)
            self.edge_cut_next = False
            await self._async_save()
            return

        _LOGGER.info("MowMaster: Calling lawn_mower.start_mowing for %s", mower_entity)
        await self.hass.services.async_call(
            "lawn_mower",
            "start_mowing",
            {"entity_id": mower_entity},
            blocking=True,
        )

    async def async_dock_mower(self) -> None:
        """Recall mower to dock."""
        mower_entity = self._get_opt(CONF_MOWER_ENTITY)
        if not mower_entity:
            return

        _LOGGER.info("MowMaster: Calling lawn_mower.dock for %s", mower_entity)
        await self.hass.services.async_call(
            "lawn_mower",
            "dock",
            {"entity_id": mower_entity},
            blocking=True,
        )

    async def async_set_fertilized(self, d: date | None = None) -> None:
        """Record fertilization date."""
        target_d = d or dt_util.now().date()
        self.last_fertilized_date = target_d.isoformat()
        await self._async_save()
        await self.async_refresh()

    async def async_toggle_auto_mow(self, enabled: bool) -> None:
        """Enable or disable autonomous mowing switch."""
        self.auto_mow_enabled = enabled
        await self._async_save()
        await self.async_refresh()

    async def async_set_edge_cut_next(self, enabled: bool) -> None:
        """Set or clear the edge cut next run flag."""
        self.edge_cut_next = enabled
        await self._async_save()
        await self.async_refresh()

    async def async_reset_daily_budget(self) -> None:
        """Reset mowed minutes counter for today."""
        self.mowed_minutes_today = 0.0
        self._session_start_time = None
        await self._async_save()
        await self.async_refresh()

    async def async_set_moisture_score(self, score: float) -> None:
        """Manually calibrate or set the internal lawn moisture score."""
        self.internal_moisture_score = round(max(0.0, min(100.0, float(score))), 1)
        self._moisture_initialized = True
        self._last_moisture_update = dt_util.now()
        await self._async_save()
        await self.async_refresh()
