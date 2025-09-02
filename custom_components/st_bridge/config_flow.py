from __future__ import annotations

import voluptuous as vol
from typing import Any

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    ConfigEntry,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import selector

from .const import (
    DOMAIN,
    CONF_TOKEN,
    CONF_PORT,
    CONF_ENTITIES,
    DEFAULT_PORT,
    SUPPORTED_DOMAINS
)

def _entities_selector():
    """Return a selector for entity selection."""
    return selector({
        "entity": {
            "multiple": True,
            "filter": [{"domain": d} for d in sorted(SUPPORTED_DOMAINS)]
        }
    })

class STBridgeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ST Bridge."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step."""
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="ST Bridge",
                data={CONF_TOKEN: user_input[CONF_TOKEN], CONF_PORT: user_input[CONF_PORT]},
                options={CONF_ENTITIES: []},
            )
        schema = vol.Schema({
            vol.Required(CONF_TOKEN): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        })
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow for this config entry."""
        return STBridgeOptionsFlow(config_entry)


class STBridgeOptionsFlow(OptionsFlow):
    """Handle options for the ST Bridge config entry."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.entry.options.get(CONF_ENTITIES, [])
        schema = vol.Schema({vol.Required(CONF_ENTITIES, default=current): _entities_selector()})
        return self.async_show_form(step_id="init", data_schema=schema)
