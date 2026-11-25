"""Tests for AristonEntity.available and the get_is_available hook."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.ariston.const import (
    ARISTON_BINARY_SENSOR_TYPES,
    AristonBinarySensorEntityDescription,
)
from custom_components.ariston.entity import AristonEntity


class _Entity(AristonEntity):
    """Concrete entity so the abstract base can be instantiated."""


def _make_entity(*, coordinator_ok: bool, get_is_available, has_heat_pump=True):
    device = SimpleNamespace(has_heat_pump=has_heat_pump)
    coordinator = MagicMock()
    coordinator.device = device
    coordinator.last_update_success = coordinator_ok
    description = AristonBinarySensorEntityDescription(
        key="test",
        get_is_on=lambda entity: True,
        get_is_available=get_is_available,
    )
    return _Entity(coordinator, description)


@pytest.mark.parametrize(
    ("coordinator_ok", "predicate", "expected"),
    [
        # No predicate: availability follows the coordinator alone.
        (True, None, True),
        (False, None, False),
        # Predicate True: still follows the coordinator.
        (True, lambda e: True, True),
        (False, lambda e: True, False),
        # Predicate False hides the entity even when the coordinator is healthy.
        (True, lambda e: False, False),
        (False, lambda e: False, False),
    ],
)
def test_available_combines_coordinator_and_predicate(
    coordinator_ok, predicate, expected
):
    entity = _make_entity(coordinator_ok=coordinator_ok, get_is_available=predicate)
    assert entity.available is expected


def test_predicate_not_called_when_coordinator_unavailable():
    predicate = MagicMock(return_value=True)
    entity = _make_entity(coordinator_ok=False, get_is_available=predicate)
    assert entity.available is False
    predicate.assert_not_called()


def test_predicate_receives_entity_and_result_is_coerced_to_bool():
    seen = []

    def predicate(entity):
        seen.append(entity)
        return 1  # truthy non-bool

    entity = _make_entity(coordinator_ok=True, get_is_available=predicate)
    assert entity.available is True
    assert seen == [entity]


@pytest.mark.parametrize("has_heat_pump", [True, False])
def test_bsb_heat_pump_sensor_availability_follows_device(has_heat_pump):
    """The BSB 'is heating pump on' sensor is hidden on boiler-type BSB units."""
    description = next(
        d
        for d in ARISTON_BINARY_SENSOR_TYPES
        if d.get_is_available is not None
    )
    device = SimpleNamespace(has_heat_pump=has_heat_pump)
    coordinator = MagicMock()
    coordinator.device = device
    coordinator.last_update_success = True
    entity = _Entity(coordinator, description)
    assert entity.available is has_heat_pump


def test_base_class_is_coordinator_entity():
    assert issubclass(AristonEntity, CoordinatorEntity)
