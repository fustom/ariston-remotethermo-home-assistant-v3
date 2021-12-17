"""Coordinator class for Ariston module."""
from __future__ import annotations
from datetime import timedelta

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .device import AristonDevice
from .ariston import PlantMode, ZoneMode

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
            name=f"{DOMAIN}-{device.plant_name}",
            update_interval=timedelta(seconds=60),
        )

        self.device = device

    async def _async_update_data(self):
        await self.device.async_update_state()

    async def async_set_temperature(self, zone: int, temperature: float):
        """Set comfort temperature wrapper"""
        await self.device.thermostat(zone).async_set_temperature(temperature)

    async def async_set_plant_mode(self, plant_mode: PlantMode):
        """Set plant mode wrapper"""
        await self.device.async_set_plant_mode(plant_mode)

    async def async_set_zone_mode(self, zone: int, zone_mode: ZoneMode):
        """Set zone mode wrapper"""
        await self.device.thermostat(zone).async_set_mode(zone_mode)

    async def async_set_dhwtemp(self, temperature: float):
        """Set domestic hot water temperature wrapper"""
        await self.device.async_set_dhwtemp(temperature)
