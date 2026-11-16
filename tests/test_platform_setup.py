"""Tests for platform entity selection and zone expansion."""

from unittest.mock import AsyncMock, MagicMock

from ariston.const import WheType
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.ariston import (
    binary_sensor,
    climate,
    number,
    select,
    sensor,
    switch,
    water_heater,
)
from custom_components.ariston.binary_sensor import AristonBinarySensor
from custom_components.ariston.climate import AristonThermostat
from custom_components.ariston.const import (
    BUS_ERRORS_COORDINATOR,
    COORDINATOR,
    DOMAIN,
    ENERGY_COORDINATOR,
)
from custom_components.ariston.binary_sensor import SERVICE_CREATE_VACATION
from custom_components.ariston.number import AristonNumber
from custom_components.ariston.select import AristonSelect
from custom_components.ariston.sensor import AristonSensor
from custom_components.ariston.switch import AristonSwitch
from custom_components.ariston.water_heater import AristonWaterHeater


async def test_platforms_add_supported_entities_and_expand_zones(
    hass, coordinator, ariston_device
):
    ariston_device.zone_numbers = [1, 2]
    ariston_device.whe_type = WheType.Unknown

    def is_available(device_features, system_types, whe_types):
        return (not system_types or ariston_device.system_type in system_types) and (
            not whe_types or ariston_device.whe_type in whe_types
        )

    ariston_device.are_device_features_available = is_available
    ariston_device.async_set_holiday = AsyncMock()
    hass.data[DOMAIN] = {
        "entry-1": {
            COORDINATOR: coordinator,
            ENERGY_COORDINATOR: coordinator,
            BUS_ERRORS_COORDINATOR: coordinator,
        }
    }
    entry = MockConfigEntry(domain=DOMAIN, unique_id="entry-1", data={})
    entry.add_to_hass(hass)
    platforms = {
        "binary_sensor": (binary_sensor, AristonBinarySensor),
        "climate": (climate, AristonThermostat),
        "number": (number, AristonNumber),
        "select": (select, AristonSelect),
        "sensor": (sensor, AristonSensor),
        "switch": (switch, AristonSwitch),
        "water_heater": (water_heater, AristonWaterHeater),
    }

    added_by_platform = {}
    for platform_name, (platform, entity_type) in platforms.items():
        added = []

        def add_entities(entities):
            for entity in entities:
                entity.async_write_ha_state = MagicMock()
            added.extend(entities)

        await platform.async_setup_entry(
            hass, entry, add_entities
        )
        assert added
        assert all(isinstance(entity, entity_type) for entity in added)
        added_by_platform[platform_name] = added

    assert len(added_by_platform["climate"]) == 2
    assert {
        entity.unique_id for entity in added_by_platform["climate"]
    } == {"gateway-1_1", "gateway-1_2"}
    assert len(added_by_platform["water_heater"]) == 1
    zone_numbers = [entity for entity in added_by_platform["number"] if entity.zone]
    assert {entity.zone for entity in zone_numbers} == {1, 2}

    registered_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "serial-1")},
        name="Test boiler",
    )
    await hass.services.async_call(
        DOMAIN,
        SERVICE_CREATE_VACATION,
        {ATTR_DEVICE_ID: registered_device.id},
        blocking=True,
    )
    ariston_device.async_set_holiday.assert_awaited_once_with(None)
