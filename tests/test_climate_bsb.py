"""Tests for BSB zone presets and desiredRoomTemp normalization."""

from unittest.mock import AsyncMock, patch

import pytest

from ariston.const import BsbZoneMode
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.const import ATTR_TEMPERATURE

from custom_components.ariston.climate import AristonThermostat, _normalize_temp
from custom_components.aroiston.const import ARISTON_CLIMATE_TYPES

ZONE = 1
COMFORT = {"value": 21.0, "min": 15.0, "max": 25.0, "step": 0.5}
REDUCED = {"value": 18.0, "min": 10.0, "max": 18.0, "step": 0.5}
MISSING = object()

@pytest.fixture
def bsb_device(ariston_device):
    """Turn the shared fake device into a BSB device with zone data."""
    zone = {"chComfTemp": dict(COMFORT), "chRedTemp": dict(REDUCED)}
    ariston_device.zone_data = zone
    ariston_device.plant_mode_supported = False
    ariston_device.get_zone = lambda z: zone
    ariston_device.get_zone_ch_comf_temp = lambda z: zone["chComfTemp"]
    ariston_device.get_zone_ch_red_temp = lambda z: zone["chRedTemp"]
    ariston_device.get_zone_mode = lambda z: BsbZoneMode.UNDEFINED
    ariston_device.get_zone_mode_options = lambda z: [0, 1, 2, 3]
    ariston_device.get_target_temp_value = lambda z: COMFORT["value"]
    ariston_device.get_comfort_temp_min = lambda z: COMFORT["min"]
    ariston_device.get_comfort_temp_max = lambda z: COMFORT["max"]
    ariston_device.get_target_temp_step = lambda z: COMFORT["step"]
    ariston_device.get_reduced_temp_min = lambda z: REDUCED["min"]
    ariston_device.get_reduced_temp_max = lambda z: REDUCED["max"]
    ariston_device.get_reduced_temp_step = lambda z: REDUCED["step"]
    ariston_device.async_set_comfort_temp = AsyncMock()
    ariston_device.async_set_reduced_temp = AsyncMock()
    ariston_device.async_set_zone_mode = AsyncMock()
    return ariston_device

@pytest.fixture
def make_entity(coordinator, bsb_device):
    """Build a thernmostat, optionally setting desiredRoomTemp."""

    def _make(desired=MISSING):
        if desired is not MISSING:
            bsb_device.zone_data["desiredRoomTemp"] = desired
        return AristonThermostat(ZONE, coordinator, ARISTON_CLIMATE_TYPES[0])

    return _make



# --- _normalize_temp() --------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (18, 18.0),
        (18.5, 18.5),
        ("18.5", 18.5),
        ({"value": 18}, 18.0),
        ({"value": 18.5, "min": 10}, 18.5),
        ({"value": "21"}, 21.0),
        (None, None),
        ({}, None),
        ({"value": None}, None),
        ("abc", None),
        ([18], None)
        (True, None)
        (float("nan"), None),
        (float("inf"), None),
    ],
)
def test_normalize_temp(raw, expected):
    assert _normalize_temp(raw) == expected



# --- native_target_temperature --------------------------------------------------------------



@pytest.mark.parametrize(
    ("desired", "expected"),
    [(19.5, 19.5), (19, 19.0), ({"value": 19.5}, 19.5), ({"value": 18}, 18.0)]
)
def test_target_uses_normalized_desired(make_entity, desired, expected):
    result = make_entity(desired).native_target_temperature
    assert result == expected
    assert isinstance(result, float)


def test_target_ignores_desired_for_plant_devices(make_entity, bsb_device):
    bsb_device.plant_mode_supported = True
    assert make_entity(19.5).native_target_temperature == COMFORT["value"]



# --- _is_bsb_currently_reduced --------------------------------------------------------------



@pytest.mark.parametrize("desired", [18, 18.0, "18", {"value": 18}, 18.0000001])
def test_target_falls_back(make_entity, desired):
    assert make_entity(desired)._is_bsb_currently_reduced() is True


