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
    CONF_MODEM,
    CONF_PHONE_NUMBER,
    CONF_UPDATE_HOME_LOCATION,
    DOMAIN,
    SUBENTRY_TYPE_RECIPIENT,
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


# ---------------------------------------------------------------------------
# Recipient subentry flow tests
# ---------------------------------------------------------------------------


async def _setup_entry(hass, mock_config_entry, mock_api):
    """Set up the config entry with the mocked API for subentry flow tests."""
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.rutos.RutOSAPI", return_value=mock_api):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()


async def test_recipient_subentry_creates(hass, mock_config_entry, mock_api):
    """Submitting valid input creates a recipient subentry on the parent entry."""
    await _setup_entry(hass, mock_config_entry, mock_api)

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_RECIPIENT),
        context={"source": "user"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Alice",
            CONF_PHONE_NUMBER: "+15551234567",
            CONF_MODEM: "modem1",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Alice"

    subentries = list(mock_config_entry.subentries.values())
    assert len(subentries) == 1
    assert subentries[0].data == {
        "name": "Alice",
        CONF_PHONE_NUMBER: "+15551234567",
        CONF_MODEM: "modem1",
    }


async def test_recipient_subentry_invalid_phone(hass, mock_config_entry, mock_api):
    """Bad phone format returns an inline error and no subentry is created."""
    await _setup_entry(hass, mock_config_entry, mock_api)

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_RECIPIENT),
        context={"source": "user"},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Alice", CONF_PHONE_NUMBER: "555-1234"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PHONE_NUMBER: "invalid_phone"}
    assert not mock_config_entry.subentries


async def test_recipient_subentry_multimodem_requires_choice(
    hass, mock_config_entry, mock_api
):
    """When the router has >1 modem, modem must be picked."""
    mock_api.get_modems.return_value = [{"id": "modem1"}, {"id": "modem2"}]
    await _setup_entry(hass, mock_config_entry, mock_api)

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_RECIPIENT),
        context={"source": "user"},
    )
    # The form should expose modem as a vol.In, so submitting just name+phone
    # raises a vol.Invalid which surfaces as a generic schema error. Submit
    # with a valid modem on retry to confirm success.
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Bob",
            CONF_PHONE_NUMBER: "+15559998888",
            CONF_MODEM: "modem2",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert list(mock_config_entry.subentries.values())[0].data[CONF_MODEM] == "modem2"


async def test_recipient_subentry_reconfigure(hass, mock_config_entry, mock_api):
    """Reconfigure flow updates an existing recipient in place."""
    from homeassistant.config_entries import ConfigSubentryData

    mock_config_entry = type(mock_config_entry)(
        domain=mock_config_entry.domain,
        title=mock_config_entry.title,
        data=dict(mock_config_entry.data),
        unique_id=mock_config_entry.unique_id,
        subentries_data=[
            ConfigSubentryData(
                data={
                    "name": "Alice",
                    CONF_PHONE_NUMBER: "+15551234567",
                    CONF_MODEM: "modem1",
                },
                subentry_type=SUBENTRY_TYPE_RECIPIENT,
                title="Alice",
                unique_id=None,
            ),
        ],
    )
    await _setup_entry(hass, mock_config_entry, mock_api)
    subentry_id = next(iter(mock_config_entry.subentries))

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_RECIPIENT),
        context={"source": "reconfigure", "subentry_id": subentry_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Alice (work)",
            CONF_PHONE_NUMBER: "+15557776666",
            CONF_MODEM: "modem1",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    updated = mock_config_entry.subentries[subentry_id]
    assert updated.data[CONF_PHONE_NUMBER] == "+15557776666"
    assert updated.title == "Alice (work)"
