"""Switch platform for MowMaster."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up MowMaster switches."""
    coordinator: MowMasterCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            AutoMowSwitch(coordinator),
            EdgeCutNextSwitch(coordinator),
        ]
    )


class MowMasterBaseSwitch(CoordinatorEntity[MowMasterCoordinator], SwitchEntity):
    """Base class for MowMaster switches."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize switch."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title,
            manufacturer="MowMaster",
            model="Intelligent Lawn Controller",
            sw_version="1.0.0",
        )


class AutoMowSwitch(MowMasterBaseSwitch):
    """Switch to toggle autonomous dispatch and recall of the mower."""

    _attr_translation_key = "auto_mow"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_auto_mow"

    @property
    def is_on(self) -> bool:
        """Return true if autonomous mowing is active."""
        return self.coordinator.auto_mow_enabled

    @property
    def icon(self) -> str:
        """Return icon."""
        return "mdi:robot" if self.is_on else "mdi:robot-off"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable autonomous mowing."""
        await self.coordinator.async_toggle_auto_mow(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable autonomous mowing."""
        await self.coordinator.async_toggle_auto_mow(False)


class EdgeCutNextSwitch(MowMasterBaseSwitch):
    """Switch to force edge trimming during the next mowing start."""

    _attr_translation_key = "edge_cut_next"

    def __init__(self, coordinator: MowMasterCoordinator) -> None:
        """Initialize switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_edge_cut_next"

    @property
    def is_on(self) -> bool:
        """Return true if edge cutting is queued for next start."""
        return self.coordinator.edge_cut_next

    @property
    def icon(self) -> str:
        """Return icon."""
        return "mdi:border-outside"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Queue edge trimming."""
        await self.coordinator.async_set_edge_cut_next(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Cancel queued edge trimming."""
        await self.coordinator.async_set_edge_cut_next(False)

