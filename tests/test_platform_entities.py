"""Tests for generic sensor, binary sensor, switch, number, and select entities."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ariston.const import (
    ConsumptionProperties,
    ConsumptionTimeInterval,
    ConsumptionType,
    CustomDeviceFeatures,
    DeviceProperties,
    MenuItemNames,
    ThermostatProperties,
)
from homeassistant.util import dt as dt_util

from custom_components.ariston.const import (
    ARISTON_NUMBER_TYPES,
    ARISTON_SENSOR_TYPES,
    MENU_ITEM_CH_FLOW_TEMP_BOILER,
    MENU_ITEM_DHW_FLOW_RATE,
    MENU_ITEM_GAS_POWER,
    MENU_ITEM_HP_WATER_FLOW_TEMP,
    MENU_ITEM_PUMP_MODULATION,
    AristonBinarySensorEntityDescription,
    AristonNumberEntityDescription,
    AristonSelectEntityDescription,
    AristonSensorEntityDescription,
    AristonSwitchEntityDescription,
)
from custom_components.ariston.binary_sensor import AristonBinarySensor
from custom_components.ariston.number import AristonNumber
from custom_components.ariston.select import AristonSelect
from custom_components.ariston.sensor import AristonSensor
from custom_components.ariston.switch import AristonSwitch


def test_binary_sensor_reads_its_description(coordinator, ariston_device):
    ariston_device.is_ready = True
    entity = AristonBinarySensor(
        coordinator,
        AristonBinarySensorEntityDescription(
            key="ready",
            get_is_on=lambda entity: entity.device.is_ready,
        ),
    )

    assert entity.is_on is True


async def test_switch_reads_and_sets_its_description(coordinator, ariston_device):
    ariston_device.is_enabled = False
    set_value = AsyncMock()
    entity = AristonSwitch(
        coordinator,
        AristonSwitchEntityDescription(
            key="enabled",
            get_is_on=lambda entity: entity.device.is_enabled,
            set_value=lambda entity, value: set_value(value),
        ),
    )

    assert entity.is_on is False
    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_turn_on()
        await entity.async_turn_off()

    assert [call.args for call in set_value.await_args_list] == [(True,), (False,)]
    assert write_state.call_count == 2


async def test_number_exposes_dynamic_limits_and_sets_value(
    coordinator, ariston_device
):
    ariston_device.minimum = "20"
    ariston_device.maximum = "80"
    ariston_device.step = "0.5"
    ariston_device.value = 24
    set_native_value = AsyncMock()
    entity = AristonNumber(
        coordinator,
        AristonNumberEntityDescription(
            key="temperature",
            native_min_value=0,
            native_max_value=100,
            native_step=1,
            get_native_value=lambda entity: entity.device.value,
            get_native_min_value=lambda entity: entity.device.minimum,
            get_native_max_value=lambda entity: entity.device.maximum,
            get_native_step=lambda entity: entity.device.step,
            set_native_value=lambda entity, value: set_native_value(value),
        ),
    )

    assert entity.native_value == 24
    assert entity.native_min_value == 20.0
    assert entity.native_max_value == 80.0
    assert entity.native_step == 0.5
    assert entity.native_min_value <= 26 <= entity.native_max_value
    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_set_native_value(26)

    set_native_value.assert_awaited_once_with(26)
    write_state.assert_called_once()


@pytest.mark.parametrize(
    "invalid_limit",
    [None, "invalid", float("nan"), float("inf"), float("-inf")],
)
def test_number_rejects_invalid_limits(coordinator, invalid_limit):
    entity = AristonNumber(
        coordinator,
        AristonNumberEntityDescription(
            key="invalid_limits",
            native_min_value=invalid_limit,
            native_max_value="80",
            native_step="0.5",
            get_native_value=lambda entity: 25,
            set_native_value=lambda entity, value: None,
        ),
    )

    assert entity.native_min_value is None
    assert entity.native_max_value == 80.0
    assert entity.native_step == 0.5


@pytest.mark.parametrize(
    ("cost_property", "setter_name"),
    [
        (ConsumptionProperties.ELEC_COST, "async_set_elect_cost"),
        (ConsumptionProperties.GAS_COST, "async_set_gas_cost"),
    ],
)
async def test_energy_cost_numbers_accept_four_decimal_places(
    coordinator, ariston_device, cost_property, setter_name
):
    description = next(
        description
        for description in ARISTON_NUMBER_TYPES
        if description.key == cost_property
    )
    setter = AsyncMock()
    setattr(ariston_device, setter_name, setter)
    entity = AristonNumber(coordinator, description)

    assert entity.native_step == 0.0001

    with patch.object(entity, "async_write_ha_state"):
        await entity.async_set_native_value(0.1036)

    setter.assert_awaited_once_with(0.1036)


def test_number_exposes_static_limits(coordinator):
    entity = AristonNumber(
        coordinator,
        AristonNumberEntityDescription(
            key="static",
            name="Static number",
            native_min_value=1,
            native_max_value=10,
            native_step=0.5,
            get_native_value=lambda entity: 5,
            set_native_value=lambda entity, value: None,
        ),
    )

    assert entity.name == "Static number"
    assert entity.native_min_value == 1
    assert entity.native_max_value == 10
    assert entity.native_step == 0.5


def test_dhw_total_energy_reports_daily_sum_and_reset_time(
    coordinator, ariston_device
):
    ariston_device.consumptions_sequences = [
        {
            "k": ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY.value,
            "p": ConsumptionTimeInterval.LAST_DAY.value,
            "v": [0.0, 0.72, 0.0, 1.15, 0.0],
        }
    ]
    ariston_device.consumption_sequence_last_changed_utc = datetime(
        2025, 1, 2, 11, tzinfo=timezone.utc
    )
    description = next(
        description
        for description in ARISTON_SENSOR_TYPES
        if description.key == "Domestic hot water total energy consumption"
    )
    entity = AristonSensor(coordinator, description)

    assert entity.native_value == 1.87
    assert entity.last_reset == dt_util.start_of_local_day()


def test_dhw_program_temperature_sensors_use_distinct_source_values(
    coordinator, ariston_device
):
    ariston_device.dhw_program_comfort_temp_value = 52.5
    ariston_device.dhw_program_comfort_temp_unit = "°C"
    ariston_device.dhw_program_economy_temp_value = 40.0
    ariston_device.dhw_program_economy_temp_unit = "°C"

    comfort = next(
        description
        for description in ARISTON_SENSOR_TYPES
        if description.key == DeviceProperties.DHW_TIMEPROG_COMFORT_TEMP
    )
    economy = next(
        description
        for description in ARISTON_SENSOR_TYPES
        if description.key == DeviceProperties.DHW_TIMEPROG_ECONOMY_TEMP
    )

    assert comfort.device_features == [
        CustomDeviceFeatures.HAS_DHW,
        DeviceProperties.DHW_TIMEPROG_COMFORT_TEMP,
    ]
    assert economy.device_features == [
        CustomDeviceFeatures.HAS_DHW,
        DeviceProperties.DHW_TIMEPROG_ECONOMY_TEMP,
    ]
    assert AristonSensor(coordinator, comfort).native_value == 52.5
    assert AristonSensor(coordinator, economy).native_value == 40.0
    assert AristonSensor(coordinator, comfort).native_unit_of_measurement == "°C"


def test_hybrid_menu_sensors_read_their_values_and_reported_units(
    coordinator, ariston_device
):
    values = {
        MENU_ITEM_HP_WATER_FLOW_TEMP: 28,
        MENU_ITEM_CH_FLOW_TEMP_BOILER: 49,
        MENU_ITEM_GAS_POWER: 0,
        MENU_ITEM_PUMP_MODULATION: 0,
        MENU_ITEM_DHW_FLOW_RATE: 3.2,
    }
    units = {
        MENU_ITEM_HP_WATER_FLOW_TEMP: "°C",
        MENU_ITEM_CH_FLOW_TEMP_BOILER: "°C",
        MENU_ITEM_GAS_POWER: "kW",
        MENU_ITEM_PUMP_MODULATION: "%",
        MENU_ITEM_DHW_FLOW_RATE: "l/min",
    }
    ariston_device.get_menu_item_value = lambda menu_item_id: values[menu_item_id]
    ariston_device.get_menu_item_unit = lambda menu_item_id: units[menu_item_id]

    for menu_item in values:
        description = next(
            description
            for description in ARISTON_SENSOR_TYPES
            if description.key == str(menu_item)
        )
        sensor = AristonSensor(coordinator, description)

        assert description.device_features == [str(menu_item)]
        assert sensor.native_value == values[menu_item]
        assert sensor.native_unit_of_measurement == units[menu_item]


@pytest.mark.parametrize(
    ("property_key", "getter_prefix", "setter_name", "quantity", "values"),
    [
        (
            ThermostatProperties.HEATING_FLOW_TEMP,
            "get_heating_flow_temp",
            "async_set_heating_flow_temp",
            "temperature",
            {1: 45.5, 2: 50, 3: 35},
        ),
        (
            ThermostatProperties.HEATING_FLOW_OFFSET,
            "get_heating_flow_offset",
            "async_set_heating_flow_offset",
            "offset",
            {1: -2, 2: 0, 3: 3.5},
        ),
    ],
)
async def test_flow_numbers_read_zone_values_and_set_values(
    coordinator, ariston_device, property_key, getter_prefix, setter_name, quantity, values
):
    get_value = MagicMock(side_effect=values.__getitem__)
    minimum = 20 if quantity == "temperature" else -20
    maximum = 80 if quantity == "temperature" else 20
    get_minimum = MagicMock(return_value=minimum)
    get_maximum = MagicMock(return_value=maximum)
    get_step = MagicMock(return_value=0.5)
    setter = AsyncMock()
    setattr(ariston_device, f"{getter_prefix}_value", get_value)
    setattr(ariston_device, f"{getter_prefix}_min", get_minimum)
    setattr(ariston_device, f"{getter_prefix}_max", get_maximum)
    setattr(ariston_device, f"{getter_prefix}_step", get_step)
    setattr(ariston_device, setter_name, setter)
    description = next(
        description
        for description in ARISTON_NUMBER_TYPES
        if description.key == property_key
    )

    for zone, value in values.items():
        entity = AristonNumber(coordinator, description, zone)

        assert entity.name == f"Ariston heating flow {quantity} {zone}"
        assert entity.unique_id == f"gateway-1-Ariston heating flow {quantity} {zone}-{zone}"
        assert entity.native_value == value
        assert entity.native_min_value == minimum
        assert entity.native_max_value == maximum
        assert entity.native_step == 0.5
        get_value.assert_called_with(zone)
        get_minimum.assert_called_with(zone)
        get_maximum.assert_called_with(zone)
        get_step.assert_called_with(zone)
        with patch.object(entity, "async_write_ha_state") as write_state:
            await entity.async_set_native_value(value + 0.5)

        setter.assert_awaited_with(value + 0.5, zone)
        write_state.assert_called_once()
    assert coordinator.async_request_refresh.await_count == len(values)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([42, 0, 0.0, 43, 0], [42, 42, 42, 43, 43]),
        ([0, 0.0, 41.5, 0], [None, None, 41.5, 41.5]),
        ([None, 0, 42, None, 0], [None, None, 42, None, 42]),
        ([0.1, 0, -0.1, 0], [0.1, 0.1, -0.1, -0.1]),
        ([42, "0", "0.0", " 0 ", 43], [42, 42, 42, 42, 43]),
        (["0", "41.5", "0.0", 42, 0], [None, "41.5", "41.5", 42, 42]),
        ([42, "invalid", 0], [42, "invalid", 42]),
        ([42, {}, 0], [42, {}, 42]),
        ([42, "NaN", 0], [42, None, 42]),
        ([42, float("inf"), 0], [42, None, 42]),
        ([42, float("-inf"), 0], [42, None, 42]),
        ([0], [None]),
        (["NaN"], [None]),
        ([float("inf")], [None]),
        ([float("-inf")], [None]),
    ],
)
def test_ch_return_temperature_ignores_zero_and_nonfinite_values(
    coordinator, ariston_device, values, expected
):
    description = next(
        description
        for description in ARISTON_SENSOR_TYPES
        if description.key == str(MenuItemNames.CH_RETURN_TEMP)
    )
    entity = AristonSensor(coordinator, description)

    assert entity.name == "Ariston CH return temp"
    assert entity.unique_id == "gateway-1-Ariston CH return temp"
    for value, expected_value in zip(values, expected, strict=True):
        ariston_device.ch_return_temp_value = value
        assert entity.native_value == expected_value
        assert entity.native_value == expected_value


def test_ch_return_temperature_cache_is_per_entity(coordinator, ariston_device):
    description = next(
        description
        for description in ARISTON_SENSOR_TYPES
        if description.key == str(MenuItemNames.CH_RETURN_TEMP)
    )
    first = AristonSensor(coordinator, description)
    second = AristonSensor(coordinator, description)
    ariston_device.ch_return_temp_value = 42
    assert first.native_value == 42

    ariston_device.ch_return_temp_value = 0
    assert first.native_value == 42
    assert second.native_value is None


def test_ch_flow_temperature_keeps_valid_zero(coordinator, ariston_device):
    description = next(
        description
        for description in ARISTON_SENSOR_TYPES
        if description.key == DeviceProperties.CH_FLOW_TEMP
    )
    entity = AristonSensor(coordinator, description)
    ariston_device.ch_flow_temp_value = 42
    assert entity.native_value == 42

    ariston_device.ch_flow_temp_value = 0
    assert entity.native_value == 0


async def test_select_exposes_options_and_selects_value(coordinator, ariston_device):
    ariston_device.option = "eco"
    select_option = AsyncMock()
    entity = AristonSelect(
        coordinator,
        AristonSelectEntityDescription(
            key="mode",
            get_current_option=lambda entity: entity.device.option,
            get_options=lambda entity: ["eco", "boost"],
            select_option=lambda entity, option: select_option(option),
        ),
    )

    assert entity.current_option == "eco"
    assert entity.options == ["eco", "boost"]
    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_select_option("boost")

    select_option.assert_awaited_once_with("boost")
    write_state.assert_called_once()


def test_sensor_reads_value_units_and_reset_time(coordinator, ariston_device):
    reset_time = datetime(2025, 1, 2, tzinfo=timezone.utc)
    ariston_device.temperature = 19.5
    entity = AristonSensor(
        coordinator,
        AristonSensorEntityDescription(
            key="temperature",
            native_unit_of_measurement="°C",
            get_native_value=lambda entity: entity.device.temperature,
            get_last_reset=lambda entity: reset_time,
        ),
    )

    assert entity.native_value == 19.5
    assert entity.native_unit_of_measurement == "°C"
    assert entity.last_reset == reset_time


def test_sensor_prefers_dynamic_unit_and_handles_optional_metadata(coordinator):
    entity = AristonSensor(
        coordinator,
        AristonSensorEntityDescription(
            key="temperature",
            native_unit_of_measurement="static-unit",
            get_native_value=lambda entity: None,
            get_native_unit_of_measurement=lambda entity: "dynamic-unit",
        ),
    )
    empty = AristonSensor(
        coordinator,
        AristonSensorEntityDescription(
            key="empty",
            get_native_value=lambda entity: None,
        ),
    )

    assert entity.native_unit_of_measurement == "dynamic-unit"
    assert entity.last_reset is None
    assert empty.native_unit_of_measurement is None
