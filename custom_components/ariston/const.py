"""Constants for the Ariston integration."""

import sys

from collections.abc import Callable, Coroutine
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
from homeassistant.const import UnitOfEnergy, UnitOfTime, UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory, EntityDescription

from ariston.device import AristonDevice
from ariston.const import (
    DeviceProperties,
    VelisDeviceProperties,
    SlpDeviceSettings,
    EvoLydosDeviceProperties,
    NuosSplitProperties,
    EvoDeviceProperties,
    EvoOneDeviceProperties,
    ThermostatProperties,
    ConsumptionProperties,
    ConsumptionType,
    DeviceFeatures,
    CustomDeviceFeatures,
    MedDeviceSettings,
    SystemType,
    WheType,
    DeviceAttribute,
    SeDeviceSettings,
    MenuItemNames,
    ARISTON_BUS_ERRORS,
)

try:
    from homeassistant.components.water_heater import WaterHeaterEntityDescription
except ImportError:
    # compatibility code for HA < 2025.1
    from homeassistant.components.water_heater import WaterHeaterEntityEntityDescription

    WaterHeaterEntityDescription = WaterHeaterEntityEntityDescription

DOMAIN: final = "ariston"
NAME: final = "Ariston"
COORDINATOR: final = "coordinator"
ENERGY_COORDINATOR: final = "energy_coordinator"
ENERGY_SCAN_INTERVAL: final = "energy_scan_interval"
BUS_ERRORS_COORDINATOR: final = "bus_errors_coordinator"
BUS_ERRORS_SCAN_INTERVAL: final = "bus_errors_scan_interval"
API_URL_SETTING: final = "api_url_setting"

DEFAULT_SCAN_INTERVAL_SECONDS: final = 180
DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES: final = 60
DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS: final = 600

ATTR_TARGET_TEMP_STEP: final = "target_temp_step"
ATTR_HEAT_REQUEST: final = "heat_request"
ATTR_ECONOMY_TEMP: final = "economy_temp"
ATTR_HOLIDAY: final = "holiday"
ATTR_ZONE: final = "zone_number"
ATTR_ERRORS: final = "errors"

EXTRA_STATE_ATTRIBUTE: final = "Attribute"
EXTRA_STATE_DEVICE_METHOD: final = "DeviceMethod"


@dataclass(kw_only=True)
class AristonBaseEntityDescription(EntityDescription):
    """An abstract class that describes Ariston entites"""

    device_features: list[DeviceFeatures] = None
    coordinator: str = COORDINATOR
    extra_states: list[
        dict[EXTRA_STATE_ATTRIBUTE:str],
        dict[EXTRA_STATE_DEVICE_METHOD : Callable[[AristonDevice], Coroutine]],
    ] = None
    system_types: list[SystemType] = None
    whe_types: list[WheType] = None
    zone: bool = False


@dataclass(kw_only=True)
class AristonClimateEntityDescription(
    ClimateEntityDescription, AristonBaseEntityDescription
):
    """A class that describes climate entities."""


@dataclass(kw_only=True)
class AristonWaterHeaterEntityDescription(
    WaterHeaterEntityDescription, AristonBaseEntityDescription
):
    """A class that describes climate entities."""


@dataclass(kw_only=True)
class AristonBinarySensorEntityDescription(
    BinarySensorEntityDescription, AristonBaseEntityDescription
):
    """A class that describes binary sensor entities."""

    get_is_on: Callable[[AristonDevice], Coroutine] = None


@dataclass(kw_only=True)
class AristonSwitchEntityDescription(
    SwitchEntityDescription, AristonBaseEntityDescription
):
    """A class that describes switch entities."""

    set_value: Callable[[AristonDevice, bool], Coroutine] = None
    get_is_on: Callable[[AristonDevice], Coroutine] = None


