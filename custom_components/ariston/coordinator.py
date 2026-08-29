"""Coordinator class for Ariston module."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from ariston.base_device import AristonBaseDevice
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Write prop -> (device attribute holding the confirmed value,
#                device method that (re)issues the write)
DEVICE_WRITE_PROPS: dict[str, tuple[str, str]] = {
    "temperature": (
        "water_heater_target_temperature",
        "async_set_water_heater_temperature",
    ),
    "operation_mode": (
        "water_heater_current_mode_text",
        "async_set_water_heater_operation_mode",
    ),
}


@dataclass
class PendingWrite:
    """A write whose effect still has to show up in a regular poll."""

    prop: str  # "temperature" | "operation_mode" | "boost"
    expected: Any
    tries: int = 0
    max_tries: int = 3


class DeviceDataUpdateCoordinator(DataUpdateCoordinator):
    """Manages polling for state changes from the device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: AristonBaseDevice,
        scan_interval_seconds: int,
        coordinator_name: str,
        async_update_state: Callable,
    ) -> None:
        """Initialize the data update coordinator."""
        self._async_device_update_state = async_update_state
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{device.name}-{coordinator_name}",
            update_interval=timedelta(seconds=scan_interval_seconds),
            update_method=self._async_update_and_verify,
        )

        self.device = device
        self.pending_writes: dict[str, PendingWrite] = {}

    async def _async_update_and_verify(self):
        """Poll the device, then verify pending writes against the new state.

        Verification rides on the regular poll — no extra API reads.
        """
        data = await self._async_device_update_state()
        await self._async_check_pending_writes()
        return data

    async def _async_check_pending_writes(self) -> None:
        """Check pending writes against freshly polled device state.

        Match: clear. Mismatch with tries left: write again. Out of tries:
        warn and give up, so verification can never become a write loop.
        """
        for prop, pending in list(self.pending_writes.items()):
            if prop not in DEVICE_WRITE_PROPS:
                _LOGGER.warning(
                    "No verification accessor for pending write %s; dropping it",
                    prop,
                )
                del self.pending_writes[prop]
                continue
            read_attr, write_attr = DEVICE_WRITE_PROPS[prop]
            try:
                actual = getattr(self.device, read_attr)
            except (AttributeError, NameError):
                # Device type does not expose this property.
                del self.pending_writes[prop]
                continue

            if actual == pending.expected:
                del self.pending_writes[prop]
                continue

            if pending.tries >= pending.max_tries:
                _LOGGER.warning(
                    "Write verification for %s gave up after %s tries "
                    "(device stayed at %s, expected %s)",
                    prop,
                    pending.max_tries,
                    actual,
                    pending.expected,
                )
                del self.pending_writes[prop]
                continue

            pending.tries += 1
            try:
                await getattr(self.device, write_attr)(pending.expected)
            except Exception as err:  # noqa: BLE001 - a failed retry must never kill polling
                _LOGGER.warning(
                    "Retry write for %s failed (%s); trying again next poll",
                    prop,
                    err,
                )
