"""Tests for the NuosSplit heat pump state entities (hpState)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ariston.ariston_api import ConnectionException
from ariston.const import (
    DeviceAttribute,
    EvoLydosDeviceProperties,
    NuosSplitProperties,
    SystemType,
    VelisDeviceAttribute,
    WheType,
)
from ariston.lydos_device import AristonLydosDevice
from ariston.nuos_split_device import AristonNuosSplitDevice
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass

from custom_components.ariston.binary_sensor import AristonBinarySensor
from custom_components.ariston.const import (
    ARISTON_BINARY_SENSOR_TYPES,
    ARISTON_SENSOR_TYPES,
    ATTR_RAW_HP_STATE,
    DEVICE_FEATURE_HP_HEATING,
)
from custom_components.ariston.coordinator import DeviceDataUpdateCoordinator
from custom_components.ariston.entity import is_entity_description_available
from custom_components.ariston.sensor import AristonSensor

# Sanitized: no real gateway ID.
PLANT = {
    "gw": "GATEWAY",
    "on": True,
    "mode": 2,
    "waterTemp": 57.0,
    "comfortTemp": 62.0,
    "reducedTemp": 40.0,
    "procReqTemp": 62.0,
    "opMode": 0,
    "holidayUntil": None,
    "boostOn": False,
    "hpState": 1,
}

STATE_DESC = next(
    d for d in ARISTON_SENSOR_TYPES if d.key == NuosSplitProperties.HP_STATE
)
HEATING_DESC = next(
    d for d in ARISTON_BINARY_SENSOR_TYPES if d.key == DEVICE_FEATURE_HP_HEATING
)
IS_HEATING_DESC = next(
    d for d in ARISTON_BINARY_SENSOR_TYPES if d.key == EvoLydosDeviceProperties.HEAT_REQ
)


def _attributes(whe_type: WheType) -> dict:
    return {
        DeviceAttribute.GW: "GATEWAY",
        DeviceAttribute.SYS: SystemType.VELIS.value,
        VelisDeviceAttribute.WHE_TYPE: whe_type.value,
    }


@pytest.fixture
def api():
    api = MagicMock()
    api.async_get_velis_plant_data = AsyncMock(return_value=dict(PLANT))
    return api


@pytest.fixture
async def nuos(hass, api):
    device = AristonNuosSplitDevice(api, _attributes(WheType.NuosSplit))
    coordinator = DeviceDataUpdateCoordinator(
        hass, device, 300, "test", device.async_update_state
    )
    await coordinator.async_refresh()
    yield (
        api,
        coordinator,
        AristonSensor(coordinator, STATE_DESC),
        AristonBinarySensor(coordinator, HEATING_DESC),
    )
    await coordinator.async_shutdown()


def test_descriptions():
    assert STATE_DESC.device_class is SensorDeviceClass.ENUM
    assert STATE_DESC.options == [
        "lockout",
        "idle",
        "heating",
        "antilegionella",
        "antifreeze",
    ]
    assert HEATING_DESC.device_class is BinarySensorDeviceClass.RUNNING


@pytest.mark.parametrize(
    ("raw", "state", "heating"),
    [
        (0, "lockout", False),
        (1, "idle", False),
        (2, "heating", True),
        (3, "antilegionella", None),
        (4, "antifreeze", None),
        (99, None, None),
        (None, None, None),
    ],
)
async def test_mapping(nuos, raw, state, heating):
    api, coordinator, state_sensor, heating_sensor = nuos
    api.async_get_velis_plant_data.return_value = dict(PLANT, hpState=raw)
    await coordinator.async_refresh()

    assert state_sensor.native_value == state
    assert heating_sensor.is_on is heating
    attrs = state_sensor.extra_state_attributes
    assert attrs == ({} if raw is None else {ATTR_RAW_HP_STATE: raw})


async def test_missing_field_is_unknown(nuos):
    api, coordinator, state_sensor, heating_sensor = nuos
    plant = dict(PLANT)
    del plant["hpState"]
    api.async_get_velis_plant_data.return_value = plant
    await coordinator.async_refresh()

    assert state_sensor.native_value is None
    assert heating_sensor.is_on is None


async def test_transitions_follow_refreshes_without_extra_calls(nuos):
    api, coordinator, _, heating_sensor = nuos
    api.async_get_velis_plant_data.reset_mock()

    seen = []
    for raw in (2, 1, 2):
        api.async_get_velis_plant_data.return_value = dict(PLANT, hpState=raw)
        await coordinator.async_refresh()
        seen.append(heating_sensor.is_on)

    assert seen == [True, False, True]
    assert api.async_get_velis_plant_data.await_count == 3


async def test_failed_refresh_is_unavailable_then_recovers(nuos):
    api, coordinator, state_sensor, heating_sensor = nuos
    assert heating_sensor.available is True

    api.async_get_velis_plant_data.side_effect = ConnectionException(503)
    await coordinator.async_refresh()
    assert heating_sensor.available is False
    assert state_sensor.available is False

    api.async_get_velis_plant_data.side_effect = None
    api.async_get_velis_plant_data.return_value = dict(PLANT, hpState=2)
    await coordinator.async_refresh()
    assert heating_sensor.available is True
    assert heating_sensor.is_on is True


@pytest.mark.parametrize(
    ("device_cls", "whe_type", "has_hp", "has_is_heating"),
    [
        (AristonNuosSplitDevice, WheType.NuosSplit, True, False),
        (AristonLydosDevice, WheType.Lydos, False, True),
    ],
)
def test_gating(api, device_cls, whe_type, has_hp, has_is_heating):
    coordinator = MagicMock(device=device_cls(api, _attributes(whe_type)))

    assert is_entity_description_available(coordinator, STATE_DESC) is has_hp
    assert is_entity_description_available(coordinator, HEATING_DESC) is has_hp
    assert is_entity_description_available(coordinator, IS_HEATING_DESC) is has_is_heating


def test_lydos_is_heating_unchanged(api):
    device = AristonLydosDevice(api, _attributes(WheType.Lydos))
    device.data = {EvoLydosDeviceProperties.HEAT_REQ: True}
    entity = MagicMock(device=device)
    assert IS_HEATING_DESC.get_is_on(entity) is True