@dataclass(kw_only=True)
class AristonNumberEntityDescription(
    NumberEntityDescription, AristonBaseEntityDescription
):
    """A class that describes switch entities."""

    set_native_value: Callable[[AristonDevice, float], Coroutine] = None
    get_native_value: Callable[[AristonDevice], Coroutine] = None
    get_native_min_value: Callable[[AristonDevice], Coroutine] = None
    get_native_max_value: Callable[[AristonDevice], Coroutine] = None
    get_native_step: Callable[[AristonDevice], Coroutine] = None


@dataclass(kw_only=True)
class AristonSensorEntityDescription(
    SensorEntityDescription, AristonBaseEntityDescription
):
    """A class that describes sensor entities."""

    get_native_unit_of_measurement: Callable[[AristonDevice], Coroutine] = None
    get_last_reset: Callable[[AristonDevice], Coroutine] = None
    get_native_value: Callable[[AristonDevice], Coroutine] = None


@dataclass(kw_only=True)
class AristonSelectEntityDescription(
    SelectEntityDescription, AristonBaseEntityDescription
):
    """A class that describes select entities."""

    get_current_option: Callable[[AristonDevice], Coroutine] = None
    get_options: Callable[[AristonDevice], Coroutine] = None
    select_option: Callable[[AristonDevice, str], Coroutine] = None


ARISTON_CLIMATE_TYPES: list[AristonClimateEntityDescription] = (
    AristonClimateEntityDescription(
        key="AristonClimate",
        extra_states=[
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_HEAT_REQUEST,
                EXTRA_STATE_DEVICE_METHOD: lambda entity: entity.device.get_zone_heat_request_value(
                    entity.zone
                ),
            },
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_ECONOMY_TEMP,
                EXTRA_STATE_DEVICE_METHOD: lambda entity: entity.device.get_zone_economy_temp_value(
                    entity.zone
                ),
            },
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_ZONE,
                EXTRA_STATE_DEVICE_METHOD: lambda entity: entity.zone,
            },
        ],
        system_types=[SystemType.GALEVO],
    ),
    AristonClimateEntityDescription(
        key="AristonClimate",
        system_types=[SystemType.BSB],
    ),
)

ARISTON_WATER_HEATER_TYPES: list[AristonWaterHeaterEntityDescription] = (
    AristonWaterHeaterEntityDescription(
        key="AristonWaterHeater",
        extra_states=[
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_TARGET_TEMP_STEP,
                EXTRA_STATE_DEVICE_METHOD: lambda entity: entity.device.water_heater_temperature_step,
            }
        ],
        device_features=[CustomDeviceFeatures.HAS_DHW],
        system_types=[SystemType.GALEVO, SystemType.BSB],
    ),
    AristonWaterHeaterEntityDescription(
        key="AristonWaterHeater",
        extra_states=[
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_TARGET_TEMP_STEP,
                EXTRA_STATE_DEVICE_METHOD: lambda entity: entity.device.water_heater_temperature_step,
            }
        ],
        device_features=[CustomDeviceFeatures.HAS_DHW],
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Andris2,
            WheType.Evo2,
            WheType.Lux,
            WheType.Lux2,
            WheType.Lydos,
            WheType.LydosHybrid,
            WheType.NuosSplit,
        ],
    ),
)

