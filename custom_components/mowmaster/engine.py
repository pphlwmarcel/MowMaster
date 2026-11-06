"""Calculation engine for MowMaster.

Contains meteorological, astronomical location-based photoperiod, biological growth (GDD),
physical lawn surface moisture, and slot-evaluation algorithms for autonomous robot mowers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
import math

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
    DEFAULT_SOLAR_DIFF_THRESHOLD,
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
    growth_dormant_blocked: bool = False
    urgency_score: int = 0  # 0 to 100%


def calculate_photoperiod(latitude: float, day_of_year: int) -> tuple[float, float]:
    """Calculate astronomical daylight hours and seasonal trend based on latitude and day of year.

    Returns (daylight_hours, seasonal_trend).
    seasonal_trend > 0: Days are lengthening (Spring approaching Summer).
    seasonal_trend < 0: Days are shortening (Summer heading into Autumn/Winter).
    Works globally for Northern, Southern and Equatorial hemispheres.
    """
    lat_rad = math.radians(max(-89.5, min(89.5, float(latitude))))

    # Solar declination angle (Cooper 1969)
    declination = 23.45 * math.sin(math.radians((360.0 / 365.0) * (day_of_year - 81)))
    dec_rad = math.radians(declination)

    # Seasonal trend: positive when approaching peak summer, negative when approaching winter
    hemisphere_sign = 1.0 if latitude >= 0 else -1.0
    seasonal_trend = math.cos(math.radians((360.0 / 365.0) * (day_of_year - 81))) * hemisphere_sign

    val = -math.tan(lat_rad) * math.tan(dec_rad)
    if val >= 1.0:
        daylight_hours = 0.0  # Polar night
    elif val <= -1.0:
        daylight_hours = 24.0  # Polar day
    else:
        hour_angle = math.acos(val)
        daylight_hours = (24.0 / math.pi) * hour_angle

    return round(daylight_hours, 2), seasonal_trend


def calculate_seasonal_growth_factor(latitude: float, day_of_year: int) -> tuple[float, float]:
    """Calculate biological turfgrass seasonal growth factor based on latitude-dependent photoperiod.

    Works dynamically for any location worldwide:
    - In Central Europe / North America: Summer in June/July, Winter in December/January.
    - In Australia / New Zealand / South Africa: Summer in December/January, Winter in June/July.
    - At the Equator: Steady year-round photoperiod.
    Returns (season_factor, daylight_hours).
    """
    daylight, trend = calculate_photoperiod(latitude, day_of_year)

    if daylight <= 8.5:
        factor = 0.0
    elif daylight <= 10.0:
        factor = (daylight - 8.5) / 1.5 * 0.15
    elif daylight <= 12.0:
        factor = 0.15 + ((daylight - 10.0) / 2.0) * 0.65
    elif daylight <= 14.5:
        factor = 0.80 + ((daylight - 12.0) / 2.5) * 0.45
    else:
        factor = min(1.35, 1.25 + (daylight - 14.5) * 0.05)

    # Phenological spring surge vs autumn dormancy allocation
    if trend > 0:
        factor *= 1.10
    else:
        factor *= 0.85

    season_factor = round(max(0.0, min(1.4, factor)), 2)
    return season_factor, daylight


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
    solar_binary_on: bool = False,
    solar_diff_threshold: float = DEFAULT_SOLAR_DIFF_THRESHOLD,
    rain_mm: float = 0.0,
    mower_wet: bool = False,
    weather_condition: str | None = None,
    sun_elevation: float = 0.0,
    sun_below_horizon: bool = False,
    daylight_hours: float = 12.0,
) -> float:
    """Calculate lawn surface drying rate (pts/h) using physical energy balance."""
    cond = (weather_condition or "").lower()
    rain_conditions = ["rainy", "pouring", "lightning-rainy", "fog", "snowy", "snowy-rainy", "hail"]
    spreizung = temp_c - dew_c
    strahlung_nacht = min(diff_sonne, 0.0)
    t_halm = temp_c + strahlung_nacht

    sun_active = (
        diff_sonne >= solar_diff_threshold
        or solar_rad_wm2 >= 120.0
        or solar_binary_on
    )
    t_effective = temp_c + (max(0.0, diff_sonne) if diff_sonne >= solar_diff_threshold else (6.0 if sun_active else 0.0))
    temp_cutoff = t_effective < 4.0 if sun_active else temp_c < 6.0

    # Check cutoff conditions where drying is physically impossible
    if (
        sun_below_horizon
        or sun_elevation < 3.0
        or spreizung < 1.5
        or t_halm <= (dew_c + 0.5)
        or temp_cutoff
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

    # Solar input from differential temperature (°C), pyranometer (W/m²), or binary sun sensor
    if diff_sonne >= solar_diff_threshold:
        raw_sun = min(22.0, 2.0 + ((diff_sonne - solar_diff_threshold) / 25.0) * 20.0)
    elif solar_rad_wm2 >= 120.0:
        raw_sun = min(22.0, 2.0 + ((solar_rad_wm2 - 120.0) / 730.0) * 20.0)
    elif solar_binary_on:
        raw_sun = 10.0
    else:
        raw_sun = 0.0

    sun_boost = raw_sun * elev_factor

    # Location-based photoperiod drying factor
    if daylight_hours <= 10.0:
        season_factor = 0.65
    elif daylight_hours <= 12.0:
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
    """Calculate Growing Degree Days (GDD) for cool-season turfgrass (Method 1).

    Uses true daily average temperature without artificially clamping cold nights up to t_base,
    so frost/cold nights accurately reduce daily mean soil & grass temperature.
    """
    t_high = max(float(t_max), float(t_min))
    t_low = min(float(t_max), float(t_min))

    effective_max = min(t_high, t_cap)
    mean_temp = (effective_max + t_low) / 2.0
    gdd = max(0.0, mean_temp - t_base)
    return round(gdd, 2)


def calculate_fertilizer_factor(days_since_fertilized: int | None) -> float:
    """Calculate growth multiplier from lawn fertilization with 28-day exponential decay."""
    if days_since_fertilized is None or days_since_fertilized < 0 or days_since_fertilized > 45:
        return 1.0

    decay_rate = 0.075
    boost = 0.7 * math.exp(-decay_rate * float(days_since_fertilized))
    return round(1.0 + boost, 2)


def calculate_soil_factor(
    soil_moisture_percent: float | None,
    lawn_irrigated: bool = False,
    gdd: float = 10.0,
) -> float:
    """Calculate growth multiplier based on soil moisture or irrigation setting."""
    if soil_moisture_percent is not None:
        sm = max(0.0, min(100.0, float(soil_moisture_percent)))
        if sm < 15.0:
            return 0.3  # Drought dormancy
        if sm < 25.0:
            return 0.7  # Dry stress
        if sm <= 75.0:
            return 1.15  # Optimal root zone moisture
        return 1.0  # Saturated

    # Without hardware soil sensor: account for regular summer irrigation vs dry heat slump
    if lawn_irrigated:
        return 1.15 if gdd >= 8.0 else 1.0

    if gdd > 15.0:
        # Unirrigated C3 grass slows down during summer heat (mean temp > 21°C)
        return round(max(0.65, 1.0 - (gdd - 15.0) * 0.04), 2)

    return 1.0


def calculate_growth_index(
    gdd: float,
    latitude: float = 50.0,
    day_of_year: int = 135,
    fertilizer_factor: float = 1.0,
    soil_factor: float = 1.0,
) -> tuple[float, float, float]:
    """Combine GDD, location-based photoperiod season factor, fertilizer, and soil factors.

    Models C3 cool-season turfgrass optimum curve (peak efficiency around 16-21°C mean temp)
    and calculates exact season factor from latitude and day of year worldwide.
    Returns (growth_index, season_factor, daylight_hours).
    """
    # C3 grass optimum curve: above GDD=15 (mean temp > 21°C), photorespiration tapers net growth
    effective_gdd = gdd if gdd <= 15.0 else 15.0 + (gdd - 15.0) * 0.35
    base_growth = effective_gdd / 10.0

    season_factor, daylight_hours = calculate_seasonal_growth_factor(latitude, day_of_year)
    index = base_growth * season_factor * fertilizer_factor * soil_factor
    growth_index = round(max(0.0, min(3.0, index)), 2)
    return growth_index, season_factor, daylight_hours


def calculate_daily_target_minutes(
    lawn_area_m2: float,
    mower_type: str,
    growth_index: float,
    custom_capacity_m2h: float | None = None,
) -> int:
    """Calculate the target mowing duration (minutes) for today.

    In peak season (growth_index = 1.0), a robot mower should cover the entire lawn
    approximately 2.5 times per week (chaos) or 1.8 times per week (systematic).
    In late autumn / winter (target < 15 min), grass growth is negligible,
    resulting in 0 minutes mowing time.
    """
    area = max(10.0, float(lawn_area_m2))

    if custom_capacity_m2h and custom_capacity_m2h > 5.0:
        capacity = float(custom_capacity_m2h)
    elif mower_type == MOWER_TYPE_SYSTEMATIC:
        capacity = DEFAULT_CAPACITY_SYSTEMATIC
    else:
        capacity = DEFAULT_CAPACITY_CHAOS

    # Time needed to cut 100% of the lawn once (in hours)
    full_cut_hours = area / capacity

    # Weekly mowing baseline at growth_index = 1.0:
    # Systematic mowers: ~1.8 cuts per week
    # Chaos mowers: ~2.5 cuts per week (due to random overlap)
    cuts_per_week = 1.8 if mower_type == MOWER_TYPE_SYSTEMATIC else 2.5
    weekly_hours = full_cut_hours * cuts_per_week

    # Daily minutes at growth_index = 1.0
    daily_base_minutes = (weekly_hours * 60.0) / 7.0

    # Scale dynamically by biological growth rate
    target_minutes = round(daily_base_minutes * growth_index)

    # If target is less than 15 minutes, cutting is not worthwhile/needed
    if target_minutes < 15:
        return 0

    return max(0, min(720, target_minutes))


def is_surface_dry(
    moisture_score: float,
    moisture_threshold: float,
    dew_spread: float,
    dew_spread_threshold: float,
    mower_rain_sensor: bool = False,
    sun_elevation: float = 10.0,
) -> tuple[bool, str | None]:
    """Determine if the grass surface is dry enough to mow and return optional blocking reason.

    When the moisture account has already dried down to ~0.0 pts and the sun is well up
    (> 20° elevation), a condensation safety spread of 1.5°C is sufficient so warm, humid
    cloud cover doesn't falsely block a dry lawn. During morning dew dry-off or when residual
    moisture > 0.2 pts exists, the full configured dew_spread_threshold is enforced.
    """
    if mower_rain_sensor:
        return False, "rain_active"

    if moisture_score >= moisture_threshold:
        return False, "lawn_surface_wet"

    effective_dew_min = (
        min(1.5, dew_spread_threshold)
        if (moisture_score <= 0.2 and sun_elevation > 20.0)
        else dew_spread_threshold
    )
    if dew_spread < effective_dew_min:
        return False, "dew_spread_low"

    return True, None


def is_time_in_range(now_time: time, start_str: str, end_str: str) -> bool:
    """Check if now_time falls inside a HH:MM to HH:MM window."""
    try:
        parts_s = start_str.split(":")
        parts_e = end_str.split(":")
        start = time(int(parts_s[0]), int(parts_s[1]))
        end = time(int(parts_e[0]), int(parts_e[1]))
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
    growth_index: float = 1.0,
    daylight_hours: float = 12.0,
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
    target_daily_minutes: int | None = None,
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

    # Rain Radar imminent warning
    if rain_radar_sum is not None and rain_radar_sum >= 0.2:
        rain_blocked = True
        if "rain_radar_approaching" not in blocking_reasons:
            blocking_reasons.append("rain_radar_approaching")
    elif rain_radar_minutes is not None and 0.0 < rain_radar_minutes <= radar_buffer_minutes:
        rain_blocked = True
        if "rain_radar_approaching" not in blocking_reasons:
            blocking_reasons.append("rain_radar_approaching")

    # 2. Moisture / Nässe-Score & Dew Spread Check
    dew_spread = round(current_temp - dew_point, 2)
    surface_ok, dew_reason = is_surface_dry(
        moisture_score=moisture_score,
        moisture_threshold=moisture_threshold,
        dew_spread=dew_spread,
        dew_spread_threshold=dew_spread_threshold,
        mower_rain_sensor=False,  # Already handled under rain_blocked
        sun_elevation=sun_elevation,
    )
    dew_blocked = not surface_ok
    if dew_blocked and dew_reason:
        blocking_reasons.append(dew_reason)

    # 3. Minimum Temperature Check (Grass freezing or too cold to cleanly cut)
    cold_blocked = current_temp < min_temp
    if cold_blocked:
        blocking_reasons.append("temperature_too_low")

    # 4. Heat Protection Check (Lawn scorching prevention)
    heat_blocked = current_temp >= heat_limit
    if heat_blocked:
        blocking_reasons.append("heat_limit_exceeded")

    # 5. Sun & Daylight Horizon Check
    # Since MowMaster calculates physical dew spread, surface moisture, minimum temperature,
    # and wildlife sunrise offsets, no rigid clock-based autumn morning curfew is needed.
    seasonal_blocked = False
    if not sun_above_horizon:
        seasonal_blocked = True
        blocking_reasons.append("sun_below_horizon")

    # 6. Biological Growth Dormancy vs. Daily Quota Completed Check
    effective_target = target_daily_minutes if target_daily_minutes is not None else remaining_minutes_today
    growth_dormant = (growth_index < 0.05) or (effective_target <= 0)
    if growth_dormant:
        blocking_reasons.append("growth_dormant")
    elif remaining_minutes_today <= 0:
        blocking_reasons.append("daily_budget_completed")

    # 7. Wildlife Protection Check (Hedgehog / Igelschutz)
    wildlife_blocked = False
    if wildlife_enabled and sunrise and sunset:
        safe_start = sunrise + timedelta(minutes=wildlife_sunrise_offset)
        safe_end = sunset - timedelta(minutes=wildlife_sunset_offset)

        if now < safe_start or now > safe_end:
            wildlife_blocked = True
            blocking_reasons.append("wildlife_protection")

    # 8. Quiet Hours Check
    quiet_blocked = is_time_in_range(now.time(), quiet_start, quiet_end)
    if quiet_blocked:
        blocking_reasons.append("quiet_hours")

    # 9. Battery Level Check
    battery_blocked = False
    if battery_level is not None and battery_level < min_battery:
        battery_blocked = True
        blocking_reasons.append("battery_low")

    # Overall permission
    is_permitted = len(blocking_reasons) == 0

    # Urgency Score calculation (0 - 100%)
    urgency = 0
    if remaining_minutes_today > 0 and not growth_dormant:
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
        growth_dormant_blocked=growth_dormant,
        urgency_score=urgency,
    )
