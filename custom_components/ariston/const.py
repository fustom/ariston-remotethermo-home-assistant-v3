"""Constants for the Ariston integration."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import logging
import sys
from typing import Any, Final

from ariston.const import (
    ARISTON_BUS_ERRORS,
    ConsumptionProperties,
    ConsumptionType,
    CustomDeviceFeatures,
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
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.helpers.entity import EntityCategory, EntityDescription
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

try:
    from homeassistant.components.water_heater import WaterHeaterEntityDescription
except ImportError:  # HA < 2025.1
    from homeassistant.components.water_heater import (
        WaterHeaterEntityEntityDescription as WaterHeaterEntityDescription,
    )

_LOGGER = logging.getLogger(__name__)

# ==================== GENERAL CONSTANTS ====================

DOMAIN: Final[str] = "ariston"
NAME: Final[str] = "Ariston"
COORDINATOR: Final[str] = "coordinator"
ENERGY_COORDINATOR: Final[str] = "energy_coordinator"
ENERGY_SCAN_INTERVAL: Final[str] = "energy_scan_interval"
BUS_ERRORS_COORDINATOR: Final[str] = "bus_errors_coordinator"
BUS_ERRORS_SCAN_INTERVAL: Final[str] = "bus_errors_scan_interval"
API_URL_SETTING: Final[str] = "api_url_setting"
API_USER_AGENT: Final[str] = "api_user_agent"
WATER_HEATER_TEMPERATURE_UNIT: Final[str] = "water_heater_temperature_unit"
RATED_POWER_W: Final[str] = "rated_power_w"

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

# ==================== CONSUMPTION CONFIG ====================

# API Keys for consumption sequences
GAS_HEATING_KEY: Final[int] = 7
GAS_DHW_KEY: Final[int] = 10
ELEC_HEATING_KEY: Final[int] = 20
ELEC_DHW_KEY: Final[int] = 21

# Gas Configuration
GAS_CALORIFIC_VALUES_KWH_PER_M3 = {
    GasType.NATURAL_GAS: 11.2,
    GasType.LPG: 26.0,
    GasType.PROPANE: 25.5,
    GasType.AIR_PROPANED: 8.5,
    GasType.GPO: 10.0,
}
DEFAULT_CALORIFIC_VALUE = 11.2
DEFAULT_GAS_TYPE = GasType.NATURAL_GAS

# Per-device custom calorific value overrides.
# Key: device gateway/ID string.  Value: kWh/m³ entered by the user.
# Cleared automatically whenever the gas type selector changes so the
# displayed value always reflects the new gas type's default unless the
# user subsequently edits it again.
_calorific_value_overrides: dict[str, float] = {}

_STORAGE_KEY = "ariston.calorific_overrides"
_STORAGE_VERSION = 1


def _device_id(entity: Any) -> str:
    """Return a stable string key that uniquely identifies a device."""
    # Prefer `gateway` (present on most Ariston device objects); fall back to
    # the Python id() so the dict never raises a KeyError on unusual objects.
    return str(getattr(entity.device, "gateway", id(entity.device)))


async def async_load_calorific_overrides(hass: Any) -> None:
    """Load saved calorific overrides from disk into memory."""
    store: Store = Store(hass, _STORAGE_VERSION, _STORAGE_KEY)
    data = await store.async_load()
    if data and isinstance(data, dict):
        _calorific_value_overrides.update(data)
        _LOGGER.debug("Loaded calorific overrides from storage: %s", data)


async def _async_save_calorific_overrides(hass: Any) -> None:
    """Save calorific overrides from memory to disk."""
    store: Store = Store(hass, _STORAGE_VERSION, _STORAGE_KEY)
    await store.async_save(dict(_calorific_value_overrides))


# ==================== DATA PROCESSING UTILITIES ====================

def get_consumption_sequence(entity: Any, key: int, period: int) -> list[float] | None:
    """Extract a specific sequence from the device consumption data."""
    sequences = getattr(entity.device, "consumptions_sequences", None)
    if not sequences:
        return None
    for seq in sequences:
        if seq.get("k") == key and seq.get("p") == period:
            return seq.get("v", [])
    return None

def _last(values: list[float] | None) -> float | None:
    """Return the last value in a list."""
    return round(values[-1], 2) if values else None

def _rolling(values: list[float] | None, length: int) -> float | None:
    """Return the sum of the last N values."""
    if not values or len(values) < length:
        return None
    return round(sum(values[-length:]), 2)

def _current_month(values: list[float] | None) -> float | None:
    """
    Calculate month-to-date consumption.
    API returns finalized daily values (p=3). We sum the subset belonging to the current month.
    Today is usually excluded in finalized data.
    """
    if not values:
        return None

    now = dt_util.now()
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # tm_yday is 1-indexed. Array is 0-indexed.
    start_index = first_of_month.timetuple().tm_yday - 1
    
    return round(sum(values[start_index:]), 2)

# ==================== SEMANTIC ACCESSORS ====================

def yesterday(entity: Any, key: int) -> float | None:
    """Get consumption for yesterday (last value of period 3)."""
    return _last(get_consumption_sequence(entity, key, 3))

def current_month(entity: Any, key: int) -> float | None:
    """Get consumption for the current month (subset of period 3)."""
    return _current_month(get_consumption_sequence(entity, key, 3))

def last_month(entity: Any, key: int) -> float | None:
    """Get consumption for last month (last value of period 4)."""
    return _last(get_consumption_sequence(entity, key, 4))

def rolling(entity: Any, key: int, period: int, length: int) -> float | None:
    """Get rolling consumption."""
    return _rolling(get_consumption_sequence(entity, key, period), length)

# ==================== GAS UTILITIES ====================

def get_gas_type_from_config(entity: Any) -> GasType:
    """Safely retrieve the GasType from the device."""
    try:
        return GasType(getattr(entity.device, "gas_type", None))
    except (ValueError, TypeError):
        return DEFAULT_GAS_TYPE


def get_default_calorific_value_for_gas_type(entity: Any) -> float:
    """Return the *built-in* calorific value for the device's current gas type.

    This is the unmodified lookup from the static table and is used both as a
    display fallback and to re-seed the editable number entity after a gas-type
    change.
    """
    return GAS_CALORIFIC_VALUES_KWH_PER_M3.get(
        get_gas_type_from_config(entity),
        DEFAULT_CALORIFIC_VALUE,
    )


def get_gas_calorific_value(entity: Any) -> float:
    """Return the *effective* calorific value for the device.

    Priority order:
    1. A user-supplied custom value stored in ``_calorific_value_overrides``.
    2. The built-in default for the device's current gas type.

    This function is the single source of truth used by every m³ conversion so
    that both the sensor display and all consumption calculations stay in sync.
    """
    return _calorific_value_overrides.get(
        _device_id(entity),
        get_default_calorific_value_for_gas_type(entity),
    )


def set_gas_calorific_value(entity: Any, value: float) -> None:
    """Persist a custom calorific value for the given device (in-memory).

    The value survives for the lifetime of the HA process.  It is cleared by
    ``clear_calorific_value_override`` when the gas type selector changes so
    the stored override never silently contradicts the selected gas type.
    """
    _calorific_value_overrides[_device_id(entity)] = round(value, 4)
    _LOGGER.debug(
        "Custom calorific value set for device %s: %.4f kWh/m³",
        _device_id(entity),
        value,
    )


def clear_calorific_value_override(entity: Any) -> None:
    """Remove any custom calorific value for the device.

    Called automatically by the gas-type select wrapper so the editable number
    entity reverts to the new gas type's built-in default.
    """
    key = _device_id(entity)
    removed = _calorific_value_overrides.pop(key, None)
    if removed is not None:
        _LOGGER.debug(
            "Custom calorific value cleared for device %s (was %.4f kWh/m³)",
            key,
            removed,
        )


async def _async_set_and_save_calorific_value(entity: Any, value: float) -> None:
    """Set the gas calorific override, save to disk, and refresh sensors."""
    set_gas_calorific_value(entity, value)
    await _async_save_calorific_overrides(entity.hass)
    await entity.coordinator.async_request_refresh()


async def _async_clear_and_set_gas_type(entity: Any, option: str) -> None:
    """Clear the calorific override, save, and set the new gas type."""
    clear_calorific_value_override(entity)
    await _async_save_calorific_overrides(entity.hass)
    await entity.device.async_set_gas_type(option)


def gas_kwh_to_m3(entity: Any, value: float | None) -> float | None:
    """Convert kWh to m³ based on the *effective* calorific value."""
    if value is None:
        return None
    return round(value / get_gas_calorific_value(entity), 3)


def get_estimated_power(entity: Any) -> int | None:
    """Estimate instantaneous power from configured rating and heating state."""
    heating = getattr(entity.device, "is_heating", None)
    rated_power_w = entity.coordinator.rated_power_w
    if heating is None or rated_power_w is None:
        return None
    return rated_power_w if heating else 0


# ==================== ENTITY DESCRIPTION BASE CLASSES ====================

@dataclass(kw_only=True, frozen=True)
class AristonBaseEntityDescription(EntityDescription):
    """Base class for Ariston entity descriptions."""
    device_features: list[str] | None = None
    coordinator: str = COORDINATOR
    extra_states: list[dict[str, Any]] | None = None
    system_types: list[SystemType] | None = None
    whe_types: list[WheType] | None = None
    zone: bool = False
    get_is_supported: Callable[[Any], bool] | None = None
    get_is_available: Callable[[Any], bool] | None = None

@dataclass(kw_only=True, frozen=True)
class AristonClimateEntityDescription(ClimateEntityDescription, AristonBaseEntityDescription):
    """Climate entity description."""

@dataclass(kw_only=True, frozen=True)
class AristonWaterHeaterEntityDescription(WaterHeaterEntityDescription, AristonBaseEntityDescription):
    """Water heater entity description."""

@dataclass(kw_only=True, frozen=True)
class AristonBinarySensorEntityDescription(BinarySensorEntityDescription, AristonBaseEntityDescription):
    """Binary sensor entity description."""
    get_is_on: Callable[[Any], bool]

@dataclass(kw_only=True, frozen=True)
class AristonSwitchEntityDescription(SwitchEntityDescription, AristonBaseEntityDescription):
    """Switch entity description."""
    set_value: Callable[[Any, bool], Coroutine]
    get_is_on: Callable[[Any], bool]

@dataclass(kw_only=True, frozen=True)
class AristonNumberEntityDescription(NumberEntityDescription, AristonBaseEntityDescription):
    """Number entity description."""
    set_native_value: Callable[[Any, float], Coroutine]
    get_native_value: Callable[[Any], Coroutine]
    get_native_min_value: Callable[[Any], float] | None = None
    get_native_max_value: Callable[[Any], float | None] | None = None
    get_native_step: Callable[[Any], Coroutine] | None = None

@dataclass(kw_only=True, frozen=True)
class AristonSensorEntityDescription(SensorEntityDescription, AristonBaseEntityDescription):
    """Sensor entity description."""
    get_native_unit_of_measurement: Callable[[Any], str] | None = None
    get_last_reset: Callable[[Any], dt_util.datetime] | None = None
    get_native_value: Callable[[Any], Any]

@dataclass(kw_only=True, frozen=True)
class AristonSelectEntityDescription(SelectEntityDescription, AristonBaseEntityDescription):
    """Select entity description."""
    get_current_option: Callable[[Any], str]
    get_options: Callable[[Any], list[str]]
    select_option: Callable[[Any, str], Coroutine]

# ==================== SENSOR GENERATION ====================

def _create_sensor_description(
    key: str,
    name: str,
    value_fn: Callable[[Any], Any],
    device_class: SensorDeviceClass | None,
    unit: str,
    state_class: SensorStateClass,
    features: list[str],
) -> AristonSensorEntityDescription:
    """Factory to create a standardized sensor description."""
    return AristonSensorEntityDescription(
        key=key,
        name=f"{NAME} {name}",
        icon="mdi:gas-cylinder" if "gas" in key else "mdi:lightning-bolt",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=state_class,
        device_class=device_class,
        native_unit_of_measurement=unit,
        device_features=[DeviceFeatures.HAS_METERING, *features],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=value_fn,
    )

def _generate_consumption_sensors() -> list[AristonSensorEntityDescription]:
    """Generate all consumption sensor descriptions dynamically."""
    sensors = []
    
    # Define Metrics (Source)
    metrics = [
        {
            "name": "heating gas",
            "key": GAS_HEATING_KEY,
            "feature": ConsumptionType.CENTRAL_HEATING_GAS.name,
            "is_gas": True,
        },
        {
            "name": "DHW gas",
            "key": GAS_DHW_KEY,
            "feature": ConsumptionType.DOMESTIC_HOT_WATER_GAS.name,
            "is_gas": True,
        },
        {
            "name": "heating electricity",
            "key": ELEC_HEATING_KEY,
            "feature": ConsumptionType.CENTRAL_HEATING_ELECTRICITY.name,
            "is_gas": False,
        },
        {
            "name": "DHW electricity",
            "key": ELEC_DHW_KEY,
            "feature": ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY.name,
            "is_gas": False,
        },
    ]

    # Define Periods (Time dimensions)
    periods = [
        {"suffix": "yesterday", "state_class": SensorStateClass.TOTAL, "fn": lambda e, k: yesterday(e, k)},
        {"suffix": "current month", "state_class": SensorStateClass.TOTAL_INCREASING, "fn": lambda e, k: current_month(e, k)},
        {"suffix": "last month", "state_class": SensorStateClass.TOTAL, "fn": lambda e, k: last_month(e, k)},
        {"suffix": "rolling 24h", "state_class": SensorStateClass.MEASUREMENT, "fn": lambda e, k: rolling(e, k, 1, 24)},
        {"suffix": "rolling 7d", "state_class": SensorStateClass.MEASUREMENT, "fn": lambda e, k: rolling(e, k, 2, 7)},
        {"suffix": "rolling 30d", "state_class": SensorStateClass.MEASUREMENT, "fn": lambda e, k: rolling(e, k, 3, 30)},
    ]

    for metric in metrics:
        for period in periods:
            base_name = f"{period['suffix']} {metric['name']}"
            kwh_key = f"{period['suffix']}_{metric['name'].replace(' ', '_')}_kwh"
            kwh_name = f"{base_name} energy" if metric['is_gas'] else base_name
            
            # 1. Energy Sensor (kWh)
            sensors.append(
                _create_sensor_description(
                    key=kwh_key,
                    name=kwh_name,
                    value_fn=lambda e, k=metric['key'], f=period['fn']: f(e, k),
                    device_class=SensorDeviceClass.ENERGY,
                    unit=UnitOfEnergy.KILO_WATT_HOUR,
                    state_class=period['state_class'],
                    features=[metric['feature']],
                )
            )

            # 2. Volume Sensor (m³) - Only for Gas
            if metric['is_gas']:
                m3_key = f"{period['suffix']}_{metric['name'].replace(' ', '_')}_m3"
                m3_name = base_name
                
                # Wrapper to convert kWh function result to m³
                def m3_wrapper(e: Any, k: int, f: Callable):
                    val = f(e, k)
                    return gas_kwh_to_m3(e, val)

                sensors.append(
                    _create_sensor_description(
                        key=m3_key,
                        name=m3_name,
                        value_fn=lambda e, k=metric['key'], f=period['fn']: gas_kwh_to_m3(e, f(e, k)),
                        device_class=SensorDeviceClass.GAS,
                        unit=UnitOfVolume.CUBIC_METERS,
                        state_class=period['state_class'],
                        features=[metric['feature']],
                    )
                )
    return sensors

# ==================== ENTITY LISTS ====================

ARISTON_CLIMATE_TYPES: list[AristonClimateEntityDescription] = [
    AristonClimateEntityDescription(
        key="AristonClimate",
        extra_states=[
            {EXTRA_STATE_ATTRIBUTE: ATTR_HEAT_REQUEST, EXTRA_STATE_DEVICE_METHOD: lambda e: e.device.get_zone_heat_request_value(e.zone)},
            {EXTRA_STATE_ATTRIBUTE: ATTR_ECONOMY_TEMP, EXTRA_STATE_DEVICE_METHOD: lambda e: e.device.get_zone_economy_temp_value(e.zone)},
            {EXTRA_STATE_ATTRIBUTE: ATTR_ZONE, EXTRA_STATE_DEVICE_METHOD: lambda e: e.zone},
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
        extra_states=[{EXTRA_STATE_ATTRIBUTE: ATTR_TARGET_TEMP_STEP, EXTRA_STATE_DEVICE_METHOD: lambda e: e.device.water_heater_temperature_step}],
        device_features=[CustomDeviceFeatures.HAS_DHW],
        system_types=[SystemType.GALEVO, SystemType.BSB],
    ),
    AristonWaterHeaterEntityDescription(
        key="AristonWaterHeater",
        extra_states=[{EXTRA_STATE_ATTRIBUTE: ATTR_TARGET_TEMP_STEP, EXTRA_STATE_DEVICE_METHOD: lambda e: e.device.water_heater_temperature_step}],
        device_features=[CustomDeviceFeatures.HAS_DHW],
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Andris2, WheType.Evo2, WheType.Lux, WheType.Lux2, WheType.Lydos, WheType.LydosHybrid, WheType.NuosSplit],
    ),
]

ARISTON_SENSOR_TYPES: list[AristonSensorEntityDescription] = [
    # --- Device Status Sensors ---
    AristonSensorEntityDescription(
        key=DeviceProperties.HEATING_CIRCUIT_PRESSURE,
        name=f"{NAME} heating circuit pressure",
        icon="mdi:gauge",
        device_class=SensorDeviceClass.PRESSURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda e: e.device.heating_circuit_pressure_value,
        get_native_unit_of_measurement=lambda e: e.device.heating_circuit_pressure_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.CH_FLOW_SETPOINT_TEMP,
        name=f"{NAME} CH flow setpoint temp",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda e: e.device.ch_flow_setpoint_temp_value,
        get_native_unit_of_measurement=lambda e: e.device.ch_flow_setpoint_temp_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.CH_FLOW_TEMP,
        name=f"{NAME} CH flow temp",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda e: e.device.ch_flow_temp_value,
        get_native_unit_of_measurement=lambda e: e.device.ch_flow_temp_unit,
        device_features=[DeviceProperties.CH_FLOW_TEMP],
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=str(MenuItemNames.SIGNAL_STRENGTH),
        name=f"{NAME} signal strength",
        icon="mdi:wifi",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        get_native_value=lambda e: e.device.signal_strength_value,
        get_native_unit_of_measurement=lambda e: e.device.signal_strength_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=str(MenuItemNames.CH_RETURN_TEMP),
        name=f"{NAME} CH return temp",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda e: e.device.ch_return_temp_value,
        get_native_unit_of_measurement=lambda e: e.device.ch_return_temp_unit,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.OUTSIDE_TEMP,
        name=f"{NAME} Outside temp",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        device_features=[CustomDeviceFeatures.HAS_OUTSIDE_TEMP],
        get_native_value=lambda e: e.device.outside_temp_value,
        get_native_unit_of_measurement=lambda e: e.device.outside_temp_unit,
        system_types=[SystemType.GALEVO, SystemType.BSB],
    ),
    AristonSensorEntityDescription(
        key=EvoLydosDeviceProperties.AV_SHW,
        name=f"{NAME} average showers",
        icon="mdi:shower-head",
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda e: e.device.av_shw_value,
        native_unit_of_measurement="",
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Lux, WheType.Evo, WheType.Evo2, WheType.Lydos, WheType.LydosHybrid, WheType.Andris2, WheType.Lux2],
    ),
    AristonSensorEntityDescription(
        key="estimated_power",
        name=f"{NAME} estimated instantaneous power",
        icon="mdi:flash",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        get_native_value=get_estimated_power,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Evo,
            WheType.Evo2,
            WheType.Lydos,
            WheType.Lux,
            WheType.Lux2,
            WheType.Andris2,
        ],
        get_is_supported=lambda coordinator: coordinator.rated_power_w is not None,
        get_is_available=lambda entity: getattr(entity.device, "is_heating", None)
        is not None,
    ),

    # --- Gas Config Sensor ---
    # This sensor always reflects the *effective* calorific value — either a
    # custom value entered via the number entity below, or the built-in default
    # for the currently selected gas type.
    AristonSensorEntityDescription(
        key="gas_calorific_value",
        name=f"{NAME} gas calorific value",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=f"{UnitOfEnergy.KILO_WATT_HOUR}/{UnitOfVolume.CUBIC_METERS}",
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        # get_gas_calorific_value honours the user override if present
        get_native_value=get_gas_calorific_value,
    ),

    # --- Generated Consumption Sensors ---
    *_generate_consumption_sensors(),

    # --- Other Sensors ---
    AristonSensorEntityDescription(
        key=EvoDeviceProperties.RM_TM,
        name=f"{NAME} remaining time",
        icon="mdi:timer",
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda e: e.device.rm_tm_in_minutes,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Lux, WheType.Evo, WheType.Evo2, WheType.Lux2, WheType.Lydos],
    ),
    AristonSensorEntityDescription(
        key=SlpDeviceSettings.SLP_HEATING_RATE,
        name=f"{NAME} heating rate",
        icon="mdi:chart-line",
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda e: e.device.water_heater_heating_rate,
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
        get_native_value=lambda e: len(e.device.bus_errors),
        native_unit_of_measurement="",
        extra_states=[{EXTRA_STATE_ATTRIBUTE: ATTR_ERRORS, EXTRA_STATE_DEVICE_METHOD: lambda e: e.device.bus_errors}],
    ),
    AristonSensorEntityDescription(
        key=EvoOneDeviceProperties.TEMP,
        name=f"{NAME} current temperature",
        icon="mdi:thermometer-auto",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda e: e.device.water_heater_current_temperature,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Evo],
    ),
    AristonSensorEntityDescription(
        key=VelisDeviceProperties.PROC_REQ_TEMP,
        name=f"{NAME} proc req temp",
        icon="mdi:thermometer-auto",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda e: e.device.proc_req_temp_value,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit, WheType.Evo2, WheType.LydosHybrid, WheType.Lydos, WheType.Andris2, WheType.Lux, WheType.Lux2],
    ),
]

ARISTON_BINARY_SENSOR_TYPES: list[AristonBinarySensorEntityDescription] = [
    AristonBinarySensorEntityDescription(key=DeviceProperties.IS_FLAME_ON, name=f"{NAME} is flame on", icon="mdi:fire", get_is_on=lambda e: e.device.is_flame_on_value, system_types=[SystemType.GALEVO, SystemType.BSB]),
    AristonBinarySensorEntityDescription(key=DeviceProperties.IS_HEATING_PUMP_ON, name=f"{NAME} is heating pump on", icon="mdi:heat-pump-outline", get_is_on=lambda e: e.device.is_heating_pump_on_value, device_features=[DeviceFeatures.HP_SYS], system_types=[SystemType.GALEVO]),
    AristonBinarySensorEntityDescription(key=DeviceProperties.HOLIDAY, name=f"{NAME} holiday mode", icon="mdi:island", extra_states=[{EXTRA_STATE_ATTRIBUTE: ATTR_HOLIDAY, EXTRA_STATE_DEVICE_METHOD: lambda e: e.device.holiday_expires_on}], get_is_on=lambda e: e.device.holiday_mode_value, system_types=[SystemType.GALEVO]),
    AristonBinarySensorEntityDescription(key=EvoLydosDeviceProperties.HEAT_REQ, name=f"{NAME} is heating", icon="mdi:fire", get_is_on=lambda e: e.device.is_heating, system_types=[SystemType.VELIS], whe_types=[WheType.Lux, WheType.Evo, WheType.Evo2, WheType.Lydos, WheType.LydosHybrid, WheType.Andris2, WheType.Lux2]),
    AristonBinarySensorEntityDescription(key=EvoLydosDeviceProperties.ANTI_LEG, name=f"{NAME} anti-legionella cycle", icon="mdi:bacteria", get_is_on=lambda e: e.device.is_antileg, system_types=[SystemType.VELIS], whe_types=[WheType.Evo2, WheType.Lydos, WheType.LydosHybrid, WheType.Andris2]),
]

ARISTON_SWITCH_TYPES: list[AristonSwitchEntityDescription] = [
    AristonSwitchEntityDescription(key=DeviceProperties.AUTOMATIC_THERMOREGULATION, name=f"{NAME} automatic thermoregulation", icon="mdi:radiator", device_features=[DeviceFeatures.AUTO_THERMO_REG], set_value=lambda e, v: e.device.async_set_automatic_thermoregulation(v), get_is_on=lambda e: e.device.automatic_thermoregulation, system_types=[SystemType.GALEVO]),
    AristonSwitchEntityDescription(key=DeviceProperties.IS_QUIET, name=f"{NAME} is quiet", icon="mdi:volume-off", entity_category=EntityCategory.CONFIG, device_features=[DeviceProperties.IS_QUIET], set_value=lambda e, v: e.device.async_set_is_quiet(v), get_is_on=lambda e: e.device.is_quiet_value, system_types=[SystemType.GALEVO]),
    AristonSwitchEntityDescription(key=EvoDeviceProperties.ECO, name=f"{NAME} eco mode", icon="mdi:leaf", set_value=lambda e, v: e.device.async_set_eco_mode(v), get_is_on=lambda e: e.device.water_heater_eco_value, system_types=[SystemType.VELIS], whe_types=[WheType.Lux, WheType.Evo, WheType.Evo2, WheType.Lydos, WheType.Andris2, WheType.Lux2]),
    AristonSwitchEntityDescription(key=EvoDeviceProperties.PWR_OPT, name=f"{NAME} power option", icon="mdi:leaf", set_value=lambda e, v: e.device.async_set_water_heater_power_option(v), get_is_on=lambda e: e.device.water_heater_power_option_value, system_types=[SystemType.VELIS], whe_types=[WheType.Lux2]),
    AristonSwitchEntityDescription(key=VelisDeviceProperties.ON, name=f"{NAME} power", icon="mdi:power", set_value=lambda e, v: e.device.async_set_power(v), get_is_on=lambda e: e.device.water_heater_power_value, system_types=[SystemType.VELIS]),
    AristonSwitchEntityDescription(key=MedDeviceSettings.MED_ANTILEGIONELLA_ON_OFF, name=f"{NAME} anti legionella", icon="mdi:bacteria-outline", entity_category=EntityCategory.CONFIG, set_value=lambda e, v: e.device.async_set_antilegionella(v), get_is_on=lambda e: e.device.water_anti_leg_value, system_types=[SystemType.VELIS], whe_types=[WheType.Andris2, WheType.Evo2, WheType.Lux, WheType.Lux2, WheType.Lydos, WheType.LydosHybrid, WheType.NuosSplit]),
    AristonSwitchEntityDescription(key=SlpDeviceSettings.SLP_PRE_HEATING_ON_OFF, name=f"{NAME} preheating", icon="mdi:heat-wave", entity_category=EntityCategory.CONFIG, set_value=lambda e, v: e.device.async_set_preheating(v), get_is_on=lambda e: e.device.water_heater_preheating_on_off, system_types=[SystemType.VELIS], whe_types=[WheType.NuosSplit]),
    AristonSwitchEntityDescription(key=NuosSplitProperties.BOOST_ON, name=f"{NAME} boost", icon="mdi:car-turbocharger", entity_category=EntityCategory.CONFIG, set_value=lambda e, v: e.device.async_set_water_heater_boost(v), get_is_on=lambda e: e.device.water_heater_boost, system_types=[SystemType.VELIS], whe_types=[WheType.NuosSplit]),
    AristonSwitchEntityDescription(key=SeDeviceSettings.SE_PERMANENT_BOOST_ON_OFF, name=f"{NAME} permanent boost", icon="mdi:car-turbocharger", entity_category=EntityCategory.CONFIG, set_value=lambda e, v: e.device.async_set_permanent_boost_value(v), get_is_on=lambda e: e.device.permanent_boost_value, system_types=[SystemType.VELIS], whe_types=[WheType.LydosHybrid]),
    AristonSwitchEntityDescription(key=SeDeviceSettings.SE_ANTI_COOLING_ON_OFF, name=f"{NAME} anti cooling", icon="mdi:snowflake-thermometer", entity_category=EntityCategory.CONFIG, set_value=lambda e, v: e.device.async_set_anti_cooling_value(v), get_is_on=lambda e: e.device.anti_cooling_value, system_types=[SystemType.VELIS], whe_types=[WheType.LydosHybrid]),
    AristonSwitchEntityDescription(key=SeDeviceSettings.SE_NIGHT_MODE_ON_OFF, name=f"{NAME} night mode", icon="mdi:weather-night", entity_category=EntityCategory.CONFIG, set_value=lambda e, v: e.device.async_set_night_mode_value(v), get_is_on=lambda e: e.device.night_mode_value, system_types=[SystemType.VELIS], whe_types=[WheType.LydosHybrid]),
]

ARISTON_NUMBER_TYPES: list[AristonNumberEntityDescription] = [
    AristonNumberEntityDescription(key=ConsumptionProperties.ELEC_COST, name=f"{NAME} elec cost", icon="mdi:currency-sign", entity_category=EntityCategory.CONFIG, native_min_value=0, native_max_value=sys.maxsize, native_step=0.01, device_features=[DeviceFeatures.HAS_METERING], coordinator=ENERGY_COORDINATOR, get_native_value=lambda e: e.device.elect_cost, set_native_value=lambda e, v: e.device.async_set_elect_cost(v), system_types=[SystemType.GALEVO]),
    AristonNumberEntityDescription(key=ConsumptionProperties.GAS_COST, name=f"{NAME} gas cost", icon="mdi:currency-sign", entity_category=EntityCategory.CONFIG, native_min_value=0, native_max_value=sys.maxsize, native_step=0.01, device_features=[DeviceFeatures.HAS_METERING], coordinator=ENERGY_COORDINATOR, get_native_value=lambda e: e.device.gas_cost, set_native_value=lambda e, v: e.device.async_set_gas_cost(v), system_types=[SystemType.GALEVO]),
    AristonNumberEntityDescription(key=MedDeviceSettings.MED_MAX_SETPOINT_TEMPERATURE, name=f"{NAME} max setpoint temperature", icon="mdi:thermometer-high", entity_category=EntityCategory.CONFIG, get_native_min_value=lambda e: e.device.water_heater_maximum_setpoint_temperature_minimum, get_native_max_value=lambda e: e.device.water_heater_maximum_setpoint_temperature_maximum, native_step=1, get_native_value=lambda e: e.device.water_heater_maximum_setpoint_temperature, set_native_value=lambda e, v: e.device.async_set_max_setpoint_temp(v), system_types=[SystemType.VELIS], whe_types=[WheType.Andris2, WheType.Evo2, WheType.Lux, WheType.Lux2, WheType.Lydos, WheType.LydosHybrid, WheType.NuosSplit]),
    AristonNumberEntityDescription(key=SlpDeviceSettings.SLP_MIN_SETPOINT_TEMPERATURE, name=f"{NAME} min setpoint temperature", icon="mdi:thermometer-low", entity_category=EntityCategory.CONFIG, get_native_min_value=lambda e: e.device.water_heater_minimum_setpoint_temperature_minimum, get_native_max_value=lambda e: e.device.water_heater_minimum_setpoint_temperature_maximum, native_step=1, get_native_value=lambda e: e.device.water_heater_minimum_setpoint_temperature, set_native_value=lambda e, v: e.device.async_set_min_setpoint_temp(v), system_types=[SystemType.VELIS], whe_types=[WheType.NuosSplit]),
    AristonNumberEntityDescription(key=NuosSplitProperties.REDUCED_TEMP, name=f"{NAME} reduced temperature", icon="mdi:thermometer-chevron-down", entity_category=EntityCategory.CONFIG, get_native_min_value=lambda e: e.device.water_heater_minimum_temperature, get_native_max_value=lambda e: e.device.water_heater_maximum_temperature, native_step=1, get_native_value=lambda e: e.device.water_heater_reduced_temperature, set_native_value=lambda e, v: e.device.async_set_water_heater_reduced_temperature(v), system_types=[SystemType.VELIS], whe_types=[WheType.NuosSplit]),
    AristonNumberEntityDescription(key=ThermostatProperties.HEATING_FLOW_TEMP, name=f"{NAME} heating flow temperature", icon="mdi:thermometer", native_unit_of_measurement=UnitOfTemperature.CELSIUS, entity_category=EntityCategory.CONFIG, zone=True, get_native_min_value=lambda e: e.device.get_heating_flow_temp_min(e.zone), get_native_max_value=lambda e: e.device.get_heating_flow_temp_max(e.zone), get_native_step=lambda e: e.device.get_heating_flow_temp_step(e.zone), get_native_value=lambda e: e.device.get_heating_flow_temp_value(e.zone), set_native_value=lambda e, v: e.device.async_set_heating_flow_temp(v, e.zone), system_types=[SystemType.GALEVO]),
    AristonNumberEntityDescription(key=ThermostatProperties.HEATING_FLOW_OFFSET, name=f"{NAME} heating flow offset", icon="mdi:progress-wrench", native_unit_of_measurement=UnitOfTemperature.CELSIUS, entity_category=EntityCategory.CONFIG, zone=True, get_native_min_value=lambda e: e.device.get_heating_flow_offset_min(e.zone), get_native_max_value=lambda e: e.device.get_heating_flow_offset_max(e.zone), get_native_step=lambda e: e.device.get_heating_flow_offset_step(e.zone), get_native_value=lambda e: e.device.get_heating_flow_offset_value(e.zone), set_native_value=lambda e, v: e.device.async_set_heating_flow_offset(v, e.zone), system_types=[SystemType.GALEVO]),
    AristonNumberEntityDescription(key=EvoOneDeviceProperties.AV_SHW, name=f"{NAME} requested number of showers", icon="mdi:shower-head", native_min_value=0, get_native_max_value=lambda e: e.device.max_req_shower, native_step=1, get_native_value=lambda e: e.device.req_shower, set_native_value=lambda e, v: e.device.async_set_water_heater_number_of_showers(int(v)), whe_types=[WheType.Evo]),
    AristonNumberEntityDescription(key=SeDeviceSettings.SE_ANTI_COOLING_TEMPERATURE, name=f"{NAME} anti cooling temperature", icon="mdi:thermometer-alert", entity_category=EntityCategory.CONFIG, get_native_min_value=lambda e: e.device.anti_cooling_temperature_minimum, get_native_max_value=lambda e: e.device.anti_cooling_temperature_maximum, native_step=1, get_native_value=lambda e: e.device.anti_cooling_temperature_value, set_native_value=lambda e, v: e.device.async_set_cooling_temperature_value(int(v)), whe_types=[WheType.LydosHybrid]),

    # ---- Editable gas calorific value ----
    # Displayed in the CONFIG category so it appears in the device settings UI.
    # Reading returns the *effective* value (custom override or gas-type default).
    # Writing stores a custom override for this device only.
    # The companion sensor "gas_calorific_value" in ARISTON_SENSOR_TYPES shows
    # the same effective value as a diagnostic sensor.
    AristonNumberEntityDescription(
        key="gas_calorific_value_input",
        name=f"{NAME} gas calorific value",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=f"{UnitOfEnergy.KILO_WATT_HOUR}/{UnitOfVolume.CUBIC_METERS}",
        # Practical range: 1–50 kWh/m³ covers all real gas types with headroom.
        native_min_value=1.0,
        native_max_value=50.0,
        native_step=0.1,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        # Returns the effective value (override if set, otherwise gas-type default)
        get_native_value=get_gas_calorific_value,
        # Stores the user's custom value, saves to disk, and refreshes sensors.
        set_native_value=_async_set_and_save_calorific_value,
        system_types=[SystemType.GALEVO],
    ),
]

ARISTON_SELECT_TYPES: list[AristonSelectEntityDescription] = [
    AristonSelectEntityDescription(key=ConsumptionProperties.CURRENCY, name=f"{NAME} currency", icon="mdi:cash-100", device_class=SensorDeviceClass.MONETARY, entity_category=EntityCategory.CONFIG, device_features=[DeviceFeatures.HAS_METERING], coordinator=ENERGY_COORDINATOR, get_current_option=lambda e: e.device.currency, get_options=lambda e: e.device.get_currencies(), select_option=lambda e, o: e.device.async_set_currency(o), system_types=[SystemType.GALEVO]),
    # Gas type: clears any custom calorific value override so the editable
    # number entity (and the sensor) immediately reflect the new gas type's
    # built-in default on the next coordinator refresh.
    AristonSelectEntityDescription(
        key=ConsumptionProperties.GAS_TYPE,
        name=f"{NAME} gas type",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        get_current_option=lambda e: e.device.gas_type,
        get_options=lambda e: e.device.get_gas_types(),
        # Clear the calorific override, save, then set the new gas type.
        select_option=_async_clear_and_set_gas_type,
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(key=ConsumptionProperties.GAS_ENERGY_UNIT, name=f"{NAME} gas energy unit", icon="mdi:cube-scan", entity_category=EntityCategory.CONFIG, device_features=[DeviceFeatures.HAS_METERING], coordinator=ENERGY_COORDINATOR, get_current_option=lambda e: e.device.gas_energy_unit, get_options=lambda e: e.device.get_gas_energy_units(), select_option=lambda e, o: e.device.async_set_gas_energy_unit(o), system_types=[SystemType.GALEVO]),
    AristonSelectEntityDescription(key=DeviceProperties.HYBRID_MODE, name=f"{NAME} hybrid mode", icon="mdi:cog", entity_category=EntityCategory.CONFIG, device_features=[DeviceFeatures.HYBRID_SYS], get_current_option=lambda e: e.device.hybrid_mode, get_options=lambda e: e.device.hybrid_mode_opt_texts, select_option=lambda e, o: e.device.async_set_hybrid_mode(o), system_types=[SystemType.GALEVO]),
    AristonSelectEntityDescription(key=DeviceProperties.BUFFER_CONTROL_MODE, name=f"{NAME} buffer control mode", icon="mdi:cup-water", entity_category=EntityCategory.CONFIG, device_features=[DeviceFeatures.BUFFER_TIME_PROG_AVAILABLE], get_current_option=lambda e: e.device.buffer_control_mode, get_options=lambda e: e.device.buffer_control_mode_opt_texts, select_option=lambda e, o: e.device.async_set_buffer_control_mode(o), system_types=[SystemType.GALEVO]),
    AristonSelectEntityDescription(key=EvoOneDeviceProperties.MODE, name=f"{NAME} operation mode", icon="mdi:cog", get_current_option=lambda e: e.device.water_heater_current_mode_text, get_options=lambda e: e.device.water_heater_mode_operation_texts, select_option=lambda e, o: e.device.async_set_water_heater_operation_mode(o), system_types=[SystemType.VELIS], whe_types=[WheType.Evo]),
]