ARISTON_SENSOR_TYPES: list[AristonSensorEntityDescription] = (
    AristonSensorEntityDescription(
        key=DeviceProperties.HEATING_CIRCUIT_PRESSURE,
        name=f"{NAME} heating circuit pressure",
        device_class=SensorDeviceClass.PRESSURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.heating_circuit_pressure_value,
        get_native_unit_of_measurement=lambda entity: entity.device.heating_circuit_pressure_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.CH_FLOW_SETPOINT_TEMP,
        name=f"{NAME} CH flow setpoint temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.ch_flow_setpoint_temp_value,
        get_native_unit_of_measurement=lambda entity: entity.device.ch_flow_setpoint_temp_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.CH_FLOW_TEMP,
        name=f"{NAME} CH flow temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.ch_flow_temp_value,
        get_native_unit_of_measurement=lambda entity: entity.device.ch_flow_temp_unit,
        device_features=[DeviceProperties.CH_FLOW_TEMP],
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=MenuItemNames.SIGNAL_STRENGTH,
        name=f"{NAME} signal strength",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        get_native_value=lambda entity: entity.device.signal_strength_value,
        get_native_unit_of_measurement=lambda entity: entity.device.signal_strength_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=MenuItemNames.CH_RETURN_TEMP,
        name=f"{NAME} CH return temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.ch_return_temp_value,
        get_native_unit_of_measurement=lambda entity: entity.device.ch_return_temp_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.OUTSIDE_TEMP,
        name=f"{NAME} Outside temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        device_features=[CustomDeviceFeatures.HAS_OUTSIDE_TEMP],
        get_native_value=lambda entity: entity.device.outside_temp_value,
        get_native_unit_of_measurement=lambda entity: entity.device.outside_temp_unit,
        system_types=[SystemType.GALEVO, SystemType.BSB],
    ),
    AristonSensorEntityDescription(
        key=EvoLydosDeviceProperties.AV_SHW,
        name=f"{NAME} average showers",
        icon="mdi:shower-head",
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.av_shw_value,
        native_unit_of_measurement="",
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Lux,
            WheType.Evo,
            WheType.Evo2,
            WheType.Lydos,
            WheType.LydosHybrid,
            WheType.Andris2,
            WheType.Lux2,
        ],
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
        get_native_value=lambda entity: entity.device.gas_consumption_for_heating_last_month,
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
        get_native_value=lambda entity: entity.device.electricity_consumption_for_heating_last_month,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Electricity consumption for cooling last month",
        name=f"{NAME} electricity consumption for cooling last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING, DeviceAttribute.HPMP_SYS],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: entity.device.electricity_consumption_for_cooling_last_month,
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
        get_native_value=lambda entity: entity.device.gas_consumption_for_water_last_month,
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
        get_native_value=lambda entity: entity.device.electricity_consumption_for_water_last_month,
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
        get_native_value=lambda entity: entity.device.central_heating_total_energy_consumption,
        get_last_reset=lambda entity: entity.device.consumption_sequence_last_changed_utc,
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
        get_native_value=lambda entity: entity.device.domestic_hot_water_total_energy_consumption,
        get_last_reset=lambda entity: entity.device.consumption_sequence_last_changed_utc,
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
        get_native_value=lambda entity: entity.device.central_heating_gas_consumption,
        get_last_reset=lambda entity: entity.device.consumption_sequence_last_changed_utc,
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
        get_native_value=lambda entity: entity.device.domestic_hot_water_heating_pump_electricity_consumption,
        get_last_reset=lambda entity: entity.device.consumption_sequence_last_changed_utc,
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
        get_native_value=lambda entity: entity.device.domestic_hot_water_resistor_electricity_consumption,
        get_last_reset=lambda entity: entity.device.consumption_sequence_last_changed_utc,
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
        get_native_value=lambda entity: entity.device.domestic_hot_water_gas_consumption,
        get_last_reset=lambda entity: entity.device.consumption_sequence_last_changed_utc,
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
        get_native_value=lambda entity: entity.device.central_heating_electricity_consumption,
        get_last_reset=lambda entity: entity.device.consumption_sequence_last_changed_utc,
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
        get_native_value=lambda entity: entity.device.domestic_hot_water_electricity_consumption,
        get_last_reset=lambda entity: entity.device.consumption_sequence_last_changed_utc,
    ),
    AristonSensorEntityDescription(
        key=EvoDeviceProperties.RM_TM,
        name=f"{NAME} remaining time",
        icon="mdi:timer",
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.rm_tm_in_minutes,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Lux,
            WheType.Evo,
            WheType.Evo2,
            WheType.Lux2,
            WheType.Lydos,
        ],
    ),
    AristonSensorEntityDescription(
        key=SlpDeviceSettings.SLP_HEATING_RATE,
        name=f"{NAME} heating rate",
        icon="mdi:chart-line",
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.water_heater_heating_rate,
        native_unit_of_measurement="",
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonSensorEntityDescription(
        key=ARISTON_BUS_ERRORS,
        name=f"{NAME} errors count",
        icon="mdi:alert-outline",
        coordinator=BUS_ERRORS_COORDINATOR,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        get_native_value=lambda entity: len(entity.device.bus_errors),
        native_unit_of_measurement="",
        extra_states=[
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_ERRORS,
                EXTRA_STATE_DEVICE_METHOD: lambda entity: entity.device.bus_errors,
            },
        ],
    ),
    AristonSensorEntityDescription(
        key=EvoOneDeviceProperties.TEMP,
        name=f"{NAME} current temperature",
        icon="mdi:thermometer-auto",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.water_heater_current_temperature,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Evo,
        ],
    ),
    AristonSensorEntityDescription(
        key=VelisDeviceProperties.PROC_REQ_TEMP,
        name=f"{NAME} proc req temp",
        icon="mdi:thermometer-auto",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.proc_req_temp_value,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.NuosSplit,
            WheType.Evo2,
            WheType.LydosHybrid,
            WheType.Lydos,
            WheType.Andris2,
            WheType.Lux,
            WheType.Lux2,
        ],
    ),
)

