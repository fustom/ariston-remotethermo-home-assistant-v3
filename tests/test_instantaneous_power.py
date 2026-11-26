"""Tests for the estimated instantaneous power sensor and its rated power option."""

import pytest

from ariston.const import WheType
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.ariston.const import (
    ARISTON_SENSOR_TYPES,
    BUS_ERRORS_SCAN_INTERVAL,
    DOMAIN,
    ENERGY_SCAN_INTERVAL,
    RATED_POWER_W,
)
from custom_components.ariston.sensor import AristonSensor

POWER_KEY = "Instantaneous power"

BASE_OPTIONS = {
    "scan_interval": 180,
    ENERGY_SCAN_INTERVAL: 60,
    BUS_ERRORS_SCAN_INTERVAL: 600,
}


def _power_description():
    return next(
        description
        for description in ARISTON_SENSOR_TYPES
        if description.key == POWER_KEY
    )


@pytest.mark.parametrize(
    ("rated_power_w", "is_heating", "expected"),
    [
        (1500, True, 1500),
        (1500, False, 0),
        (1500, None, None),
        (None, True, None),
        (None, False, None),
    ],
    ids=["heating", "idle", "heating-unknown", "not-configured", "not-configured-idle"],
)
def test_power_sensor_value(
    coordinator, ariston_device, rated_power_w, is_heating, expected
):
    coordinator.rated_power_w = rated_power_w
    ariston_device.is_heating = is_heating
    sensor = AristonSensor(coordinator, _power_description())

    assert sensor.native_value == expected


def test_power_sensor_reports_watts():
    description = _power_description()

    assert description.native_unit_of_measurement == "W"
    assert description.device_class == "power"
    assert description.state_class == "measurement"


def test_power_sensor_excludes_hybrid_heat_pump():
    whe_types = _power_description().whe_types

    assert WheType.LydosHybrid not in whe_types
    assert WheType.Evo in whe_types
    assert WheType.Lydos in whe_types


async def _open_options(hass, stored_options):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="gateway-1",
        data={},
        options=stored_options,
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    return result


def _suggested_rating(result):
    for key in result["data_schema"].schema:
        if key == RATED_POWER_W:
            return (key.description or {}).get("suggested_value")
    raise AssertionError("rated power field missing from options form")


async def test_options_flow_rating_is_optional_and_empty_by_default(hass):
    result = await _open_options(hass, {})

    assert _suggested_rating(result) is None
    assert RATED_POWER_W not in result["data_schema"]({})


async def test_options_flow_sets_rating(hass):
    result = await _open_options(hass, {})

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], BASE_OPTIONS | {RATED_POWER_W: 1500}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == BASE_OPTIONS | {RATED_POWER_W: 1500}


async def test_options_flow_shows_saved_rating_and_changes_it(hass):
    result = await _open_options(hass, BASE_OPTIONS | {RATED_POWER_W: 1500})

    assert _suggested_rating(result) == 1500

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], BASE_OPTIONS | {RATED_POWER_W: 2000}
    )

    assert result["data"][RATED_POWER_W] == 2000


async def test_options_flow_clears_saved_rating(hass):
    result = await _open_options(hass, BASE_OPTIONS | {RATED_POWER_W: 1500})

    # The frontend omits an emptied optional field.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], BASE_OPTIONS
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert RATED_POWER_W not in result["data"]


async def test_options_flow_rejects_non_positive_rating(hass):
    result = await _open_options(hass, {})

    with pytest.raises(Exception):
        await hass.config_entries.options.async_configure(
            result["flow_id"], BASE_OPTIONS | {RATED_POWER_W: 0}
        )
