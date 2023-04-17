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
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.entity import EntityCategory, EntityDescription

from ariston.galevo_device import AristonGalevoDevice
from ariston.velis_device import AristonVelisDevice
from ariston.evo_device import AristonEvoDevice
from ariston.lux_device import AristonLuxDevice
from ariston.device import AristonDevice
from ariston.evo_lydos_device import AristonEvoLydosDevice
from ariston.nuos_split_device import AristonNuosSplitDevice
from ariston.const import (
    DeviceProperties,
    VelisDeviceProperties,
    SlpDeviceSettings,
    EvoLydosDeviceProperties,
    NuosSplitProperties,
    EvoDeviceProperties,
    ThermostatProperties,
    ConsumptionProperties,
    ConsumptionType,
    DeviceFeatures,
    CustomDeviceFeatures,
    MedDeviceSettings,
    SystemType,
    WheType,
)

DOMAIN: final = "ariston"
NAME: final = "Ariston"
COORDINATOR: final = "coordinator"
ENERGY_COORDINATOR: final = "energy_coordinator"
ENERGY_SCAN_INTERVAL: final = "energy_scan_interval"

DEFAULT_SCAN_INTERVAL_SECONDS: final = 60
DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES: final = 60

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

    device_features: list[DeviceFeatures] = None
    coordinator: str = COORDINATOR
    extra_states: list[
        dict[EXTRA_STATE_ATTRIBUTE:str], dict[EXTRA_STATE_DEVICE_METHOD:Callable]
    ] = None
    zone: bool = False
    system_types: list[SystemType] = None
    whe_types: list[WheType] = None


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
    min: Callable = None
    max: Callable = None
    getstep: Callable = None


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
        key=DeviceProperties.CH_FLOW_TEMP,
        name=f"{NAME} CH flow temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=AristonGalevoDevice.get_ch_flow_temp_value,
        get_native_unit_of_measurement=AristonGalevoDevice.get_ch_flow_temp_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.OUTSIDE_TEMP,
        name=f"{NAME} Outside temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        device_features=[CustomDeviceFeatures.HAS_OUTSIDE_TEMP],
        get_native_value=AristonGalevoDevice.get_outside_temp_value,
        get_native_unit_of_measurement=AristonGalevoDevice.get_outside_temp_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=EvoLydosDeviceProperties.AV_SHW,
        name=f"{NAME} average showers",
        icon="mdi:shower-head",
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=AristonEvoLydosDevice.get_av_shw_value,
        get_native_unit_of_measurement=AristonVelisDevice.get_empty_unit,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Lux, WheType.Evo, WheType.Evo2, WheType.LydosHybrid],
    ),
    AristonSensorEntityDescription(
        key="Gas consumption for heating last month",
        name=f"{NAME} gas consumption for heating last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonGalevoDevice.get_gas_consumption_for_heating_last_month,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Electricity consumption for heating last month",
        name=f"{NAME} electricity consumption for heating last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonGalevoDevice.get_electricity_consumption_for_heating_last_month,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Gas consumption for water last month",
        name=f"{NAME} gas consumption for water last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING, CustomDeviceFeatures.HAS_DHW],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonGalevoDevice.get_gas_consumption_for_water_last_month,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Electricity consumption for water last month",
        name=f"{NAME} electricity consumption for water last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING, CustomDeviceFeatures.HAS_DHW],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonGalevoDevice.get_electricity_consumption_for_water_last_month,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Central heating total energy consumption",
        name=f"{NAME} central heating total energy consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_TOTAL_ENERGY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonDevice.get_central_heating_total_energy_consumption,
        get_last_reset=AristonDevice.get_consumption_sequence_last_changed_utc,
    ),
    AristonSensorEntityDescription(
        key="Domestic hot water total energy consumption",
        name=f"{NAME} domestic hot water total energy consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonDevice.get_domestic_hot_water_total_energy_consumption,
        get_last_reset=AristonDevice.get_consumption_sequence_last_changed_utc,
    ),
    AristonSensorEntityDescription(
        key="Central heating gas consumption",
        name=f"{NAME} central heating gas consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonDevice.get_central_heating_gas_consumption,
        get_last_reset=AristonDevice.get_consumption_sequence_last_changed_utc,
    ),
    AristonSensorEntityDescription(
        key="Domestic hot water heating pump electricity consumption",
        name=f"{NAME} domestic hot water heating pump electricity consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_HEATING_PUMP_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonDevice.get_domestic_hot_water_heating_pump_electricity_consumption,
        get_last_reset=AristonDevice.get_consumption_sequence_last_changed_utc,
    ),
    AristonSensorEntityDescription(
        key="Domestic hot water resistor electricity consumption",
        name=f"{NAME} domestic hot water resistor electricity consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_RESISTOR_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonDevice.get_domestic_hot_water_resistor_electricity_consumption,
        get_last_reset=AristonDevice.get_consumption_sequence_last_changed_utc,
    ),
    AristonSensorEntityDescription(
        key="Domestic hot water gas consumption",
        name=f"{NAME} domestic hot water gas consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonDevice.get_domestic_hot_water_gas_consumption,
        get_last_reset=AristonDevice.get_consumption_sequence_last_changed_utc,
    ),
    AristonSensorEntityDescription(
        key="Central heating electricity consumption",
        name=f"{NAME} central heating electricity consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonDevice.get_central_heating_electricity_consumption,
        get_last_reset=AristonDevice.get_consumption_sequence_last_changed_utc,
    ),
    AristonSensorEntityDescription(
        key="Domestic hot water electricity consumption",
        name=f"{NAME} domestic hot water electricity consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=AristonDevice.get_domestic_hot_water_electricity_consumption,
        get_last_reset=AristonDevice.get_consumption_sequence_last_changed_utc,
    ),
    AristonSensorEntityDescription(
        key=EvoDeviceProperties.RM_TM,
        name=f"{NAME} remaining time",
        icon="mdi:timer",
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=AristonEvoDevice.get_rm_tm_value,
        get_native_unit_of_measurement=AristonVelisDevice.get_empty_unit,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Lux, WheType.Evo, WheType.Evo2],
    ),
    AristonSensorEntityDescription(
        key=SlpDeviceSettings.SLP_HEATING_RATE,
        name=f"{NAME} heating rate",
        icon="mdi:chart-line",
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=AristonNuosSplitDevice.get_water_heater_heating_rate,
        get_native_unit_of_measurement=AristonVelisDevice.get_empty_unit,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
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
        key=DeviceProperties.IS_HEATING_PUMP_ON,
        name=f"{NAME} is heating pump on",
        icon="mdi:heat-pump-outline",
        get_is_on=AristonGalevoDevice.get_is_heating_pump_on_value,
        device_features=[DeviceFeatures.HYBRID_SYS],
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
    AristonBinarySensorEntityDescription(
        key=EvoLydosDeviceProperties.HEAT_REQ,
        name=f"{NAME} is heating",
        icon="mdi:fire",
        get_is_on=AristonEvoLydosDevice.get_is_heating,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Lux, WheType.Evo, WheType.Evo2, WheType.LydosHybrid],
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
        key=EvoDeviceProperties.ECO,
        name=f"{NAME} eco mode",
        icon="mdi:leaf",
        setter=AristonEvoDevice.async_set_eco_mode,
        getter=AristonEvoDevice.get_water_heater_eco_value,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Lux, WheType.Evo, WheType.Evo2],
    ),
    AristonSwitchEntityDescription(
        key=VelisDeviceProperties.ON,
        name=f"{NAME} power",
        icon="mdi:power",
        setter=AristonVelisDevice.async_set_power,
        getter=AristonVelisDevice.get_water_heater_power_value,
        system_types=[SystemType.VELIS],
    ),
    AristonSwitchEntityDescription(
        key=MedDeviceSettings.MED_ANTILEGIONELLA_ON_OFF,
        name=f"{NAME} anti legionella",
        icon="mdi:bacteria-outline",
        entity_category=EntityCategory.CONFIG,
        setter=AristonVelisDevice.async_set_antilegionella,
        getter=AristonVelisDevice.get_water_anti_leg_value,
        system_types=[SystemType.VELIS],
    ),
    AristonSwitchEntityDescription(
        key=SlpDeviceSettings.SLP_PRE_HEATING_ON_OFF,
        name=f"{NAME} preheating",
        icon="mdi:heat-wave",
        entity_category=EntityCategory.CONFIG,
        setter=AristonNuosSplitDevice.async_set_preheating,
        getter=AristonNuosSplitDevice.get_water_heater_preheating_on_off,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonSwitchEntityDescription(
        key=NuosSplitProperties.BOOST_ON,
        name=f"{NAME} boost",
        icon="mdi:car-turbocharger",
        entity_category=EntityCategory.CONFIG,
        setter=AristonNuosSplitDevice.async_set_water_heater_boost,
        getter=AristonNuosSplitDevice.get_water_heater_boost,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
)

ARISTON_NUMBER_TYPES: tuple[AristonNumberEntityDescription, ...] = (
    AristonNumberEntityDescription(
        key=ConsumptionProperties.ELEC_COST,
        name=f"{NAME} elec cost",
        icon="mdi:currency-sign",
        entity_category=EntityCategory.CONFIG,
        native_min_value=0,
        native_max_value=sys.maxsize,
        native_step=0.01,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        getter=AristonGalevoDevice.get_elect_cost,
        setter=AristonGalevoDevice.async_set_elect_cost,
        system_types=[SystemType.GALEVO],
    ),
    AristonNumberEntityDescription(
        key=ConsumptionProperties.GAS_COST,
        name=f"{NAME} gas cost",
        icon="mdi:currency-sign",
        entity_category=EntityCategory.CONFIG,
        native_min_value=0,
        native_max_value=sys.maxsize,
        native_step=0.01,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        getter=AristonGalevoDevice.get_gas_cost,
        setter=AristonGalevoDevice.async_set_gas_cost,
        system_types=[SystemType.GALEVO],
    ),
    AristonNumberEntityDescription(
        key=MedDeviceSettings.MED_MAX_SETPOINT_TEMPERATURE,
        name=f"{NAME} max setpoint temperature",
        icon="mdi:thermometer-high",
        entity_category=EntityCategory.CONFIG,
        min=AristonVelisDevice.get_water_heater_maximum_setpoint_temperature_minimum,
        max=AristonVelisDevice.get_water_heater_maximum_setpoint_temperature_maximum,
        native_step=1,
        getter=AristonVelisDevice.get_water_heater_maximum_setpoint_temperature,
        setter=AristonEvoDevice.async_set_max_setpoint_temp,
        system_types=[SystemType.VELIS],
    ),
    AristonNumberEntityDescription(
        key=SlpDeviceSettings.SLP_MIN_SETPOINT_TEMPERATURE,
        name=f"{NAME} min setpoint temperature",
        icon="mdi:thermometer-low",
        entity_category=EntityCategory.CONFIG,
        min=AristonNuosSplitDevice.get_water_heater_minimum_setpoint_temperature_minimum,
        max=AristonNuosSplitDevice.get_water_heater_minimum_setpoint_temperature_maximum,
        native_step=1,
        getter=AristonNuosSplitDevice.get_water_heater_minimum_setpoint_temperature,
        setter=AristonNuosSplitDevice.async_set_min_setpoint_temp,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonNumberEntityDescription(
        key=NuosSplitProperties.REDUCED_TEMP,
        name=f"{NAME} reduced temperature",
        icon="mdi:thermometer-chevron-down",
        entity_category=EntityCategory.CONFIG,
        min=AristonNuosSplitDevice.get_water_heater_minimum_temperature,
        max=AristonNuosSplitDevice.get_water_heater_maximum_temperature,
        native_step=1,
        getter=AristonNuosSplitDevice.get_water_heater_reduced_temperature,
        setter=AristonNuosSplitDevice.async_set_water_heater_reduced_temperature,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonNumberEntityDescription(
        key=ThermostatProperties.HEATING_FLOW_TEMP,
        name=f"{NAME} heating flow temperature",
        icon="mdi:thermometer",
        entity_category=EntityCategory.CONFIG,
        min=AristonGalevoDevice.get_heating_flow_temp_min,
        max=AristonGalevoDevice.get_heating_flow_temp_max,
        getstep=AristonGalevoDevice.get_heating_flow_temp_step,
        getter=AristonGalevoDevice.get_heating_flow_temp_value,
        setter=AristonGalevoDevice.async_set_heating_flow_temp,
        zone=True,
        system_types=[SystemType.GALEVO],
    ),
    AristonNumberEntityDescription(
        key=ThermostatProperties.HEATING_FLOW_OFFSET,
        name=f"{NAME} heating flow offset",
        icon="mdi:progress-wrench",
        entity_category=EntityCategory.CONFIG,
        min=AristonGalevoDevice.get_heating_flow_offset_min,
        max=AristonGalevoDevice.get_heating_flow_offset_max,
        getstep=AristonGalevoDevice.get_heating_flow_offset_step,
        getter=AristonGalevoDevice.get_heating_flow_offset_value,
        setter=AristonGalevoDevice.async_set_heating_flow_offset,
        zone=True,
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
        getter=AristonGalevoDevice.get_currency,
        get_options=AristonGalevoDevice.get_currencies,
        setter=AristonGalevoDevice.async_set_currency,
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=ConsumptionProperties.GAS_TYPE,
        name=f"{NAME} gas type",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        getter=AristonGalevoDevice.get_gas_type,
        get_options=AristonGalevoDevice.get_gas_types,
        setter=AristonGalevoDevice.async_set_gas_type,
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=ConsumptionProperties.GAS_ENERGY_UNIT,
        name=f"{NAME} gas energy unit",
        icon="mdi:cube-scan",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        getter=AristonGalevoDevice.get_gas_energy_unit,
        get_options=AristonGalevoDevice.get_gas_energy_units,
        setter=AristonGalevoDevice.async_set_gas_energy_unit,
        system_types=[SystemType.GALEVO],
    ),
)