ARISTON_BINARY_SENSOR_TYPES: list[AristonBinarySensorEntityDescription] = (
    AristonBinarySensorEntityDescription(
        key=DeviceProperties.IS_FLAME_ON,
        name=f"{NAME} is flame on",
        icon="mdi:fire",
        get_is_on=lambda entity: entity.device.is_flame_on_value,
        system_types=[SystemType.GALEVO, SystemType.BSB],
    ),
    AristonBinarySensorEntityDescription(
        key=DeviceProperties.IS_HEATING_PUMP_ON,
        name=f"{NAME} is heating pump on",
        icon="mdi:heat-pump-outline",
        get_is_on=lambda entity: entity.device.is_heating_pump_on_value,
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
                EXTRA_STATE_DEVICE_METHOD: lambda entity: entity.device.holiday_expires_on,
            }
        ],
        get_is_on=lambda entity: entity.device.holiday_mode_value,
        system_types=[SystemType.GALEVO],
    ),
    AristonBinarySensorEntityDescription(
        key=EvoLydosDeviceProperties.HEAT_REQ,
        name=f"{NAME} is heating",
        icon="mdi:fire",
        get_is_on=lambda entity: entity.device.is_heating,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Lux,
            WheType.Evo,
            WheType.Evo2,
            WheType.Lydos,
            WheType.LydosHybrid,
            WheType.Andris2,
            WheType.Lux2,
        ],
    ),
    AristonBinarySensorEntityDescription(
        key=EvoLydosDeviceProperties.ANTI_LEG,
        name=f"{NAME} anti-legionella cycle",
        icon="mdi:bacteria",
        get_is_on=lambda entity: entity.device.is_antileg,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Evo2,
            WheType.Lydos,
            WheType.LydosHybrid,
            WheType.Andris2,
        ],
    ),
)

