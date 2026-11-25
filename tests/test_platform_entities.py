"""Tests for generic sensor, binary sensor, switch, number, and select entities."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from ariston.const import (
    ConsumptionProperties,
    ConsumptionTimeInterval,
    ConsumptionType,
    CustomDeviceFeatures,
    DeviceProperties,
)

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
from custom_components.ariston.energy import period_last_reset
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
    ariston_device.minimum = 5
    ariston_device.maximum = 80
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
            set_native_value=lambda entity, value: set_native_value(value),
        ),
    )

    assert entity.native_value == 24
    assert entity.native_min_value == 5
    assert entity.native_max_value == 80
    assert entity.native_step == 1
    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_set_native_value(26)

    set_native_value.assert_awaited_once_with(26)
    write_state.assert_called_once()


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
    # last_reset is anchored to local midnight, matching the sum's cut-off.
    assert entity.last_reset == period_last_reset(ConsumptionTimeInterval.LAST_DAY)


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


def test_heat_pump_menu_entities_read_device_values(coordinator, ariston_device):
    from ariston.const import MenuItemNames
    from custom_components.ariston.const import (
        ARISTON_BINARY_SENSOR_TYPES,
        MENU_ITEM_CH_BACKUP_RESISTANCE_1,
        MENU_ITEM_HP_MODE,
        MENU_ITEM_HP_OUTSIDE_AIR_TEMP,
    )

    ariston_device.get_menu_item_value = (
        lambda menu_item_id: -2.0
        if menu_item_id == MENU_ITEM_HP_OUTSIDE_AIR_TEMP
        else None
    )
    ariston_device.get_menu_item_unit = (
        lambda menu_item_id: "°C"
        if menu_item_id == MENU_ITEM_HP_OUTSIDE_AIR_TEMP
        else None
    )
    ariston_device.hp_mode_value = "Heating"
    ariston_device.ch_backup_resistance_1_value = True

    sensor_by_key = {desc.key: desc for desc in ARISTON_SENSOR_TYPES}
    assert sensor_by_key[str(MenuItemNames.CH_RETURN_TEMP)].device_features == [
        str(MenuItemNames.CH_RETURN_TEMP.value)
    ]

    hp_outside = AristonSensor(
        coordinator, sensor_by_key[str(MENU_ITEM_HP_OUTSIDE_AIR_TEMP)]
    )
    hp_mode = AristonSensor(coordinator, sensor_by_key[str(MENU_ITEM_HP_MODE)])

    assert hp_outside.native_value == -2.0
    assert hp_outside.native_unit_of_measurement == "°C"
    assert hp_mode.native_value == "Heating"

    backup_desc = next(
        desc
        for desc in ARISTON_BINARY_SENSOR_TYPES
        if desc.key == str(MENU_ITEM_CH_BACKUP_RESISTANCE_1)
    )
    assert backup_desc.device_features == [str(MENU_ITEM_CH_BACKUP_RESISTANCE_1)]
    backup_entity = AristonBinarySensor(coordinator, backup_desc)
    assert backup_entity.is_on is True
