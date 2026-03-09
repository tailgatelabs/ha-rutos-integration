"""Tests for the RutOS config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.rutos.api import RutOSAuthError, RutOSConnectionError
from custom_components.rutos.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, DOMAIN

USER_INPUT = {
    CONF_HOST: "192.168.1.1",
    CONF_USERNAME: "admin",
    CONF_PASSWORD: "admin01",
}

DEVICE_INFO = {
    "name": "RUTX50",
    "serial": "1234567890",
    "mac": "00:1E:42:AA:BB:CC",
    "model": "RUTX50",
    "firmware": "RUTX_R_00.07.06.1",
}


async def test_form_shown_on_init(hass: HomeAssistant):
    """Test the form is displayed on first step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_successful_config_flow(hass: HomeAssistant):
    """Test a complete successful config flow creates an entry."""
    with patch(
        "custom_components.rutos.config_flow.RutOSAPI"
    ) as mock_api_cls:
        mock_api = AsyncMock()
        mock_api.login.return_value = None
        mock_api.get_device_info.return_value = DEVICE_INFO
        mock_api_cls.return_value = mock_api

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "RUTX50"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == "1234567890"


async def test_invalid_auth_error(hass: HomeAssistant):
    """Test RutOSAuthError shows invalid_auth error."""
    with patch(
        "custom_components.rutos.config_flow.RutOSAPI"
    ) as mock_api_cls:
        mock_api = AsyncMock()
        mock_api.login.side_effect = RutOSAuthError("bad password")
        mock_api_cls.return_value = mock_api

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_cannot_connect_error(hass: HomeAssistant):
    """Test RutOSConnectionError shows cannot_connect error."""
    with patch(
        "custom_components.rutos.config_flow.RutOSAPI"
    ) as mock_api_cls:
        mock_api = AsyncMock()
        mock_api.login.side_effect = RutOSConnectionError("refused")
        mock_api_cls.return_value = mock_api

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_unknown_error(hass: HomeAssistant):
    """Test unexpected exception shows unknown error."""
    with patch(
        "custom_components.rutos.config_flow.RutOSAPI"
    ) as mock_api_cls:
        mock_api = AsyncMock()
        mock_api.login.side_effect = RuntimeError("oops")
        mock_api_cls.return_value = mock_api

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_duplicate_device_aborts(hass: HomeAssistant, mock_config_entry):
    """Test same serial number aborts with already_configured."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.rutos.config_flow.RutOSAPI"
    ) as mock_api_cls:
        mock_api = AsyncMock()
        mock_api.login.return_value = None
        mock_api.get_device_info.return_value = DEVICE_INFO
        mock_api_cls.return_value = mock_api

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_no_serial_creates_entry_without_unique_id(hass: HomeAssistant):
    """Test that missing serial still creates an entry using model as title."""
    device_info_no_serial = {
        "name": "RUTX50",
        "model": "RUTX50",
        "firmware": "RUTX_R_00.07.06.1",
    }

    with patch(
        "custom_components.rutos.config_flow.RutOSAPI"
    ) as mock_api_cls:
        mock_api = AsyncMock()
        mock_api.login.return_value = None
        mock_api.get_device_info.return_value = device_info_no_serial
        mock_api_cls.return_value = mock_api

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "RUTX50"
