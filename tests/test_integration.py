"""Tests for config-entry setup, services, and unload handling."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol

from ariston import DeviceAttribute
from ariston.ariston_api import AristonAPI, ConnectionException
from ariston.const import (
    ARISTON_API_URL,
    ARISTON_USER_AGENT,
    ConsumptionTimeInterval,
    ConsumptionType,
    DeviceFeatures,
    DeviceProperties,
    LydosDeviceProperties,
    LydosPlantMode,
    PlantMode,
    PropertyType,
    SystemType,
    ThermostatProperties,
    VelisDeviceAttribute,
    WheType,
    ZoneAttribute,
    ZoneMode,
)
from ariston.galevo_device import AristonGalevoDevice
from ariston.lydos_hybrid_device import AristonLydosHybridDevice
from homeassistant.components.climate.const import ATTR_CURRENT_TEMPERATURE
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_DEVICE,
    CONF_PASSWORD,
    CONF_USERNAME,
    STATE_UNAVAILABLE,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_system import METRIC_SYSTEM
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.ariston import (
    ATTR_ITEM_ID,
    ATTR_VALUE,
    ATTR_ZONE,
    DOMAIN,
    SERVICE_SET_ITEM_BY_ID,
    SET_ITEM_BY_ID_SCHEMA,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.ariston.const import (
    ARISTON_SENSOR_TYPES,
    BUS_ERRORS_COORDINATOR,
    BUS_ERRORS_SCAN_INTERVAL,
    COORDINATOR,
    DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    ENERGY_COORDINATOR,
    ENERGY_SCAN_INTERVAL,
)
from custom_components.ariston.sensor import AristonSensor


def _entry(**options):
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="gateway-1",
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_DEVICE: {
                DeviceAttribute.GW: "gateway-1",
                DeviceAttribute.NAME: "Test boiler",
            },
        },
        options=options,
    )


def _mock_client(monkeypatch, client):
    monkeypatch.setattr(
        "custom_components.ariston.Ariston", MagicMock(return_value=client)
    )


def _mock_device(*, has_metering=False, system_type=SystemType.BSB):
    return SimpleNamespace(
        name="Test boiler",
        gateway="gateway-1",
        has_metering=has_metering,
        system_type=system_type,
        async_get_features=AsyncMock(),
        async_update_state=AsyncMock(),
        async_get_bus_errors=AsyncMock(),
        async_update_energy=AsyncMock(),
        async_set_item_by_id=AsyncMock(),
        async_set_holiday=AsyncMock(),
    )


async def test_setup_creates_coordinators_and_unload_removes_entry_data(
    hass, monkeypatch
):
    device = _mock_device(has_metering=True, system_type=SystemType.GALEVO)
    client = MagicMock()
    client.async_connect = AsyncMock(return_value=True)
    client.async_hello = AsyncMock(return_value=device)
    _mock_client(monkeypatch, client)
    forward_platforms = AsyncMock()
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", forward_platforms
    )
    entry = _entry(
        **{
            "scan_interval": 120,
            ENERGY_SCAN_INTERVAL: 30,
            BUS_ERRORS_SCAN_INTERVAL: 900,
        }
    )
    entry.add_to_hass(hass)
    entry._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)

    assert await async_setup_entry(hass, entry)

    coordinators = hass.data[DOMAIN][entry.unique_id]
    assert set(coordinators) == {COORDINATOR, BUS_ERRORS_COORDINATOR, ENERGY_COORDINATOR}
    assert coordinators[COORDINATOR].update_interval.total_seconds() == 120
    assert coordinators[BUS_ERRORS_COORDINATOR].update_interval.total_seconds() == 900
    assert coordinators[ENERGY_COORDINATOR].update_interval.total_seconds() == 1800
    client.async_connect.assert_awaited_once_with(
        "user@example.com", "secret", ARISTON_API_URL, ARISTON_USER_AGENT
    )
    client.async_hello.assert_awaited_once_with(
        "gateway-1", hass.config.units is METRIC_SYSTEM
    )
    device.async_get_features.assert_awaited_once()
    device.async_update_state.assert_awaited_once()
    device.async_get_bus_errors.assert_awaited_once()
    device.async_update_energy.assert_awaited_once()
    forward_platforms.assert_awaited_once()
    assert hass.services.has_service(DOMAIN, SERVICE_SET_ITEM_BY_ID)

    registered_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "serial-1")},
        name="Test boiler",
    )
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_ITEM_BY_ID,
        {
            ATTR_DEVICE_ID: registered_device.id,
            ATTR_ITEM_ID: "comfort_temp",
            ATTR_ZONE: 1,
            ATTR_VALUE: 20,
        },
        blocking=True,
    )
    device.async_set_item_by_id.assert_awaited_once_with(
        "comfort_temp", 20.0, 1
    )

    unload_platforms = AsyncMock(return_value=True)
    monkeypatch.setattr(
        hass.config_entries, "async_unload_platforms", unload_platforms
    )
    assert await async_unload_entry(hass, entry)
    assert entry.unique_id not in hass.data[DOMAIN]


async def test_setup_continues_when_bus_errors_first_refresh_fails(
    hass, monkeypatch
):
    device = _mock_device()
    device.bus_errors = []
    device.async_get_bus_errors = AsyncMock(
        side_effect=[ConnectionException(500), None]
    )
    client = MagicMock()
    client.async_connect = AsyncMock(return_value=True)
    client.async_hello = AsyncMock(return_value=device)
    _mock_client(monkeypatch, client)
    forward_platforms = AsyncMock()
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", forward_platforms
    )
    entry = _entry()
    entry.add_to_hass(hass)
    entry._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)

    assert await async_setup_entry(hass, entry)

    coordinators = hass.data[DOMAIN][entry.unique_id]
    assert coordinators[COORDINATOR].last_update_success
    bus_errors_coordinator = coordinators[BUS_ERRORS_COORDINATOR]
    assert not bus_errors_coordinator.last_update_success
    forward_platforms.assert_awaited_once()

    description = next(
        description
        for description in ARISTON_SENSOR_TYPES
        if description.coordinator == BUS_ERRORS_COORDINATOR
    )
    sensor = AristonSensor(bus_errors_coordinator, description)
    assert not sensor.available

    device.bus_errors = [{"code": "E1"}]
    await bus_errors_coordinator.async_refresh()

    assert sensor.available
    assert sensor.native_value == 1


@pytest.mark.parametrize(
    "fail_at_startup", [True, False], ids=["startup", "polling"]
)
async def test_lydos_energy_http_500_does_not_interrupt_water_heater(
    hass, enable_custom_integrations, monkeypatch, fail_at_startup
):
    """Load the real platforms and recover energy data after a cloud failure."""
    entry = _entry(**{ENERGY_SCAN_INTERVAL: 1})
    api = MagicMock(spec=AristonAPI)
    api.async_get_features_for_device.return_value = {
        DeviceFeatures.HAS_METERING: True
    }
    api.async_get_velis_plant_settings.return_value = {}
    api.async_get_velis_plant_data.return_value = {
        LydosDeviceProperties.MODE: LydosPlantMode.GREEN.value,
        LydosDeviceProperties.ON: True,
        LydosDeviceProperties.TEMP: 48,
        LydosDeviceProperties.REQ_TEMP: 55,
    }
    api.async_get_bus_errors.return_value = []
    consumption = [
        {
            "k": ConsumptionType.DOMESTIC_HOT_WATER_HEATING_PUMP_ELECTRICITY.value,
            "p": ConsumptionTimeInterval.LAST_DAY.value,
            "v": [0.5, 1.25],
        }
    ]
    # Fewer than 24 hourly buckets: the daily sensor sums the whole series.
    expected = "1.75"
    energy_failure = ConnectionException(500)
    api.async_get_consumptions_sequences.side_effect = (
        [energy_failure, consumption]
        if fail_at_startup
        else [consumption, energy_failure, consumption]
    )

    device = AristonLydosHybridDevice(
        api,
        {
            **entry.data[CONF_DEVICE],
            DeviceAttribute.SYS: SystemType.VELIS.value,
            DeviceAttribute.SN: "lydos-1",
            VelisDeviceAttribute.WHE_TYPE: WheType.LydosHybrid.value,
        },
    )
    client = MagicMock()
    client.async_connect = AsyncMock(return_value=True)
    client.async_hello = AsyncMock(return_value=device)
    _mock_client(monkeypatch, client)
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    heater_id = "water_heater.test_boiler"
    energy_id = (
        "sensor.test_boiler_ariston_domestic_"
        "hot_water_heating_pump_electricity_consumption"
    )
    coordinators = hass.data[DOMAIN][entry.unique_id]
    assert coordinators[COORDINATOR].last_update_success
    assert coordinators[BUS_ERRORS_COORDINATOR].last_update_success
    if fail_at_startup:
        assert not coordinators[ENERGY_COORDINATOR].last_update_success
        assert hass.states.get(energy_id) is None
    else:
        assert hass.states.get(energy_id).state == expected
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
        await hass.async_block_till_done()
        assert not coordinators[ENERGY_COORDINATOR].last_update_success
        assert hass.states.get(energy_id).state == STATE_UNAVAILABLE

    heater = hass.states.get(heater_id)
    assert heater is not None
    assert heater.state != STATE_UNAVAILABLE
    assert heater.attributes[ATTR_CURRENT_TEMPERATURE] == 48

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()

    assert coordinators[ENERGY_COORDINATOR].last_update_success
    assert hass.states.get(energy_id).state == expected
    assert hass.states.get(heater_id).state == heater.state


async def test_galevo_thermostat_recovers_after_menu_http_429(
    hass, enable_custom_integrations, monkeypatch
):
    """A thermostat publishes fresh data when cloud reads succeed again."""
    entry = _entry()
    api = MagicMock(spec=AristonAPI)
    api.async_get_features_for_device.return_value = {
        DeviceFeatures.ZONES: [{ZoneAttribute.NUM: 1, ZoneAttribute.NAME: "Living"}],
    }
    api.async_get_bus_errors.return_value = []
    api.async_get_menu_items.side_effect = [
        [],
        ConnectionException(429, b"Requests are blocked for 66 seconds"),
        [],
    ]

    def properties(measured_temperature):
        return {
            "items": [
                {
                    "id": DeviceProperties.PLANT_MODE,
                    PropertyType.ZONE: 0,
                    PropertyType.VALUE: PlantMode.WINTER.value,
                    PropertyType.OPTIONS: [PlantMode.WINTER.value],
                    PropertyType.OPT_TEXTS: ["Winter"],
                },
                {
                    "id": ThermostatProperties.ZONE_MODE,
                    PropertyType.ZONE: 1,
                    PropertyType.VALUE: ZoneMode.MANUAL.value,
                    PropertyType.OPTIONS: [ZoneMode.MANUAL.value],
                },
                {
                    "id": ThermostatProperties.ZONE_MEASURED_TEMP,
                    PropertyType.ZONE: 1,
                    PropertyType.VALUE: measured_temperature,
                    PropertyType.UNIT: "°C",
                    PropertyType.DECIMALS: 1,
                },
                {
                    "id": ThermostatProperties.ZONE_COMFORT_TEMP,
                    PropertyType.ZONE: 1,
                    PropertyType.MIN: 10,
                    PropertyType.MAX: 30,
                },
                {
                    "id": ThermostatProperties.ZONE_DESIRED_TEMP,
                    PropertyType.ZONE: 1,
                    PropertyType.VALUE: 21,
                    PropertyType.STEP: 0.5,
                },
            ]
        }

    api.async_get_properties.side_effect = [
        properties(19),
        properties(19),
        properties(20),
    ]
    device = AristonGalevoDevice(
        api,
        {
            **entry.data[CONF_DEVICE],
            DeviceAttribute.SYS: SystemType.GALEVO.value,
            DeviceAttribute.SN: "galevo-1",
            DeviceAttribute.HPMP_SYS: True,
        },
        is_metric=True,
        language_tag="en-US",
    )
    client = MagicMock()
    client.async_connect = AsyncMock(return_value=True)
    client.async_hello = AsyncMock(return_value=device)
    _mock_client(monkeypatch, client)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    thermostat_id = "climate.test_boiler"
    assert hass.states.get(thermostat_id).attributes[ATTR_CURRENT_TEMPERATURE] == 19

    coordinator = hass.data[DOMAIN][entry.unique_id][COORDINATOR]
    await coordinator.async_refresh()
    await coordinator.async_refresh()

    thermostat = hass.states.get(thermostat_id)
    assert api.async_get_menu_items.await_count == 3
    assert entry.state is ConfigEntryState.LOADED
    assert thermostat.state == "heat"
    assert thermostat.attributes[ATTR_CURRENT_TEMPERATURE] == 20


async def test_primary_refresh_failure_still_blocks_setup(hass, monkeypatch):
    device = _mock_device()
    device.async_update_state.side_effect = RuntimeError("primary endpoint failed")
    client = MagicMock()
    client.async_connect = AsyncMock(return_value=True)
    client.async_hello = AsyncMock(return_value=device)
    _mock_client(monkeypatch, client)
    forward_platforms = AsyncMock()
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", forward_platforms
    )
    entry = _entry()
    entry.add_to_hass(hass)
    entry._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)

    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)

    forward_platforms.assert_not_awaited()


async def test_bus_errors_auth_failure_starts_reauth(hass, monkeypatch):
    device = _mock_device()
    client = MagicMock()
    client.async_connect = AsyncMock(return_value=True)
    client.async_hello = AsyncMock(return_value=device)
    _mock_client(monkeypatch, client)
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", AsyncMock()
    )
    entry = _entry()
    entry.add_to_hass(hass)
    entry._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)

    assert await async_setup_entry(hass, entry)

    start_reauth = MagicMock()
    monkeypatch.setattr(
        type(entry),
        "async_start_reauth_if_available",
        lambda config_entry, target_hass: start_reauth(target_hass),
    )
    device.async_get_bus_errors.side_effect = ConfigEntryAuthFailed("expired")

    await hass.data[DOMAIN][entry.unique_id][BUS_ERRORS_COORDINATOR].async_refresh()

    start_reauth.assert_called_once_with(hass)


async def test_setup_skips_energy_coordinator_when_device_has_no_metering(
    hass, monkeypatch
):
    device = _mock_device(has_metering=False)
    client = MagicMock()
    client.async_connect = AsyncMock(return_value=True)
    client.async_hello = AsyncMock(return_value=device)
    _mock_client(monkeypatch, client)
    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", AsyncMock()
    )
    entry = _entry()
    entry.add_to_hass(hass)
    entry._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)

    assert await async_setup_entry(hass, entry)

    coordinators = hass.data[DOMAIN][entry.unique_id]
    assert set(coordinators) == {
        COORDINATOR,
        BUS_ERRORS_COORDINATOR,
        ENERGY_COORDINATOR,
    }
    assert coordinators[ENERGY_COORDINATOR] == {}
    assert coordinators[COORDINATOR].update_interval.total_seconds() == (
        DEFAULT_SCAN_INTERVAL_SECONDS
    )
    assert coordinators[BUS_ERRORS_COORDINATOR].update_interval.total_seconds() == (
        DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS
    )
    assert not hass.services.has_service(DOMAIN, SERVICE_SET_ITEM_BY_ID)


async def test_setup_raises_auth_error_when_cloud_rejects_credentials(
    hass, monkeypatch
):
    client = MagicMock()
    client.async_connect = AsyncMock(return_value=False)
    _mock_client(monkeypatch, client)
    entry = _entry()

    with pytest.raises(ConfigEntryAuthFailed):
        await async_setup_entry(hass, entry)


async def test_setup_wraps_unexpected_cloud_error_as_not_ready(hass, monkeypatch):
    client = MagicMock()
    client.async_connect = AsyncMock(side_effect=RuntimeError("cloud unavailable"))
    _mock_client(monkeypatch, client)
    entry = _entry()

    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)


async def test_setup_returns_false_when_device_is_not_found(hass, monkeypatch):
    client = MagicMock()
    client.async_connect = AsyncMock(return_value=True)
    client.async_hello = AsyncMock(return_value=None)
    _mock_client(monkeypatch, client)

    assert await async_setup_entry(hass, _entry()) is False
    client.async_hello.assert_awaited_once()


def test_set_item_by_id_schema_accepts_valid_payload():
    payload = {
        ATTR_DEVICE_ID: "device-1",
        ATTR_ITEM_ID: "comfort_temp",
        ATTR_ZONE: 1,
        ATTR_VALUE: 20,
    }

    validated = SET_ITEM_BY_ID_SCHEMA(payload)

    assert validated[ATTR_VALUE] == 20.0
    assert isinstance(validated[ATTR_VALUE], float)


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {ATTR_DEVICE_ID: "device-1", ATTR_ITEM_ID: "item", ATTR_ZONE: 0, ATTR_VALUE: 1},
        {ATTR_DEVICE_ID: "device-1", ATTR_ITEM_ID: "item", ATTR_ZONE: 1},
    ],
)
def test_set_item_by_id_schema_rejects_invalid_payload(invalid_payload):
    with pytest.raises(vol.Invalid):
        SET_ITEM_BY_ID_SCHEMA(invalid_payload)


async def test_unload_keeps_entry_data_when_platform_unload_fails(hass, monkeypatch):
    entry = _entry()
    hass.data[DOMAIN] = {entry.unique_id: {COORDINATOR: object()}}
    monkeypatch.setattr(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False)
    )

    assert await async_unload_entry(hass, entry) is False
    assert entry.unique_id in hass.data[DOMAIN]
