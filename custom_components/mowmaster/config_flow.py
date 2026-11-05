"""Config flow and Options flow for the MowMaster integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
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
    DEFAULT_MULTI_CYCLE,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_WILDLIFE_SUNRISE,
    DEFAULT_WILDLIFE_SUNSET,
    DOMAIN,
    MOWER_TYPE_CHAOS,
    MOWER_TYPE_SYSTEMATIC,
)

_LOGGER = logging.getLogger(__name__)


class MowMasterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MowMaster."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle initial step: basic beginner-friendly configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mower_entity = user_input[CONF_MOWER_ENTITY]
            await self.async_set_unique_id(f"mowmaster_{mower_entity}")
            self._abort_if_unique_id_configured()

            # Set sensible mower capacity default based on type
            mower_type = user_input.get(CONF_MOWER_TYPE, DEFAULT_MOWER_TYPE)
            if CONF_MOWER_CAPACITY not in user_input:
                user_input[CONF_MOWER_CAPACITY] = (
                    DEFAULT_CAPACITY_SYSTEMATIC
                    if mower_type == MOWER_TYPE_SYSTEMATIC
                    else DEFAULT_CAPACITY_CHAOS
                )

            # Friendly title
            state = self.hass.states.get(mower_entity)
            name = state.name if state else mower_entity
            return self.async_create_entry(title=f"MowMaster ({name})", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_MOWER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="lawn_mower")
                ),
                vol.Required(CONF_WEATHER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="weather")
                ),
                vol.Required(CONF_LAWN_AREA, default=DEFAULT_LAWN_AREA): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=10000,
                        step=10,
                        unit_of_measurement="m²",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(CONF_MOWER_TYPE, default=DEFAULT_MOWER_TYPE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=MOWER_TYPE_CHAOS,
                                label="Chaos-Prinzip / Begrenzungskabel (Standard)",
                            ),
                            selector.SelectOptionDict(
                                value=MOWER_TYPE_SYSTEMATIC,
                                label="Systematisch in Bahnen (RTK / LiDAR / Kamera)",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return MowMasterOptionsFlow(config_entry)


class MowMasterOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for MowMaster Pro settings."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._options = dict(config_entry.options)

    def _get_val(self, key: str, default: Any = None) -> Any:
        """Helper to get option or fallback to config entry data."""
        if key in self._options:
            return self._options[key]
        return self.config_entry.data.get(key, default)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Present options menu for Pro settings."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["sensors", "thresholds", "mower_management"],
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure optional local weather and soil sensors."""
        if user_input is not None:
            self._options.update(user_input)
            return await self._async_save_options()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SENSOR_TEMP,
                    description={"suggested_value": self._get_val(CONF_SENSOR_TEMP)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor", "weather"])
                ),
                vol.Optional(
                    CONF_SENSOR_HUMIDITY,
                    description={"suggested_value": self._get_val(CONF_SENSOR_HUMIDITY)},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(
                    CONF_SENSOR_RAIN,
                    description={"suggested_value": self._get_val(CONF_SENSOR_RAIN)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
                ),
                vol.Optional(
                    CONF_SENSOR_RAIN_RADAR,
                    description={"suggested_value": self._get_val(CONF_SENSOR_RAIN_RADAR)},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(
                    CONF_SENSOR_SOLAR,
                    description={"suggested_value": self._get_val(CONF_SENSOR_SOLAR)},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(
                    CONF_SENSOR_WIND,
                    description={"suggested_value": self._get_val(CONF_SENSOR_WIND)},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(
                    CONF_SENSOR_SOIL,
                    description={"suggested_value": self._get_val(CONF_SENSOR_SOIL)},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
                vol.Optional(
                    CONF_SENSOR_BATTERY,
                    description={"suggested_value": self._get_val(CONF_SENSOR_BATTERY)},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            }
        )

        return self.async_show_form(step_id="sensors", data_schema=schema)

    async def async_step_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure weather thresholds, wildlife and quiet hours."""
        if user_input is not None:
            self._options.update(user_input)
            return await self._async_save_options()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DEW_SPREAD_MIN,
                    default=self._get_val(CONF_DEW_SPREAD_MIN, DEFAULT_DEW_SPREAD_MIN),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.5,
                        max=8.0,
                        step=0.1,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_HEAT_LIMIT,
                    default=self._get_val(CONF_HEAT_LIMIT, DEFAULT_HEAT_LIMIT),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=20.0,
                        max=40.0,
                        step=0.5,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_WILDLIFE_ENABLED,
                    default=self._get_val(CONF_WILDLIFE_ENABLED, True),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_WILDLIFE_SUNRISE_OFFSET,
                    default=self._get_val(CONF_WILDLIFE_SUNRISE_OFFSET, DEFAULT_WILDLIFE_SUNRISE),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=180,
                        step=15,
                        unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_WILDLIFE_SUNSET_OFFSET,
                    default=self._get_val(CONF_WILDLIFE_SUNSET_OFFSET, DEFAULT_WILDLIFE_SUNSET),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=180,
                        step=15,
                        unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_QUIET_HOURS_START,
                    default=self._get_val(CONF_QUIET_HOURS_START, DEFAULT_QUIET_HOURS_START),
                ): selector.TimeSelector(),
                vol.Required(
                    CONF_QUIET_HOURS_END,
                    default=self._get_val(CONF_QUIET_HOURS_END, DEFAULT_QUIET_HOURS_END),
                ): selector.TimeSelector(),
            }
        )

        return self.async_show_form(step_id="thresholds", data_schema=schema)

    async def async_step_mower_management(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure runtime limits, battery thresholds, and edge mowing."""
        if user_input is not None:
            self._options.update(user_input)
            return await self._async_save_options()

        current_type = self._get_val(CONF_MOWER_TYPE, DEFAULT_MOWER_TYPE)
        default_cap = (
            DEFAULT_CAPACITY_SYSTEMATIC
            if current_type == MOWER_TYPE_SYSTEMATIC
            else DEFAULT_CAPACITY_CHAOS
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MOWER_CAPACITY,
                    default=self._get_val(CONF_MOWER_CAPACITY, default_cap),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=10,
                        max=500,
                        step=5,
                        unit_of_measurement="m²/h",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_MIN_BATTERY_LEVEL,
                    default=self._get_val(CONF_MIN_BATTERY_LEVEL, DEFAULT_MIN_BATTERY),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=20,
                        max=100,
                        step=5,
                        unit_of_measurement="%",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_MAX_RUN_TIME,
                    default=self._get_val(CONF_MAX_RUN_TIME, 0),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=300,
                        step=10,
                        unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_MULTI_CYCLE,
                    default=self._get_val(CONF_MULTI_CYCLE, DEFAULT_MULTI_CYCLE),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_EDGE_CUT_INTERVAL,
                    default=self._get_val(CONF_EDGE_CUT_INTERVAL, 0),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=20,
                        step=1,
                        unit_of_measurement="Starts",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_EDGE_CUT_SERVICE,
                    description={"suggested_value": self._get_val(CONF_EDGE_CUT_SERVICE, "")},
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_EDGE_CUT_DATA,
                    description={"suggested_value": self._get_val(CONF_EDGE_CUT_DATA, "")},
                ): selector.TextSelector(),
            }
        )

        return self.async_show_form(step_id="mower_management", data_schema=schema)

    async def _async_save_options(self) -> config_entries.ConfigFlowResult:
        """Save updated options."""
        return self.async_create_entry(title="", data=self._options)

