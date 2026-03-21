"""Config flow for the RutOS integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RutOSAPI, RutOSAuthError, RutOSConnectionError
from .const import (
    CONF_FAILOVER_GROUPS,
    CONF_UPDATE_HOME_LOCATION,
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

MAX_FAILOVER_GROUPS = 5


class RutOSConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RutOS."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
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

    def __init__(self) -> None:
        """Initialize options flow."""
        self._options_data: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage general options."""
        if user_input is not None:
            self._options_data.update(user_input)
            return await self.async_step_failover_groups()

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

    async def async_step_failover_groups(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure failover interface groups."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Group interfaces by label
            groups: dict[str, list[str]] = {}
            has_invalid_label = False
            for iface_id, label in user_input.items():
                label = label.strip()
                if "," in label:
                    has_invalid_label = True
                if label:
                    groups.setdefault(label, []).append(iface_id)

            if has_invalid_label:
                errors["base"] = "invalid_label"
            elif len(groups) < 2:  # noqa: PLR2004
                errors["base"] = "too_few_groups"
            elif len(groups) > MAX_FAILOVER_GROUPS:
                errors["base"] = "too_many_groups"
            else:
                self._options_data[CONF_FAILOVER_GROUPS] = groups
                return self.async_create_entry(title="", data=self._options_data)

        # Fetch current failover members from the router
        coordinator = self.config_entry.runtime_data
        members = await coordinator.api.get_failover_members()

        # Build reverse map: iface_id → existing label
        existing_groups: dict[str, list[str]] = self.config_entry.options.get(
            CONF_FAILOVER_GROUPS, {}
        )
        existing_labels: dict[str, str] = {}
        for label, ifaces in existing_groups.items():
            for iface in ifaces:
                existing_labels[iface] = label

        # Build dynamic schema: one text field per interface
        schema: dict[vol.Required, type] = {}
        for member in sorted(members, key=lambda m: int(m.get("metric", 0))):
            iface_id = member.get("interface", member.get("id", ""))
            default = existing_labels.get(iface_id, iface_id)
            if user_input and iface_id in user_input:
                default = user_input[iface_id]
            schema[vol.Required(iface_id, default=default)] = str

        return self.async_show_form(
            step_id="failover_groups",
            data_schema=vol.Schema(schema),
            errors=errors,
        )