ARISTON_SWITCH_TYPES: list[AristonSwitchEntityDescription] = (
    AristonSwitchEntityDescription(
        key=DeviceProperties.AUTOMATIC_THERMOREGULATION,
        name=f"{NAME} automatic thermoregulation",
        icon="mdi:radiator",
        device_features=[DeviceFeatures.AUTO_THERMO_REG],
        set_value=lambda entity,
        value: entity.device.async_set_automatic_thermoregulation(value),
        get_is_on=lambda entity: entity.device.automatic_thermoregulation,
        system_types=[SystemType.GALEVO],
    ),
    AristonSwitchEntityDescription(
        key=DeviceProperties.IS_QUIET,
        name=f"{NAME} is quiet",
        icon="mdi:volume-off",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceProperties.IS_QUIET],
        set_value=lambda entity, value: entity.device.async_set_is_quiet(value),
        get_is_on=lambda entity: entity.device.is_quiet_value,
        system_types=[SystemType.GALEVO],
    ),
    AristonSwitchEntityDescription(
        key=EvoDeviceProperties.ECO,
        name=f"{NAME} eco mode",
        icon="mdi:leaf",
        set_value=lambda entity, value: entity.device.async_set_eco_mode(value),
        get_is_on=lambda entity: entity.device.water_heater_eco_value,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Lux,
            WheType.Evo,
            WheType.Evo2,
            WheType.Lydos,
            WheType.Andris2,
            WheType.Lux2,
        ],
    ),
    AristonSwitchEntityDescription(
        key=EvoDeviceProperties.PWR_OPT,
        name=f"{NAME} power option",
        icon="mdi:leaf",
        set_value=lambda entity,
        value: entity.device.async_set_water_heater_power_option(value),
        get_is_on=lambda entity: entity.device.water_heater_power_option_value,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Lux2],
    ),
    AristonSwitchEntityDescription(
        key=VelisDeviceProperties.ON,
        name=f"{NAME} power",
        icon="mdi:power",
        set_value=lambda entity, value: entity.device.async_set_power(value),
        get_is_on=lambda entity: entity.device.water_heater_power_value,
        system_types=[SystemType.VELIS],
    ),
    AristonSwitchEntityDescription(
        key=MedDeviceSettings.MED_ANTILEGIONELLA_ON_OFF,
        name=f"{NAME} anti legionella",
        icon="mdi:bacteria-outline",
        entity_category=EntityCategory.CONFIG,
        set_value=lambda entity, value: entity.device.async_set_antilegionella(value),
        get_is_on=lambda entity: entity.device.water_anti_leg_value,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Andris2,
            WheType.Evo2,
            WheType.Lux,
            WheType.Lux2,
            WheType.Lydos,
            WheType.LydosHybrid,
            WheType.NuosSplit,
        ],
    ),
    AristonSwitchEntityDescription(
        key=SlpDeviceSettings.SLP_PRE_HEATING_ON_OFF,
        name=f"{NAME} preheating",
        icon="mdi:heat-wave",
        entity_category=EntityCategory.CONFIG,
        set_value=lambda entity, value: entity.device.async_set_preheating(value),
        get_is_on=lambda entity: entity.device.water_heater_preheating_on_off,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonSwitchEntityDescription(
        key=NuosSplitProperties.BOOST_ON,
        name=f"{NAME} boost",
        icon="mdi:car-turbocharger",
        entity_category=EntityCategory.CONFIG,
        set_value=lambda entity, value: entity.device.async_set_water_heater_boost(
            value
        ),
        get_is_on=lambda entity: entity.device.water_heater_boost,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonSwitchEntityDescription(
        key=SeDeviceSettings.SE_PERMANENT_BOOST_ON_OFF,
        name=f"{NAME} permanent boost",
        icon="mdi:car-turbocharger",
        entity_category=EntityCategory.CONFIG,
        set_value=lambda entity, value: entity.device.async_set_permanent_boost_value(
            value
        ),
        get_is_on=lambda entity: entity.device.permanent_boost_value,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.LydosHybrid],
    ),
    AristonSwitchEntityDescription(
        key=SeDeviceSettings.SE_ANTI_COOLING_ON_OFF,
        name=f"{NAME} anti cooling",
        icon="mdi:snowflake-thermometer",
        entity_category=EntityCategory.CONFIG,
        set_value=lambda entity, value: entity.device.async_set_anti_cooling_value(
            value
        ),
        get_is_on=lambda entity: entity.device.anti_cooling_value,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.LydosHybrid],
    ),
    AristonSwitchEntityDescription(
        key=SeDeviceSettings.SE_NIGHT_MODE_ON_OFF,
        name=f"{NAME} night mode",
        icon="mdi:weather-night",
        entity_category=EntityCategory.CONFIG,
        set_value=lambda entity, value: entity.device.async_set_night_mode_value(value),
        get_is_on=lambda entity: entity.device.night_mode_value,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.LydosHybrid],
    ),
)

