"""Button platform for MowMaster."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    """Set up MowMaster buttons."""
    coordinator: MowMasterCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            MarkFertilizedButton(coordinator),
            StartMowingNowButton(coordinator),
            DockMowerButton(coordinator),
            ResetDailyBudgetButton(coordinator),
        ]
    )


class MowMasterBaseButton(CoordinatorEntity[MowMasterCoordinator], ButtonEntity):
    """Base class for MowMaster buttons."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize button."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title,
            manufacturer="MowMaster",
            model="Intelligent Lawn Controller",
            sw_version="1.0.0",
        )


class MarkFertilizedButton(MowMasterBaseButton):
    """Button to mark today as the fertilization date."""

    _attr_name = "Rasen heute gedüngt"
    _attr_translation_key = "mark_fertilized"
    _attr_icon = "mdi:shaping-polygon"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_mark_fertilized"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.coordinator.async_set_fertilized()


class StartMowingNowButton(MowMasterBaseButton):
    """Button to trigger mower start immediately."""

    _attr_name = "Mähvorgang jetzt starten"
    _attr_translation_key = "start_mow_now"
    _attr_icon = "mdi:play-circle-outline"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_start_mow_now"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.coordinator.async_start_mowing()


class DockMowerButton(MowMasterBaseButton):
    """Button to send mower back to charging station."""

    _attr_name = "Mäher zur Ladestation senden"
    _attr_translation_key = "dock_mower"
    _attr_icon = "mdi:home-import-outline"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_dock_mower"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.coordinator.async_dock_mower()


class ResetDailyBudgetButton(MowMasterBaseButton):
    """Button to reset today's mowed minutes."""

    _attr_name = "Tagesmähzeit zurücksetzen"
    _attr_translation_key = "reset_daily_budget"
    _attr_icon = "mdi:restore"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_reset_daily_budget"

    async def async_press(self) -> None:
        """Handle button press."""
        await self.coordinator.async_reset_daily_budget()

