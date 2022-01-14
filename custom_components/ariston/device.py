"""Device class for Ariston module."""
from __future__ import annotations
from ast import Raise

import logging

from abc import ABC, abstractmethod
from typing import Any

from .ariston import (
    AristonAPI,
    ConsumptionProperties,
    CustomDeviceFeatures,
    DeviceAttribute,
    DeviceFeatures,
)

_LOGGER = logging.getLogger(__name__)


class AristonDevice(ABC):
    """Class representing a physical device, it's state and properties."""

    def __init__(
        self,
        attributes: dict[str, Any],
        api: AristonAPI,
        extra_energy_features: bool,
        is_metric: bool = True,
    ) -> None:
        self.api = api
        self.attributes = attributes
        self.extra_energy_features = extra_energy_features
        self.umsys = "si" if is_metric else "us"

        self.location = "en-US"

        self.features: dict = {}
        self.consumptions_settings: dict = {}
        self.energy_account: dict = {}
        self.consumptions_sequences: list = []
        self.data: dict = {}
        self.plant_settings: dict = {}

    async def async_get_features(self) -> None:
        """Get device features wrapper"""
        self.features = await self.api.async_get_features_for_device(
            self.attributes.get(DeviceAttribute.GW)
        )

    @abstractmethod
    def get_water_heater_temperature_step(self) -> None:
        """Abstract method for get water heater temperature step"""
        Raise(NotImplementedError)

    async def async_update_energy(self) -> None:
        """Update the device energy settings from the cloud"""

        # k=1: heating k=2: water
        # p=1: 12*2 hours p=2: 7*1 day p=3: 15*2 days p=4: 12*? year
        # v: first element is the latest, last element is the newest"""
        self.consumptions_sequences = await self.api.async_get_consumptions_sequences(
            self.attributes.get(DeviceAttribute.GW),
            self.features.get(CustomDeviceFeatures.HAS_CH),
            self.features.get(CustomDeviceFeatures.HAS_DHW),
            self.features.get(DeviceFeatures.HAS_SLP),
        )

        if self.extra_energy_features:
            # These settings only for official clients
            self.consumptions_settings = await self.api.async_get_consumptions_settings(
                self.attributes.get(DeviceAttribute.GW)
            )

            # Last month consumption in kwh
            self.energy_account = await self.api.async_get_energy_account(
                self.attributes.get(DeviceAttribute.GW)
            )

    async def async_set_consumptions_settings(
        self, consumption_property: ConsumptionProperties, value: int
    ):
        """Set consumption settings"""
        new_settings = self.consumptions_settings.copy()
        new_settings[consumption_property] = value
        await self.api.async_set_consumptions_settings(
            self.attributes.get(DeviceAttribute.GW), new_settings
        )
        self.consumptions_settings[consumption_property] = value

    def are_device_features_available(
        self, device_features, extra_energy_feature, system_types
    ) -> bool:
        """Checks features availability"""
        if self.attributes.get(DeviceAttribute.SYS) not in system_types:
            return False

        if extra_energy_feature and not self.extra_energy_features:
            return False

        if device_features is None:
            return True

        for device_feature in device_features:
            if self.features.get(device_feature) is not True:
                return False

        return True
