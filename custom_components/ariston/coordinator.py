"""Coordinator class for Ariston module."""

from __future__ import annotations

import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ariston import ConnectionException
from ariston.base_device import AristonBaseDevice

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PendingWrite:
    """A command awaiting confirmation from a normal device poll."""

    expected: Any
    read_value: Callable[[], Any]
    retry_write: Callable[[], Awaitable[Any]]
    tolerance: float | None = None
    retries: int = 0
    max_retries: int = 3


def _values_match(actual: Any, pending: PendingWrite) -> bool:
    """Compare refreshed state with the command's expected value."""
    if pending.tolerance is not None:
        try:
            return math.isclose(
                float(actual),
                float(pending.expected),
                rel_tol=0.0,
                abs_tol=pending.tolerance,
            )
        except (TypeError, ValueError):
            return False
    return actual == pending.expected


class DeviceDataUpdateCoordinator(DataUpdateCoordinator):
    """Manages polling for state changes from the device."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry | None,
        device: AristonBaseDevice,
        scan_interval_seconds: int,
        coordinator_name: str,
        async_update_state: Callable[[], Awaitable[Any]],
    ) -> None:
        """Initialize the data update coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN}-{device.name}-{coordinator_name}",
            update_interval=timedelta(seconds=scan_interval_seconds),
        )

        self.device = device
        self._async_update_state = async_update_state
        self.pending_writes: dict[str, PendingWrite] = {}
        self._write_generations: dict[str, int] = {}
        self.water_heater_temperature_unit = "auto"

    def begin_pending_write(self, key: str) -> int:
        """Reserve the newest request for a property before its first await."""
        generation = self._write_generations.get(key, 0) + 1
        self._write_generations[key] = generation
        self.pending_writes.pop(key, None)
        return generation

    def track_pending_write(
        self,
        key: str,
        expected: Any,
        read_value: Callable[[], Any],
        retry_write: Callable[[], Awaitable[Any]],
        *,
        tolerance: float | None = None,
        generation: int | None = None,
    ) -> bool:
        """Replace any older command for the same device property."""
        if generation is None:
            generation = self.begin_pending_write(key)
        elif self._write_generations.get(key) != generation:
            return False
        self.pending_writes[key] = PendingWrite(
            expected=expected,
            read_value=read_value,
            retry_write=retry_write,
            tolerance=tolerance,
        )
        return True

    async def _async_check_pending_writes(self) -> None:
        """Confirm or reissue commands using already-refreshed device state."""
        for key, pending in tuple(self.pending_writes.items()):
            if self.pending_writes.get(key) is not pending:
                continue
            if _values_match(pending.read_value(), pending):
                if self.pending_writes.get(key) is pending:
                    self.pending_writes.pop(key)
                continue

            pending.retries += 1
            try:
                await pending.retry_write()
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "Failed to reissue Ariston write %s (%d/%d): %s",
                    key,
                    pending.retries,
                    pending.max_retries,
                    err,
                )

            if (
                pending.retries >= pending.max_retries
                and self.pending_writes.get(key) is pending
            ):
                self.pending_writes.pop(key)
                _LOGGER.warning(
                    "Ariston write %s was not confirmed after %d reissues",
                    key,
                    pending.retries,
                )

    async def _async_update_data(self) -> Any:
        """Fetch data once and let Home Assistant schedule another attempt."""
        try:
            result = await self._async_update_state()
        except ConnectionException as err:
            raise UpdateFailed(f"Error communicating with Ariston: {err}") from err
        await self._async_check_pending_writes()
        return result
