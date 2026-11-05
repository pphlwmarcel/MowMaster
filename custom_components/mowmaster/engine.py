"""Calculation engine for MowMaster.

Contains meteorological, biological growth (GDD), physical lawn surface moisture
(drying rate vs wetting rate balance), and slot-evaluation algorithms for autonomous robot mowers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
import math
from typing import Any

from .const import (
    DEFAULT_CAPACITY_CHAOS,
    DEFAULT_CAPACITY_SYSTEMATIC,
    DEFAULT_DEW_SPREAD_MIN,
    DEFAULT_HEAT_LIMIT,
    DEFAULT_MIN_BATTERY,
    DEFAULT_MIN_TEMP,
    DEFAULT_MOISTURE_THRESHOLD,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_RADAR_RAIN_BUFFER,
    DEFAULT_WILDLIFE_SUNRISE,
    DEFAULT_WILDLIFE_SUNSET,
    MOWER_TYPE_CHAOS,
    MOWER_TYPE_SYSTEMATIC,
)


@dataclass
class MoistureStatus:
    """Represents surface moisture and physical rate calculations."""

    dew_point: float
    dew_spread: float
    moisture_score: float  # 0.0 (bone dry) to 100.0 (saturated/raining)
    is_dry: bool
    state_description: str
    drying_rate: float = 0.0  # pts/h
    wetting_rate: float = 0.0  # pts/h


@dataclass
class SlotEvaluation:
    """Represents the real-time slot permission check."""

    permitted: bool
    blocking_reasons: list[str] = field(default_factory=list)
    rain_blocked: bool = False
    dew_blocked: bool = False
    heat_blocked: bool = False
    cold_blocked: bool = False
    wildlife_blocked: bool = False
    quiet_hours_blocked: bool = False
    battery_blocked: bool = False
    seasonal_time_blocked: bool = False
    urgency_score: int = 0  # 0 to 100%


def calculate_dew_point(temperature_c: float, humidity_percent: float) -> float:
    """Calculate dew point using the Magnus-Tetens formula (°C).

    α = (17.27 * T) / (237.7 + T) + ln(RH / 100)
    T_dew = (237.7 * α) / (17.27 - α)
    """
    temp = float(temperature_c)
    rh = max(1.0, min(100.0, float(humidity_percent)))

    a = 17.27
    b = 237.7
    alpha = ((a * temp) / (b + temp)) + math.log(rh / 100.0)
    dew_point = (b * alpha) / (a - alpha)
    return round(dew_point, 2)


def calculate_drying_rate(
    temp_c: float,
    dew_c: float,
    wind_kmh: float = 0.0,
    diff_sonne: float = 0.0,
    solar_rad_wm2: float = 0.0,
    rain_mm: float = 0.0,
    mower_wet: bool = False,
    weather_condition: str | None = None,
    sun_elevation: float = 0.0,
    sun_below_horizon: bool = False,
    now_month: int = 5,
) -> float:
    """Calculate lawn surface drying rate (pts/h) using physical energy balance."""
    cond = (weather_condition or "").lower()
    rain_conditions = ["rainy", "pouring", "lightning-rainy", "fog", "snowy", "snowy-rainy", "hail"]
    spreizung = temp_c - dew_c
    strahlung_nacht = min(diff_sonne, 0.0)
    t_halm = temp_c + strahlung_nacht

    # Check cutoff conditions where drying is physically impossible
    if (
        sun_below_horizon
        or sun_elevation < 3.0
        or spreizung < 1.5
        or t_halm <= (dew_c + 0.5)
        or temp_c < 6.0
        or rain_mm > 0.0
        or mower_wet
        or any(rc in cond for rc in rain_conditions)
    ):
        return 0.0

    # Base rate from evaporation vapor pressure gradient and wind
    base = (spreizung * 1.2) + (wind_kmh * 0.2)

    # Temperature kinetic boost above 18°C
    temp_boost = max(0.0, (temp_c - 18.0) * 1.5)

    # Solar elevation factor (sun angle 6° to 35°)
    elev_factor = (min(1.0, max(0.0, (sun_elevation - 6.0) / 29.0))) * 0.85 + 0.15

    # Solar input from temperature diff or pyranometer W/m²
    if diff_sonne >= 3.0:
        raw_sun = min(diff_sonne * 1.0, 22.0)
    elif solar_rad_wm2 > 50.0:
        raw_sun = min(solar_rad_wm2 / 40.0, 22.0)
    else:
        raw_sun = 0.0

    sun_boost = raw_sun * elev_factor

    # Seasonal adjustment factor (lower sun intensity and shorter daylight in autumn/winter)
    if now_month in [10, 11, 12, 1, 2]:
        season_factor = 0.65
    elif now_month in [3, 9]:
        season_factor = 0.85
    else:
        season_factor = 1.0

    drying_rate = (base + temp_boost + sun_boost) * season_factor
    return round(max(0.0, drying_rate), 1)


def calculate_wetting_rate(
    temp_c: float,
    dew_c: float,
    humidity_percent: float = 70.0,
    wind_kmh: float = 0.0,
    diff_sonne: float = 0.0,
    rain_mm: float = 0.0,
    mower_wet: bool = False,
    weather_condition: str | None = None,
    sun_elevation: float = 0.0,
) -> float:
    """Calculate lawn surface wetting rate (pts/h) from precipitation, fog, or night dew condensation."""
    cond = (weather_condition or "").lower()
    rain_conditions = ["rainy", "pouring", "lightning-rainy", "hail", "snowy", "snowy-rainy"]

    if rain_mm > 0.0 or mower_wet or any(rc in cond for rc in rain_conditions):
        return round(min(100.0, 35.0 + (rain_mm * 35.0)), 1)

    if cond == "fog":
        return 10.0

    strahlung_nacht = min(diff_sonne, 0.0)
    t_halm = temp_c + strahlung_nacht

    # Nocturnal dew formation when grass cools below dew point
    if sun_elevation < 8.0 and wind_kmh < 18.0 and (
        t_halm <= (dew_c + 0.5) or (humidity_percent >= 90.0 and strahlung_nacht <= -1.0)
    ):
        tau_diff = max(0.2, (dew_c + 0.5) - t_halm)
        wetting_rate = min(10.0, max(4.0, 4.0 + (tau_diff * 2.5)))
        return round(wetting_rate, 1)

    return 0.0


def calculate_gdd(
    t_max: float,
    t_min: float,
    t_base: float = 6.0,
    t_cap: float = 28.0,
) -> float:
    """Calculate Growing Degree Days (GDD) for cool-season turfgrass."""
    effective_max = min(float(t_max), t_cap)
    effective_min = max(float(t_min), t_base)
    mean_temp = (effective_max + effective_min) / 2.0
    gdd = max(0.0, mean_temp - t_base)
    return round(gdd, 2)


def calculate_fertilizer_factor(days_since_fertilized: int | None) -> float:
    """Calculate growth multiplier from lawn fertilization with 28-day exponential decay."""
    if days_since_fertilized is None or days_since_fertilized < 0 or days_since_fertilized > 45:
        return 1.0

    decay_rate = 0.075
    boost = 0.7 * math.exp(-decay_rate * float(days_since_fertilized))
    return round(1.0 + boost, 2)


def calculate_soil_factor(soil_moisture_percent: float | None) -> float:
    """Calculate growth multiplier based on soil moisture."""
    if soil_moisture_percent is None:
        return 1.0

    sm = max(0.0, min(100.0, float(soil_moisture_percent)))
    if sm < 15.0:
        return 0.3
    if sm < 25.0:
        return 0.7
    if sm <= 60.0:
        return 1.15
    return 1.0


def calculate_growth_index(
    gdd: float,
    fertilizer_factor: float = 1.0,
    soil_factor: float = 1.0,
) -> float:
    """Combine GDD, fertilizer, and soil factors into a daily growth index."""
    base_growth = gdd / 12.0
    index = base_growth * fertilizer_factor * soil_factor
    return round(max(0.0, min(3.0, index)), 2)


def calculate_daily_target_minutes(
    lawn_area_m2: float,
    mower_type: str,
    growth_index: float,
    custom_capacity_m2h: float | None = None,
) -> int:
    """Calculate the target mowing duration (minutes) for today."""
    area = max(10.0, float(lawn_area_m2))

    if custom_capacity_m2h and custom_capacity_m2h > 5.0:
        capacity = float(custom_capacity_m2h)
    elif mower_type == MOWER_TYPE_SYSTEMATIC:
        capacity = DEFAULT_CAPACITY_SYSTEMATIC
    else:
        capacity = DEFAULT_CAPACITY_CHAOS

    base_hours = area / capacity

    if growth_index < 0.1:
        return 0

    target_minutes = round(base_hours * 60.0 * growth_index)
    return max(0, min(720, target_minutes))


def is_time_in_range(now_time: time, start_str: str, end_str: str) -> bool:
    """Check if now_time falls inside a HH:MM to HH:MM window."""
    try:
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        start = time(sh, sm)
        end = time(eh, em)
    except Exception:
        return False

    if start <= end:
        return start <= now_time <= end
    return now_time >= start or now_time <= end


def evaluate_slot(
    now: datetime,
    current_temp: float,
    humidity: float,
    dew_point: float,
    weather_condition: str | None,
    moisture_score: float,
    moisture_threshold: float = DEFAULT_MOISTURE_THRESHOLD,
    rain_rate_mmh: float = 0.0,
    mower_rain_sensor: bool = False,
    rain_radar_minutes: float | None = None,
    rain_radar_sum: float | None = None,
    radar_buffer_minutes: int = DEFAULT_RADAR_RAIN_BUFFER,
    battery_level: float | None = None,
    sunrise: datetime | None = None,
    sunset: datetime | None = None,
    sun_elevation: float = 10.0,
    sun_above_horizon: bool = True,
    # Thresholds
    dew_spread_threshold: float = DEFAULT_DEW_SPREAD_MIN,
    min_temp: float = DEFAULT_MIN_TEMP,
    heat_limit: float = DEFAULT_HEAT_LIMIT,
    wildlife_enabled: bool = True,
    wildlife_sunrise_offset: int = DEFAULT_WILDLIFE_SUNRISE,
    wildlife_sunset_offset: int = DEFAULT_WILDLIFE_SUNSET,
    quiet_start: str = DEFAULT_QUIET_HOURS_START,
    quiet_end: str = DEFAULT_QUIET_HOURS_END,
    min_battery: int = DEFAULT_MIN_BATTERY,
    remaining_minutes_today: int = 0,
) -> SlotEvaluation:
    """Comprehensive evaluation matching physical lawn requirements and user criteria."""
    blocking_reasons: list[str] = []

    # 1. Rain & Weather Condition Check
    rain_blocked = False
    condition = (weather_condition or "").lower()
    rain_keywords = ["rain", "regen", "pour", "snow", "hail", "thunder", "blitz", "gewitter"]
    if any(k in condition for k in rain_keywords) or rain_rate_mmh > 0.0 or mower_rain_sensor:
        rain_blocked = True
        blocking_reasons.append("rain_active")

    # Rain Radar imminent warning (checks minutes to rain or radar forecast sum)
    if rain_radar_sum is not None and rain_radar_sum >= 0.2:
        rain_blocked = True
        blocking_reasons.append("rain_radar_approaching")
    elif rain_radar_minutes is not None and 0 <= rain_radar_minutes <= radar_buffer_minutes:
        rain_blocked = True
        blocking_reasons.append("rain_radar_approaching")

    # 2. Moisture / Nässe-Score Check (Physical Wetness Balance)
    dew_spread = round(current_temp - dew_point, 2)
    dew_blocked = False
    if moisture_score >= moisture_threshold:
        dew_blocked = True
        blocking_reasons.append("lawn_surface_wet")
    elif dew_spread < dew_spread_threshold:
        dew_blocked = True
        blocking_reasons.append("dew_spread_low")

    # 3. Minimum Temperature Check (Grass freezing or too cold to cleanly cut)
    cold_blocked = current_temp < min_temp
    if cold_blocked:
        blocking_reasons.append("temperature_too_low")

    # 4. Heat Protection Check (Lawn scorching prevention)
    heat_blocked = current_temp >= heat_limit
    if heat_blocked:
        blocking_reasons.append("heat_limit_exceeded")

    # 5. Seasonal Daylight Window (Autumn midday requirement & sun above horizon)
    seasonal_blocked = False
    if not sun_above_horizon:
        seasonal_blocked = True
        blocking_reasons.append("sun_below_horizon")
    else:
        # In autumn (Sep, Oct, Nov) grass needs until at least 10:00 or 12:00 to warm up
        req_hour = 12 if now.month in [9, 10, 11] else 10
        if now.hour < req_hour:
            seasonal_blocked = True
            blocking_reasons.append("seasonal_morning_cold")

    # 6. Wildlife Protection Check (Hedgehog / Igelschutz)
    wildlife_blocked = False
    if wildlife_enabled and sunrise and sunset:
        import datetime as dt_module

        safe_start = sunrise + dt_module.timedelta(minutes=wildlife_sunrise_offset)
        safe_end = sunset - dt_module.timedelta(minutes=wildlife_sunset_offset)

        if now < safe_start or now > safe_end:
            wildlife_blocked = True
            blocking_reasons.append("wildlife_protection")

    # 7. Quiet Hours Check
    quiet_blocked = is_time_in_range(now.time(), quiet_start, quiet_end)
    if quiet_blocked:
        blocking_reasons.append("quiet_hours")

    # 8. Battery Level Check
    battery_blocked = False
    if battery_level is not None and battery_level < min_battery:
        battery_blocked = True
        blocking_reasons.append("battery_low")

    # Overall permission
    is_permitted = len(blocking_reasons) == 0

    # Urgency Score calculation (0 - 100%)
    urgency = 0
    if remaining_minutes_today > 0:
        base_urgency = min(80, int((remaining_minutes_today / 120.0) * 50))
        if is_permitted:
            urgency = min(100, base_urgency + 30)
        else:
            urgency = base_urgency

    return SlotEvaluation(
        permitted=is_permitted,
        blocking_reasons=blocking_reasons,
        rain_blocked=rain_blocked,
        dew_blocked=dew_blocked,
        heat_blocked=heat_blocked,
        cold_blocked=cold_blocked,
        wildlife_blocked=wildlife_blocked,
        quiet_hours_blocked=quiet_blocked,
        battery_blocked=battery_blocked,
        seasonal_time_blocked=seasonal_blocked,
        urgency_score=urgency,
    )

