"""Tests for water-heater temperature-unit options and conversion."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import homeassistant  # noqa: F401  # Install Home Assistant's schema compatibility
import pytest
import voluptuous as vol
from ariston.const import SystemType
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    UnitOfTemperature,
)

from custom_components.ariston.config_flow import AristonOptionsFlow
from custom_components.ariston.const import (
    API_URL_SETTING,
    API_USER_AGENT,
    ARISTON_WATER_HEATER_TYPES,
    BUS_ERRORS_SCAN_INTERVAL,
    ENERGY_SCAN_INTERVAL,
    WATER_HEATER_TEMPERATURE_UNIT,
)
from custom_components.ariston.coordinator import DeviceDataUpdateCoordinator
from custom_components.ariston.water_heater import AristonWaterHeater


def _make_water_heater(
    *,
    native_unit=UnitOfTemperature.CELSIUS,
    override="auto",
    system_type=SystemType.VELIS,
    decimals=1,
) -> tuple[AristonWaterHeater, list[float]]:
    writes = []

    async def set_temperature(value):
        writes.append(value)

    async def update():
        return None

    device = SimpleNamespace(
        name="Velis",
        gateway="gw",
        system_type=system_type,
        water_heater_temperature_unit=native_unit,
        water_heater_temperature_decimals=decimals,
        water_heater_temperature_step=0.5,
        water_heater_current_temperature=45.0,
        water_heater_target_temperature=50.0,
        water_heater_minimum_temperature=10.0,
        water_heater_maximum_temperature=80.0,
        async_set_water_heater_temperature=set_temperature,
    )
    coordinator = DeviceDataUpdateCoordinator(
        object(), None, device, 180, "state", update
    )
    coordinator.water_heater_temperature_unit = override
    description = (
        ARISTON_WATER_HEATER_TYPES[1]
        if system_type is SystemType.VELIS
        else ARISTON_WATER_HEATER_TYPES[0]
    )
    entity = AristonWaterHeater(coordinator, description)
    entity.async_write_ha_state = lambda: None
    return entity, writes


@pytest.mark.parametrize(
    ("native_unit", "override", "native", "display"),
    [
        (UnitOfTemperature.CELSIUS, "auto", 50.0, 50.0),
        (UnitOfTemperature.CELSIUS, "fahrenheit", 50.0, 122.0),
        (UnitOfTemperature.FAHRENHEIT, "celsius", 122.0, 50.0),
    ],
)
def test_velis_temperature_conversion(native_unit, override, native, display) -> None:
    """Convert Velis target values once from native to selected units."""
    entity, _ = _make_water_heater(native_unit=native_unit, override=override)
    entity.device.water_heater_target_temperature = native

    assert entity.target_temperature == pytest.approx(display)


def test_velis_converts_all_displayed_temperature_values() -> None:
    """Keep current, target, and bounds in the same displayed unit."""
    entity, _ = _make_water_heater(override="fahrenheit")

    assert entity.current_temperature == pytest.approx(113.0)
    assert entity.target_temperature == pytest.approx(122.0)
    assert entity.min_temp == pytest.approx(50.0)
    assert entity.max_temp == pytest.approx(176.0)
    assert entity.temperature_unit == UnitOfTemperature.FAHRENHEIT


def test_none_temperature_remains_none() -> None:
    """Preserve unavailable device values during conversion."""
    entity, _ = _make_water_heater(override="fahrenheit")
    entity.device.water_heater_current_temperature = None

    assert entity.current_temperature is None


def test_non_velis_device_bypasses_override() -> None:
    """Do not double-convert device families normalized by the library."""
    entity, _ = _make_water_heater(
        override="fahrenheit", system_type=SystemType.GALEVO
    )

    assert entity.target_temperature == 50.0
    assert entity.temperature_unit == UnitOfTemperature.CELSIUS


def test_outbound_override_converts_once_and_tracks_native_value() -> None:
    """Send and confirm the device-native value after display conversion."""
    entity, writes = _make_water_heater(override="fahrenheit")

    asyncio.run(entity.async_set_temperature(**{ATTR_TEMPERATURE: 122.0}))

    assert writes == [50.0]
    pending = entity.coordinator.pending_writes["water_heater_temperature"]
    assert pending.expected == 50.0


def test_outbound_override_rounds_to_native_decimals() -> None:
    """Avoid confirmation churn from unsupported native precision."""
    entity, writes = _make_water_heater(
        native_unit=UnitOfTemperature.FAHRENHEIT,
        override="celsius",
        decimals=1,
    )

    asyncio.run(entity.async_set_temperature(**{ATTR_TEMPERATURE: 25.01}))

    assert writes == [77.0]


def test_outbound_override_clamps_to_native_bounds() -> None:
    """Keep converted service calls within the device's existing limits."""
    entity, writes = _make_water_heater(override="fahrenheit")

    asyncio.run(entity.async_set_temperature(**{ATTR_TEMPERATURE: 200.0}))

    assert writes == [80.0]


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


def test_temperature_unit_option_defaults_to_auto() -> None:
    """Keep existing entries unchanged until a user selects an override."""
    values = _options_flow()._get_options_schema()({})

    assert values[WATER_HEATER_TEMPERATURE_UNIT] == "auto"


@pytest.mark.parametrize("invalid", ["kelvin", "", None])
def test_temperature_unit_option_rejects_unknown_values(invalid) -> None:
    """Accept only the three supported option values."""
    schema = _options_flow()._get_options_schema()

    with pytest.raises(vol.Invalid):
        schema({WATER_HEATER_TEMPERATURE_UNIT: invalid})


def test_options_flow_persists_temperature_unit() -> None:
    """Include the validated selection in saved options."""
    flow = _options_flow()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    user_input = {
        CONF_USERNAME: "user",
        CONF_PASSWORD: "pass",
        API_URL_SETTING: "url",
        API_USER_AGENT: "agent",
        CONF_SCAN_INTERVAL: 180,
        ENERGY_SCAN_INTERVAL: 60,
        BUS_ERRORS_SCAN_INTERVAL: 600,
        WATER_HEATER_TEMPERATURE_UNIT: "fahrenheit",
    }

    asyncio.run(flow.async_step_init(user_input))

    saved = flow.async_create_entry.call_args.kwargs["data"]
    assert saved[WATER_HEATER_TEMPERATURE_UNIT] == "fahrenheit"
