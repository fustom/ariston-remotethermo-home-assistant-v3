"""Constants for the Ariston integration."""
import sys

from dataclasses import dataclass
from enum import IntFlag
from typing import final

from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.const import ENERGY_KILO_WATT_HOUR
from homeassistant.helpers.entity import EntityCategory

from .ariston import (
    ConsumptionProperties,
    Currency,
    DeviceProperties,
    GasEnergyUnit,
    GasType,
)


DOMAIN: final = "ariston"
NAME: final = "Ariston"
COORDINATOR: final = "coordinator"
ENERGY_COORDINATOR: final = "energy_coordinator"
ENERGY_SCAN_INTERVAL: final = "energy_scan_interval"
EXTRA_ENERGY_FEATURES: final = "extra_energy_features"

DEFAULT_SCAN_INTERVAL_SECONDS: final = 60
DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES: final = 60
DEFAULT_EXTRA_ENERGY_FEATURES: final = False

ATTR_TARGET_TEMP_STEP = "target_temp_step"

ARISTON_SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=DeviceProperties.HEATING_CIRCUIT_PRESSURE,
        name=f"{NAME} heating circuit pressure",
        device_class=SensorDeviceClass.PRESSURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=DeviceProperties.CH_FLOW_SETPOINT_TEMP,
        name=f"{NAME} CH flow setpoint temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)

ARISTON_BINARY_SENSOR_TYPES: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key=DeviceProperties.IS_FLAME_ON,
        name=f"{NAME} is flame on",
        icon="mdi:fire",
    ),
    BinarySensorEntityDescription(
        key=DeviceProperties.HOLIDAY,
        name=f"{NAME} holiday mode",
        icon="mdi:island",
    ),
)

ARISTON_SWITCH_TYPES: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(
        key=DeviceProperties.AUTOMATIC_THERMOREGULATION,
        name=f"{NAME} automatic thermoregulation",
        icon="mdi:radiator",
    ),
)

ARISTON_NUMBER_TYPES: tuple[NumberEntityDescription, ...] = (
    NumberEntityDescription(
        key=ConsumptionProperties.ELEC_COST,
        name=f"{NAME} elec cost",
        icon="mdi:currency-sign",
        entity_category=EntityCategory.CONFIG,
        min_value=0,
        max_value=sys.maxsize,
        step=0.01,
    ),
    NumberEntityDescription(
        key=ConsumptionProperties.GAS_COST,
        name=f"{NAME} gas cost",
        icon="mdi:currency-sign",
        entity_category=EntityCategory.CONFIG,
        min_value=0,
        max_value=sys.maxsize,
        step=0.01,
    ),
)


@dataclass
class AristonSelectEntityDescription(SelectEntityDescription):
    """A class that describes select entities."""

    enum_class: IntFlag or None = 0


ARISTON_SELECT_TYPES: tuple[AristonSelectEntityDescription, ...] = (
    AristonSelectEntityDescription(
        key=ConsumptionProperties.CURRENCY,
        name=f"{NAME} currency",
        icon="mdi:cash-100",
        device_class=SensorDeviceClass.MONETARY,
        entity_category=EntityCategory.CONFIG,
        enum_class=Currency,
    ),
    AristonSelectEntityDescription(
        key=ConsumptionProperties.GAS_TYPE,
        name=f"{NAME} gas type",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.CONFIG,
        enum_class=GasType,
    ),
    AristonSelectEntityDescription(
        key=ConsumptionProperties.GAS_ENERGY_UNIT,
        name=f"{NAME} gas energy unit",
        icon="mdi:cube-scan",
        entity_category=EntityCategory.CONFIG,
        enum_class=GasEnergyUnit,
    ),
)

ARISTON_GAS_CONSUMPTION_HEATING_LAST_TWO_HOURS_TYPE = SensorEntityDescription(
    key="0",
    name=f"{NAME} gas consumption for heating last two hours",
    icon="mdi:cash",
    entity_category=EntityCategory.DIAGNOSTIC,
    state_class=SensorStateClass.TOTAL,
    device_class=SensorDeviceClass.ENERGY,
    native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
)

ARISTON_GAS_CONSUMPTION_WATER_LAST_TWO_HOURS_TYPE = SensorEntityDescription(
    key="4",
    name=f"{NAME} gas consumption for water last two hours",
    icon="mdi:cash",
    entity_category=EntityCategory.DIAGNOSTIC,
    state_class=SensorStateClass.TOTAL,
    device_class=SensorDeviceClass.ENERGY,
    native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
)

ARISTON_HEATING_CONSUMPTION_LAST_MONTH_SENSORS_TYPES: tuple[
    SensorEntityDescription, ...
] = (
    SensorEntityDescription(
        key="0|gas",
        name=f"{NAME} gas consumption for heating last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
    ),
    SensorEntityDescription(
        key="0|elect",
        name=f"{NAME} electricity consumption for heating last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
    ),
)

ARISTON_WATER_CONSUMPTION_LAST_MONTH_SENSORS_TYPES: tuple[
    SensorEntityDescription, ...
] = (
    SensorEntityDescription(
        key="1|gas",
        name=f"{NAME} gas consumption for water last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
    ),
    SensorEntityDescription(
        key="1|elect",
        name=f"{NAME} electricity consumption for water last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
    ),
)
