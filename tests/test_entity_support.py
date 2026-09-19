"""Tests for shared Ariston entity support and availability rules."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import homeassistant  # noqa: F401  # Install Home Assistant's schema compatibility
from ariston.const import SystemType

from custom_components.ariston import binary_sensor
from custom_components.ariston.const import (
    COORDINATOR,
    DOMAIN,
    ENERGY_COORDINATOR,
    AristonSensorEntityDescription,
)
from custom_components.ariston.entity import (
    AristonEntity,
    description_is_supported,
    get_coordinator_for_description,
)


def _coordinator(*, features_available: bool = True, current_value=None):
    device = SimpleNamespace(
        are_device_features_available=lambda *_: features_available,
        current_value=current_value,
    )
    return SimpleNamespace(device=device, last_update_success=True)


def _description(**kwargs) -> AristonSensorEntityDescription:
    return AristonSensorEntityDescription(
        key="test",
        get_native_value=lambda entity: entity.device.current_value,
        **kwargs,
    )


def test_missing_optional_coordinator_is_skipped() -> None:
    """Skip an optional entity when its coordinator was not created."""
    hass = SimpleNamespace(data={DOMAIN: {"gw": {}}})
    entry = SimpleNamespace(unique_id="gw")
    description = _description(coordinator=ENERGY_COORDINATOR)

    assert get_coordinator_for_description(hass, entry, description) is None


def test_placeholder_optional_coordinator_is_skipped() -> None:
    """Skip stale setup placeholders that are not real coordinators."""
    hass = SimpleNamespace(data={DOMAIN: {"gw": {ENERGY_COORDINATOR: {}}}})
    entry = SimpleNamespace(unique_id="gw")
    description = _description(coordinator=ENERGY_COORDINATOR)

    assert get_coordinator_for_description(hass, entry, description) is None


def test_device_feature_filter_can_disable_entity() -> None:
    """Keep the existing device capability filter in the shared helper."""
    coordinator = _coordinator(features_available=False)

    assert description_is_supported(coordinator, _description()) is False


def test_support_predicate_can_disable_entity() -> None:
    """Allow configuration-specific support rules without another setup path."""
    coordinator = _coordinator()
    description = _description(get_is_supported=lambda value: False)

    assert description_is_supported(coordinator, description) is False


def test_entity_availability_combines_coordinator_and_predicate() -> None:
    """Require both a current coordinator and usable entity state."""
    coordinator = _coordinator(current_value=None)
    entity = AristonEntity(
        coordinator,
        _description(
            get_is_available=lambda value: value.device.current_value is not None
        ),
    )

    assert entity.available is False
    entity.device.current_value = 1
    assert entity.available is True
    entity.coordinator.last_update_success = False
    assert entity.available is False


def test_binary_sensor_service_uses_primary_coordinator_when_list_is_empty(
    monkeypatch,
) -> None:
    """Register device services without relying on a setup-loop variable."""
    primary = SimpleNamespace(device=SimpleNamespace(system_type=SystemType.GALEVO))
    hass = SimpleNamespace(
        data={DOMAIN: {"gw": {COORDINATOR: primary}}},
        services=SimpleNamespace(async_register=MagicMock()),
    )
    entry = SimpleNamespace(unique_id="gw")
    added = []
    monkeypatch.setattr(binary_sensor, "ARISTON_BINARY_SENSOR_TYPES", [])

    asyncio.run(binary_sensor.async_setup_entry(hass, entry, added.extend))

    assert added == []
    assert hass.services.async_register.call_count == 1
