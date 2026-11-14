"""Tests for generic sensor, binary sensor, switch, number, and select entities."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from custom_components.ariston.const import (
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
