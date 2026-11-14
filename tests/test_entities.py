"""Tests for shared entity metadata and climate/water-heater behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ariston.const import BsbZoneMode, PlantMode, SystemType, WheType, ZoneMode
from homeassistant.components.climate import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
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


def test_climate_properties_and_supported_modes(coordinator, ariston_device):
    ariston_device.get_measured_temp_unit = lambda zone: "°C"
    ariston_device.get_measured_temp_decimals = lambda zone: 1
    ariston_device.get_comfort_temp_min = lambda zone: 5
    ariston_device.get_comfort_temp_max = lambda zone: 30
    ariston_device.get_target_temp_step = lambda zone: 0.5
    ariston_device.get_measured_temp_value = lambda zone: 19.5
    ariston_device.get_target_temp_value = lambda zone: 20
    ariston_device.plant_mode_supported = True
    ariston_device.is_plant_in_heat_mode = True
    ariston_device.is_plant_in_cool_mode = False
    ariston_device.is_zone_in_manual_mode = lambda zone: True
    ariston_device.is_zone_mode_options_contains_manual = lambda zone: True
    ariston_device.is_plant_mode_options_contains_cooling = True
    ariston_device.is_zone_mode_options_contains_time_program = lambda zone: True
    ariston_device.is_zone_mode_options_contains_off = lambda zone: True
    ariston_device.plant_mode_text = "winter"
    ariston_device.plant_mode_opt_texts = ["winter", "summer"]
    entity = AristonThermostat(1, coordinator, ARISTON_CLIMATE_TYPES[0])

    assert entity.name == "Test boiler"
    assert entity.unique_id == "gateway-1_1"
    assert entity.icon == "mdi:radiator"
    assert entity.temperature_unit == "°C"
    assert entity.precision == 0.1
    assert entity.min_temp == 5
    assert entity.max_temp == 30
    assert entity.target_temperature_step == 0.5
    assert entity.current_temperature == 19.5
    assert entity.target_temperature == 20
    assert entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert entity.supported_features & ClimateEntityFeature.PRESET_MODE
    assert entity.hvac_mode == HVACMode.HEAT
    assert entity.hvac_modes == [
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.AUTO,
        HVACMode.OFF,
    ]
    assert entity.preset_mode == "winter"
    assert entity.preset_modes == ["winter", "summer"]
    ariston_device.is_plant_in_heat_mode = False
    assert entity.icon == "mdi:radiator-off"


@pytest.mark.parametrize(
    ("heating", "cooling", "manual", "time_program", "expected"),
    [
        (True, False, False, True, HVACMode.AUTO),
        (False, True, True, False, HVACMode.COOL),
        (False, True, False, True, HVACMode.AUTO),
        (False, False, False, False, HVACMode.OFF),
    ],
)
def test_climate_hvac_mode_reflects_plant_and_zone_state(
    coordinator, ariston_device, heating, cooling, manual, time_program, expected
):
    ariston_device.is_plant_in_heat_mode = heating
    ariston_device.is_plant_in_cool_mode = cooling
    ariston_device.is_zone_in_manual_mode = lambda zone: manual
    ariston_device.is_zone_in_time_program_mode = lambda zone: time_program
    entity = AristonThermostat(1, coordinator, ARISTON_CLIMATE_TYPES[0])

    assert entity.hvac_mode == expected


@pytest.mark.parametrize(
    (
        "hvac_mode",
        "current_mode",
        "plant_modes",
        "zone_modes",
        "off_supported",
        "expected_plant_modes",
        "expected_zone_modes",
    ),
    [
        (
            HVACMode.OFF,
            PlantMode.SUMMER,
            [],
            [],
            True,
            [PlantMode.OFF],
            [],
        ),
        (
            HVACMode.OFF,
            PlantMode.SUMMER,
            [],
            [],
            False,
            [PlantMode.SUMMER],
            [],
        ),
        (
            HVACMode.AUTO,
            PlantMode.SUMMER,
            [],
            [ZoneMode.MANUAL_NIGHT],
            False,
            [PlantMode.WINTER],
            [(ZoneMode.TIME_PROGRAM, 1)],
        ),
        (
            HVACMode.AUTO,
            PlantMode.WINTER,
            [],
            [],
            False,
            [],
            [(ZoneMode.TIME_PROGRAM, 1)],
        ),
        (
            HVACMode.AUTO,
            PlantMode.OFF,
            [PlantMode.HEATING_ONLY],
            [],
            False,
            [PlantMode.HEATING_ONLY],
            [(ZoneMode.TIME_PROGRAM, 1)],
        ),
        (
            HVACMode.AUTO,
            PlantMode.OFF,
            [],
            [],
            False,
            [PlantMode.WINTER],
            [(ZoneMode.TIME_PROGRAM, 1)],
        ),
        (
            HVACMode.HEAT,
            PlantMode.OFF,
            [PlantMode.HEATING_ONLY],
            [ZoneMode.MANUAL_NIGHT],
            False,
            [PlantMode.HEATING_ONLY],
            [(ZoneMode.MANUAL_NIGHT, 1)],
        ),
        (
            HVACMode.HEAT,
            PlantMode.WINTER,
            [],
            [],
            False,
            [],
            [(ZoneMode.MANUAL, 1)],
        ),
        (
            HVACMode.HEAT,
            PlantMode.SUMMER,
            [],
            [],
            False,
            [PlantMode.WINTER],
            [(ZoneMode.MANUAL, 1)],
        ),
        (
            HVACMode.COOL,
            PlantMode.WINTER,
            [],
            [],
            False,
            [PlantMode.COOLING],
            [(ZoneMode.MANUAL, 1)],
        ),
        (
            HVACMode.COOL,
            PlantMode.WINTER,
            [],
            [ZoneMode.MANUAL_NIGHT],
            False,
            [PlantMode.COOLING],
            [(ZoneMode.MANUAL_NIGHT, 1)],
        ),
    ],
)
async def test_climate_sets_heat_pump_modes(
    coordinator,
    ariston_device,
    hvac_mode,
    current_mode,
    plant_modes,
    zone_modes,
    off_supported,
    expected_plant_modes,
    expected_zone_modes,
):
    ariston_device.plant_mode_supported = True
    ariston_device.plant_mode = current_mode
    ariston_device.plant_mode_options = plant_modes
    ariston_device.get_zone_mode_options = MagicMock(return_value=zone_modes)
    ariston_device.is_plant_mode_options_contains_off = off_supported
    ariston_device.async_set_plant_mode = AsyncMock()
    ariston_device.async_set_zone_mode = AsyncMock()
    entity = AristonThermostat(1, coordinator, ARISTON_CLIMATE_TYPES[0])

    with patch.object(entity, "async_write_ha_state"):
        await entity.async_set_hvac_mode(hvac_mode)

    plant_mode_calls = [
        call.args[0] for call in ariston_device.async_set_plant_mode.await_args_list
    ]
    zone_mode_calls = [
        call.args for call in ariston_device.async_set_zone_mode.await_args_list
    ]
    assert plant_mode_calls == expected_plant_modes
    assert zone_mode_calls == expected_zone_modes


@pytest.mark.parametrize(
    ("hvac_mode", "expected_mode"),
    [
        (HVACMode.OFF, BsbZoneMode.OFF),
        (HVACMode.AUTO, BsbZoneMode.TIME_PROGRAM),
        (HVACMode.HEAT, BsbZoneMode.MANUAL),
    ],
)
async def test_climate_sets_bsb_modes(
    coordinator, ariston_device, hvac_mode, expected_mode
):
    ariston_device.plant_mode_supported = False
    ariston_device.async_set_zone_mode = AsyncMock()
    entity = AristonThermostat(1, coordinator, ARISTON_CLIMATE_TYPES[0])

    with patch.object(entity, "async_write_ha_state"):
        await entity.async_set_hvac_mode(hvac_mode)

    ariston_device.async_set_zone_mode.assert_awaited_once_with(expected_mode, 1)
    assert not entity.supported_features & ClimateEntityFeature.PRESET_MODE


@pytest.mark.parametrize(
    (
        "preset",
        "current_cool",
        "zone_modes",
        "zone_off_supported",
        "expected_zone_modes",
    ),
    [
        (
            "off",
            True,
            [ZoneMode.MANUAL],
            True,
            [(ZoneMode.MANUAL, 1), (BsbZoneMode.OFF, 1)],
        ),
        ("cooling", True, [ZoneMode.MANUAL], False, []),
        ("winter", False, [], False, []),
    ],
)
async def test_climate_sets_preset_mode(
    coordinator,
    ariston_device,
    preset,
    current_cool,
    zone_modes,
    zone_off_supported,
    expected_zone_modes,
):
    ariston_device.plant_mode_opt_texts = ["off", "winter", "cooling"]
    ariston_device.plant_mode_options = [
        PlantMode.OFF,
        PlantMode.WINTER,
        PlantMode.COOLING,
    ]
    ariston_device.is_plant_in_cool_mode = current_cool
    ariston_device.get_zone_mode_options = MagicMock(return_value=zone_modes)
    ariston_device.is_zone_mode_options_contains_off = (
        lambda zone: zone_off_supported
    )
    ariston_device.async_set_plant_mode = AsyncMock()
    ariston_device.async_set_zone_mode = AsyncMock()
    entity = AristonThermostat(1, coordinator, ARISTON_CLIMATE_TYPES[0])

    with patch.object(entity, "async_write_ha_state"):
        await entity.async_set_preset_mode(preset)

    preset_index = ariston_device.plant_mode_opt_texts.index(preset)
    assert ariston_device.async_set_plant_mode.await_args.args == (
        ariston_device.plant_mode_options[preset_index],
    )
    zone_mode_calls = [
        call.args for call in ariston_device.async_set_zone_mode.await_args_list
    ]
    assert zone_mode_calls == expected_zone_modes


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
    assert entity.name == "Test boiler"
    assert entity.unique_id == "gateway-1-water_heater"
    assert entity.icon == "mdi:water-pump"
    expected_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )
    if "ON_OFF" in WaterHeaterEntityFeature.__members__:
        expected_features |= WaterHeaterEntityFeature.ON_OFF
    assert entity.supported_features == expected_features
    ariston_device.water_heater_mode_operation_texts = ["eco", "boost"]
    ariston_device.water_heater_current_mode_text = "eco"
    assert entity.operation_list == ["eco", "boost"]
    assert entity.current_operation == "eco"


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

    with patch.object(entity, "async_write_ha_state"):
        await getattr(entity, method)()

    ariston_device.async_set_power.assert_awaited_once_with(power)


async def test_water_heater_sets_operation_mode(coordinator, ariston_device):
    ariston_device.async_set_water_heater_operation_mode = AsyncMock()
    entity = AristonWaterHeater(coordinator, ARISTON_WATER_HEATER_TYPES[0])

    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_set_operation_mode("boost")

    ariston_device.async_set_water_heater_operation_mode.assert_awaited_once_with(
        "boost"
    )
    write_state.assert_called_once()
