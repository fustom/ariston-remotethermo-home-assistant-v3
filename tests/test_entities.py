"""Tests for shared entity metadata and climate/water-heater behavior."""

from unittest.mock import AsyncMock, patch

import pytest

from ariston.const import SystemType, WheType
from homeassistant.components.climate import HVACAction
from homeassistant.components.water_heater import WaterHeaterEntityFeature
from homeassistant.const import ATTR_TEMPERATURE

from custom_components.ariston.climate import AristonThermostat
from custom_components.ariston.const import (
    ARISTON_CLIMATE_TYPES,
    ARISTON_WATER_HEATER_TYPES,
    EXTRA_STATE_ATTRIBUTE,
    EXTRA_STATE_DEVICE_METHOD,
    AristonBaseEntityDescription,
)
from custom_components.ariston.entity import AristonEntity
from custom_components.ariston.water_heater import AristonWaterHeater


def test_entity_identity_device_info_and_model(coordinator, ariston_device):
    entity = AristonEntity(coordinator, AristonBaseEntityDescription(key="test"), 2)

    assert entity.unique_id == "gateway-1-Test boiler-2"
    assert entity.model == SystemType.GALEVO.name
    assert entity.device_info["identifiers"] == {("ariston", "serial-1")}
    assert entity.device_info["manufacturer"] == "ariston"
    assert entity.device_info["name"] == "Test boiler"

    ariston_device.whe_type = WheType.Lux
    assert entity.model == f"{SystemType.GALEVO.name} {WheType.Lux.name}"
    ariston_device.whe_model_type = 42
    assert entity.model.endswith("| Model 42")


def test_entity_extra_attributes_omit_none_values(coordinator, ariston_device):
    ariston_device.example_attribute = "available"
    description = AristonBaseEntityDescription(
        key="test",
        extra_states=[
            {
                EXTRA_STATE_ATTRIBUTE: "present",
                EXTRA_STATE_DEVICE_METHOD: lambda entity: entity.device.example_attribute,
            },
            {
                EXTRA_STATE_ATTRIBUTE: "missing",
                EXTRA_STATE_DEVICE_METHOD: lambda entity: None,
            },
            {EXTRA_STATE_ATTRIBUTE: "no callback"},
        ],
    )
    entity = AristonEntity(coordinator, description)

    assert entity.extra_state_attributes == {"present": "available"}
    assert AristonEntity(
        coordinator, AristonBaseEntityDescription(key="empty")
    ).extra_state_attributes is None


@pytest.mark.parametrize(
    ("heating", "cooling", "flame", "pump", "expected"),
    [
        (False, False, False, False, HVACAction.OFF),
        (True, False, False, False, HVACAction.IDLE),
        (True, False, True, False, HVACAction.HEATING),
        (False, True, False, False, HVACAction.IDLE),
        (False, True, False, True, HVACAction.COOLING),
    ],
)
def test_climate_hvac_action_reflects_heat_pump_activity(
    coordinator, ariston_device, heating, cooling, flame, pump, expected
):
    ariston_device.is_plant_in_heat_mode = heating
    ariston_device.is_plant_in_cool_mode = cooling
    ariston_device.is_flame_on_value = flame
    ariston_device.is_heating_pump_on_value = pump
    entity = AristonThermostat(1, coordinator, ARISTON_CLIMATE_TYPES[0])

    assert entity.hvac_action is expected


async def test_climate_temperature_requires_value_and_updates_device(
    coordinator, ariston_device
):
    ariston_device.async_set_comfort_temp = AsyncMock()
    entity = AristonThermostat(1, coordinator, ARISTON_CLIMATE_TYPES[0])

    with pytest.raises(ValueError, match=ATTR_TEMPERATURE):
        await entity.async_set_temperature()

    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_set_temperature(**{ATTR_TEMPERATURE: 21.5})

    ariston_device.async_set_comfort_temp.assert_awaited_once_with(21.5, 1)
    write_state.assert_called_once()


def test_water_heater_properties_and_supported_features(coordinator, ariston_device):
    ariston_device.water_heater_current_temperature = 45
    ariston_device.water_heater_minimum_temperature = 30
    ariston_device.water_heater_target_temperature = 55
    ariston_device.water_heater_maximum_temperature = 70
    ariston_device.water_heater_temperature_decimals = 1
    ariston_device.water_heater_temperature_unit = "°C"
    ariston_device.dhw_mode_changeable = True
    ariston_device.system_type = SystemType.VELIS
    entity = AristonWaterHeater(coordinator, ARISTON_WATER_HEATER_TYPES[0])

    assert entity.current_temperature == 45
    assert entity.min_temp == 30
    assert entity.target_temperature == 55
    assert entity.max_temp == 70
    assert entity.precision == 0.1
    assert entity.temperature_unit == "°C"
    expected_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )
    if "ON_OFF" in WaterHeaterEntityFeature.__members__:
        expected_features |= WaterHeaterEntityFeature.ON_OFF
    assert entity.supported_features == expected_features


@pytest.mark.parametrize("temperature", [None, 50])
async def test_water_heater_temperature_command(coordinator, ariston_device, temperature):
    ariston_device.async_set_water_heater_temperature = AsyncMock()
    entity = AristonWaterHeater(coordinator, ARISTON_WATER_HEATER_TYPES[0])

    if temperature is None:
        with pytest.raises(ValueError, match=ATTR_TEMPERATURE):
            await entity.async_set_temperature()
        ariston_device.async_set_water_heater_temperature.assert_not_awaited()
        return

    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_set_temperature(**{ATTR_TEMPERATURE: temperature})

    ariston_device.async_set_water_heater_temperature.assert_awaited_once_with(
        temperature
    )
    write_state.assert_called_once()


@pytest.mark.parametrize(
    ("method", "power"),
    [("async_turn_on", True), ("async_turn_off", False)],
)
async def test_water_heater_power_commands(coordinator, ariston_device, method, power):
    ariston_device.async_set_power = AsyncMock()
    entity = AristonWaterHeater(coordinator, ARISTON_WATER_HEATER_TYPES[0])

    await getattr(entity, method)()

    ariston_device.async_set_power.assert_awaited_once_with(power)
