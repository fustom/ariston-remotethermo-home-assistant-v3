"""Coordinator class for Ariston module."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
import logging

from ariston.ariston_api import ConnectionException
from ariston.base_device import AristonBaseDevice
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


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
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{device.name}-{coordinator_name}",
            update_interval=timedelta(seconds=scan_interval_seconds),
            update_method=self._async_update_with_rate_limit(async_update_state),
        )

        self.device = device
        self._original_update_interval = timedelta(seconds=scan_interval_seconds)
        self._async_update_state = async_update_state
        self._rate_limit_backoff = 1.0

    def _async_update_with_rate_limit(self, async_update_method: Callable) -> Callable:
        """Wrap the update method with rate limit handling."""

        async def wrapper() -> None:
            """Update data with rate limit handling."""
            try:
                return await async_update_method()
            except ConnectionException as err:
                if err.status == 429:
                    # Rate limit error - increase backoff and extend update interval
                    self._rate_limit_backoff = min(self._rate_limit_backoff * 2, 10.0)
                    new_interval = int(
                        self._original_update_interval.total_seconds()
                        * self._rate_limit_backoff
                    )
                    _LOGGER.warning(
                        "Rate limited (429) by Ariston API. Extending update interval "
                        "from %d to %d seconds for %s",
                        int(self._original_update_interval.total_seconds()),
                        new_interval,
                        self.name,
                    )
                    self.update_interval = timedelta(seconds=new_interval)
                    raise
                else:
                    # Reset backoff on other connection errors
                    self._rate_limit_backoff = 1.0
                    raise

        return wrapper

    async def _async_refresh(self) -> None:
        """Refresh data and reset backoff on success."""
        try:
            await super()._async_refresh()
            # Reset backoff on successful update
            if self._rate_limit_backoff > 1.0:
                self._rate_limit_backoff = 1.0
                _LOGGER.info(
                    "Rate limit recovered. Restoring original update interval for %s",
                    self.name,
                )
                self.update_interval = self._original_update_interval
        except Exception:
            # Log the error and re-raise
            raise


