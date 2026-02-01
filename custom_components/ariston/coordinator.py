"""Coordinator class for Ariston module."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
import asyncio
from typing import Any

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
        )

        self.device = device
        self._async_update_state = async_update_state
        self._is_updating = False

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API with unlimited retry logic."""
        # Prevent multiple simultaneous updates
        if self._is_updating:
            _LOGGER.debug("%s update already in progress, skipping", self.name)
            return {}
            
        self._is_updating = True
        try:
            while True:
                try:
                    _LOGGER.debug("Updating %s data", self.name)
                    result = await self._async_update_state()
                    return result
                    
                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.warning(
                        "Error updating %s data: %s. Retrying in 30 seconds...",
                        self.name,
                        err
                    )
                    await asyncio.sleep(30)  # Wait 30 seconds before retry
                    
        finally:
            self._is_updating = False