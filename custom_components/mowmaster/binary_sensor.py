"""Binary sensor platform for MowMaster."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
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
    """Set up MowMaster binary sensors."""
    coordinator: MowMasterCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            MowPermittedBinarySensor(coordinator),
            RainMoistureBlockedBinarySensor(coordinator),
            HeatBlockedBinarySensor(coordinator),
            ColdBlockedBinarySensor(coordinator),
            WildlifeBlockedBinarySensor(coordinator),
            QuietHoursBlockedBinarySensor(coordinator),
            SeasonalTimeBlockedBinarySensor(coordinator),
            GrowthDormantBinarySensor(coordinator),
        ]
    )


class MowMasterBaseBinarySensor(CoordinatorEntity[MowMasterCoordinator], BinarySensorEntity):
    """Base class for MowMaster binary sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title,
            manufacturer="MowMaster",
            model="Intelligent Lawn Controller",
            sw_version="1.0.0",
        )


class MowPermittedBinarySensor(MowMasterBaseBinarySensor):
    """Master binary sensor indicating whether mowing is currently safe and permitted."""

    _attr_translation_key = "mowing_permitted"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_mowing_permitted"

    @property
    def is_on(self) -> bool:
        """Return true if mowing is permitted right now."""
        return bool(self.coordinator.data.get("mowing_permitted", False))

    @property
    def icon(self) -> str:
        """Return icon based on status."""
        return "mdi:robot-mower" if self.is_on else "mdi:robot-mower-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return blocking reasons and environmental diagnostics."""
        data = self.coordinator.data
        moisture = data.get("moisture_status")
        return {
            "blocking_reasons": data.get("blocking_reasons", []),
            "dew_spread": data.get("dew_spread"),
            "dew_point": data.get("dew_point"),
            "moisture_score": moisture.moisture_score if moisture else None,
            "drying_rate": data.get("drying_rate"),
            "wetting_rate": data.get("wetting_rate"),
            "surface_state": moisture.state_description if moisture else None,
            "growth_index": data.get("growth_index"),
            "daily_target_minutes": data.get("target_daily_minutes"),
            "remaining_minutes_today": data.get("remaining_minutes_today"),
        }


class RainMoistureBlockedBinarySensor(MowMasterBaseBinarySensor):
    """Indicates whether rain or wet grass is currently blocking mowing."""

    _attr_translation_key = "rain_moisture_blocked"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_rain_moisture_blocked"

    @property
    def is_on(self) -> bool:
        """Return true if rain or wet dew is blocking."""
        data = self.coordinator.data
        return bool(data.get("rain_blocked") or data.get("dew_blocked"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return moisture diagnostics."""
        moisture = self.coordinator.data.get("moisture_status")
        return {
            "rain_active": self.coordinator.data.get("rain_blocked", False),
            "dew_wet": self.coordinator.data.get("dew_blocked", False),
            "moisture_score": moisture.moisture_score if moisture else None,
            "surface_description": moisture.state_description if moisture else None,
            "dew_spread_c": self.coordinator.data.get("dew_spread"),
        }


class HeatBlockedBinarySensor(MowMasterBaseBinarySensor):
    """Indicates if heat protection is currently active to avoid lawn damage."""

    _attr_translation_key = "heat_blocked"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_heat_blocked"

    @property
    def is_on(self) -> bool:
        """Return true if heat limit is exceeded."""
        return bool(self.coordinator.data.get("heat_blocked", False))

    @property
    def icon(self) -> str:
        """Return icon based on heat block status."""
        return "mdi:weather-sunny-alert" if self.is_on else "mdi:thermometer-check"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return temperature details."""
        return {
            "current_temperature": self.coordinator.data.get("temperature"),
        }


class ColdBlockedBinarySensor(MowMasterBaseBinarySensor):
    """Indicates if temperatures are below safe grass cutting threshold."""

    _attr_translation_key = "cold_blocked"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_cold_blocked"

    @property
    def is_on(self) -> bool:
        """Return true if below minimum temperature."""
        return bool(self.coordinator.data.get("cold_blocked", False))

    @property
    def icon(self) -> str:
        """Return icon."""
        return "mdi:snowflake-alert" if self.is_on else "mdi:thermometer-low"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return current temp."""
        return {
            "current_temperature": self.coordinator.data.get("temperature"),
        }


class WildlifeBlockedBinarySensor(MowMasterBaseBinarySensor):
    """Indicates if wildlife (hedgehog) protection window is currently active."""

    _attr_translation_key = "wildlife_blocked"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_wildlife_blocked"

    @property
    def is_on(self) -> bool:
        """Return true if mowing is blocked due to dusk/night/wildlife."""
        return bool(self.coordinator.data.get("wildlife_blocked", False))

    @property
    def icon(self) -> str:
        """Return icon."""
        return "mdi:paw" if self.is_on else "mdi:paw-off"


class QuietHoursBlockedBinarySensor(MowMasterBaseBinarySensor):
    """Indicates if quiet hours curfew is active."""

    _attr_translation_key = "quiet_hours_blocked"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_quiet_hours_blocked"

    @property
    def is_on(self) -> bool:
        """Return true if quiet hours are currently active."""
        return bool(self.coordinator.data.get("quiet_hours_blocked", False))

    @property
    def icon(self) -> str:
        """Return icon."""
        return "mdi:volume-off" if self.is_on else "mdi:volume-high"


class SeasonalTimeBlockedBinarySensor(MowMasterBaseBinarySensor):
    """Indicates if mowing is blocked due to autumn morning cold or low sun elevation."""

    _attr_translation_key = "seasonal_time_blocked"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_seasonal_time_blocked"

    @property
    def is_on(self) -> bool:
        """Return true if seasonal morning cold is blocking."""
        return bool(self.coordinator.data.get("seasonal_time_blocked", False))

    @property
    def icon(self) -> str:
        """Return icon."""
        return "mdi:weather-partly-cloudy" if self.is_on else "mdi:weather-sunny"


class GrowthDormantBinarySensor(MowMasterBaseBinarySensor):
    """Indicates if mowing is blocked because grass is dormant / no growth today."""

    _attr_translation_key = "growth_dormant_blocked"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_growth_dormant_blocked"

    @property
    def is_on(self) -> bool:
        """Return true if grass growth is dormant / budget is 0."""
        return bool(self.coordinator.data.get("growth_dormant_blocked", False))

    @property
    def icon(self) -> str:
        """Return icon."""
        return "mdi:snowflake-thermometer" if self.is_on else "mdi:sprout"