@pytest.mark.parametrize(
    "desired", [21.0, {"value": 21.0}, 18.5, MISSING, None, "abc"]
)
def test_is_reduced_false(make_entity, desired):
    assert make_entity(desired)._is_bsb_currently_reduced() is False


def test_is_reduced_false_when_reduced_value_missing(make_entity, bsb_device):
    bsb_device.zone_data["chRedTemp"] = {}
    assert make_entity(18.0)._is_bsb_currently_reduced() is False


def test_comfort_wins_when_setpoint_equals(make_entity, bsb_device):
    bsb_device.zone_data["chComfTemp"]["value"] = REDUCED["value"]
    assert make_entity(18.0)._is_bsb_currently_reduced() is False


# --- slider bounds follow the active setpoint -----------------------------------------------
@pytest.mark.parametrize(
    ("desired", "limits"),
    [
        (18.0, REDUCED),
        ({"value": 18.0}, REDUCED),
        (21.0, COMFORT),
        ({"value": 21.0}, COMFORT),
    ],
)
def test_bounds_follow_active_setpoint(make_entity, desired, limits):
    entity = make_entity(desired)
    assert entity.min_temp == limits["min"]
    assert entity.max_temp == limits["max"]
    assert entity.target_temperature_step == limits["step"]


# --- async_set_temperature writes the active setpoint ---------------------------------------



@pytest.mark.parametrize(
    ("desired", "setter", "other")
    [
        (18.0, "async_set_reduced_temp", "async_set_comfort_temp"),
        ({"value": 18.0}, "async_set_reduced_temp", "async_set_comfort_temp"),
        (21.0, "async_set_comfort_temp", "async_set_reduced_temp"),
    ]
)
async def test_set_temperature_targets_active_setpoint(
    make_entity, bsb_device, coordinator, desired, setter, other
):
    entity = make_entity(desired)
    with patch.object(entity, "async_write_ha_state"):
        await entity.async_set_temperature(**{ATTR_TEMPERATURE: 17.0})

    getattr(bsb_device, setter).assert_awaited_once_with(17.0, ZONE)
    getattr(bsb_device, other).assert_not_awaited()
    coordinator.async_set_updated_data.assert_awaited_once()


# --- BSB presets ----------------------------------------------------------------------------



def test_bsb_supports_preset_mode(make_entity):
    assert make_entity(18.0).supported_features & ClimateEntityFeature.PRESET_MODE


@pytest.mark.parametrize(
    ("mode", "expected"),
    [(0, "protection"), (1, "automatic"), (2, "reduced"), (3, "comfort")],
)
def test_preset_mode_maps_zone_mode(make_entity, bsb_device, mode, expected):
    # mode 0 covers the workaround for the upstream `value or UNDEFINED` bug
    bsb_device.zone_data["mode"] = {"value": mode}
    assert make_entity().preset_mode == expected


def test_preset_mode_undefined_when_mode_missing(make_entity):
    assert make_entity().preset_mode == str(BsbZoneMode.UNDEFINED.value)


def test_preset_modes_lists_allowed_options(make_entity):
    assert make_entity().preset_modes == [
        "protection",
        "automatic",
        "reduced",
        "comfort"
    ]


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        ("protection", BsbZoneMode.OFF),
        ("automatic", BsbZoneMode.TIME_PROGRAM),
        ("reduced", BsbZoneMode.MANUAL_NIGHT),
        ("comfort", BsbZoneMode.MANUAL),
    ],
)
async def test_set_bsb_preset_mode(
    make_entity, bsb_device, coordinator, preset, expected
):
    entity = make_entity()
    with patch.object(entity, "async_write_ha_state"):
        await entity.async_set_preset_mode(preset)

    bsb_device.async_set_zone_mode.assert_awaited_once_with(expected, ZONE)
    coordinator.async_request_refresh.assert_awaited_once()


async def test_set_bsb_preset_mode_rejects_unknown(make_entity, bsb_device):
    entity = make_entity()
    with patch.object(entity, "async_write_ha_state"):
        await entity.async_set_preset_mode("turbo")

    bsb_device.async_set_zone_mode.assert_not_awaited()