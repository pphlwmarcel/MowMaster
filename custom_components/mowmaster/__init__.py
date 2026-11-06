"""MowMaster - The Intelligent Lawn Mower Slot & Growth Controller for Home Assistant."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DATE
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import ATTR_MOISTURE_SCORE, DOMAIN, PLATFORMS
from .coordinator import MowMasterCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_FERTILIZED = "set_fertilized"
SERVICE_START_MOWING = "start_mowing"
SERVICE_DOCK_MOWER = "dock_mower"
SERVICE_RESET_BUDGET = "reset_daily_budget"
SERVICE_SET_MOISTURE_SCORE = "set_moisture_score"

ALL_SERVICES = (
    SERVICE_SET_FERTILIZED,
    SERVICE_START_MOWING,
    SERVICE_DOCK_MOWER,
    SERVICE_RESET_BUDGET,
    SERVICE_SET_MOISTURE_SCORE,
)

SCHEMA_SET_FERTILIZED = vol.Schema(
    {
        vol.Optional(ATTR_DATE): cv.date,
    }
)

SCHEMA_SET_MOISTURE_SCORE = vol.Schema(
    {
        vol.Required(ATTR_MOISTURE_SCORE): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=100.0)
        ),
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the MowMaster integration from configuration.yaml (not used, purely UI config)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MowMaster from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = MowMasterCoordinator(hass, entry)
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Register integration-level services
    async def handle_set_fertilized(call: ServiceCall) -> None:
        """Service call to record fertilization."""
        d = call.data.get(ATTR_DATE)
        for coord in hass.data[DOMAIN].values():
            if isinstance(coord, MowMasterCoordinator):
                await coord.async_set_fertilized(d)

    async def handle_start_mowing(call: ServiceCall) -> None:
        """Service call to trigger mowing."""
        for coord in hass.data[DOMAIN].values():
            if isinstance(coord, MowMasterCoordinator):
                await coord.async_start_mowing()

    async def handle_dock_mower(call: ServiceCall) -> None:
        """Service call to dock mower."""
        for coord in hass.data[DOMAIN].values():
            if isinstance(coord, MowMasterCoordinator):
                await coord.async_dock_mower()

    async def handle_reset_budget(call: ServiceCall) -> None:
        """Service call to reset budget."""
        for coord in hass.data[DOMAIN].values():
            if isinstance(coord, MowMasterCoordinator):
                await coord.async_reset_daily_budget()

    async def handle_set_moisture_score(call: ServiceCall) -> None:
        """Service call to calibrate internal moisture score."""
        score = float(call.data[ATTR_MOISTURE_SCORE])
        for coord in hass.data[DOMAIN].values():
            if isinstance(coord, MowMasterCoordinator):
                await coord.async_set_moisture_score(score)

    if not hass.services.has_service(DOMAIN, SERVICE_SET_FERTILIZED):
        hass.services.async_register(
            DOMAIN, SERVICE_SET_FERTILIZED, handle_set_fertilized, schema=SCHEMA_SET_FERTILIZED
        )
    if not hass.services.has_service(DOMAIN, SERVICE_START_MOWING):
        hass.services.async_register(DOMAIN, SERVICE_START_MOWING, handle_start_mowing)
    if not hass.services.has_service(DOMAIN, SERVICE_DOCK_MOWER):
        hass.services.async_register(DOMAIN, SERVICE_DOCK_MOWER, handle_dock_mower)
    if not hass.services.has_service(DOMAIN, SERVICE_RESET_BUDGET):
        hass.services.async_register(DOMAIN, SERVICE_RESET_BUDGET, handle_reset_budget)
    if not hass.services.has_service(DOMAIN, SERVICE_SET_MOISTURE_SCORE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_MOISTURE_SCORE,
            handle_set_moisture_score,
            schema=SCHEMA_SET_MOISTURE_SCORE,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: MowMasterCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_unload()

        # Remove services if last entry is unloaded
        if not hass.data[DOMAIN]:
            for svc in ALL_SERVICES:
                if hass.services.has_service(DOMAIN, svc):
                    hass.services.async_remove(DOMAIN, svc)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry after options change."""
    await hass.config_entries.async_reload(entry.entry_id)
