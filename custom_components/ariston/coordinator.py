"""Coordinator class for Ariston module."""
from __future__ import annotations
from datetime import timedelta

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    COORDINATOR,
    DOMAIN,
    ENERGY_COORDINATOR,
)
from .device import AristonDevice
from .ariston import DeviceAttribute

_LOGGER = logging.getLogger(__name__)


class DeviceDataUpdateCoordinator(DataUpdateCoordinator):
    """Manages polling for state changes from the device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: AristonDevice,
        scan_interval_seconds: int,
    ) -> None:
        """Initialize the data update coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{device.attributes[DeviceAttribute.PLANT_NAME]}-{COORDINATOR}",
            update_interval=timedelta(seconds=scan_interval_seconds),
        )

        self.device = device

    async def _async_update_data(self):
        await self.device.async_update_state()


class DeviceEnergyUpdateCoordinator(DataUpdateCoordinator):
    """Manages polling for energy changes from the device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: AristonDevice,
        energy_interval_minutes: int,
    ) -> None:
        """Initialize the data update coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{device.attributes[DeviceAttribute.PLANT_NAME]}-{ENERGY_COORDINATOR}",
            update_interval=timedelta(minutes=energy_interval_minutes),
        )

        self.device = device

    async def _async_update_data(self):
        await self.device.async_update_energy()
