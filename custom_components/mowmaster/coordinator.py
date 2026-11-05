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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.util.dt as dt_util

from .const import (
    ATTR_DAYS_SINCE_FERTILIZED,
    ATTR_DEW_POINT,
    ATTR_DEW_SPREAD,
    ATTR_GDD,
    ATTR_GROWTH_INDEX,
    ATTR_MOISTURE_SCORE,
    ATTR_MOWED_MINUTES,
    ATTR_REASONS,
    ATTR_REMAINING_MINUTES,
    ATTR_RUNS_COUNT,
    ATTR_TARGET_MINUTES,
    CONF_DEW_SPREAD_MIN,
    CONF_EDGE_CUT_DATA,
    CONF_EDGE_CUT_INTERVAL,
    CONF_EDGE_CUT_SERVICE,
    CONF_HEAT_LIMIT,
    CONF_LAWN_AREA,
    CONF_MAX_RUN_TIME,
    CONF_MIN_BATTERY_LEVEL,
    CONF_MOWER_CAPACITY,
    CONF_MOWER_ENTITY,
    CONF_MOWER_TYPE,
    CONF_MULTI_CYCLE,
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    CONF_SENSOR_BATTERY,
    CONF_SENSOR_HUMIDITY,
    CONF_SENSOR_RAIN,
    CONF_SENSOR_RAIN_RADAR,
    CONF_SENSOR_SOIL,
    CONF_SENSOR_SOLAR,
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
    DEFAULT_MOWER_TYPE,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_WILDLIFE_SUNRISE,
    DEFAULT_WILDLIFE_SUNSET,
    DOMAIN,
    MOWER_TYPE_SYSTEMATIC,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .engine import (
    MoistureStatus,
    SlotEvaluation,
    calculate_daily_target_minutes,
    calculate_fertilizer_factor,
    calculate_gdd,
    calculate_growth_index,
    calculate_soil_factor,
    evaluate_moisture,
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

        # Live session tracking
        self._session_start_time: datetime | None = None
        self._last_mower_state: str | None = None
        self._unsub_trackers: list[CALLBACK_TYPE] = []

    async def async_setup(self) -> None:
        """Load stored data and register state change listeners."""
        # Load stored data
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self.last_fertilized_date = stored.get("last_fertilized_date")
            self.mowed_minutes_today = float(stored.get("mowed_minutes_today", 0.0))
            self.last_reset_date = stored.get("last_reset_date", dt_util.now().date().isoformat())
            self.total_runs_count = int(stored.get("total_runs_count", 0))
            self.edge_cut_next = bool(stored.get("edge_cut_next", False))
            self.auto_mow_enabled = bool(stored.get("auto_mow_enabled", False))

        # Check date rollover
        today_str = dt_util.now().date().isoformat()
        if self.last_reset_date != today_str:
            self.mowed_minutes_today = 0.0
            self.last_reset_date = today_str
            await self._async_save()

        # Listen to mower state changes in real time
        mower_entity = self._get_opt(CONF_MOWER_ENTITY)
        if mower_entity:
            self._unsub_trackers.append(
                async_track_state_change_event(
                    self.hass, [mower_entity], self._handle_mower_state_change
                )
            )

        # Listen to weather and radar changes
        radar_entity = self._get_opt(CONF_SENSOR_RAIN_RADAR)
        entities_to_watch = [e for e in [self._get_opt(CONF_WEATHER_ENTITY), radar_entity] if e]
        if entities_to_watch:
            self._unsub_trackers.append(
                async_track_state_change_event(
                    self.hass, entities_to_watch, self._handle_weather_state_change
                )
            )

    async def async_unload(self) -> None:
        """Unload listeners and save data."""
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

        # Mower started mowing
        if new_val in MOWING_STATES and old_val not in MOWING_STATES:
            _LOGGER.info("MowMaster: Mower started mowing session at %s", now)
            self._session_start_time = now
            self.total_runs_count += 1
            if self.edge_cut_next:
                self.edge_cut_next = False
            self.hass.async_create_task(self._async_save())

        # Mower finished or stopped mowing
        elif old_val in MOWING_STATES and new_val not in MOWING_STATES:
            if self._session_start_time:
                duration_min = (now - self._session_start_time).total_seconds() / 60.0
                self.mowed_minutes_today += duration_min
                _LOGGER.info(
                    "MowMaster: Mowing session ended. Duration: %.1f min. Today total: %.1f min",
                    duration_min,
                    self.mowed_minutes_today,
                )
                self._session_start_time = None
                self.hass.async_create_task(self._async_save())

        self._last_mower_state = new_val
        self.async_set_updated_data(self._calculate_all())

    @callback
    def _handle_weather_state_change(self, event: Event) -> None:
        """Handle real-time changes to weather or rain radar."""
        self.async_set_updated_data(self._calculate_all())

    def _get_sun_times(self, now: datetime) -> tuple[datetime | None, datetime | None]:
        """Get sunrise and sunset for today."""
        try:
            from homeassistant.helpers import sun

            sr = sun.get_astral_event_date(self.hass, "sunrise", now.date())
            ss = sun.get_astral_event_date(self.hass, "sunset", now.date())
            if sr and ss:
                return sr, ss
        except Exception:
            pass

        # Fallback using sun.sun state
        sun_state = self.hass.states.get("sun.sun")
        if sun_state and sun_state.attributes:
            nr = sun_state.attributes.get("next_rising")
            ns = sun_state.attributes.get("next_setting")
            try:
                sr_dt = dt_util.parse_datetime(nr) if nr else None
                ss_dt = dt_util.parse_datetime(ns) if ns else None
                return sr_dt, ss_dt
            except Exception:
                pass

        return None, None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch updated data and execute autonomous decision checks."""
        # Rollover check
        today_str = dt_util.now().date().isoformat()
        if self.last_reset_date != today_str:
            self.mowed_minutes_today = 0.0
            self.last_reset_date = today_str
            await self._async_save()

        data = self._calculate_all()

        # Run autonomous dispatch logic if auto_mow is enabled
        await self._async_manage_auto_mow(data)

        return data

    def _calculate_all(self) -> dict[str, Any]:
        """Perform all mathematical and status evaluations."""
        now = dt_util.now()

        # Extract current weather & environmental readings
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

            # Forecast for GDD (min/max temp)
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

        # Pro sensor overrides
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

        rain_sensor = self._get_opt(CONF_SENSOR_RAIN)
        rain_rate: float = 0.0
        if rain_sensor:
            st = self.hass.states.get(rain_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    rain_rate = float(st.state)
                except ValueError:
                    # Could be binary (on/off)
                    if st.state.lower() in ("on", "true", "wet"):
                        rain_rate = 1.0

        rain_radar_sensor = self._get_opt(CONF_SENSOR_RAIN_RADAR)
        radar_minutes: float | None = None
        if rain_radar_sensor:
            st = self.hass.states.get(rain_radar_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    radar_minutes = float(st.state)
                except ValueError:
                    pass

        wind_sensor = self._get_opt(CONF_SENSOR_WIND)
        wind_speed: float = 0.0
        if wind_sensor:
            st = self.hass.states.get(wind_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    wind_speed = float(st.state)
                except ValueError:
                    pass

        solar_sensor = self._get_opt(CONF_SENSOR_SOLAR)
        solar_rad: float = 0.0
        if solar_sensor:
            st = self.hass.states.get(solar_sensor)
            if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    solar_rad = float(st.state)
                except ValueError:
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

        # Mower & Battery status
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

        # 1. Biological Lawn Growth Calculations
        gdd = calculate_gdd(t_max=t_max, t_min=t_min)

        days_since_fert: int | None = None
        if self.last_fertilized_date:
            try:
                fert_d = date.fromisoformat(self.last_fertilized_date)
                days_since_fert = (now.date() - fert_d).days
            except Exception:
                pass

        fert_factor = calculate_fertilizer_factor(days_since_fert)
        soil_factor = calculate_soil_factor(soil_pct)
        growth_index = calculate_growth_index(gdd, fert_factor, soil_factor)

        # 2. Daily Mowing Budget
        lawn_area = float(self._get_opt(CONF_LAWN_AREA, DEFAULT_LAWN_AREA))
        mower_type = self._get_opt(CONF_MOWER_TYPE, DEFAULT_MOWER_TYPE)
        custom_cap = self._get_opt(CONF_MOWER_CAPACITY)

        target_minutes = calculate_daily_target_minutes(
            lawn_area_m2=lawn_area,
            mower_type=mower_type,
            growth_index=growth_index,
            custom_capacity_m2h=custom_cap,
        )

        # Elapsed today + ongoing session duration
        elapsed_today = self.mowed_minutes_today
        if self._session_start_time:
            ongoing_session_min = (now - self._session_start_time).total_seconds() / 60.0
            elapsed_today += ongoing_session_min

        remaining_minutes = max(0, int(target_minutes - elapsed_today))

        # 3. Moisture Evaluation
        dew_spread_min = float(self._get_opt(CONF_DEW_SPREAD_MIN, DEFAULT_DEW_SPREAD_MIN))
        moisture = evaluate_moisture(
            temperature_c=current_temp,
            humidity_percent=current_humidity,
            dew_spread_threshold=dew_spread_min,
            rain_rate_mmh=rain_rate,
            solar_radiation_wm2=solar_rad,
            wind_speed_kmh=wind_speed,
        )

        # 4. Astronomical & Slot Evaluation
        sunrise, sunset = self._get_sun_times(now)
        slot = evaluate_slot(
            now=now,
            current_temp=current_temp,
            humidity=current_humidity,
            weather_condition=weather_cond,
            rain_rate_mmh=rain_rate,
            rain_radar_minutes=radar_minutes,
            battery_level=battery_level,
            sunrise=sunrise,
            sunset=sunset,
            dew_spread_threshold=dew_spread_min,
            heat_limit=float(self._get_opt(CONF_HEAT_LIMIT, DEFAULT_HEAT_LIMIT)),
            wildlife_enabled=bool(self._get_opt(CONF_WILDLIFE_ENABLED, True)),
            wildlife_sunrise_offset=int(self._get_opt(CONF_WILDLIFE_SUNRISE_OFFSET, DEFAULT_WILDLIFE_SUNRISE)),
            wildlife_sunset_offset=int(self._get_opt(CONF_WILDLIFE_SUNSET_OFFSET, DEFAULT_WILDLIFE_SUNSET)),
            quiet_start=str(self._get_opt(CONF_QUIET_HOURS_START, DEFAULT_QUIET_HOURS_START)),
            quiet_end=str(self._get_opt(CONF_QUIET_HOURS_END, DEFAULT_QUIET_HOURS_END)),
            min_battery=int(self._get_opt(CONF_MIN_BATTERY_LEVEL, DEFAULT_MIN_BATTERY)),
            remaining_minutes_today=remaining_minutes,
            solar_radiation_wm2=solar_rad,
            wind_speed_kmh=wind_speed,
        )

        return {
            "mowing_permitted": slot.permitted,
            "blocking_reasons": slot.blocking_reasons,
            "rain_blocked": slot.rain_blocked,
            "dew_blocked": slot.dew_blocked,
            "heat_blocked": slot.heat_blocked,
            "wildlife_blocked": slot.wildlife_blocked,
            "quiet_hours_blocked": slot.quiet_hours_blocked,
            "battery_blocked": slot.battery_blocked,
            "urgency_score": slot.urgency_score,
            "moisture_status": moisture,
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

        # CASE 1: Mower is currently mowing - check safety & anti-overmowing rules
        if current_state in MOWING_STATES:
            # Check maximum single-run duration (anti-overmowing / early recall)
            max_run = int(self._get_opt(CONF_MAX_RUN_TIME, 0))
            if max_run > 0 and self._session_start_time:
                now = dt_util.now()
                ongoing_min = (now - self._session_start_time).total_seconds() / 60.0
                if ongoing_min >= max_run:
                    _LOGGER.info(
                        "MowMaster: Session limit reached (%.1f / %d min). Calling mower to dock.",
                        ongoing_min,
                        max_run,
                    )
                    await self.async_dock_mower()
                    return

            # Check if daily budget is exhausted
            if remaining_min <= 0:
                _LOGGER.info("MowMaster: Daily budget reached. Recalling mower.")
                await self.async_dock_mower()
                return

            # Check acute safety blocks (e.g. rain started, heat spike, quiet hours)
            if data.get("rain_blocked") or data.get("heat_blocked") or data.get("wildlife_blocked"):
                _LOGGER.warning(
                    "MowMaster: Unsafe condition detected while mowing (%s). Recalling mower immediately.",
                    data.get("blocking_reasons"),
                )
                await self.async_dock_mower()
                return

        # CASE 2: Mower is docked & conditions are ideal -> Dispatch!
        elif current_state in DOCKED_STATES:
            multi_cycle = bool(self._get_opt(CONF_MULTI_CYCLE, True))
            # Start only if permitted and remaining mowing needed is significant (> 10 min)
            if is_permitted and remaining_min >= 10:
                if self.mowed_minutes_today == 0 or multi_cycle:
                    _LOGGER.info(
                        "MowMaster: Conditions optimal and budget remaining (%d min). Starting mowing session.",
                        remaining_min,
                    )
                    await self.async_start_mowing()

    async def async_start_mowing(self) -> None:
        """Trigger mower start, including edge-cutting service if scheduled."""
        mower_entity = self._get_opt(CONF_MOWER_ENTITY)
        if not mower_entity:
            return

        # Check if edge cut is scheduled
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

            _LOGGER.info("MowMaster: Calling custom edge cut service %s with %s", edge_service, call_data)
            await self.hass.services.async_call(domain, svc, call_data, blocking=True)
            self.edge_cut_next = False
            await self._async_save()
            return

        # Standard HA lawn_mower start call
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
        """Record today (or specified date) as fertilization date."""
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

