"""Device class for Ariston module."""
from __future__ import annotations
from ast import Raise

import datetime as dt
import logging

from abc import ABC, abstractmethod
from typing import Any

from .ariston import (
    AristonAPI,
    ConsumptionProperties,
    ConsumptionTimeInterval,
    ConsumptionType,
    Currency,
    CustomDeviceFeatures,
    DeviceAttribute,
    DeviceFeatures,
    GasEnergyUnit,
    GasType,
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
        self.consumption_sequence_last_changed_utc: dt.datetime = None

    async def async_get_features(self) -> None:
        """Get device features wrapper"""
        self.features = await self.api.async_get_features_for_device(
            self.attributes.get(DeviceAttribute.GW)
        )

    @abstractmethod
    async def async_update_state(self) -> None:
        """Update the device states from the cloud"""
        Raise(NotImplementedError)

    @abstractmethod
    def get_water_heater_temperature_step(self) -> None:
        """Abstract method for get water heater temperature step"""
        Raise(NotImplementedError)

    def get_elect_cost(self) -> float:
        """Get electric consumption cost"""
        return self.consumptions_settings.get(ConsumptionProperties.ELEC_COST)

    def get_gas_cost(self) -> float:
        """Get gas consumption cost"""
        return self.consumptions_settings.get(ConsumptionProperties.GAS_COST)

    def get_gas_type(self) -> str:
        """Get gas type"""
        return GasType(
            self.consumptions_settings.get(ConsumptionProperties.GAS_TYPE)
        ).name

    @staticmethod
    def get_gas_types() -> list[str]:
        """Get all gas types"""
        return [c.name for c in GasType]

    async def async_set_gas_type(self, selected: str):
        """Set gas type"""
        await self.async_set_consumptions_settings(
            ConsumptionProperties.GAS_TYPE, GasType[selected]
        )

    def get_currency(self) -> str:
        """Get gas type"""
        return Currency(
            self.consumptions_settings.get(ConsumptionProperties.CURRENCY)
        ).name

    @staticmethod
    def get_currencies() -> list[str]:
        """Get all currency"""
        return [c.name for c in Currency]

    async def async_set_currency(self, selected: str):
        """Set currency"""
        await self.async_set_consumptions_settings(
            ConsumptionProperties.CURRENCY, Currency[selected]
        )

    def get_gas_energy_unit(self) -> str:
        """Get gas energy unit"""
        return GasEnergyUnit(
            self.consumptions_settings.get(ConsumptionProperties.GAS_ENERGY_UNIT)
        ).name

    @staticmethod
    def get_gas_energy_units() -> list[str]:
        """Get all gas energy unit"""
        return [c.name for c in GasEnergyUnit]

    async def async_set_gas_energy_unit(self, selected: str):
        """Set gas energy unit"""
        await self.async_set_consumptions_settings(
            ConsumptionProperties.GAS_ENERGY_UNIT, GasEnergyUnit[selected]
        )

    def get_consumption_sequence_last_value(
        self, consumption_type: ConsumptionType, time_interval: ConsumptionTimeInterval
    ) -> int:
        """Get last value for consumption sequence"""
        for sequence in self.consumptions_sequences:
            if sequence["k"] == consumption_type and sequence["p"] == time_interval:
                return sequence["v"][-1]

        return "nan"

    def get_gas_consumption_for_heating_last_month(self) -> int:
        """Get gas consumption for heating last month"""
        return self.energy_account.get("LastMonth")[0]["gas"]

    def get_electricity_consumption_for_heating_last_month(self) -> int:
        """Get electricity consumption for heating last month"""
        return self.energy_account.get("LastMonth")[0]["elect"]

    def get_gas_consumption_for_water_last_month(self) -> int:
        """Get gas consumption for water last month"""
        return self.energy_account.get("LastMonth")[1]["gas"]

    def get_electricity_consumption_for_water_last_month(self) -> int:
        """Get electricity consumption for water last month"""
        return self.energy_account.get("LastMonth")[1]["elect"]

    def get_total_consumption_for_heating_last_two_hours(self) -> int:
        """Get total consumption for heating last two hours"""
        return self.get_consumption_sequence_last_value(
            ConsumptionType.HEATING_TOTAL_ENERGY, ConsumptionTimeInterval.TWO_HOURS
        )

    def get_total_consumption_for_water_last_two_hours(self) -> int:
        """Get total consumption for water last two hours"""
        return self.get_consumption_sequence_last_value(
            ConsumptionType.WATER_TOTAL_ENERGY, ConsumptionTimeInterval.TWO_HOURS
        )

    def get_gas_consumption_for_heating_last_two_hours(self) -> int:
        """Get gas consumption for heating last two hours"""
        return self.get_consumption_sequence_last_value(
            ConsumptionType.HEATING_GAS, ConsumptionTimeInterval.TWO_HOURS
        )

    def get_gas_consumption_for_water_last_two_hours(self) -> int:
        """Get gas consumption for water last two hours"""
        return self.get_consumption_sequence_last_value(
            ConsumptionType.WATER_GAS, ConsumptionTimeInterval.TWO_HOURS
        )

    def get_electricity_consumption_for_heating_last_two_hours(self) -> int:
        """Get electricity consumption for heating last two hours"""
        return self.get_consumption_sequence_last_value(
            ConsumptionType.HEATING_ELECTRICITY, ConsumptionTimeInterval.TWO_HOURS
        )

    def get_electricity_consumption_for_water_last_two_hours(self) -> int:
        """Get electricity consumption for water last two hours"""
        return self.get_consumption_sequence_last_value(
            ConsumptionType.WATER_ELECTRICITY, ConsumptionTimeInterval.TWO_HOURS
        )

    def get_consumption_sequence_last_changed_utc(self) -> dt.datetime:
        """Get consumption sequence last changed in utc"""
        return self.consumption_sequence_last_changed_utc

    async def async_update_energy(self) -> None:
        """Update the device energy settings from the cloud"""
        old_consumptions_sequences = self.consumptions_sequences
        self.consumptions_sequences = await self.api.async_get_consumptions_sequences(
            self.attributes.get(DeviceAttribute.GW),
            self.features.get(CustomDeviceFeatures.HAS_CH),
            self.features.get(CustomDeviceFeatures.HAS_DHW),
            self.features.get(DeviceFeatures.HAS_SLP),
        )

        if (
            old_consumptions_sequences is not None
            and old_consumptions_sequences != self.consumptions_sequences
        ):
            self.consumption_sequence_last_changed_utc = dt.datetime.now(
                dt.timezone.utc
            ) - dt.timedelta(hours=1)

        if self.extra_energy_features:
            # These settings only for official clients
            self.consumptions_settings = await self.api.async_get_consumptions_settings(
                self.attributes.get(DeviceAttribute.GW)
            )

            # Last month consumption in kwh
            self.energy_account = await self.api.async_get_energy_account(
                self.attributes.get(DeviceAttribute.GW)
            )

    async def async_set_elect_cost(self, value: float):
        """Set electric cost"""
        await self.async_set_consumptions_settings(
            ConsumptionProperties.ELEC_COST, value
        )

    async def async_set_gas_cost(self, value: float):
        """Set gas cost"""
        await self.async_set_consumptions_settings(
            ConsumptionProperties.GAS_COST, value
        )

    async def async_set_consumptions_settings(
        self, consumption_property: ConsumptionProperties, value: float
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
