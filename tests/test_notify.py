"""Tests for the RutOS notify platform (SMS)."""

from __future__ import annotations

from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest

from homeassistant.config_entries import ConfigSubentry
from homeassistant.exceptions import HomeAssistantError

from custom_components.rutos.api import RutOSAPIError
from custom_components.rutos.const import (
    CONF_MODEM,
    CONF_PHONE_NUMBER,
    SUBENTRY_TYPE_RECIPIENT,
)
from custom_components.rutos.coordinator import RutOSDataUpdateCoordinator
from custom_components.rutos.notify import RutosSmsNotifyEntity


def _make_subentry(
    *,
    name: str = "Alice",
    phone: str = "+15551234567",
    modem: str | None = None,
    subentry_id: str = "sub-alice",
) -> ConfigSubentry:
    """Build a recipient ConfigSubentry for tests."""
    data: dict = {"name": name, CONF_PHONE_NUMBER: phone}
    if modem:
        data[CONF_MODEM] = modem
    return ConfigSubentry(
        data=MappingProxyType(data),
        subentry_type=SUBENTRY_TYPE_RECIPIENT,
        title=name,
        unique_id=None,
        subentry_id=subentry_id,
    )


class TestRutosSmsNotifyEntity:
    """Tests for the SMS notify entity."""

    def test_unique_id_includes_subentry_id(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """unique_id is {serial}_sms_{subentry_id}."""
        entity = RutosSmsNotifyEntity(mock_coordinator, _make_subentry())
        assert entity.unique_id == "1234567890_sms_sub-alice"

    def test_name_uses_recipient(self, mock_coordinator: RutOSDataUpdateCoordinator):
        """Entity name is 'SMS <recipient>'."""
        entity = RutosSmsNotifyEntity(mock_coordinator, _make_subentry(name="Bob"))
        assert entity.name == "SMS Bob"

    async def test_send_uses_explicit_modem(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Modem stored on the subentry is passed to api.send_sms."""
        entity = RutosSmsNotifyEntity(
            mock_coordinator,
            _make_subentry(phone="+15550001111", modem="modem9"),
        )

        await entity.async_send_message("hello world")

        mock_coordinator.api.send_sms.assert_awaited_once_with(
            "+15550001111", "hello world", "modem9"
        )

    async def test_send_auto_picks_single_modem(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """No modem on subentry, router has one modem -> auto-pick it."""
        # mock_modems fixture defaults to [{"id": "modem1"}].
        entity = RutosSmsNotifyEntity(mock_coordinator, _make_subentry())

        await entity.async_send_message("ping")

        mock_coordinator.api.send_sms.assert_awaited_once_with(
            "+15551234567", "ping", "modem1"
        )

    async def test_send_title_prefixed(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Title is prepended to the message body since SMS has no title field."""
        entity = RutosSmsNotifyEntity(mock_coordinator, _make_subentry())

        await entity.async_send_message("door open", title="ALERT")

        mock_coordinator.api.send_sms.assert_awaited_once_with(
            "+15551234567", "ALERT: door open", "modem1"
        )

    async def test_send_ambiguous_modem_raises(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Multiple modems with no explicit choice -> HomeAssistantError."""
        mock_coordinator.data.modems = [{"id": "modemA"}, {"id": "modemB"}]
        entity = RutosSmsNotifyEntity(mock_coordinator, _make_subentry())

        with pytest.raises(HomeAssistantError, match="multiple modems"):
            await entity.async_send_message("hi")
        mock_coordinator.api.send_sms.assert_not_called()

    async def test_send_no_modem_raises(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Router reports no modems -> HomeAssistantError."""
        mock_coordinator.data.modems = []
        entity = RutosSmsNotifyEntity(mock_coordinator, _make_subentry())

        with pytest.raises(HomeAssistantError, match="No modem available"):
            await entity.async_send_message("hi")

    async def test_send_api_error_wrapped(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """RutOSAPIError surfaces as HomeAssistantError."""
        mock_coordinator.api.send_sms = AsyncMock(
            side_effect=RutOSAPIError("invalid number")
        )
        entity = RutosSmsNotifyEntity(mock_coordinator, _make_subentry())

        with pytest.raises(HomeAssistantError, match="Failed to send SMS"):
            await entity.async_send_message("hi")

    async def test_send_empty_phone_raises(
        self, mock_coordinator: RutOSDataUpdateCoordinator
    ):
        """Subentry with no phone number is rejected before any API call."""
        entity = RutosSmsNotifyEntity(mock_coordinator, _make_subentry(phone=""))

        with pytest.raises(HomeAssistantError, match="no phone number"):
            await entity.async_send_message("hi")
        mock_coordinator.api.send_sms.assert_not_called()
