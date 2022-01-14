"""Constants for the Ariston integration."""
from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntFlag
from typing import final

from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.components.climate import ClimateEntityDescription
from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.components.water_heater import WaterHeaterEntityEntityDescription
from homeassistant.const import ENERGY_KILO_WATT_HOUR
from homeassistant.helpers.entity import EntityCategory, EntityDescription

from .galevo_device import AristonGalevoDevice
from .velis_device import AristonVelisDevice
from .ariston import (
    ConsumptionProperties,
    Currency,
    DeviceFeatures,
    DeviceProperties,
    GasEnergyUnit,
    GasType,
    SystemType,
    VelisDeviceProperties,
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

ATTR_TARGET_TEMP_STEP: final = "target_temp_step"
ATTR_HEAT_REQUEST: final = "heat_request"
ATTR_ECONOMY_TEMP: final = "economy_temp"
ATTR_HOLIDAY: final = "holiday"
ATTR_ZONE: final = "zone_number"

EXTRA_STATE_ATTRIBUTE: final = "Attribute"
EXTRA_STATE_DEVICE_METHOD: final = "DeviceMethod"


@dataclass
class AristonBaseEntityDescription(EntityDescription, ABC):
    """An abstract class that describes Ariston entites"""

    device_features: list[DeviceFeatures] or None = None
    coordinator: str = COORDINATOR
    extra_energy_feature: bool = False
    extra_states: list[
        dict[EXTRA_STATE_ATTRIBUTE:str],
        dict[EXTRA_STATE_DEVICE_METHOD:Callable],
    ] or None = None
    zone: int = 0
    system_types: list[SystemType] or None = None


@dataclass
class AristonClimateEntityDescription(
    ClimateEntityDescription, AristonBaseEntityDescription
):
    """A class that describes climate entities."""


@dataclass
class AristonWaterHeaterEntityDescription(
    WaterHeaterEntityEntityDescription, AristonBaseEntityDescription
):
    """A class that describes climate entities."""


@dataclass
class AristonBinarySensorEntityDescription(
    BinarySensorEntityDescription, AristonBaseEntityDescription
):
    """A class that describes binary sensor entities."""


@dataclass
class AristonSwitchEntityDescription(
    SwitchEntityDescription, AristonBaseEntityDescription
):
    """A class that describes switch entities."""

    setter: Callable = None
    getter: Callable = None


@dataclass
class AristonNumberEntityDescription(
    NumberEntityDescription, AristonBaseEntityDescription
):
    """A class that describes switch entities."""


@dataclass
class AristonSensorEntityDescription(
    SensorEntityDescription, AristonBaseEntityDescription
):
    """A class that describes sensor entities."""


@dataclass
class AristonSelectEntityDescription(
    SelectEntityDescription, AristonBaseEntityDescription
):
    """A class that describes select entities."""

    enum_class: IntFlag or None = 0


ARISTON_CLIMATE_TYPE = AristonClimateEntityDescription(
    key="AristonClimate",
    extra_states=[
        {
            EXTRA_STATE_ATTRIBUTE: ATTR_HEAT_REQUEST,
            EXTRA_STATE_DEVICE_METHOD: AristonGalevoDevice.get_zone_heat_request_value,
        },
        {
            EXTRA_STATE_ATTRIBUTE: ATTR_ECONOMY_TEMP,
            EXTRA_STATE_DEVICE_METHOD: AristonGalevoDevice.get_zone_economy_temp_value,
        },
        {
            EXTRA_STATE_ATTRIBUTE: ATTR_ZONE,
            EXTRA_STATE_DEVICE_METHOD: AristonGalevoDevice.get_zone_number,
        },
    ],
    system_types=[SystemType.GALEVO],
)

ARISTON_WATER_HEATER_TYPES: tuple[AristonWaterHeaterEntityDescription, ...] = (
    AristonWaterHeaterEntityDescription(
        key="AristonWaterHeater",
        extra_states=[
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_TARGET_TEMP_STEP,
                EXTRA_STATE_DEVICE_METHOD: AristonGalevoDevice.get_water_heater_temperature_step,
            }
        ],
        device_features=[DeviceFeatures.HAS_BOILER],
        system_types=[SystemType.GALEVO],
    ),
    AristonWaterHeaterEntityDescription(
        key="AristonWaterHeater",
        extra_states=[
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_TARGET_TEMP_STEP,
                EXTRA_STATE_DEVICE_METHOD: AristonVelisDevice.get_water_heater_temperature_step,
            }
        ],
        system_types=[SystemType.VELIS],
    ),
)

ARISTON_SENSOR_TYPES: tuple[AristonSensorEntityDescription, ...] = (
    AristonSensorEntityDescription(
        key=DeviceProperties.HEATING_CIRCUIT_PRESSURE,
        name=f"{NAME} heating circuit pressure",
        device_class=SensorDeviceClass.PRESSURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.CH_FLOW_SETPOINT_TEMP,
        name=f"{NAME} CH flow setpoint temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        system_types=[SystemType.GALEVO],
    ),
)


