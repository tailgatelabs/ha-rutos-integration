"""Config flow for the RutOS integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RutOSAPI, RutOSAuthError, RutOSConnectionError
from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_UPDATE_HOME_LOCATION,
    CONF_USERNAME,
    DEFAULT_USERNAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class RutOSConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RutOS."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigFlow,
    ) -> RutOSOptionsFlowHandler:
        """Get the options flow for this handler."""
        return RutOSOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass, verify_ssl=False)
            api = RutOSAPI(
                host=user_input[CONF_HOST],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                session=session,
            )

            try:
                await api.login()
                device_info = await api.get_device_info()
            except RutOSAuthError:
                errors["base"] = "invalid_auth"
            except RutOSConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                serial = device_info.get("serial", "")
                if serial:
                    await self.async_set_unique_id(serial)
                    self._abort_if_unique_id_configured()

                title = device_info.get(
                    "model", device_info.get("name", "RutOS Device")
                )
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class RutOSOptionsFlowHandler(OptionsFlow):
    """Handle RutOS options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_HOME_LOCATION,
                        default=self.config_entry.options.get(
                            CONF_UPDATE_HOME_LOCATION, True
                        ),
                    ): bool,
                }
            ),
        )
