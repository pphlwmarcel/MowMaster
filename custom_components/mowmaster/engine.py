"""Calculation engine for MowMaster.

Contains meteorological, biological growth (GDD), surface moisture,
and slot-evaluation algorithms for autonomous robot lawn mowers.
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
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_WILDLIFE_SUNRISE,
    DEFAULT_WILDLIFE_SUNSET,
    MOWER_TYPE_CHAOS,
    MOWER_TYPE_SYSTEMATIC,
)


@dataclass
class MoistureStatus:
    """Represents surface moisture calculation result."""

    dew_point: float
    dew_spread: float
    moisture_score: float  # 0 (bone dry) to 100 (saturated/raining)
    is_dry: bool
    state_description: str


@dataclass
class SlotEvaluation:
    """Represents the real-time slot permission check."""

    permitted: bool
    blocking_reasons: list[str] = field(default_factory=list)
    rain_blocked: bool = False
    dew_blocked: bool = False
    heat_blocked: bool = False
    wildlife_blocked: bool = False
    quiet_hours_blocked: bool = False
    battery_blocked: bool = False
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


def evaluate_moisture(
    temperature_c: float,
    humidity_percent: float,
    dew_spread_threshold: float = DEFAULT_DEW_SPREAD_MIN,
    rain_rate_mmh: float = 0.0,
    solar_radiation_wm2: float = 0.0,
    wind_speed_kmh: float = 0.0,
) -> MoistureStatus:
    """Evaluate whether the lawn surface is dry enough to mow.

    Dew spread = Temperature - Dew Point.
    When Dew spread >= threshold (typically 2.5°C), the surface layer is dry.
    Solar radiation and wind accelerate evaporation.
    """
    dew_pt = calculate_dew_point(temperature_c, humidity_percent)
    dew_spread = round(temperature_c - dew_pt, 2)

    # Calculate moisture score (0 = dry, 100 = soaked)
    if rain_rate_mmh > 0.1:
        moisture_score = min(100.0, 70.0 + (rain_rate_mmh * 10.0))
        is_dry = False
        desc = "Regen / Niederschlag"
    elif dew_spread < 1.0:
        moisture_score = 90.0
        is_dry = False
        desc = "Sehr feucht / Starker Tau"
    elif dew_spread < dew_spread_threshold:
        # Interpolate between 50% and 80%
        factor = (dew_spread_threshold - dew_spread) / max(0.1, dew_spread_threshold - 1.0)
        moisture_score = round(50.0 + (factor * 30.0), 1)
        is_dry = False
        desc = "Morgentau / Abtrocknend"
    else:
        # Grass is dry, further reduced if sunny/windy
        drying_bonus = min(20.0, (solar_radiation_wm2 / 50.0) + (wind_speed_kmh / 3.0))
        moisture_score = max(5.0, round(35.0 - (dew_spread * 3.0) - drying_bonus, 1))
        is_dry = True
        desc = "Trocken"

    return MoistureStatus(
        dew_point=dew_pt,
        dew_spread=dew_spread,
        moisture_score=moisture_score,
        is_dry=is_dry,
        state_description=desc,
    )


def calculate_gdd(
    t_max: float,
    t_min: float,
    t_base: float = 6.0,
    t_cap: float = 28.0,
) -> float:
    """Calculate Growing Degree Days (GDD) for cool-season turfgrass.

    Base temperature is typically 6°C. Growth slows or ceases above 28°C.
    """
    effective_max = min(float(t_max), t_cap)
    effective_min = max(float(t_min), t_base)
    mean_temp = (effective_max + effective_min) / 2.0
    gdd = max(0.0, mean_temp - t_base)
    return round(gdd, 2)


def calculate_fertilizer_factor(days_since_fertilized: int | None) -> float:
    """Calculate growth multiplier from lawn fertilization.

    Starts around 1.7x boost, exponentially decaying to 1.0x over ~28 days.
    """
    if days_since_fertilized is None or days_since_fertilized < 0 or days_since_fertilized > 45:
        return 1.0

    # Boost starts at 0.7 above baseline (1.7 total) and decays with 21-day half-life
    decay_rate = 0.075
    boost = 0.7 * math.exp(-decay_rate * float(days_since_fertilized))
    return round(1.0 + boost, 2)


def calculate_soil_factor(soil_moisture_percent: float | None) -> float:
    """Calculate growth multiplier based on soil moisture.

    < 20%: Drought stress, growth severely limited.
    25-50%: Optimal moisture.
    > 75%: Saturated.
    """
    if soil_moisture_percent is None:
        return 1.0

    sm = max(0.0, min(100.0, float(soil_moisture_percent)))
    if sm < 15.0:
        return 0.3  # Dormant / heat stress
    if sm < 25.0:
        return 0.7  # Mild drought
    if sm <= 60.0:
        return 1.15  # Optimal
    return 1.0  # Saturated


def calculate_growth_index(
    gdd: float,
    fertilizer_factor: float = 1.0,
    soil_factor: float = 1.0,
) -> float:
    """Combine GDD, fertilizer, and soil factors into a daily growth index.

    1.0 represents standard moderate spring/early summer growth (~12 GDD).
    0.0 represents zero growth (winter/dormant).
    2.0+ represents peak surge growth.
    """
    base_growth = gdd / 12.0
    index = base_growth * fertilizer_factor * soil_factor
    return round(max(0.0, min(3.0, index)), 2)


def calculate_daily_target_minutes(
    lawn_area_m2: float,
    mower_type: str,
    growth_index: float,
    custom_capacity_m2h: float | None = None,
) -> int:
    """Calculate the target mowing duration (minutes) for today.

    Based on area, mower navigation efficiency, and daily grass growth rate.
    """
    area = max(10.0, float(lawn_area_m2))

    if custom_capacity_m2h and custom_capacity_m2h > 5.0:
        capacity = float(custom_capacity_m2h)
    elif mower_type == MOWER_TYPE_SYSTEMATIC:
        capacity = DEFAULT_CAPACITY_SYSTEMATIC
    else:
        capacity = DEFAULT_CAPACITY_CHAOS

    # Hours to cover the entire lawn once
    base_hours = area / capacity

    # If growth index is 0 (freezing cold or extreme drought), no mowing needed
    if growth_index < 0.1:
        return 0

    # Scale daily budget: at growth_index = 1.0, budget is proportional to base hours
    target_minutes = round(base_hours * 60.0 * growth_index)

    # Clamp between 0 and 720 minutes (12 hours maximum)
    return max(0, min(720, target_minutes))


def is_time_in_range(now_time: time, start_str: str, end_str: str) -> bool:
    """Check if now_time falls inside a HH:MM to HH:MM window (handles overnight wrap)."""
    try:
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        start = time(sh, sm)
        end = time(eh, em)
    except Exception:
        return False

    if start <= end:
        return start <= now_time <= end
    # Overnight range (e.g. 20:00 to 08:00)
    return now_time >= start or now_time <= end


def evaluate_slot(
    now: datetime,
    current_temp: float,
    humidity: float,
    weather_condition: str | None,
    rain_rate_mmh: float = 0.0,
    rain_radar_minutes: float | None = None,
    battery_level: float | None = None,
    sunrise: datetime | None = None,
    sunset: datetime | None = None,
    # Thresholds
    dew_spread_threshold: float = DEFAULT_DEW_SPREAD_MIN,
    heat_limit: float = DEFAULT_HEAT_LIMIT,
    wildlife_enabled: bool = True,
    wildlife_sunrise_offset: int = DEFAULT_WILDLIFE_SUNRISE,
    wildlife_sunset_offset: int = DEFAULT_WILDLIFE_SUNSET,
    quiet_start: str = DEFAULT_QUIET_HOURS_START,
    quiet_end: str = DEFAULT_QUIET_HOURS_END,
    min_battery: int = DEFAULT_MIN_BATTERY,
    remaining_minutes_today: int = 0,
    solar_radiation_wm2: float = 0.0,
    wind_speed_kmh: float = 0.0,
) -> SlotEvaluation:
    """Comprehensive evaluation of current slot conditions for mowing."""
    blocking_reasons: list[str] = []

    # 1. Rain & Weather Condition Check
    rain_blocked = False
    condition = (weather_condition or "").lower()
    rain_keywords = ["rain", "regen", "pour", "snow", "hail", "thunder", "blitz", "gewitter"]
    if any(k in condition for k in rain_keywords) or rain_rate_mmh > 0.1:
        rain_blocked = True
        blocking_reasons.append("rain_active")

    # Rain Radar imminent warning (e.g. DWD radar reports rain in next 30 mins)
    if rain_radar_minutes is not None and 0 <= rain_radar_minutes <= 35:
        rain_blocked = True
        blocking_reasons.append("rain_radar_approaching")

    # 2. Moisture / Dew Spread Check
    moisture = evaluate_moisture(
        temperature_c=current_temp,
        humidity_percent=humidity,
        dew_spread_threshold=dew_spread_threshold,
        rain_rate_mmh=rain_rate_mmh,
        solar_radiation_wm2=solar_radiation_wm2,
        wind_speed_kmh=wind_speed_kmh,
    )
    dew_blocked = not moisture.is_dry
    if dew_blocked and not rain_blocked:
        blocking_reasons.append("grass_wet_dew")

    # 3. Heat Protection Check (lawn scorching prevention)
    heat_blocked = current_temp >= heat_limit
    if heat_blocked:
        blocking_reasons.append("heat_limit_exceeded")

    # 4. Wildlife Protection Check (Hedgehog / Igelschutz)
    wildlife_blocked = False
    if wildlife_enabled and sunrise and sunset:
        import datetime as dt_module

        safe_start = sunrise + dt_module.timedelta(minutes=wildlife_sunrise_offset)
        safe_end = sunset - dt_module.timedelta(minutes=wildlife_sunset_offset)

        if now < safe_start or now > safe_end:
            wildlife_blocked = True
            blocking_reasons.append("wildlife_protection")

    # 5. Quiet Hours Check
    quiet_blocked = is_time_in_range(now.time(), quiet_start, quiet_end)
    if quiet_blocked:
        blocking_reasons.append("quiet_hours")

    # 6. Battery Level Check
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
        # If permitted right now, boost urgency so user/automation is motivated
        if is_permitted:
            urgency = min(100, base_urgency + 30)
        else:
            urgency = base_urgency
    else:
        urgency = 0

    return SlotEvaluation(
        permitted=is_permitted,
        blocking_reasons=blocking_reasons,
        rain_blocked=rain_blocked,
        dew_blocked=dew_blocked,
        heat_blocked=heat_blocked,
        wildlife_blocked=wildlife_blocked,
        quiet_hours_blocked=quiet_blocked,
        battery_blocked=battery_blocked,
        urgency_score=urgency,
    )

