"""DataUpdateCoordinator for the MowMaster integration."""
from __future__ import annotations

from datetime import date, datetime, timedelta
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

from .const import (
    ATTR_DAYS_SINCE_FERTILIZED,
    ATTR_DEW_POINT,
    ATTR_DEW_SPREAD,
    ATTR_DRYING_RATE,
    ATTR_GDD,
    ATTR_GROWTH_INDEX,
    ATTR_MOISTURE_SCORE,
    ATTR_MOWED_MINUTES,
    ATTR_REASONS,
    ATTR_REMAINING_MINUTES,
    ATTR_RUNS_COUNT,
    ATTR_TARGET_MINUTES,
    ATTR_WETTING_RATE,
    CONF_DEW_SPREAD_MIN,
    CONF_EDGE_CUT_DATA,
    CONF_EDGE_CUT_INTERVAL,
    CONF_EDGE_CUT_SERVICE,
    CONF_HEAT_LIMIT,
    CONF_LAWN_AREA,
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
    CONF_SENSOR_SOLAR_DIFF,
    CONF_SENSOR_TEMP,
    CONF_SENSOR_WIND,
    CONF_WEATHER_ENTITY,
    CONF_WILDLIFE_ENABLED,
    CONF_WILDLIFE_SUNRISE_OFFSET,
    CONF_WILDLIFE_SUNSET_OFFSET,
    DEFAULT_CAPACITY_CHAOS,
    DEFAULT_CAPACITY_SYSTEMATIC,
    DEFAULT_DEW_SPREAD_MIN,
    DEFAULT_HEAT_LIMIT,
    DEFAULT_LAWN_AREA,
    DEFAULT_MIN_BATTERY,
    DEFAULT_MIN_TEMP,
    DEFAULT_MOISTURE_THRESHOLD,
    DEFAULT_MOWER_TYPE,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_RADAR_RAIN_BUFFER,
    DEFAULT_WILDLIFE_SUNRISE,
    DEFAULT_WILDLIFE_SUNSET,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .engine import (
    MoistureStatus,
    SlotEvaluation,
    calculate_daily_target_minutes,
    calculate_dew_point,
    calculate_drying_rate,
    calculate_fertilizer_factor,
    calculate_gdd,
    calculate_growth_index,
    calculate_soil_factor,
    calculate_wetting_rate,
    evaluate_slot,
)

_LOGGER = logging.getLogger(__name__)

MOWING_STATES = {"mowing", "cutting", "mow"}
DOCKED_STATES = {"docked", "charging", "idle"}


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
        self._last_moisture_update: datetime = dt_util.now()

        # Live session tracking
        self._session_start_time: datetime | None = None
        self._last_mower_state: str | None = None
        self._unsub_trackers: list[CALLBACK_TYPE] = []

    async def async_setup(self) -> None:
        """Load stored data and register state change listeners."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self.last_fertilized_date = stored.get("last_fertilized_date")
            self.mowed_minutes_today = float(stored.get("mowed_minutes_today", 0.0))
            self.last_reset_date = stored.get("last_reset_date", dt_util.now().date().isoformat())
            self.total_runs_count = int(stored.get("total_runs_count", 0))
            self.edge_cut_next = bool(stored.get("edge_cut_next", False))
            self.auto_mow_enabled = bool(stored.get("auto_mow_enabled", False))
            self.internal_moisture_score = float(stored.get("internal_moisture_score", 0.0))

        # Date rollover check
        today_str = dt_util.now().date().isoformat()
        if self.last_reset_date != today_str:
            self.mowed_minutes_today = 0.0
            self.last_reset_date = today_str
            await self._async_save()

        # Listen to mower entity in real time
        mower_entity = self._get_opt(CONF_MOWER_ENTITY)
        if mower_entity:
            self._unsub_trackers.append(
                async_track_state_change_event(
                    self.hass, [mower_entity], self._handle_mower_state_change
                )
            )

        # Listen to weather, radar, moisture score and rain sensors in real time
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

        # Started mowing
        if new_val in MOWING_STATES and old_val not in MOWING_STATES:
            _LOGGER.info("MowMaster: Mower started mowing session at %s", now)
            self._session_start_time = now
            self.total_runs_count += 1
            if self.edge_cut_next:
                self.edge_cut_next = False
            self.hass.async_create_task(self._async_save())

        # Finished or docked
        elif old_val in MOWING_STATES and new_val not in MOWING_STATES:
            if self._session_start_time:
                duration_min = (now - self._session_start_time).total_seconds() / 60.0
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
        self.async_set_updated_data(self._calculate_all())

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

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch updated data and execute autonomous decision checks."""
        today_str = dt_util.now().date().isoformat()
        if self.last_reset_date != today_str:
            self.mowed_minutes_today = 0.0
            self.last_reset_date = today_str
            await self._async_save()

        data = self._calculate_all()
        await self._async_manage_auto_mow(data)
        return data

    def _calculate_all(self) -> dict[str, Any]:
        """Perform all mathematical, physical rate and status evaluations."""
        now = dt_util.now()

        # 1. Base weather readings
        weather_entity = self._get_opt(CONF_WEATHER_ENTITY)
        weather_state = self.hass.states.get(weather_entity) if weather_entity else None

        current_temp: float = 20.0
        current_humidity: float = 60.0
        weather_cond: str = "sunny"
        t_max: float = 22.0
        t_min: float = 12.0

        if weather_state and weather_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            weather_cond = weather_state.state
            attrs = weather_state.attributes
            if ATTR_TEMPERATURE in attrs and attrs[ATTR_TEMPERATURE] is not None:
                current_temp = float(attrs[ATTR_TEMPERATURE])
            if "humidity" in attrs and attrs["humidity"] is not None:
                current_humidity = float(attrs["humidity"])

            forecast = attrs.get("forecast")
            if isinstance(forecast, list) and len(forecast) > 0:
                first_fc = forecast[0]
                if "temperature" in first_fc and first_fc["temperature"] is not None:
                    t_max = float(first_fc["temperature"])
                if "templow" in first_fc and first_fc["templow"] is not None:
                    t_min = float(first_fc["templow"])
                else:
                    t_min = t_max - 8.0
            else:
                t_max = current_temp + 2.0
                t_min = max(4.0, current_temp - 6.0)

        # 2. Sensor Overrides
        temp_sensor = self._get_opt(CONF_SENSOR_TEMP)
        if temp_sensor:
            st = self.hass.states.get(temp_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    current_temp = float(st.state)
                except ValueError:
                    pass

        hum_sensor = self._get_opt(CONF_SENSOR_HUMIDITY)
        if hum_sensor:
            st = self.hass.states.get(hum_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    current_humidity = float(st.state)
                except ValueError:
                    pass

        # Dew point
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

        # Rain radar sensor (e.g. DWD radar)
        rain_radar_sensor = self._get_opt(CONF_SENSOR_RAIN_RADAR)
        radar_minutes: float | None = None
        radar_sum: float | None = None
        if rain_radar_sensor:
            st = self.hass.states.get(rain_radar_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                if st.attributes and "sum" in st.attributes:
                    try:
                        radar_sum = float(st.attributes["sum"])
                    except (ValueError, TypeError):
                        pass

                # Check if state is a timestamp
                parsed_time = dt_util.parse_datetime(st.state)
                if parsed_time:
                    diff_sec = (parsed_time - now).total_seconds()
                    radar_minutes = max(0.0, diff_sec / 60.0)
                else:
                    try:
                        radar_minutes = float(st.state)
                    except ValueError:
                        pass

        # Sun astronomical position
        sunrise, sunset, elevation, above_horizon = self._get_sun_times(now)

        # 3. Physical Drying & Wetting Rate Model
        drying_rate = calculate_drying_rate(
            temp_c=current_temp,
            dew_c=dew_point,
            wind_kmh=wind_speed,
            diff_sonne=diff_sonne,
            solar_rad_wm2=solar_rad,
            rain_mm=rain_rate,
            mower_wet=mower_rain_active,
            weather_condition=weather_cond,
            sun_elevation=elevation,
            sun_below_horizon=not above_horizon,
            now_month=now.month,
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

        # Moisture score determination (external helper or internal simulation)
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
            # Update internal score balance across time
            delta_hours = max(0.01, min(1.0, (now - self._last_moisture_update).total_seconds() / 3600.0))
            self._last_moisture_update = now
            delta = (wetting_rate - drying_rate) * delta_hours
            rain_active = (
                rain_rate > 0.0
                or mower_rain_active
                or any(
                    rc in weather_cond.lower()
                    for rc in ["rainy", "pouring", "lightning-rainy", "hail", "snowy", "snowy-rainy"]
                )
            )
            ziel_max = 100.0 if rain_active else max(self.internal_moisture_score, 55.0)
            self.internal_moisture_score = round(
                min(ziel_max, max(0.0, self.internal_moisture_score + delta)), 1
            )
            moisture_score = self.internal_moisture_score

        moisture_threshold = float(self._get_opt(CONF_MOISTURE_THRESHOLD, DEFAULT_MOISTURE_THRESHOLD))
        is_dry = (moisture_score < moisture_threshold) and not mower_rain_active and (dew_spread >= 1.5)

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

        # 4. Biological Growth & GDD
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

        fert_factor = calculate_fertilizer_factor(days_since_fert)
        soil_factor = calculate_soil_factor(soil_pct)
        growth_index = calculate_growth_index(gdd, fert_factor, soil_factor)

        # 5. Daily Mowing Budget
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
            ongoing_min = (now - self._session_start_time).total_seconds() / 60.0
            elapsed_today += ongoing_min

        remaining_minutes = max(0, int(target_minutes - elapsed_today))

        # 6. Mower & Battery status
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

        # 7. Slot Evaluation
        dew_spread_min = float(self._get_opt(CONF_DEW_SPREAD_MIN, DEFAULT_DEW_SPREAD_MIN))
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
            "urgency_score": slot.urgency_score,
            "moisture_status": moisture_status,
            "growth_index": growth_index,
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

        current_state = data.get("current_mower_state", "unknown")
        is_permitted = data.get("mowing_permitted", False)
        remaining_min = data.get("remaining_minutes_today", 0)

        # Mower is active - check limits and acute weather changes
        if current_state in MOWING_STATES:
            max_run = int(self._get_opt(CONF_MAX_RUN_TIME, 0))
            if max_run > 0 and self._session_start_time:
                now = dt_util.now()
                ongoing_min = (now - self._session_start_time).total_seconds() / 60.0
                if ongoing_min >= max_run:
                    _LOGGER.info("MowMaster: Max session limit reached (%.1f min). Recalling.", ongoing_min)
                    await self.async_dock_mower()
                    return

            if remaining_min <= 0:
                _LOGGER.info("MowMaster: Daily budget finished. Recalling mower to dock.")
                await self.async_dock_mower()
                return

            if data.get("rain_blocked") or data.get("heat_blocked") or data.get("wildlife_blocked"):
                _LOGGER.warning(
                    "MowMaster: Unsafe condition (%s). Calling mower home immediately.",
                    data.get("blocking_reasons"),
                )
                await self.async_dock_mower()
                return

        # Mower is docked - check if conditions are green
        elif current_state in DOCKED_STATES:
            multi_cycle = bool(self._get_opt(CONF_MULTI_CYCLE, True))
            if is_permitted and remaining_min >= 10:
                if self.mowed_minutes_today == 0 or multi_cycle:
                    _LOGGER.info(
                        "MowMaster: Optimal slot! Remaining: %d min. Dispatching mower.",
                        remaining_min,
                    )
                    await self.async_start_mowing()

    async def async_start_mowing(self) -> None:
        """Trigger mower start, executing edge-cutting service if scheduled."""
        mower_entity = self._get_opt(CONF_MOWER_ENTITY)
        if not mower_entity:
            return

        edge_interval = int(self._get_opt(CONF_EDGE_CUT_INTERVAL, 0))
        should_cut_edge = self.edge_cut_next or (
            edge_interval > 0 and (self.total_runs_count % edge_interval == 0)
        )

        edge_service = self._get_opt(CONF_EDGE_CUT_SERVICE)
        if should_cut_edge and edge_service and "." in edge_service:
            domain, svc = edge_service.split(".", 1)
            raw_data = self._get_opt(CONF_EDGE_CUT_DATA)
            call_data = {"entity_id": mower_entity}
            if raw_data:
                import json

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

