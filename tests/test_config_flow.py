"""Tests for the RutOS config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch


from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.rutos.api import RutOSAuthError, RutOSConnectionError
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from custom_components.rutos.const import (
    CONF_FAILOVER_GROUPS,
    CONF_UPDATE_HOME_LOCATION,
    DOMAIN,
)


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
    with (
        patch("custom_components.rutos.config_flow.RutOSAPI") as mock_api_cls,
        patch("custom_components.rutos.async_setup_entry", return_value=True),
    ):
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
    with patch("custom_components.rutos.config_flow.RutOSAPI") as mock_api_cls:
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
    with patch("custom_components.rutos.config_flow.RutOSAPI") as mock_api_cls:
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
    with patch("custom_components.rutos.config_flow.RutOSAPI") as mock_api_cls:
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

    with patch("custom_components.rutos.config_flow.RutOSAPI") as mock_api_cls:
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

    with (
        patch("custom_components.rutos.config_flow.RutOSAPI") as mock_api_cls,
        patch("custom_components.rutos.async_setup_entry", return_value=True),
    ):
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


async def test_options_flow_shows_form(hass: HomeAssistant, mock_config_entry):
    """Test options flow shows init form with default values."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.rutos.async_setup_entry", return_value=True):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_init_advances_to_failover_groups(
    hass: HomeAssistant, mock_config_entry, mock_api
):
    """Test submitting init step advances to failover_groups step."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.rutos.RutOSAPI", return_value=mock_api):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_UPDATE_HOME_LOCATION: True},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "failover_groups"


async def test_options_flow_saves_failover_groups(
    hass: HomeAssistant, mock_config_entry, mock_api
):
    """Test full options flow saves both general options and failover groups."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.rutos.RutOSAPI", return_value=mock_api):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # Step 1: init
        result = await hass.config_entries.options.async_init(
            mock_config_entry.entry_id
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={CONF_UPDATE_HOME_LOCATION: False},
        )

        # Step 2: failover_groups — saving triggers a reload via the update
        # listener, which re-instantiates RutOSAPI; keep the patch active and
        # flush pending tasks so the reload uses the mock.
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "mob1s1a1": "Cellular",
                "mob1s2a1": "Cellular",
                "wan1": "Starlink",
                "wan2": "WiFi",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_UPDATE_HOME_LOCATION] is False
    assert mock_config_entry.options[CONF_FAILOVER_GROUPS] == {
        "Cellular": ["mob1s1a1", "mob1s2a1"],
        "Starlink": ["wan1"],
        "WiFi": ["wan2"],
    }


async def test_options_flow_too_few_groups_error(
    hass: HomeAssistant, mock_config_entry, mock_api
):
    """Test that fewer than 2 distinct labels shows an error."""
    mock_config_entry.add_to_hass(hass)

    with patch("custom_components.rutos.RutOSAPI", return_value=mock_api):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_UPDATE_HOME_LOCATION: True},
    )

    # All interfaces same label
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "mob1s1a1": "All",
            "mob1s2a1": "All",
            "wan1": "All",
            "wan2": "All",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "too_few_groups"}
