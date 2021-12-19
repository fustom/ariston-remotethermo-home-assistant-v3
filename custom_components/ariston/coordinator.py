"""Coordinator class for Ariston module."""
from __future__ import annotations
from datetime import timedelta

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .device import AristonDevice
from .ariston import DeviceAttribute

_LOGGER = logging.getLogger(__name__)


class DeviceDataUpdateCoordinator(DataUpdateCoordinator):
    """Manages polling for state changes from the device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: AristonDevice,
    ) -> None:
        """Initialize the data update coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{device.attributes[DeviceAttribute.PLANT_NAME]}",
            update_interval=timedelta(seconds=60),
        )

        self.device = device

    async def _async_update_data(self):
        await self.device.async_update_state()
