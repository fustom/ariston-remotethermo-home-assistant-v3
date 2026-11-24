"""Coordinator class for Ariston module."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any

from ariston.ariston_api import ConnectionException
from ariston.base_device import AristonBaseDevice
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def rate_limit_retry_after(error: BaseException) -> float | None:
    """Return seconds to wait if error is an Ariston 429, else None.

    Newer ariston libraries raise RateLimitException with a retry_after
    attribute; older ones raise ConnectionException(429, ...) without it,
    which maps to 0 (rate limited, duration unknown).
    """
    if not isinstance(error, ConnectionException) or error.args[:1] != (429,):
        return None
    return float(getattr(error, "retry_after", 0) or 0)


class DeviceDataUpdateCoordinator(DataUpdateCoordinator):
    """Manages polling for state changes from the device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: AristonBaseDevice,
        scan_interval_seconds: int,
        coordinator_name: str,
        async_update_state: Callable,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize the data update coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN}-{device.name}-{coordinator_name}",
            update_interval=timedelta(seconds=scan_interval_seconds),
            update_method=async_update_state,
        )

        self.device = device
        self.rated_power_w: int | None = None

    async def _async_update_data(self) -> Any:
        """Report Ariston rate limits and HTTP server errors as failed updates."""
        try:
            return await super()._async_update_data()
        except ConnectionException as error:
            if (retry_after := rate_limit_retry_after(error)) is not None:
                # Only ever slow polling down: a block shorter than the normal
                # interval must not make this coordinator poll sooner.
                interval = (
                    self.update_interval.total_seconds() if self.update_interval else 0
                )
                raise UpdateFailed(
                    f"Ariston cloud is rate limiting requests (HTTP 429); "
                    f"retrying in {max(retry_after, interval):.0f} seconds",
                    retry_after=retry_after if retry_after > interval else None,
                ) from error
            match error.args:
                case (int(status),) if 500 <= status < 600:
                    raise UpdateFailed(f"Ariston cloud returned HTTP {status}") from error
            raise
