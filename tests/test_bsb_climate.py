"""Tests for BSB climate behavior and heat-pump feature gating."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock

import homeassistant  # noqa: F401  # Install Home Assistant's schema compatibility
import pytest
from ariston.bsb_device import AristonBsbDevice
from ariston.const import (
    BsbZoneMode,
    BsbZoneProperties,
    DeviceFeatures,
    DeviceProperties,
    PropertyType,
    SystemType,
)
from homeassistant.const import ATTR_TEMPERATURE

from custom_components.ariston.climate import AristonThermostat
from custom_components.ariston.const import (
    ARISTON_BINARY_SENSOR_TYPES,
    ARISTON_CLIMATE_TYPES,
)

_MISSING = object()


def _make_bsb_thermostat(
    *, mode=0, options=(0, 1, 2, 3), desired=_MISSING, reduced=_MISSING
) -> AristonThermostat:
    zone = {BsbZoneProperties.MODE: {PropertyType.VALUE: mode}}
    if desired is not _MISSING:
        zone[BsbZoneProperties.DESIRED_ROOM_TEMP] = desired
    if reduced is not _MISSING:
        zone[BsbZoneProperties.CH_RED_TEMP] = reduced

    device = SimpleNamespace(
        system_type=SystemType.BSB,
        gateway="gw",
        plant_mode_supported=False,
        get_zone=lambda zone_number: zone,
        get_zone_mode_options=lambda zone_number: (
            None if options is None else list(options)
        ),
        get_target_temp_value=lambda zone_number: 21.0,
        get_comfort_temp_min=lambda zone_number: 5.0,
        get_comfort_temp_max=lambda zone_number: 30.0,
        get_target_temp_step=lambda zone_number: 0.5,
        get_reduced_temp_min=lambda zone_number: 6.0,
        get_reduced_temp_max=lambda zone_number: 24.0,
        get_reduced_temp_step=lambda zone_number: 0.2,
        async_set_zone_mode=AsyncMock(),
        async_set_reduced_temp=AsyncMock(),
        async_set_comfort_temp=AsyncMock(),
    )
    coordinator = SimpleNamespace(
        device=device,
        last_update_success=True,
        async_request_refresh=AsyncMock(),
    )
    thermostat = AristonThermostat(1, coordinator, ARISTON_CLIMATE_TYPES[1])
    thermostat._attr_has_thermostat = True
    thermostat.async_write_ha_state = lambda: None
    return thermostat


def test_heat_pump_activity_requires_hp_feature() -> None:
    """Expose pump activity on pure heat pumps, not only hybrid systems."""
    description = next(
        value
        for value in ARISTON_BINARY_SENSOR_TYPES
        if value.key == DeviceProperties.IS_HEATING_PUMP_ON
    )

    assert description.device_features == [DeviceFeatures.HP_SYS]


def test_bsb_mode_zero_is_protection() -> None:
    """Do not let numeric zero collapse into the undefined fallback."""
    thermostat = _make_bsb_thermostat(mode=0)

    assert thermostat._get_bsb_zone_mode() is BsbZoneMode.OFF
    assert thermostat.preset_mode == "protection"


@pytest.mark.parametrize("mode", [None, "bad", {}, 1.5, 99])
def test_malformed_bsb_mode_is_undefined(mode) -> None:
    """Keep malformed cloud mode data from breaking the climate entity."""
    thermostat = _make_bsb_thermostat(mode=mode)

    assert thermostat._get_bsb_zone_mode() is BsbZoneMode.UNDEFINED
    assert thermostat.preset_mode is None


@pytest.mark.parametrize(
    ("desired", "expected"),
    [
        (18.5, 18.5),
        ({PropertyType.VALUE: 19.5}, 19.5),
        (None, 21.0),
        ({}, 21.0),
        ("invalid", 21.0),
        (float("nan"), 21.0),
        (float("inf"), 21.0),
    ],
)
def test_bsb_target_temperature_accepts_scalar_or_property(desired, expected) -> None:
    """Use schedule-aware desired temperature only when it is numeric."""
    thermostat = _make_bsb_thermostat(desired=desired)

    assert thermostat.target_temperature == expected


def test_bsb_preset_modes_filter_unknowns_and_duplicates() -> None:
    """Expose each supported known BSB mode once."""
    thermostat = _make_bsb_thermostat(
        options=[0, "0", BsbZoneMode.TIME_PROGRAM, 99, "bad", 2, 3]
    )

    assert thermostat.preset_modes == [
        "protection",
        "automatic",
        "reduced",
        "comfort",
    ]


def test_missing_bsb_preset_options_returns_empty_list() -> None:
    """Keep the entity usable when the cloud omits supported mode options."""
    thermostat = _make_bsb_thermostat(options=None)

    assert thermostat.preset_modes == []


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        ("protection", BsbZoneMode.OFF),
        ("automatic", BsbZoneMode.TIME_PROGRAM),
        ("reduced", BsbZoneMode.MANUAL_NIGHT),
        ("comfort", BsbZoneMode.MANUAL),
    ],
)
def test_bsb_preset_writes_zone_mode(preset, expected) -> None:
    """Map all exposed BSB preset labels back to their enum values."""
    thermostat = _make_bsb_thermostat()

    asyncio.run(thermostat.async_set_preset_mode(preset))

    thermostat.device.async_set_zone_mode.assert_awaited_once_with(expected, 1)


def test_automatic_schedule_uses_reduced_setpoint_with_tolerance() -> None:
    """Route scheduled reduced-period changes to the reduced setpoint."""
    thermostat = _make_bsb_thermostat(
        mode=1,
        desired=17.0001,
        reduced={PropertyType.VALUE: 17.0},
    )

    asyncio.run(
        thermostat.async_set_temperature(**{ATTR_TEMPERATURE: 18.0})
    )

    thermostat.device.async_set_reduced_temp.assert_awaited_once_with(18.0, 1)
    thermostat.device.async_set_comfort_temp.assert_not_awaited()
    assert thermostat.min_temp == 6.0
    assert thermostat.max_temp == 24.0
    assert thermostat.target_temperature_step == 0.2


def test_manual_reduced_mode_uses_reduced_setpoint() -> None:
    """Treat explicit reduced mode as reduced even without desired data."""
    thermostat = _make_bsb_thermostat(mode=BsbZoneMode.MANUAL_NIGHT)

    asyncio.run(
        thermostat.async_set_temperature(**{ATTR_TEMPERATURE: 16.0})
    )

    thermostat.device.async_set_reduced_temp.assert_awaited_once_with(16.0, 1)


@pytest.mark.parametrize(
    "reduced",
    [
        "malformed",
        {PropertyType.VALUE: 17.0, PropertyType.MIN: "bad"},
        {
            PropertyType.VALUE: 17.0,
            PropertyType.MIN: 6.0,
            PropertyType.MAX: 24.0,
            PropertyType.STEP: 0,
        },
    ],
)
def test_malformed_reduced_metadata_falls_back_to_comfort_bounds(reduced) -> None:
    """Keep climate bounds usable when the cloud returns malformed reduced data."""
    thermostat = _make_bsb_thermostat(mode=BsbZoneMode.MANUAL_NIGHT, reduced=reduced)
    device = thermostat.device
    device.get_zone_ch_red_temp = MethodType(
        AristonBsbDevice.get_zone_ch_red_temp, device
    )
    device.get_reduced_temp_min = MethodType(
        AristonBsbDevice.get_reduced_temp_min, device
    )
    device.get_reduced_temp_max = MethodType(
        AristonBsbDevice.get_reduced_temp_max, device
    )
    device.get_reduced_temp_step = MethodType(
        AristonBsbDevice.get_reduced_temp_step, device
    )

    assert thermostat.min_temp == 5.0
    assert thermostat.max_temp == 30.0
    assert thermostat.target_temperature_step == 0.5


@pytest.mark.parametrize(
    ("mode", "desired", "reduced"),
    [
        (BsbZoneMode.MANUAL, _MISSING, _MISSING),
        (BsbZoneMode.TIME_PROGRAM, _MISSING, {PropertyType.VALUE: 17.0}),
        (BsbZoneMode.TIME_PROGRAM, 18.0, _MISSING),
        ("bad", 17.0, {PropertyType.VALUE: 17.0}),
    ],
)
def test_missing_or_unrecognized_bsb_data_falls_back_to_comfort(
    mode, desired, reduced
) -> None:
    """Use the established comfort command when reduced state is uncertain."""
    thermostat = _make_bsb_thermostat(
        mode=mode,
        desired=desired,
        reduced=reduced,
    )

    asyncio.run(
        thermostat.async_set_temperature(**{ATTR_TEMPERATURE: 20.0})
    )

    thermostat.device.async_set_comfort_temp.assert_awaited_once_with(20.0, 1)
    thermostat.device.async_set_reduced_temp.assert_not_awaited()


def test_galevo_presets_remain_plant_modes() -> None:
    """Leave existing non-BSB preset presentation unchanged."""
    device = SimpleNamespace(
        system_type=SystemType.GALEVO,
        plant_mode_supported=True,
        plant_mode_text="winter",
        plant_mode_opt_texts=["off", "winter"],
    )
    thermostat = AristonThermostat(
        1,
        SimpleNamespace(device=device, last_update_success=True),
        ARISTON_CLIMATE_TYPES[0],
    )

    assert thermostat.preset_mode == "winter"
    assert thermostat.preset_modes == ["off", "winter"]


def test_bsb_presets_have_translation_and_icon_metadata() -> None:
    """Keep all exposed BSB labels translatable and icon-addressable."""
    integration_dir = Path(__file__).parents[1] / "custom_components" / "ariston"
    expected = {"protection", "automatic", "reduced", "comfort"}

    icons = json.loads((integration_dir / "icons.json").read_text(encoding="utf-8"))
    icon_states = icons["entity"]["climate"]["ariston_thermostat"][
        "state_attributes"
    ]["preset_mode"]["state"]
    assert set(icon_states) == expected

    for translation_file in (integration_dir / "translations").glob("*.json"):
        translation = json.loads(translation_file.read_text(encoding="utf-8"))
        states = translation["entity"]["climate"]["ariston_thermostat"][
            "state_attributes"
        ]["preset_mode"]["state"]
        assert set(states) == expected
