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


async def _vacation_handler(devices, coordinators):
    """Run binary_sensor.async_setup_entry and capture the service handler."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from custom_components.ariston import binary_sensor
    from custom_components.ariston.const import COORDINATOR, DOMAIN

    main = SimpleNamespace(
        device=SimpleNamespace(
            async_set_holiday=AsyncMock(),
            are_device_features_available=lambda *a, **k: False,
        )
    )
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "main": {COORDINATOR: main},
            **{k: {COORDINATOR: c} for k, c in coordinators.items()},
        }
    }
    entries = {k: SimpleNamespace(domain=DOMAIN, unique_id=k) for k in coordinators}
    hass.config_entries.async_get_entry = entries.get
    registry = SimpleNamespace(devices=devices)
    with patch.object(binary_sensor.dr, "async_get", return_value=registry):
        await binary_sensor.async_setup_entry(
            hass, SimpleNamespace(unique_id="main"), lambda ents: None
        )
    handler = hass.services.async_register.call_args.args[2]
    return handler, registry, binary_sensor


async def test_create_vacation_rejects_unsupported_device():
    from unittest.mock import patch

    import pytest
    from homeassistant.exceptions import ServiceValidationError

    devices = {
        "dev-bad": SimpleNamespace(
            config_entries={"bad"}, name="Old model", name_by_user=None
        )
    }
    handler, registry, bs = await _vacation_handler(
        devices, {"bad": SimpleNamespace(device=SimpleNamespace())}
    )
    with patch.object(bs.dr, "async_get", return_value=registry):
        with pytest.raises(ServiceValidationError, match="does not support"):
            await handler(SimpleNamespace(data={"device_id": "dev-bad"}))


async def test_create_vacation_rejects_unknown_device_id():
    from unittest.mock import patch

    import pytest
    from homeassistant.exceptions import ServiceValidationError

    handler, registry, bs = await _vacation_handler({}, {})
    with patch.object(bs.dr, "async_get", return_value=registry):
        with pytest.raises(ServiceValidationError, match="not found"):
            await handler(SimpleNamespace(data={"device_id": "missing"}))


async def test_create_vacation_calls_setter_on_supported_device():
    from unittest.mock import AsyncMock, patch

    good = SimpleNamespace(
        device=SimpleNamespace(async_set_holiday=AsyncMock()),
        async_request_refresh=AsyncMock(),
    )
    devices = {
        "dev-ok": SimpleNamespace(config_entries={"ok"}, name="Nuos", name_by_user=None)
    }
    handler, registry, bs = await _vacation_handler(devices, {"ok": good})
    end = dt.date(2026, 8, 15)
    with patch.object(bs.dr, "async_get", return_value=registry):
        await handler(SimpleNamespace(data={"device_id": "dev-ok", "end_date": end}))
    good.device.async_set_holiday.assert_awaited_once_with(end)
    good.async_request_refresh.assert_awaited_once()