ARISTON_BINARY_SENSOR_TYPES: tuple[AristonBinarySensorEntityDescription, ...] = (
    AristonBinarySensorEntityDescription(
        key=DeviceProperties.IS_FLAME_ON,
        name=f"{NAME} is flame on",
        icon="mdi:fire",
        system_types=[SystemType.GALEVO],
    ),
    AristonBinarySensorEntityDescription(
        key=DeviceProperties.HOLIDAY,
        name=f"{NAME} holiday mode",
        icon="mdi:island",
        extra_states=[
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_HOLIDAY,
                EXTRA_STATE_DEVICE_METHOD: AristonGalevoDevice.get_holiday_expires_on,
            }
        ],
        system_types=[SystemType.GALEVO],
    ),
)


ARISTON_SWITCH_TYPES: tuple[AristonSwitchEntityDescription, ...] = (
    AristonSwitchEntityDescription(
        key=DeviceProperties.AUTOMATIC_THERMOREGULATION,
        name=f"{NAME} automatic thermoregulation",
        icon="mdi:radiator",
        device_features=[DeviceFeatures.AUTO_THERMO_REG],
        setter=AristonGalevoDevice.async_set_automatic_thermoregulation,
        getter=AristonGalevoDevice.get_automatic_thermoregulation,
        system_types=[SystemType.GALEVO],
    ),
    AristonSwitchEntityDescription(
        key=VelisDeviceProperties.ECO,
        name=f"{NAME} eco mode",
        icon="mdi:leaf",
        setter=AristonVelisDevice.async_set_eco_mode,
        getter=AristonVelisDevice.get_water_heater_eco_value,
        system_types=[SystemType.VELIS],
    ),
)

ARISTON_NUMBER_TYPES: tuple[AristonNumberEntityDescription, ...] = (
    AristonNumberEntityDescription(
        key=ConsumptionProperties.ELEC_COST,
        name=f"{NAME} elec cost",
        icon="mdi:currency-sign",
        entity_category=EntityCategory.CONFIG,
        # Currently released HA NumberEntityDescription do not support these fields. Dev branch does.
        # min_value=0,
        # max_value=sys.maxsize,
        # step=0.01,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        system_types=[SystemType.GALEVO],
    ),
    AristonNumberEntityDescription(
        key=ConsumptionProperties.GAS_COST,
        name=f"{NAME} gas cost",
        icon="mdi:currency-sign",
        entity_category=EntityCategory.CONFIG,
        # Currently released HA NumberEntityDescription do not support these fields. Dev branch does.
        # min_value=0,
        # max_value=sys.maxsize,
        # step=0.01,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        system_types=[SystemType.GALEVO],
    ),
)


ARISTON_SELECT_TYPES: tuple[AristonSelectEntityDescription, ...] = (
    AristonSelectEntityDescription(
        key=ConsumptionProperties.CURRENCY,
        name=f"{NAME} currency",
        icon="mdi:cash-100",
        device_class=SensorDeviceClass.MONETARY,
        entity_category=EntityCategory.CONFIG,
        enum_class=Currency,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=ConsumptionProperties.GAS_TYPE,
        name=f"{NAME} gas type",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.CONFIG,
        enum_class=GasType,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=ConsumptionProperties.GAS_ENERGY_UNIT,
        name=f"{NAME} gas energy unit",
        icon="mdi:cube-scan",
        entity_category=EntityCategory.CONFIG,
        enum_class=GasEnergyUnit,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        system_types=[SystemType.GALEVO],
    ),
)

ARISTON_GAS_CONSUMPTION_LAST_TWO_HOURS_TYPE: tuple[
    AristonSensorEntityDescription, ...
] = (
    AristonSensorEntityDescription(
        key="0",
        name=f"{NAME} gas consumption for heating last two hours",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="4",
        name=f"{NAME} gas consumption for water last two hours",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING, DeviceFeatures.HAS_BOILER],
        coordinator=ENERGY_COORDINATOR,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="0",
        name=f"{NAME} electric consumption for water last two hours",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        system_types=[SystemType.VELIS],
    ),
)

ARISTON_CONSUMPTION_LAST_MONTH_SENSORS_TYPES: tuple[
    AristonSensorEntityDescription, ...
] = (
    AristonSensorEntityDescription(
        key="0|gas",
        name=f"{NAME} gas consumption for heating last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="0|elect",
        name=f"{NAME} electricity consumption for heating last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="1|gas",
        name=f"{NAME} gas consumption for water last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING, DeviceFeatures.HAS_BOILER],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="1|elect",
        name=f"{NAME} electricity consumption for water last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING, DeviceFeatures.HAS_BOILER],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        system_types=[SystemType.GALEVO],
    ),
)
