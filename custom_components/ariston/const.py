"""Constants for the Ariston integration."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import datetime as dt
import logging
import sys
from typing import Any, Final

from ariston.const import (
    ARISTON_BUS_ERRORS,
    ConsumptionProperties,
    ConsumptionType,
    CustomDeviceFeatures,
    DeviceAttribute,
    DeviceFeatures,
    DeviceProperties,
    EvoDeviceProperties,
    EvoLydosDeviceProperties,
    EvoOneDeviceProperties,
    GasType,
    MedDeviceSettings,
    MenuItemNames,
    NuosSplitProperties,
    SeDeviceSettings,
    SlpDeviceSettings,
    SystemType,
    ThermostatProperties,
    VelisDeviceProperties,
    WheType,
)

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
from homeassistant.const import UnitOfEnergy, UnitOfTemperature, UnitOfTime, UnitOfVolume
from homeassistant.helpers.entity import EntityCategory, EntityDescription

try:
    from homeassistant.components.water_heater import WaterHeaterEntityDescription
except ImportError:  # HA < 2025.1
    from homeassistant.components.water_heater import (
        WaterHeaterEntityEntityDescription as WaterHeaterEntityDescription,
    )

_LOGGER = logging.getLogger(__name__)

DOMAIN: Final[str] = "ariston"
NAME: Final[str] = "Ariston"
COORDINATOR: Final[str] = "coordinator"
ENERGY_COORDINATOR: Final[str] = "energy_coordinator"
ENERGY_SCAN_INTERVAL: Final[str] = "energy_scan_interval"
BUS_ERRORS_COORDINATOR: Final[str] = "bus_errors_coordinator"
BUS_ERRORS_SCAN_INTERVAL: Final[str] = "bus_errors_scan_interval"
API_URL_SETTING: Final[str] = "api_url_setting"
API_USER_AGENT: Final[str] = "api_user_agent"

DEFAULT_SCAN_INTERVAL_SECONDS: Final[int] = 180
DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES: Final[int] = 60
DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS: Final[int] = 600

ATTR_TARGET_TEMP_STEP: Final[str] = "target_temp_step"
ATTR_HEAT_REQUEST: Final[str] = "heat_request"
ATTR_ECONOMY_TEMP: Final[str] = "economy_temp"
ATTR_HOLIDAY: Final[str] = "holiday"
ATTR_ZONE: Final[str] = "zone_number"
ATTR_ERRORS: Final[str] = "errors"

EXTRA_STATE_ATTRIBUTE: Final[str] = "Attribute"
EXTRA_STATE_DEVICE_METHOD: Final[str] = "DeviceMethod"

# ==================== CONSUMPTION KEYS (API TRUTH) ====================
GAS_HEATING_KEY: Final[int] = 1      # Central Heating Gas (kWh)
GAS_DHW_KEY: Final[int] = 2          # Domestic Hot Water Gas (kWh)
ELEC_HEATING_KEY: Final[int] = 10    # Central Heating Electricity (kWh)
ELEC_DHW_KEY: Final[int] = 21        # Domestic Hot Water Electricity (kWh)

# ==================== RAW ACCESS ====================

def get_consumption_sequence(entity, key: int, period: int) -> list[float] | None:
    sequences = getattr(entity.device, "consumptions_sequences", None)
    if not sequences:
        return None
    for seq in sequences:
        if seq.get("k") == key and seq.get("p") == period:
            return seq.get("v", [])
    return None


# ==================== PRIMITIVES ====================

def _last(values: list[float]) -> float | None:
    return round(values[-1], 2) if values and values[-1] > 0 else None


def _last_nonzero(values: list[float]) -> float | None:
    for v in reversed(values or []):
        if v > 0:
            return round(v, 2)
    return None


def _rolling(values: list[float], length: int) -> float | None:
    if not values or len(values) < length:
        return None
    return round(sum(values[-length:]), 2)


def _current_month(values: list[float]) -> float | None:
    """
    API returns finalized daily values.
    Today is excluded because it may be partial.
    """
    if not values:
        return None
    days_completed = dt.datetime.now().day - 1
    return round(sum(values[:days_completed]), 2)


# ==================== SEMANTIC ACCESS ====================

def yesterday(entity, key: int) -> float | None:
    return _last(get_consumption_sequence(entity, key, 3) or [])


def current_month(entity, key: int) -> float | None:
    return _current_month(get_consumption_sequence(entity, key, 3) or [])


def last_month(entity, key: int) -> float | None:
    return _last_nonzero(get_consumption_sequence(entity, key, 4) or [])


def rolling(entity, key: int, period: int, length: int) -> float | None:
    return _rolling(get_consumption_sequence(entity, key, period) or [], length)


# ==================== GAS CONFIG ====================

GAS_CALORIFIC_VALUES_KWH_PER_M3 = {
    GasType.NATURAL_GAS: 11.2,       # Natural Gas: 10.5-11.5 kWh/m³
    GasType.LPG: 26.0,               # LPG: 25-28 kWh/m³
    GasType.PROPANE: 25.5,           # Propane: 25-28 kWh/m³
    GasType.AIR_PROPANED: 8.5,       # Air-Propane mix: variable, ~8.5 kWh/m³
    GasType.GPO: 10.0,               # GPO: region-specific
}

DEFAULT_CALORIFIC_VALUE = 11.2
DEFAULT_GAS_TYPE = GasType.NATURAL_GAS


def get_gas_type_from_config(entity) -> GasType:
    try:
        return GasType(getattr(entity.device, "gas_type", None))
    except Exception:
        return DEFAULT_GAS_TYPE


def get_gas_calorific_value(entity) -> float:
    return GAS_CALORIFIC_VALUES_KWH_PER_M3.get(
        get_gas_type_from_config(entity),
        DEFAULT_CALORIFIC_VALUE,
    )


def gas_kwh_to_m3(entity, value: float | None) -> float | None:
    if value is None:
        return None
    return round(value / get_gas_calorific_value(entity), 3)


# ==================== FACTORIES ====================

def make_kwh(fn, key: int):
    return lambda entity: fn(entity, key)


def make_roll(key: int, period: int, length: int):
    return lambda entity: rolling(entity, key, period, length)


def make_m3(kwh_fn):
    return lambda entity: gas_kwh_to_m3(entity, kwh_fn(entity))


# ==================== GAS (kWh) ====================

get_yesterday_heating_gas_kwh = make_kwh(yesterday, GAS_HEATING_KEY)
get_yesterday_dhw_gas_kwh = make_kwh(yesterday, GAS_DHW_KEY)

get_current_month_heating_gas_kwh = make_kwh(current_month, GAS_HEATING_KEY)
get_current_month_dhw_gas_kwh = make_kwh(current_month, GAS_DHW_KEY)

get_last_month_heating_gas_kwh = make_kwh(last_month, GAS_HEATING_KEY)
get_last_month_dhw_gas_kwh = make_kwh(last_month, GAS_DHW_KEY)

get_rolling_24h_heating_gas_kwh = make_roll(GAS_HEATING_KEY, 1, 24)
get_rolling_24h_dhw_gas_kwh = make_roll(GAS_DHW_KEY, 1, 24)

get_rolling_7day_heating_gas_kwh = make_roll(GAS_HEATING_KEY, 2, 7)
get_rolling_7day_dhw_gas_kwh = make_roll(GAS_DHW_KEY, 2, 7)

get_rolling_30day_heating_gas_kwh = make_roll(GAS_HEATING_KEY, 3, 30)
get_rolling_30day_dhw_gas_kwh = make_roll(GAS_DHW_KEY, 3, 30)


# ==================== GAS (m³) ====================

get_yesterday_heating_gas_m3 = make_m3(get_yesterday_heating_gas_kwh)
get_yesterday_dhw_gas_m3 = make_m3(get_yesterday_dhw_gas_kwh)

get_current_month_heating_gas_m3 = make_m3(get_current_month_heating_gas_kwh)
get_current_month_dhw_gas_m3 = make_m3(get_current_month_dhw_gas_kwh)

get_last_month_heating_gas_m3 = make_m3(get_last_month_heating_gas_kwh)
get_last_month_dhw_gas_m3 = make_m3(get_last_month_dhw_gas_kwh)

get_rolling_24h_heating_gas_m3 = make_m3(get_rolling_24h_heating_gas_kwh)
get_rolling_24h_dhw_gas_m3 = make_m3(get_rolling_24h_dhw_gas_kwh)

get_rolling_7day_heating_gas_m3 = make_m3(get_rolling_7day_heating_gas_kwh)
get_rolling_7day_dhw_gas_m3 = make_m3(get_rolling_7day_dhw_gas_kwh)

get_rolling_30day_heating_gas_m3 = make_m3(get_rolling_30day_heating_gas_kwh)
get_rolling_30day_dhw_gas_m3 = make_m3(get_rolling_30day_dhw_gas_kwh)


# ==================== ELECTRICITY (kWh) ====================

get_yesterday_heating_electricity_kwh = make_kwh(yesterday, ELEC_HEATING_KEY)
get_yesterday_dhw_electricity_kwh = make_kwh(yesterday, ELEC_DHW_KEY)

get_current_month_heating_electricity_kwh = make_kwh(current_month, ELEC_HEATING_KEY)
get_current_month_dhw_electricity_kwh = make_kwh(current_month, ELEC_DHW_KEY)

get_last_month_heating_electricity_kwh = make_kwh(last_month, ELEC_HEATING_KEY)
get_last_month_dhw_electricity_kwh = make_kwh(last_month, ELEC_DHW_KEY)

get_rolling_24h_heating_electricity_kwh = make_roll(ELEC_HEATING_KEY, 1, 24)
get_rolling_24h_dhw_electricity_kwh = make_roll(ELEC_DHW_KEY, 1, 24)

get_rolling_7day_heating_electricity_kwh = make_roll(ELEC_HEATING_KEY, 2, 7)
get_rolling_7day_dhw_electricity_kwh = make_roll(ELEC_DHW_KEY, 2, 7)

get_rolling_30day_heating_electricity_kwh = make_roll(ELEC_HEATING_KEY, 3, 30)
get_rolling_30day_dhw_electricity_kwh = make_roll(ELEC_DHW_KEY, 3, 30)

@dataclass(kw_only=True, frozen=True)
class AristonBaseEntityDescription(EntityDescription):
    """An abstract class that describes Ariston entites."""

    device_features: list[str] | None = None
    coordinator: str = COORDINATOR
    extra_states: list[dict[str, Any]] | None = None
    system_types: list[SystemType] | None = None
    whe_types: list[WheType] | None = None
    zone: bool = False

@dataclass(kw_only=True, frozen=True)
class AristonClimateEntityDescription(
    ClimateEntityDescription, AristonBaseEntityDescription
):
    """A class that describes climate entities."""

@dataclass(kw_only=True, frozen=True)
class AristonWaterHeaterEntityDescription(
    WaterHeaterEntityDescription, AristonBaseEntityDescription
):
    """A class that describes climate entities."""

@dataclass(kw_only=True, frozen=True)
class AristonBinarySensorEntityDescription(
    BinarySensorEntityDescription, AristonBaseEntityDescription
):
    """A class that describes binary sensor entities."""

    get_is_on: Callable[[Any], bool]

@dataclass(kw_only=True, frozen=True)
class AristonSwitchEntityDescription(
    SwitchEntityDescription, AristonBaseEntityDescription
):
    """A class that describes switch entities."""

    set_value: Callable[[Any, bool], Coroutine]
    get_is_on: Callable[[Any], bool]

@dataclass(kw_only=True, frozen=True)
class AristonNumberEntityDescription(
    NumberEntityDescription, AristonBaseEntityDescription
):
    """A class that describes switch entities."""

    set_native_value: Callable[[Any, float], Coroutine]
    get_native_value: Callable[[Any], Coroutine]
    get_native_min_value: Callable[[Any], float] | None = None
    get_native_max_value: Callable[[Any], float | None] | None = None
    get_native_step: Callable[[Any], Coroutine] | None = None

@dataclass(kw_only=True, frozen=True)
class AristonSensorEntityDescription(
    SensorEntityDescription, AristonBaseEntityDescription
):
    """A class that describes sensor entities."""

    get_native_unit_of_measurement: Callable[[Any], str] | None = None
    get_last_reset: Callable[[Any], dt.datetime] | None = None
    get_native_value: Callable[[Any], Any]

@dataclass(kw_only=True, frozen=True)
class AristonSelectEntityDescription(
    SelectEntityDescription, AristonBaseEntityDescription
):
    """A class that describes select entities."""

    get_current_option: Callable[[Any], str]
    get_options: Callable[[Any], list[str]]
    select_option: Callable[[Any, str], Coroutine]

ARISTON_CLIMATE_TYPES: list[AristonClimateEntityDescription] = [
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
]

ARISTON_WATER_HEATER_TYPES: list[AristonWaterHeaterEntityDescription] = [
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
]

ARISTON_SENSOR_TYPES: list[AristonSensorEntityDescription] = [
    # Existing device sensors
    AristonSensorEntityDescription(
        key=DeviceProperties.HEATING_CIRCUIT_PRESSURE,
        name=f"{NAME} heating circuit pressure",
        icon="mdi:gauge",
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
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.ch_flow_setpoint_temp_value,
        get_native_unit_of_measurement=lambda entity: entity.device.ch_flow_setpoint_temp_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.CH_FLOW_TEMP,
        name=f"{NAME} CH flow temp",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.ch_flow_temp_value,
        get_native_unit_of_measurement=lambda entity: entity.device.ch_flow_temp_unit,
        device_features=[DeviceProperties.CH_FLOW_TEMP],
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=str(MenuItemNames.SIGNAL_STRENGTH),
        name=f"{NAME} signal strength",
        icon="mdi:wifi",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        get_native_value=lambda entity: entity.device.signal_strength_value,
        get_native_unit_of_measurement=lambda entity: entity.device.signal_strength_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=str(MenuItemNames.CH_RETURN_TEMP),
        name=f"{NAME} CH return temp",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.ch_return_temp_value,
        get_native_unit_of_measurement=lambda entity: entity.device.ch_return_temp_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.OUTSIDE_TEMP,
        name=f"{NAME} Outside temp",
        icon="mdi:thermometer",
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
    
    # ==================== GAS CALORIFIC VALUE ====================
    AristonSensorEntityDescription(
        key="gas_calorific_value",
        name=f"{NAME} gas calorific value",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=f"{UnitOfEnergy.KILO_WATT_HOUR}/{UnitOfVolume.CUBIC_METERS}",
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_gas_calorific_value,
    ),
    
    # ==================== YESTERDAY CONSUMPTION ====================
    # Gas - kWh
    AristonSensorEntityDescription(
        key="yesterday_heating_gas_kwh",
        name=f"{NAME} yesterday heating gas energy",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_yesterday_heating_gas_kwh,
    ),
    AristonSensorEntityDescription(
        key="yesterday_dhw_gas_kwh",
        name=f"{NAME} yesterday DHW gas energy",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_yesterday_dhw_gas_kwh,
    ),
    # Gas - m³
    AristonSensorEntityDescription(
        key="yesterday_heating_gas_m3",
        name=f"{NAME} yesterday heating gas",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_yesterday_heating_gas_m3,
    ),
    AristonSensorEntityDescription(
        key="yesterday_dhw_gas_m3",
        name=f"{NAME} yesterday DHW gas",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_yesterday_dhw_gas_m3,
    ),
    # Electricity
    AristonSensorEntityDescription(
        key="yesterday_heating_electricity_kwh",
        name=f"{NAME} yesterday heating electricity",
        icon="mdi:lightning-bolt",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_yesterday_heating_electricity_kwh,
    ),
    AristonSensorEntityDescription(
        key="yesterday_dhw_electricity_kwh",
        name=f"{NAME} yesterday DHW electricity",
        icon="mdi:lightning-bolt",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_yesterday_dhw_electricity_kwh,
    ),
    
    # ==================== CURRENT MONTH CONSUMPTION ====================
    # Gas - kWh
    AristonSensorEntityDescription(
        key="current_month_heating_gas_kwh",
        name=f"{NAME} current month heating gas energy",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_current_month_heating_gas_kwh,
    ),
    AristonSensorEntityDescription(
        key="current_month_dhw_gas_kwh",
        name=f"{NAME} current month DHW gas energy",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_current_month_dhw_gas_kwh,
    ),
    # Gas - m³
    AristonSensorEntityDescription(
        key="current_month_heating_gas_m3",
        name=f"{NAME} current month heating gas",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_current_month_heating_gas_m3,
    ),
    AristonSensorEntityDescription(
        key="current_month_dhw_gas_m3",
        name=f"{NAME} current month DHW gas",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_current_month_dhw_gas_m3,
    ),
    # Electricity
    AristonSensorEntityDescription(
        key="current_month_heating_electricity_kwh",
        name=f"{NAME} current month heating electricity",
        icon="mdi:lightning-bolt",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_current_month_heating_electricity_kwh,
    ),
    AristonSensorEntityDescription(
        key="current_month_dhw_electricity_kwh",
        name=f"{NAME} current month DHW electricity",
        icon="mdi:lightning-bolt",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_current_month_dhw_electricity_kwh,
    ),
    
    # ==================== LAST MONTH CONSUMPTION ====================
    # Gas - kWh
    AristonSensorEntityDescription(
        key="last_month_heating_gas_kwh",
        name=f"{NAME} last month heating gas energy",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_last_month_heating_gas_kwh,
    ),
    AristonSensorEntityDescription(
        key="last_month_dhw_gas_kwh",
        name=f"{NAME} last month DHW gas energy",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_last_month_dhw_gas_kwh,
    ),
    # Gas - m³
    AristonSensorEntityDescription(
        key="last_month_heating_gas_m3",
        name=f"{NAME} last month heating gas",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_last_month_heating_gas_m3,
    ),
    AristonSensorEntityDescription(
        key="last_month_dhw_gas_m3",
        name=f"{NAME} last month DHW gas",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_last_month_dhw_gas_m3,
    ),
    # Electricity
    AristonSensorEntityDescription(
        key="last_month_heating_electricity_kwh",
        name=f"{NAME} last month heating electricity",
        icon="mdi:lightning-bolt",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_last_month_heating_electricity_kwh,
    ),
    AristonSensorEntityDescription(
        key="last_month_dhw_electricity_kwh",
        name=f"{NAME} last month DHW electricity",
        icon="mdi:lightning-bolt",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_last_month_dhw_electricity_kwh,
    ),
    
    # ==================== ROLLING 24H CONSUMPTION ====================
    # Gas - kWh
    AristonSensorEntityDescription(
        key="rolling_24h_heating_gas_kwh",
        name=f"{NAME} rolling 24h heating gas energy",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_24h_heating_gas_kwh,
    ),
    AristonSensorEntityDescription(
        key="rolling_24h_dhw_gas_kwh",
        name=f"{NAME} rolling 24h DHW gas energy",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_24h_dhw_gas_kwh,
    ),
    # Gas - m³
    AristonSensorEntityDescription(
        key="rolling_24h_heating_gas_m3",
        name=f"{NAME} rolling 24h heating gas",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_24h_heating_gas_m3,
    ),
    AristonSensorEntityDescription(
        key="rolling_24h_dhw_gas_m3",
        name=f"{NAME} rolling 24h DHW gas",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_24h_dhw_gas_m3,
    ),
    # Electricity
    AristonSensorEntityDescription(
        key="rolling_24h_heating_electricity_kwh",
        name=f"{NAME} rolling 24h heating electricity",
        icon="mdi:lightning-bolt",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_24h_heating_electricity_kwh,
    ),
    AristonSensorEntityDescription(
        key="rolling_24h_dhw_electricity_kwh",
        name=f"{NAME} rolling 24h DHW electricity",
        icon="mdi:lightning-bolt",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_24h_dhw_electricity_kwh,
    ),
    
    # ==================== ROLLING 7DAY CONSUMPTION ====================
    # Gas - kWh
    AristonSensorEntityDescription(
        key="rolling_7day_heating_gas_kwh",
        name=f"{NAME} rolling 7d heating gas energy",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_7day_heating_gas_kwh,
    ),
    AristonSensorEntityDescription(
        key="rolling_7day_dhw_gas_kwh",
        name=f"{NAME} rolling 7d DHW gas energy",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_7day_dhw_gas_kwh,
    ),
    # Gas - m³
    AristonSensorEntityDescription(
        key="rolling_7day_heating_gas_m3",
        name=f"{NAME} rolling 7d heating gas",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_7day_heating_gas_m3,
    ),
    AristonSensorEntityDescription(
        key="rolling_7day_dhw_gas_m3",
        name=f"{NAME} rolling 7d DHW gas",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_7day_dhw_gas_m3,
    ),
    # Electricity
    AristonSensorEntityDescription(
        key="rolling_7day_heating_electricity_kwh",
        name=f"{NAME} rolling 7d heating electricity",
        icon="mdi:lightning-bolt",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_7day_heating_electricity_kwh,
    ),
    AristonSensorEntityDescription(
        key="rolling_7day_dhw_electricity_kwh",
        name=f"{NAME} rolling 7d DHW electricity",
        icon="mdi:lightning-bolt",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_7day_dhw_electricity_kwh,
    ),
    
    # ==================== ROLLING 30DAY CONSUMPTION ====================
    # Gas - kWh
    AristonSensorEntityDescription(
        key="rolling_30day_heating_gas_kwh",
        name=f"{NAME} rolling 30d heating gas energy",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_30day_heating_gas_kwh,
    ),
    AristonSensorEntityDescription(
        key="rolling_30day_dhw_gas_kwh",
        name=f"{NAME} rolling 30d DHW gas energy",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_30day_dhw_gas_kwh,
    ),
    # Gas - m³
    AristonSensorEntityDescription(
        key="rolling_30day_heating_gas_m3",
        name=f"{NAME} rolling 30d heating gas",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_30day_heating_gas_m3,
    ),
    AristonSensorEntityDescription(
        key="rolling_30day_dhw_gas_m3",
        name=f"{NAME} rolling 30d DHW gas",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_30day_dhw_gas_m3,
    ),
    # Electricity
    AristonSensorEntityDescription(
        key="rolling_30day_heating_electricity_kwh",
        name=f"{NAME} rolling 30d heating electricity",
        icon="mdi:lightning-bolt",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_30day_heating_electricity_kwh,
    ),
    AristonSensorEntityDescription(
        key="rolling_30day_dhw_electricity_kwh",
        name=f"{NAME} rolling 30d DHW electricity",
        icon="mdi:lightning-bolt",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=get_rolling_30day_dhw_electricity_kwh,
    ),
    
    # ==================== EXISTING SENSORS ====================
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
]

# ==================== BINARY SENSOR ENTITIES ====================

ARISTON_BINARY_SENSOR_TYPES: list[AristonBinarySensorEntityDescription] = [
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
]

# ==================== SWITCH ENTITIES ====================

ARISTON_SWITCH_TYPES: list[AristonSwitchEntityDescription] = [
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
]

# ==================== NUMBER ENTITIES ====================

ARISTON_NUMBER_TYPES: list[AristonNumberEntityDescription] = [
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
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
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
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
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
]

# ==================== SELECT ENTITIES ====================

ARISTON_SELECT_TYPES: list[AristonSelectEntityDescription] = [
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
]