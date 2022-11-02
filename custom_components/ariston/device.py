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
    DeviceAttribute,
    GasEnergyUnit,
    GasType,
    VelisDeviceAttribute,
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
        self.custom_features: dict = {}
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

    def get_consumption_sequence_last_changed_utc(self) -> dt.datetime:
        """Get consumption sequence last changed in utc"""
        return self.consumption_sequence_last_changed_utc

    def get_central_heating_total_energy_consumption(self) -> int:
        """Get central heating total energy consumption"""
        return self.get_consumption_sequence_last_value(
            ConsumptionType.CENTRAL_HEATING_TOTAL_ENERGY,
            ConsumptionTimeInterval.LAST_DAY,
        )

    def get_domestic_hot_water_total_energy_consumption(self) -> int:
        """Get domestic hot water total energy consumption"""
        return self.get_consumption_sequence_last_value(
            ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY,
            ConsumptionTimeInterval.LAST_DAY,
        )

    def get_central_heating_gas_consumption(self) -> int:
        """Get central heating gas consumption"""
        return self.get_consumption_sequence_last_value(
            ConsumptionType.CENTRAL_HEATING_GAS,
            ConsumptionTimeInterval.LAST_DAY,
        )

    def get_domestic_hot_water_heating_pump_electricity_consumption(self) -> int:
        """Get domestic hot water heating pump electricity consumption"""
        return self.get_consumption_sequence_last_value(
            ConsumptionType.DOMESTIC_HOT_WATER_HEATING_PUMP_ELECTRICITY,
            ConsumptionTimeInterval.LAST_DAY,
        )

    def get_domestic_hot_water_resistor_electricity_consumption(self) -> int:
        """Get domestic hot water resistor electricity consumption"""
        return self.get_consumption_sequence_last_value(
            ConsumptionType.DOMESTIC_HOT_WATER_RESISTOR_ELECTRICITY,
            ConsumptionTimeInterval.LAST_DAY,
        )

    def get_domestic_hot_water_gas_consumption(self) -> int:
        """Get domestic hot water gas consumption"""
        return self.get_consumption_sequence_last_value(
            ConsumptionType.DOMESTIC_HOT_WATER_GAS,
            ConsumptionTimeInterval.LAST_DAY,
        )

    def get_central_heating_electricity_consumption(self) -> int:
        """Get central heating electricity consumption"""
        return self.get_consumption_sequence_last_value(
            ConsumptionType.CENTRAL_HEATING_ELECTRICITY,
            ConsumptionTimeInterval.LAST_DAY,
        )

    def get_domestic_hot_water_electricity_consumption(self) -> int:
        """Get domestic hot water electricity consumption"""
        return self.get_consumption_sequence_last_value(
            ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY,
            ConsumptionTimeInterval.LAST_DAY,
        )

    def get_consumption_sequence_last_value(
        self,
        consumption_type: ConsumptionType,
        time_interval: ConsumptionTimeInterval,
    ) -> Any:
        """Get last value for consumption sequence"""
        for sequence in self.consumptions_sequences:
            if sequence["k"] == consumption_type and sequence["p"] == time_interval:
                return sequence["v"][-1]

        return "nan"

    @abstractmethod
    async def async_get_consumptions_sequences(self) -> dict[str, Any]:
        """Get consumption sequence"""
        Raise(NotImplementedError)

    async def async_update_energy(self) -> None:
        """Update the device energy settings from the cloud"""
        old_consumptions_sequences = self.consumptions_sequences
        await self.async_get_consumptions_sequences()

        if (
            self.custom_features.get(ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY)
            is None
        ):
            self.set_energy_features()

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

    def set_energy_features(self):
        """Set energy features"""
        for consumption_type in ConsumptionType:
            if (
                self.get_consumption_sequence_last_value(
                    consumption_type,
                    ConsumptionTimeInterval.LAST_DAY,
                )
                != "nan"
            ):
                self.custom_features[consumption_type.name] = True
            else:
                self.custom_features[consumption_type.name] = False

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
        if (
            system_types is not None
            and self.attributes.get(DeviceAttribute.SYS) not in system_types
            and self.attributes.get(VelisDeviceAttribute.WHE_TYPE) not in system_types
        ):
            return False

        if extra_energy_feature and not self.extra_energy_features:
            return False

        if device_features is not None:
            for device_feature in device_features:
                if (
                    self.features.get(device_feature) is not True
                    and self.custom_features.get(device_feature) is not True
                ):
                    return False

        return True
