"""Notify platform for sending SMS via a RutOS router."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RutOSConfigEntry
from .api import RutOSAPIError
from .const import CONF_MODEM, CONF_PHONE_NUMBER, SUBENTRY_TYPE_RECIPIENT
from .coordinator import RutOSDataUpdateCoordinator
from .entity import RutOSEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RutOSConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one notify entity per recipient subentry."""
    coordinator = entry.runtime_data
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_RECIPIENT:
            continue
        async_add_entities(
            [RutosSmsNotifyEntity(coordinator, subentry)],
            config_subentry_id=subentry_id,
        )


class RutosSmsNotifyEntity(RutOSEntity, NotifyEntity):
    """Notify entity that sends SMS to a configured recipient."""

    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(
        self,
        coordinator: RutOSDataUpdateCoordinator,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize from the recipient subentry."""
        super().__init__(coordinator)
        self._subentry = subentry
        recipient_name = str(subentry.data.get(CONF_NAME, "Recipient"))
        self._attr_name = f"SMS {recipient_name}"
        serial = coordinator.data.device_info.get("serial", "")
        self._attr_unique_id = f"{serial}_sms_{subentry.subentry_id}"

    def _resolve_modem(self) -> str:
        """Return the modem id to send through, or raise HomeAssistantError."""
        configured = self._subentry.data.get(CONF_MODEM)
        if configured:
            return str(configured)
        modem_ids = [
            m["id"]
            for m in self.coordinator.data.modems
            if isinstance(m, dict) and m.get("id")
        ]
        if len(modem_ids) == 1:
            return modem_ids[0]
        if not modem_ids:
            raise HomeAssistantError(
                "No modem available on the router to send SMS through"
            )
        raise HomeAssistantError(
            "Router has multiple modems; edit this recipient and pick one "
            f"({', '.join(modem_ids)})"
        )

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Send an SMS to the configured phone number."""
        number = str(self._subentry.data.get(CONF_PHONE_NUMBER, "")).strip()
        if not number:
            raise HomeAssistantError("Recipient has no phone number configured")
        body = f"{title}: {message}" if title else message
        modem = self._resolve_modem()
        try:
            await self.coordinator.api.send_sms(number, body, modem)
        except RutOSAPIError as err:
            raise HomeAssistantError(f"Failed to send SMS: {err}") from err
