"""Tests for the Nuos holiday entities (binary sensor + end-date sensor)."""

import datetime as dt
from types import SimpleNamespace

from ariston.const import NuosSplitProperties, SystemType, WheType

from custom_components.ariston.const import (
    ARISTON_BINARY_SENSOR_TYPES,
    ARISTON_SENSOR_TYPES,
    AristonBinarySensorEntityDescription,
    AristonSensorEntityDescription,
)


def _holiday_binary_sensor() -> AristonBinarySensorEntityDescription:
    for desc in ARISTON_BINARY_SENSOR_TYPES:
        if desc.key == NuosSplitProperties.HOLIDAY_UNTIL:
            return desc
    raise AssertionError("Nuos holiday binary sensor description missing")


def _holiday_end_sensor() -> AristonSensorEntityDescription:
    for desc in ARISTON_SENSOR_TYPES:
        if desc.key == "holiday_end":
            return desc
    raise AssertionError("Nuos holiday end sensor description missing")


def test_holiday_binary_sensor_targets_velis_nuos_split():
    """Holiday entity is family-gated, not runtime-gated. The cloud omits the
    holidayUntil field when no holiday is scheduled, but the official Ariston
    NET app still shows holiday controls on every Slp device — capability is
    decided by family, not by a runtime flag."""
    desc = _holiday_binary_sensor()
    assert desc.system_types == [SystemType.VELIS]
    assert desc.whe_types == [WheType.NuosSplit]


def test_holiday_binary_sensor_get_is_on_uses_holiday_active():
    desc = _holiday_binary_sensor()
    entity = SimpleNamespace(device=SimpleNamespace(holiday_active=True))
    assert desc.get_is_on(entity) is True
    entity.device = SimpleNamespace(holiday_active=False)
    assert desc.get_is_on(entity) is False


def test_holiday_binary_sensor_extra_state_returns_end_date_string():
    desc = _holiday_binary_sensor()
    assert desc.extra_states is not None
    method = desc.extra_states[0]["DeviceMethod"]
    entity = SimpleNamespace(
        device=SimpleNamespace(holiday_end_date="2026-08-15T00:00:00")
    )
    assert method(entity) == "2026-08-15T00:00:00"


def test_holiday_end_sensor_targets_velis_nuos_split():
    desc = _holiday_end_sensor()
    assert desc.system_types == [SystemType.VELIS]
    assert desc.whe_types == [WheType.NuosSplit]


def test_holiday_end_sensor_parses_iso_string_to_date():
    desc = _holiday_end_sensor()
    entity = SimpleNamespace(
        device=SimpleNamespace(holiday_end_date="2026-08-15T00:00:00")
    )
    assert desc.get_native_value(entity) == dt.date(2026, 8, 15)


def test_holiday_end_sensor_returns_none_when_no_holiday():
    desc = _holiday_end_sensor()
    entity = SimpleNamespace(device=SimpleNamespace(holiday_end_date=None))
    assert desc.get_native_value(entity) is None