ARISTON_NUMBER_TYPES: list[AristonNumberEntityDescription] = (
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
        get_native_value=lambda entity: entity.device.elect_cost,
        set_native_value=lambda entity, value: entity.device.async_set_elect_cost(
            value
        ),
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
        get_native_value=lambda entity: entity.device.gas_cost,
        set_native_value=lambda entity, value: entity.device.async_set_gas_cost(value),
        system_types=[SystemType.GALEVO],
    ),
    AristonNumberEntityDescription(
        key=MedDeviceSettings.MED_MAX_SETPOINT_TEMPERATURE,
        name=f"{NAME} max setpoint temperature",
        icon="mdi:thermometer-high",
        entity_category=EntityCategory.CONFIG,
        get_native_min_value=lambda entity: entity.device.water_heater_maximum_setpoint_temperature_minimum,
        get_native_max_value=lambda entity: entity.device.water_heater_maximum_setpoint_temperature_maximum,
        native_step=1,
        get_native_value=lambda entity: entity.device.water_heater_maximum_setpoint_temperature,
        set_native_value=lambda entity,
        value: entity.device.async_set_max_setpoint_temp(value),
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Andris2,
            WheType.Evo2,
            WheType.Lux,
            WheType.Lux2,
            WheType.Lydos,
            WheType.LydosHybrid,
            WheType.NuosSplit,
        ],
    ),
    AristonNumberEntityDescription(
        key=SlpDeviceSettings.SLP_MIN_SETPOINT_TEMPERATURE,
        name=f"{NAME} min setpoint temperature",
        icon="mdi:thermometer-low",
        entity_category=EntityCategory.CONFIG,
        get_native_min_value=lambda entity: entity.device.water_heater_minimum_setpoint_temperature_minimum,
        get_native_max_value=lambda entity: entity.device.water_heater_minimum_setpoint_temperature_maximum,
        native_step=1,
        get_native_value=lambda entity: entity.device.water_heater_minimum_setpoint_temperature,
        set_native_value=lambda entity,
        value: entity.device.async_set_min_setpoint_temp(value),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonNumberEntityDescription(
        key=NuosSplitProperties.REDUCED_TEMP,
        name=f"{NAME} reduced temperature",
        icon="mdi:thermometer-chevron-down",
        entity_category=EntityCategory.CONFIG,
        get_native_min_value=lambda entity: entity.device.water_heater_minimum_temperature,
        get_native_max_value=lambda entity: entity.device.water_heater_maximum_temperature,
        native_step=1,
        get_native_value=lambda entity: entity.device.water_heater_reduced_temperature,
        set_native_value=lambda entity,
        value: entity.device.async_set_water_heater_reduced_temperature(value),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonNumberEntityDescription(
        key=ThermostatProperties.HEATING_FLOW_TEMP,
        name=f"{NAME} heating flow temperature",
        icon="mdi:thermometer",
        entity_category=EntityCategory.CONFIG,
        zone=True,
        get_native_min_value=lambda entity: entity.device.get_heating_flow_temp_min(
            entity.zone
        ),
        get_native_max_value=lambda entity: entity.device.get_heating_flow_temp_max(
            entity.zone
        ),
        get_native_step=lambda entity: entity.device.get_heating_flow_temp_step(
            entity.zone
        ),
        get_native_value=lambda entity: entity.device.get_heating_flow_temp_value(
            entity.zone
        ),
        set_native_value=lambda entity,
        value: entity.device.async_set_heating_flow_temp(value, entity.zone),
        system_types=[SystemType.GALEVO],
    ),
    AristonNumberEntityDescription(
        key=ThermostatProperties.HEATING_FLOW_OFFSET,
        name=f"{NAME} heating flow offset",
        icon="mdi:progress-wrench",
        entity_category=EntityCategory.CONFIG,
        zone=True,
        get_native_min_value=lambda entity: entity.device.get_heating_flow_offset_min(
            entity.zone
        ),
        get_native_max_value=lambda entity: entity.device.get_heating_flow_offset_max(
            entity.zone
        ),
        get_native_step=lambda entity: entity.device.get_heating_flow_offset_step(
            entity.zone
        ),
        get_native_value=lambda entity: entity.device.get_heating_flow_offset_value(
            entity.zone
        ),
        set_native_value=lambda entity,
        value: entity.device.async_set_heating_flow_offset(value, entity.zone),
        system_types=[SystemType.GALEVO],
    ),
    AristonNumberEntityDescription(
        key=EvoOneDeviceProperties.AV_SHW,
        name=f"{NAME} requested number of showers",
        icon="mdi:shower-head",
        native_min_value=0,
        get_native_max_value=lambda entity: entity.device.max_req_shower,
        native_step=1,
        get_native_value=lambda entity: entity.device.req_shower,
        set_native_value=lambda entity,
        value: entity.device.async_set_water_heater_number_of_showers(int(value)),
        whe_types=[WheType.Evo],
    ),
    AristonNumberEntityDescription(
        key=SeDeviceSettings.SE_ANTI_COOLING_TEMPERATURE,
        name=f"{NAME} anti cooling temperature",
        icon="mdi:thermometer-alert",
        entity_category=EntityCategory.CONFIG,
        get_native_min_value=lambda entity: entity.device.anti_cooling_temperature_minimum,
        get_native_max_value=lambda entity: entity.device.anti_cooling_temperature_maximum,
        native_step=1,
        get_native_value=lambda entity: entity.device.anti_cooling_temperature_value,
        set_native_value=lambda entity,
        value: entity.device.async_set_cooling_temperature_value(int(value)),
        whe_types=[WheType.LydosHybrid],
    ),
)

ARISTON_SELECT_TYPES: list[AristonSelectEntityDescription] = (
    AristonSelectEntityDescription(
        key=ConsumptionProperties.CURRENCY,
        name=f"{NAME} currency",
        icon="mdi:cash-100",
        device_class=SensorDeviceClass.MONETARY,
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        get_current_option=lambda entity: entity.device.currency,
        get_options=lambda entity: entity.device.get_currencies(),
        select_option=lambda entity, option: entity.device.async_set_currency(option),
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=ConsumptionProperties.GAS_TYPE,
        name=f"{NAME} gas type",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        get_current_option=lambda entity: entity.device.gas_type,
        get_options=lambda entity: entity.device.get_gas_types(),
        select_option=lambda entity, option: entity.device.async_set_gas_type(option),
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=ConsumptionProperties.GAS_ENERGY_UNIT,
        name=f"{NAME} gas energy unit",
        icon="mdi:cube-scan",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        get_current_option=lambda entity: entity.device.gas_energy_unit,
        get_options=lambda entity: entity.device.get_gas_energy_units(),
        select_option=lambda entity, option: entity.device.async_set_gas_energy_unit(
            option
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=DeviceProperties.HYBRID_MODE,
        name=f"{NAME} hybrid mode",
        icon="mdi:cog",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HYBRID_SYS],
        get_current_option=lambda entity: entity.device.hybrid_mode,
        get_options=lambda entity: entity.device.hybrid_mode_opt_texts,
        select_option=lambda entity, option: entity.device.async_set_hybrid_mode(
            option
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=DeviceProperties.BUFFER_CONTROL_MODE,
        name=f"{NAME} buffer control mode",
        icon="mdi:cup-water",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.BUFFER_TIME_PROG_AVAILABLE],
        get_current_option=lambda entity: entity.device.buffer_control_mode,
        get_options=lambda entity: entity.device.buffer_control_mode_opt_texts,
        select_option=lambda entity,
        option: entity.device.async_set_buffer_control_mode(option),
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=EvoOneDeviceProperties.MODE,
        name=f"{NAME} operation mode",
        icon="mdi:cog",
        get_current_option=lambda entity: entity.device.water_heater_current_mode_text,
        get_options=lambda entity: entity.device.water_heater_mode_operation_texts,
        select_option=lambda entity,
        option: entity.device.async_set_water_heater_operation_mode(option),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Evo],
    ),
)
