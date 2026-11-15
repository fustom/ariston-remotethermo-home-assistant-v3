"""Integration test: consumption sensor descriptions in const.py wire correctly to the energy helpers (issue #439)."""

import datetime as dt
from types import SimpleNamespace

import pytest
from homeassistant.util import dt as dt_util
from ariston.const import ConsumptionTimeInterval, ConsumptionType

from custom_components.ariston.const import ARISTON_SENSOR_TYPES


CONSUMPTION_SENSORS_BY_KEY = {
    "Central heating total energy consumption": ConsumptionType.CENTRAL_HEATING_TOTAL_ENERGY,
    "Domestic hot water total energy consumption": ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY,
    "Central heating gas consumption": ConsumptionType.CENTRAL_HEATING_GAS,
    "Domestic hot water heating pump electricity consumption": ConsumptionType.DOMESTIC_HOT_WATER_HEATING_PUMP_ELECTRICITY,
    "Domestic hot water resistor electricity consumption": ConsumptionType.DOMESTIC_HOT_WATER_RESISTOR_ELECTRICITY,
    "Domestic hot water gas consumption": ConsumptionType.DOMESTIC_HOT_WATER_GAS,
    "Central heating electricity consumption": ConsumptionType.CENTRAL_HEATING_ELECTRICITY,
    "Domestic hot water electricity consumption": ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY,
}


def _sensor_by_key(key: str):
    for desc in ARISTON_SENSOR_TYPES:
        if desc.key == key:
            return desc
    raise AssertionError(f"sensor description not found: {key}")


def _entity_with_sequences(consumption_type: ConsumptionType, buckets):
    sequences = [
        {
            "k": consumption_type.value,
            "p": ConsumptionTimeInterval.LAST_DAY.value,
            "v": buckets,
        }
    ]
    device = SimpleNamespace(consumptions_sequences=sequences)
    return SimpleNamespace(device=device)


@pytest.mark.parametrize("sensor_key,consumption_type", list(CONSUMPTION_SENSORS_BY_KEY.items()))
def test_sensor_native_value_returns_full_period_sum(sensor_key, consumption_type):
    """Each consumption sensor must return the SUM of v[], not just v[-1] (issue #439)."""
    desc = _sensor_by_key(sensor_key)
    entity = _entity_with_sequences(consumption_type, [0.10, 0.30, 0.45, 0.50, 0.45])

    value = desc.get_native_value(entity)
    assert value == pytest.approx(1.80), f"{sensor_key} returned {value}, expected 1.80"
    # Pre-fix behavior would have returned 0.45 (last bucket only).
    assert value != pytest.approx(0.45)


@pytest.mark.parametrize("sensor_key", list(CONSUMPTION_SENSORS_BY_KEY))
def test_sensor_last_reset_is_stable_local_midnight(sensor_key):
    """`last_reset` must be a stable local midnight, not the lib's `now-1h` rotation timestamp."""
    desc = _sensor_by_key(sensor_key)
    entity = _entity_with_sequences(
        CONSUMPTION_SENSORS_BY_KEY[sensor_key], [1.0, 2.0]
    )

    reset = desc.get_last_reset(entity)
    assert reset.tzinfo is not None
    local = dt_util.as_local(reset)
    assert local.hour == 0 and local.minute == 0 and local.second == 0


def test_sensor_native_value_none_when_no_sequences():
    desc = _sensor_by_key("Domestic hot water heating pump electricity consumption")
    entity = SimpleNamespace(device=SimpleNamespace(consumptions_sequences=[]))

    assert desc.get_native_value(entity) is None
