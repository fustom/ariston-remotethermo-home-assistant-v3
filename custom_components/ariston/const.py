"""Constants for the Ariston integration."""
import sys

from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass
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
from .device import AristonDevice
from .ariston import (
    ConsumptionProperties,
    CustomDeviceFeatures,
    DeviceFeatures,
    DeviceProperties,
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

    get_is_on: Callable = None


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

    setter: Callable = None
    getter: Callable = None


@dataclass
class AristonSensorEntityDescription(
    SensorEntityDescription, AristonBaseEntityDescription
):
    """A class that describes sensor entities."""

    get_native_value: Callable = None
    get_native_unit_of_measurement: Callable = None
    get_last_reset: Callable = None


@dataclass
class AristonSelectEntityDescription(
    SelectEntityDescription, AristonBaseEntityDescription
):
    """A class that describes select entities."""

    getter: Callable = None
    get_options: Callable = None
    setter: Callable = None


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
                EXTRA_STATE_DEVICE_METHOD: AristonDevice.get_water_heater_temperature_step,
            }
        ],
        device_features=[CustomDeviceFeatures.HAS_DHW],
        system_types=[SystemType.GALEVO, SystemType.VELIS],
    ),
)

ARISTON_SENSOR_TYPES: tuple[AristonSensorEntityDescription, ...] = (
    AristonSensorEntityDescription(
        key=DeviceProperties.HEATING_CIRCUIT_PRESSURE,
        name=f"{NAME} heating circuit pressure",
        device_class=SensorDeviceClass.PRESSURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=AristonGalevoDevice.get_heating_circuit_pressure_value,
        get_native_unit_of_measurement=AristonGalevoDevice.get_heating_circuit_pressure_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.CH_FLOW_SETPOINT_TEMP,
        name=f"{NAME} CH flow setpoint temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=AristonGalevoDevice.get_ch_flow_setpoint_temp_value,
        get_native_unit_of_measurement=AristonGalevoDevice.get_ch_flow_setpoint_temp_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=VelisDeviceProperties.AV_SHW,
        name=f"{NAME} average showers",
        icon="mdi:shower-head",
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=AristonVelisDevice.get_av_shw_value,
        get_native_unit_of_measurement=AristonVelisDevice.get_av_shw_unit,
        system_types=[SystemType.VELIS],
    ),
    AristonSensorEntityDescription(
        key="Gas consumption for heating last month",
        name=f"{NAME} gas consumption for heating last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        get_native_value=AristonDevice.get_gas_consumption_for_heating_last_month,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Electricity consumption for heating last month",
        name=f"{NAME} electricity consumption for heating last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        get_native_value=AristonDevice.get_electricity_consumption_for_heating_last_month,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Gas consumption for water last month",
        name=f"{NAME} gas consumption for water last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING, CustomDeviceFeatures.HAS_DHW],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        get_native_value=AristonDevice.get_gas_consumption_for_water_last_month,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Electricity consumption for water last month",
        name=f"{NAME} electricity consumption for water last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING, CustomDeviceFeatures.HAS_DHW],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        get_native_value=AristonDevice.get_electricity_consumption_for_water_last_month,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Gas consumption for heating last two hours",
        name=f"{NAME} gas consumption for heating last two hours",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            CustomDeviceFeatures.HAS_HEATING_GAS,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonDevice.get_gas_consumption_for_heating_last_two_hours,
        get_last_reset=AristonDevice.get_consumption_sequence_last_changed_utc,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Electricity consumption for heating last two hours",
        name=f"{NAME} electricity consumption for heating last two hours",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            CustomDeviceFeatures.HAS_HEATING_ELECTRICITY,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonDevice.get_electricity_consumption_for_heating_last_two_hours,
        get_last_reset=AristonDevice.get_consumption_sequence_last_changed_utc,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Total consumption for heating last two hours",
        name=f"{NAME} total consumption for heating last two hours",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            CustomDeviceFeatures.HAS_HEATING_TOTAL_ENERGY,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonDevice.get_total_consumption_for_heating_last_two_hours,
        get_last_reset=AristonDevice.get_consumption_sequence_last_changed_utc,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Gas consumption for water last two hours",
        name=f"{NAME} gas consumption for water last two hours",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            CustomDeviceFeatures.HAS_DHW,
            CustomDeviceFeatures.HAS_WATER_GAS,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonDevice.get_gas_consumption_for_water_last_two_hours,
        get_last_reset=AristonDevice.get_consumption_sequence_last_changed_utc,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Electricity consumption for water last two hours",
        name=f"{NAME} electricity consumption for water last two hours",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            CustomDeviceFeatures.HAS_DHW,
            CustomDeviceFeatures.HAS_WATER_ELECTRICITY,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonDevice.get_electricity_consumption_for_water_last_two_hours,
        get_last_reset=AristonDevice.get_consumption_sequence_last_changed_utc,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Total consumption for water last two hours",
        name=f"{NAME} total consumption for water last two hours",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            CustomDeviceFeatures.HAS_DHW,
            CustomDeviceFeatures.HAS_WATER_TOTAL_ENERGY,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonDevice.get_total_consumption_for_water_last_two_hours,
        get_last_reset=AristonDevice.get_consumption_sequence_last_changed_utc,
        system_types=[SystemType.GALEVO, SystemType.VELIS],
    ),
)

ARISTON_BINARY_SENSOR_TYPES: tuple[AristonBinarySensorEntityDescription, ...] = (
    AristonBinarySensorEntityDescription(
        key=DeviceProperties.IS_FLAME_ON,
        name=f"{NAME} is flame on",
        icon="mdi:fire",
        get_is_on=AristonGalevoDevice.get_is_flame_on_value,
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
        get_is_on=AristonGalevoDevice.get_holiday_mode_value,
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
        min_value=0,
        max_value=sys.maxsize,
        step=0.01,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        getter=AristonDevice.get_elect_cost,
        setter=AristonDevice.async_set_elect_cost,
        system_types=[SystemType.GALEVO],
    ),
    AristonNumberEntityDescription(
        key=ConsumptionProperties.GAS_COST,
        name=f"{NAME} gas cost",
        icon="mdi:currency-sign",
        entity_category=EntityCategory.CONFIG,
        min_value=0,
        max_value=sys.maxsize,
        step=0.01,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        getter=AristonDevice.get_gas_cost,
        setter=AristonDevice.async_set_gas_cost,
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
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        getter=AristonDevice.get_currency,
        get_options=AristonDevice.get_currencies,
        setter=AristonDevice.async_set_currency,
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=ConsumptionProperties.GAS_TYPE,
        name=f"{NAME} gas type",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        getter=AristonDevice.get_gas_type,
        get_options=AristonDevice.get_gas_types,
        setter=AristonDevice.async_set_gas_type,
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=ConsumptionProperties.GAS_ENERGY_UNIT,
        name=f"{NAME} gas energy unit",
        icon="mdi:cube-scan",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        extra_energy_feature=True,
        getter=AristonDevice.get_gas_energy_unit,
        get_options=AristonDevice.get_gas_energy_units,
        setter=AristonDevice.async_set_gas_energy_unit,
        system_types=[SystemType.GALEVO],
    ),
)
