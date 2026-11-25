"""Coordinator class for Ariston module."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
import time
from typing import Any

from ariston.ariston_api import ConnectionException
from ariston.base_device import AristonBaseDevice
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _find_rate_limit(error: BaseException | None) -> ConnectionException | None:
    """Return the Ariston 429 in error or its cause chain, if any.

    The client wraps a 429 raised during login in an empty
    ConnectionException, so the status is only on error.__cause__.
    """
    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, ConnectionException) and error.args[:1] == (429,):
            return error
        error = error.__cause__
    return None


def rate_limit_retry_after(error: BaseException, api: Any = None) -> float | None:
    """Return seconds to wait if error is an Ariston 429, else None.

    The delay comes from a retry_after attribute on the exception when the
    client provides one, otherwise from the client's own block deadline
    (AristonAPI._blocked_until), which it sets from the block duration in
    the 429 body. 0 means rate limited with no known duration.
    """
    if (rate_limit := _find_rate_limit(error)) is None:
        return None
    if (retry_after := getattr(rate_limit, "retry_after", None)) is not None:
        return max(0.0, float(retry_after))
    blocked_until = getattr(api, "_blocked_until", None)
    if isinstance(blocked_until, (int, float)):
        return max(0.0, blocked_until - time.time())
    return 0.0


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
            retry_after = rate_limit_retry_after(error, getattr(self.device, "api", None))
            if retry_after is not None:
                raise UpdateFailed(
                    "Ariston cloud is rate limiting requests (HTTP 429)",
                    retry_after=self._rate_limit_delay(retry_after),
                ) from error
            match error.args:
                case (int(status),) if 500 <= status < 600:
                    raise UpdateFailed(f"Ariston cloud returned HTTP {status}") from error
            raise

    def _rate_limit_delay(self, retry_after: float) -> float | None:
        """Return the retry_after to report for a 429, or None for the default.

        During setup (first refresh) Home Assistant retries after its own short
        back-off, so any known delay is passed on. After setup, polling only
        ever slows down: a block shorter than the scan interval keeps the
        normal schedule.
        """
        if not retry_after:
            return None
        if (
            self.config_entry is not None
            and self.config_entry.state is ConfigEntryState.SETUP_IN_PROGRESS
        ):
            return retry_after
        interval = self.update_interval.total_seconds() if self.update_interval else 0
        return retry_after if retry_after > interval else None
