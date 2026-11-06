"""Config flow and Options flow for the MowMaster integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    ALL_SENSOR_KEYS,
    CONF_CONFIGURE_PRO,
    CONF_DEW_SPREAD_MIN,
    CONF_EDGE_CUT_DATA,
    CONF_EDGE_CUT_INTERVAL,
    CONF_EDGE_CUT_SERVICE,
    CONF_HEAT_LIMIT,
    CONF_LAWN_AREA,
    CONF_LAWN_IRRIGATED,
    CONF_MAX_RUN_TIME,
    CONF_MIN_BATTERY_LEVEL,
    CONF_MIN_TEMP,
    CONF_MOISTURE_THRESHOLD,
    CONF_MOWER_CAPACITY,
    CONF_MOWER_ENTITY,
    CONF_MOWER_TYPE,
    CONF_MULTI_CYCLE,
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    CONF_RADAR_RAIN_BUFFER,
    CONF_SENSOR_BATTERY,
    CONF_SENSOR_DEW_POINT,
    CONF_SENSOR_HUMIDITY,
    CONF_SENSOR_MOISTURE_SCORE,
    CONF_SENSOR_MOWER_RAIN,
    CONF_SENSOR_RAIN,
    CONF_SENSOR_RAIN_RADAR,
    CONF_SENSOR_SOIL,
    CONF_SENSOR_SOLAR,
    CONF_SENSOR_SOLAR_DIFF,
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
    DEFAULT_LAWN_IRRIGATED,
    DEFAULT_MIN_BATTERY,
    DEFAULT_MIN_TEMP,
    DEFAULT_MOISTURE_THRESHOLD,
    DEFAULT_MOWER_TYPE,
    DEFAULT_MULTI_CYCLE,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_RADAR_RAIN_BUFFER,
    DEFAULT_WILDLIFE_SUNRISE,
    DEFAULT_WILDLIFE_SUNSET,
    DOMAIN,
    MOWER_TYPE_CHAOS,
    MOWER_TYPE_SYSTEMATIC,
)

_LOGGER = logging.getLogger(__name__)


def build_basic_schema(current: dict[str, Any], include_pro_toggle: bool = False) -> vol.Schema:
    """Build schema for basic setup and basic options."""
    fields: dict[Any, Any] = {
        vol.Required(
            CONF_MOWER_ENTITY,
            default=current.get(CONF_MOWER_ENTITY, vol.UNDEFINED),
        ): selector.EntitySelector(selector.EntitySelectorConfig(domain="lawn_mower")),
        vol.Required(
            CONF_WEATHER_ENTITY,
            default=current.get(CONF_WEATHER_ENTITY, vol.UNDEFINED),
        ): selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
        vol.Required(
            CONF_LAWN_AREA,
            default=current.get(CONF_LAWN_AREA, DEFAULT_LAWN_AREA),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=10,
                max=10000,
                step=10,
                unit_of_measurement="m²",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            CONF_MOWER_TYPE,
            default=current.get(CONF_MOWER_TYPE, DEFAULT_MOWER_TYPE),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[MOWER_TYPE_CHAOS, MOWER_TYPE_SYSTEMATIC],
                translation_key="mower_type",
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(
            CONF_LAWN_IRRIGATED,
            default=current.get(CONF_LAWN_IRRIGATED, DEFAULT_LAWN_IRRIGATED),
        ): selector.BooleanSelector(),
    }

    if include_pro_toggle:
        fields[vol.Optional(CONF_CONFIGURE_PRO, default=False)] = selector.BooleanSelector()

    return vol.Schema(fields)


def build_sensors_schema(options: dict[str, Any]) -> vol.Schema:
    """Build schema for Pro sensor overrides and moisture sources."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_SENSOR_TEMP,
                description={"suggested_value": options.get(CONF_SENSOR_TEMP)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "weather"])
            ),
            vol.Optional(
                CONF_SENSOR_HUMIDITY,
                description={"suggested_value": options.get(CONF_SENSOR_HUMIDITY)},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_SENSOR_DEW_POINT,
                description={"suggested_value": options.get(CONF_SENSOR_DEW_POINT)},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_SENSOR_MOISTURE_SCORE,
                description={"suggested_value": options.get(CONF_SENSOR_MOISTURE_SCORE)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["input_number", "sensor"])
            ),
            vol.Optional(
                CONF_SENSOR_MOWER_RAIN,
                description={"suggested_value": options.get(CONF_SENSOR_MOWER_RAIN)},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor")),
            vol.Optional(
                CONF_SENSOR_RAIN,
                description={"suggested_value": options.get(CONF_SENSOR_RAIN)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
            ),
            vol.Optional(
                CONF_SENSOR_RAIN_RADAR,
                description={"suggested_value": options.get(CONF_SENSOR_RAIN_RADAR)},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_SENSOR_SOLAR_DIFF,
                description={"suggested_value": options.get(CONF_SENSOR_SOLAR_DIFF)},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_SENSOR_SOLAR,
                description={"suggested_value": options.get(CONF_SENSOR_SOLAR)},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_SENSOR_WIND,
                description={"suggested_value": options.get(CONF_SENSOR_WIND)},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_SENSOR_SOIL,
                description={"suggested_value": options.get(CONF_SENSOR_SOIL)},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(
                CONF_SENSOR_BATTERY,
                description={"suggested_value": options.get(CONF_SENSOR_BATTERY)},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        }
    )


def build_thresholds_schema(options: dict[str, Any]) -> vol.Schema:
    """Build schema for environmental thresholds and wildlife protection."""
    return vol.Schema(
        {
            vol.Required(
                CONF_DEW_SPREAD_MIN,
                default=options.get(CONF_DEW_SPREAD_MIN, DEFAULT_DEW_SPREAD_MIN),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.5,
                    max=6.0,
                    step=0.1,
                    unit_of_measurement="°C",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_MIN_TEMP,
                default=options.get(CONF_MIN_TEMP, DEFAULT_MIN_TEMP),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=4.0,
                    max=16.0,
                    step=0.5,
                    unit_of_measurement="°C",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_HEAT_LIMIT,
                default=options.get(CONF_HEAT_LIMIT, DEFAULT_HEAT_LIMIT),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=22.0,
                    max=38.0,
                    step=0.5,
                    unit_of_measurement="°C",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_MOISTURE_THRESHOLD,
                default=options.get(CONF_MOISTURE_THRESHOLD, DEFAULT_MOISTURE_THRESHOLD),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.5,
                    max=30.0,
                    step=0.5,
                    unit_of_measurement="pts",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_RADAR_RAIN_BUFFER,
                default=options.get(CONF_RADAR_RAIN_BUFFER, DEFAULT_RADAR_RAIN_BUFFER),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=10,
                    max=180,
                    step=10,
                    unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_WILDLIFE_ENABLED,
                default=options.get(CONF_WILDLIFE_ENABLED, True),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_WILDLIFE_SUNRISE_OFFSET,
                default=options.get(CONF_WILDLIFE_SUNRISE_OFFSET, DEFAULT_WILDLIFE_SUNRISE),
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
                default=options.get(CONF_WILDLIFE_SUNSET_OFFSET, DEFAULT_WILDLIFE_SUNSET),
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
                default=options.get(CONF_QUIET_HOURS_START, DEFAULT_QUIET_HOURS_START),
            ): selector.TimeSelector(),
            vol.Required(
                CONF_QUIET_HOURS_END,
                default=options.get(CONF_QUIET_HOURS_END, DEFAULT_QUIET_HOURS_END),
            ): selector.TimeSelector(),
        }
    )


def build_mower_schema(options: dict[str, Any], mower_type: str = MOWER_TYPE_CHAOS) -> vol.Schema:
    """Build schema for mower runtime, capacity and edge cut."""
    default_cap = (
        DEFAULT_CAPACITY_SYSTEMATIC
        if mower_type == MOWER_TYPE_SYSTEMATIC
        else DEFAULT_CAPACITY_CHAOS
    )
    return vol.Schema(
        {
            vol.Required(
                CONF_MOWER_CAPACITY,
                default=options.get(CONF_MOWER_CAPACITY, default_cap),
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
                default=options.get(CONF_MIN_BATTERY_LEVEL, DEFAULT_MIN_BATTERY),
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
                default=options.get(CONF_MAX_RUN_TIME, 0),
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
                default=options.get(CONF_MULTI_CYCLE, DEFAULT_MULTI_CYCLE),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_EDGE_CUT_INTERVAL,
                default=options.get(CONF_EDGE_CUT_INTERVAL, 0),
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
                description={"suggested_value": options.get(CONF_EDGE_CUT_SERVICE, "")},
            ): selector.TextSelector(),
            vol.Optional(
                CONF_EDGE_CUT_DATA,
                description={"suggested_value": options.get(CONF_EDGE_CUT_DATA, "")},
            ): selector.TextSelector(),
        }
    )


class MowMasterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MowMaster."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._basic_data: dict[str, Any] = {}
        self._pro_options: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle initial step: basic configuration with optional direct Pro setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mower_entity = user_input[CONF_MOWER_ENTITY]
            await self.async_set_unique_id(f"mowmaster_{mower_entity}")
            self._abort_if_unique_id_configured()

            # Set mower capacity default
            mower_type = user_input.get(CONF_MOWER_TYPE, DEFAULT_MOWER_TYPE)
            if CONF_MOWER_CAPACITY not in user_input:
                user_input[CONF_MOWER_CAPACITY] = (
                    DEFAULT_CAPACITY_SYSTEMATIC
                    if mower_type == MOWER_TYPE_SYSTEMATIC
                    else DEFAULT_CAPACITY_CHAOS
                )

            self._basic_data = user_input

            # If user checked Pro configuration, lead directly into Pro setup steps
            if user_input.get(CONF_CONFIGURE_PRO, False):
                return await self.async_step_pro_sensors()

            # Otherwise finish immediately
            state = self.hass.states.get(mower_entity)
            name = state.name if state else mower_entity
            return self.async_create_entry(title=f"MowMaster ({name})", data=self._basic_data)

        return self.async_show_form(
            step_id="user",
            data_schema=build_basic_schema({}, include_pro_toggle=True),
            errors=errors,
        )

    async def async_step_pro_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 2: Pro sensors configuration during initial flow."""
        if user_input is not None:
            self._pro_options.update(user_input)
            return await self.async_step_pro_thresholds()

        return self.async_show_form(
            step_id="pro_sensors",
            data_schema=build_sensors_schema(self._pro_options),
        )

    async def async_step_pro_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 3: Thresholds and wildlife during initial flow."""
        if user_input is not None:
            self._pro_options.update(user_input)
            return await self.async_step_pro_mower()

        return self.async_show_form(
            step_id="pro_thresholds",
            data_schema=build_thresholds_schema(self._pro_options),
        )

    async def async_step_pro_mower(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 4: Mower management and edge cutting during initial flow."""
        if user_input is not None:
            self._pro_options.update(user_input)
            mower_entity = self._basic_data[CONF_MOWER_ENTITY]
            state = self.hass.states.get(mower_entity)
            name = state.name if state else mower_entity
            return self.async_create_entry(
                title=f"MowMaster ({name})",
                data=self._basic_data,
                options=self._pro_options,
            )

        mower_type = self._basic_data.get(CONF_MOWER_TYPE, DEFAULT_MOWER_TYPE)
        return self.async_show_form(
            step_id="pro_mower",
            data_schema=build_mower_schema(self._pro_options, mower_type),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return MowMasterOptionsFlow(config_entry)


class MowMasterOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for MowMaster Basic and Pro settings."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow using internal _config_entry."""
        self._config_entry = config_entry
        self._options = dict(config_entry.options)

    def _merged_current(self) -> dict[str, Any]:
        """Return merged dictionary of entry data and options."""
        merged = dict(self._config_entry.data)
        merged.update(self._options)
        return merged

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Present options menu for Basic and Pro settings."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["basic", "sensors", "thresholds", "mower_management"],
        )

    async def async_step_basic(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure basic lawn area, mower type, irrigation, and entities."""
        if user_input is not None:
            self._options.update(user_input)
            return await self._async_save_options()

        return self.async_show_form(
            step_id="basic",
            data_schema=build_basic_schema(self._merged_current(), include_pro_toggle=False),
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure optional local weather and soil sensors."""
        if user_input is not None:
            for key in ALL_SENSOR_KEYS:
                val = user_input.get(key)
                if val:
                    self._options[key] = val
                else:
                    self._options.pop(key, None)
            return await self._async_save_options()

        return self.async_show_form(
            step_id="sensors",
            data_schema=build_sensors_schema(self._options),
        )

    async def async_step_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure weather thresholds, wildlife and quiet hours."""
        if user_input is not None:
            self._options.update(user_input)
            return await self._async_save_options()

        return self.async_show_form(
            step_id="thresholds",
            data_schema=build_thresholds_schema(self._options),
        )

    async def async_step_mower_management(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Configure runtime limits, battery thresholds, and edge mowing."""
        if user_input is not None:
            self._options.update(user_input)
            for opt_key in (CONF_EDGE_CUT_SERVICE, CONF_EDGE_CUT_DATA):
                val = user_input.get(opt_key)
                if val and str(val).strip():
                    self._options[opt_key] = str(val).strip()
                else:
                    self._options.pop(opt_key, None)
            return await self._async_save_options()

        mower_type = self._options.get(
            CONF_MOWER_TYPE, self._config_entry.data.get(CONF_MOWER_TYPE, DEFAULT_MOWER_TYPE)
        )
        return self.async_show_form(
            step_id="mower_management",
            data_schema=build_mower_schema(self._options, mower_type),
        )

    async def _async_save_options(self) -> config_entries.ConfigFlowResult:
        """Save updated options."""
        return self.async_create_entry(title="", data=self._options)
