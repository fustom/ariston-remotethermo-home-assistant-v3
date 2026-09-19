"""Tests for opt-in estimated instantaneous water-heater power."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import homeassistant  # noqa: F401  # Install Home Assistant's schema compatibility
import probatio
import pytest
from ariston.const import SystemType, WheType
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    UnitOfPower,
)
from homeassistant.helpers import config_validation as cv

from custom_components.ariston.config_flow import AristonOptionsFlow
from custom_components.ariston.const import (
    API_URL_SETTING,
    API_USER_AGENT,
    ARISTON_SENSOR_TYPES,
    BUS_ERRORS_SCAN_INTERVAL,
    ENERGY_SCAN_INTERVAL,
    RATED_POWER_W,
    WATER_HEATER_TEMPERATURE_UNIT,
)
from custom_components.ariston.coordinator import DeviceDataUpdateCoordinator
from custom_components.ariston.sensor import AristonSensor


def _description():
    return next(value for value in ARISTON_SENSOR_TYPES if value.key == "estimated_power")


def _options_flow(options=None) -> AristonOptionsFlow:
    flow = AristonOptionsFlow()
    entry = SimpleNamespace(
        data={
            CONF_USERNAME: "user",
            CONF_PASSWORD: "pass",
            API_URL_SETTING: "url",
            API_USER_AGENT: "agent",
        },
        options=options or {},
    )
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_known_entry=lambda entry_id: entry)
    )
    flow.handler = "entry-id"
    return flow


def _valid_options(**extra):
    return {
        CONF_USERNAME: "user",
        CONF_PASSWORD: "pass",
        API_URL_SETTING: "url",
        API_USER_AGENT: "agent",
        CONF_SCAN_INTERVAL: 180,
        ENERGY_SCAN_INTERVAL: 60,
        BUS_ERRORS_SCAN_INTERVAL: 600,
        WATER_HEATER_TEMPERATURE_UNIT: "auto",
        **extra,
    }


def test_options_schema_serializes_for_home_assistant() -> None:
    """Keep every options field renderable by Home Assistant's form encoder."""
    fields = probatio.to_field_list(
        _options_flow()._get_options_schema(),
        custom_serializer=cv.custom_serializer,
    )

    rated_power = next(field for field in fields if field["name"] == RATED_POWER_W)
    assert rated_power["type"] == "integer"
    assert rated_power["valueMin"] == 1


@pytest.mark.parametrize("invalid", [0, -1, 1800.5, "1800", True])
def test_rated_power_submission_rejects_nonpositive_and_noninteger_values(
    invalid,
) -> None:
    """Accept only a real positive integer from the device label."""
    flow = _options_flow()
    flow.async_show_form = MagicMock(return_value={"type": "form"})

    result = asyncio.run(
        flow.async_step_init(_valid_options(**{RATED_POWER_W: invalid}))
    )

    assert result == {"type": "form"}
    assert flow.async_show_form.call_args.kwargs["errors"] == {
        RATED_POWER_W: "invalid_rated_power"
    }


def test_rated_power_accepts_positive_integer() -> None:
    """Allow a positive whole-watt rating."""
    values = _options_flow()._get_options_schema()({RATED_POWER_W: 1800})

    assert values[RATED_POWER_W] == 1800


def test_absent_rated_power_has_no_default() -> None:
    """Keep the estimate opt-in for existing entries."""
    values = _options_flow()._get_options_schema()({})

    assert RATED_POWER_W not in values


def test_existing_rated_power_is_the_form_default() -> None:
    """Suggest a configured rating without restoring it after the field is cleared."""
    schema = _options_flow({RATED_POWER_W: 1800})._get_options_schema()
    marker = next(
        marker for marker in schema.schema if marker.schema == RATED_POWER_W
    )

    assert marker.description == {"suggested_value": 1800}
    assert RATED_POWER_W not in schema({})


def test_absent_rated_power_is_omitted_from_saved_options() -> None:
    """Allow disabling the estimate by clearing the field in the actual form schema."""
    flow = _options_flow({RATED_POWER_W: 1800})
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    validated = flow._get_options_schema()(_valid_options())

    asyncio.run(flow.async_step_init(validated))

    saved = flow.async_create_entry.call_args.kwargs["data"]
    assert RATED_POWER_W not in saved


def test_estimated_power_sensor_requires_configuration() -> None:
    """Do not create an estimate entity without a user-supplied rating."""
    description = _description()

    assert description.get_is_supported(SimpleNamespace(rated_power_w=None)) is False
    assert description.get_is_supported(SimpleNamespace(rated_power_w=1800)) is True


def _power_entity(*, rated_power_w, is_heating):
    async def update():
        raise AssertionError("reading the sensor must not poll the device")

    device = SimpleNamespace(name="Velis", is_heating=is_heating)
    coordinator = DeviceDataUpdateCoordinator(
        object(), None, device, 180, "state", update
    )
    coordinator.rated_power_w = rated_power_w
    return AristonSensor(coordinator, _description())


@pytest.mark.parametrize(("heating", "expected"), [(True, 1800), (False, 0)])
def test_estimated_power_uses_heating_state(heating, expected) -> None:
    """Report rated power only while heating is known active."""
    entity = _power_entity(rated_power_w=1800, is_heating=heating)

    assert entity.native_value == expected
    assert entity.available is True


def test_unknown_heating_state_is_unavailable() -> None:
    """Do not report zero when the heating state is unknown."""
    entity = _power_entity(rated_power_w=1800, is_heating=None)

    assert entity.native_value is None
    assert entity.available is False


def test_estimated_power_metadata_marks_an_estimate_in_watts() -> None:
    """Expose the value as instantaneous power, not measured energy."""
    description = _description()

    assert description.name == "Ariston estimated instantaneous power"
    assert description.device_class is SensorDeviceClass.POWER
    assert description.state_class is SensorStateClass.MEASUREMENT
    assert description.native_unit_of_measurement == UnitOfPower.WATT


def test_estimated_power_supports_only_fixed_resistance_heaters() -> None:
    """Exclude Nuos Split and include the known resistance-heater families."""
    description = _description()

    assert description.system_types == [SystemType.VELIS]
    assert set(description.whe_types) == {
        WheType.Evo,
        WheType.Evo2,
        WheType.Lydos,
        WheType.Lux,
        WheType.Lux2,
        WheType.Andris2,
    }
    assert WheType.LydosHybrid not in description.whe_types
    assert WheType.NuosSplit not in description.whe_types
