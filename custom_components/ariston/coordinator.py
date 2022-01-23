"""Coordinator class for Ariston module."""
from __future__ import annotations
from collections.abc import Callable
from datetime import timedelta

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .galevo_device import AristonGalevoDevice
from .velis_device import AristonVelisDevice
from .ariston import DeviceAttribute

_LOGGER = logging.getLogger(__name__)


class DeviceDataUpdateCoordinator(DataUpdateCoordinator):
    """Manages polling for state changes from the device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: AristonGalevoDevice or AristonVelisDevice,
        scan_interval_seconds: int,
        coordinator_name: str,
        async_update_state: Callable,
    ) -> None:
        """Initialize the data update coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{device.attributes.get(DeviceAttribute.NAME)}-{coordinator_name}",
            update_interval=timedelta(seconds=scan_interval_seconds),
        )

        self.device = device
        self.async_update_state = async_update_state

    async def _async_update_data(self):
        await self.async_update_state()
