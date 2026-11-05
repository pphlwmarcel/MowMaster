"""Sensor platform for MowMaster."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MowMasterCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MowMaster sensors."""
    coordinator: MowMasterCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            MowUrgencySensor(coordinator),
            GrowthIndexSensor(coordinator),
            DewSpreadSensor(coordinator),
            DewPointSensor(coordinator),
            LawnMoistureScoreSensor(coordinator),
            DryingRateSensor(coordinator),
            WettingRateSensor(coordinator),
            DailyBudgetRemainingSensor(coordinator),
            MowedMinutesTodaySensor(coordinator),
            DaysSinceFertilizedSensor(coordinator),
        ]
    )


class MowMasterBaseSensor(CoordinatorEntity[MowMasterCoordinator], SensorEntity):
    """Base class for MowMaster sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize base sensor."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title,
            manufacturer="MowMaster",
            model="Intelligent Lawn Controller",
            sw_version="1.0.0",
        )


class MowUrgencySensor(MowMasterBaseSensor):
    """Sensor indicating current mowing urgency percentage."""

    _attr_name = "Mähdringlichkeit"
    _attr_translation_key = "mow_urgency"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_mow_urgency"

    @property
    def native_value(self) -> int:
        """Return urgency score."""
        return int(self.coordinator.data.get("urgency_score", 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return context."""
        return {
            "target_daily_minutes": self.coordinator.data.get("target_daily_minutes"),
            "remaining_minutes_today": self.coordinator.data.get("remaining_minutes_today"),
        }


class GrowthIndexSensor(MowMasterBaseSensor):
    """Sensor reporting current biological grass growth index based on GDD and care."""

    _attr_name = "Wachstumsindex"
    _attr_translation_key = "growth_index"
    _attr_native_unit_of_measurement = "x"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:sprout"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_growth_index"

    @property
    def native_value(self) -> float:
        """Return growth multiplier."""
        return float(self.coordinator.data.get("growth_index", 1.0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return GDD attributes."""
        return {
            "growing_degree_days": self.coordinator.data.get("gdd"),
            "days_since_fertilized": self.coordinator.data.get("days_since_fertilized"),
        }


class DewSpreadSensor(MowMasterBaseSensor):
    """Reports dew point spread (T - T_dew) indicating grass surface dry-off."""

    _attr_name = "Taupunktspreizung"
    _attr_translation_key = "dew_spread"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-thermometer"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_dew_spread"

    @property
    def native_value(self) -> float | None:
        """Return dew point spread."""
        return self.coordinator.data.get("dew_spread")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return dew point and status description."""
        moisture = self.coordinator.data.get("moisture_status")
        return {
            "dew_point_c": self.coordinator.data.get("dew_point"),
            "status_description": moisture.state_description if moisture else None,
        }


class DewPointSensor(MowMasterBaseSensor):
    """Reports calculated or measured dew point."""

    _attr_name = "Taupunkt"
    _attr_translation_key = "dew_point"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer-water"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_dew_point"

    @property
    def native_value(self) -> float | None:
        """Return dew point."""
        return self.coordinator.data.get("dew_point")


class LawnMoistureScoreSensor(MowMasterBaseSensor):
    """Reports lawn moisture balance score (0 = dry, 100 = soaked)."""

    _attr_name = "Rasenfeuchte Score"
    _attr_translation_key = "moisture_score"
    _attr_native_unit_of_measurement = "pts"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:water-percent"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_moisture_score"

    @property
    def native_value(self) -> float | None:
        """Return moisture score."""
        moisture = self.coordinator.data.get("moisture_status")
        return moisture.moisture_score if moisture else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details."""
        moisture = self.coordinator.data.get("moisture_status")
        return {
            "is_dry": moisture.is_dry if moisture else None,
            "surface_state": moisture.state_description if moisture else None,
            "drying_rate_ptsh": self.coordinator.data.get("drying_rate"),
            "wetting_rate_ptsh": self.coordinator.data.get("wetting_rate"),
        }


class DryingRateSensor(MowMasterBaseSensor):
    """Reports surface drying speed based on sun, wind and vapor pressure deficit."""

    _attr_name = "Rasen Abtrocknungsrate"
    _attr_translation_key = "drying_rate"
    _attr_native_unit_of_measurement = "pts/h"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:weather-sunset-up"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_drying_rate"

    @property
    def native_value(self) -> float:
        """Return drying rate."""
        return float(self.coordinator.data.get("drying_rate", 0.0))


class WettingRateSensor(MowMasterBaseSensor):
    """Reports surface wetting speed based on rain, fog or night dew."""

    _attr_name = "Rasen Befeuchtungsrate"
    _attr_translation_key = "wetting_rate"
    _attr_native_unit_of_measurement = "pts/h"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:weather-pouring"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_wetting_rate"

    @property
    def native_value(self) -> float:
        """Return wetting rate."""
        return float(self.coordinator.data.get("wetting_rate", 0.0))


class DailyBudgetRemainingSensor(MowMasterBaseSensor):
    """Remaining target mowing duration for today in minutes."""

    _attr_name = "Verbleibende Mähzeit heute"
    _attr_translation_key = "remaining_budget"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_remaining_budget"

    @property
    def native_value(self) -> int:
        """Return remaining minutes."""
        return int(self.coordinator.data.get("remaining_minutes_today", 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return targets."""
        return {
            "target_daily_minutes": self.coordinator.data.get("target_daily_minutes"),
            "mowed_minutes_today": self.coordinator.data.get("mowed_minutes_today"),
        }


class MowedMinutesTodaySensor(MowMasterBaseSensor):
    """Minutes already mowed today."""

    _attr_name = "Gemähte Zeit heute"
    _attr_translation_key = "mowed_today"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:timer-check"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_mowed_today"

    @property
    def native_value(self) -> float:
        """Return mowed minutes today."""
        return float(self.coordinator.data.get("mowed_minutes_today", 0.0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return session counts."""
        return {
            "total_runs_count": self.coordinator.data.get("total_runs_count", 0),
        }


class DaysSinceFertilizedSensor(MowMasterBaseSensor):
    """Days elapsed since lawn was fertilized."""

    _attr_name = "Tage seit Düngung"
    _attr_translation_key = "days_since_fertilized"
    _attr_native_unit_of_measurement = "d"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_days_since_fertilized"

    @property
    def native_value(self) -> int | None:
        """Return days since fertilization."""
        return self.coordinator.data.get("days_since_fertilized")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return date string."""
        return {
            "last_fertilized_date": self.coordinator.last_fertilized_date,
        }

