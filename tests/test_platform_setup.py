"""Tests for platform entity selection and zone expansion."""

from unittest.mock import AsyncMock, MagicMock

from ariston.ariston_api import ConnectionException
from ariston.const import (
    DeviceAttribute,
    DeviceFeatures,
    MenuItemNames,
    PropertyType,
    SystemType,
    WheType,
    ZoneAttribute,
)
from ariston.galevo_device import AristonGalevoDevice
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
    MENU_ITEM_CH_BACKUP_RESISTANCE_1,
    MENU_ITEM_HP_MODE,
    MENU_ITEM_HP_OUTSIDE_AIR_TEMP,
    MENU_ITEM_HP_WATER_FLOW_TEMP,
)
from custom_components.ariston.coordinator import DeviceDataUpdateCoordinator
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


def _make_real_galevo_device(menu_side_effect):
    api = MagicMock()
    api.async_get_properties = AsyncMock(return_value={"items": []})
    api.async_get_menu_items = AsyncMock(side_effect=menu_side_effect)
    device = AristonGalevoDevice(
        api,
        {
            DeviceAttribute.GW: "gateway-1",
            DeviceAttribute.NAME: "Test heat pump",
            DeviceAttribute.SN: "serial-1",
            DeviceAttribute.SYS: SystemType.GALEVO.value,
        },
    )
    device.features = {
        DeviceFeatures.HP_SYS: True,
        DeviceFeatures.ZONES: [{ZoneAttribute.NUM: 1}],
    }
    return device


async def test_menu_item_feature_gating_with_real_device_hides_missing_items(hass):
    device = _make_real_galevo_device(
        [
            [
                {
                    "id": MenuItemNames.SIGNAL_STRENGTH.value,
                    PropertyType.VALUE: 80,
                    PropertyType.UNIT: "%",
                },
                {
                    "id": MenuItemNames.CH_RETURN_TEMP.value,
                    PropertyType.VALUE: 3276.0,
                    PropertyType.UNIT: "°C",
                },
            ]
        ]
    )
    real_coordinator = DeviceDataUpdateCoordinator(
        hass, device, 300, COORDINATOR, device.async_update_state
    )
    await real_coordinator.async_refresh()

    hass.data[DOMAIN] = {
        "entry-1": {
            COORDINATOR: real_coordinator,
            ENERGY_COORDINATOR: real_coordinator,
            BUS_ERRORS_COORDINATOR: real_coordinator,
        }
    }
    entry = MockConfigEntry(domain=DOMAIN, unique_id="entry-1", data={})
    entry.add_to_hass(hass)

    added_sensors = []
    await sensor.async_setup_entry(hass, entry, added_sensors.extend)
    sensor_keys = {entity.entity_description.key for entity in added_sensors}
    assert str(MenuItemNames.SIGNAL_STRENGTH) in sensor_keys
    assert {
        str(MenuItemNames.CH_RETURN_TEMP),
        str(MENU_ITEM_HP_WATER_FLOW_TEMP),
        str(MENU_ITEM_HP_OUTSIDE_AIR_TEMP),
        str(MENU_ITEM_HP_MODE),
    }.isdisjoint(sensor_keys)

    added_binary_sensors = []
    await binary_sensor.async_setup_entry(hass, entry, added_binary_sensors.extend)
    binary_keys = {entity.entity_description.key for entity in added_binary_sensors}
    assert str(MENU_ITEM_CH_BACKUP_RESISTANCE_1) not in binary_keys

    await real_coordinator.async_shutdown()


async def test_delayed_menu_recovery_registers_entities_after_initial_http_550(hass):
    recovered_menu = [
        {
            "id": MenuItemNames.SIGNAL_STRENGTH.value,
            PropertyType.VALUE: 80,
            PropertyType.UNIT: "%",
        },
        {
            "id": MenuItemNames.CH_RETURN_TEMP.value,
            PropertyType.VALUE: 27.5,
            PropertyType.UNIT: "°C",
        },
        {
            "id": MENU_ITEM_CH_BACKUP_RESISTANCE_1,
            PropertyType.VALUE: 0.0,
        },
        {
            "id": MENU_ITEM_HP_MODE,
            PropertyType.VALUE: 3.0,
            PropertyType.OPTIONS: {"3": "Heating"},
        },
        {
            "id": MENU_ITEM_HP_OUTSIDE_AIR_TEMP,
            PropertyType.VALUE: 2.0,
            PropertyType.UNIT: "°C",
        },
        {
            "id": MENU_ITEM_HP_WATER_FLOW_TEMP,
            PropertyType.VALUE: 31.0,
            PropertyType.UNIT: "°C",
        },
    ]
    device = _make_real_galevo_device(
        [ConnectionException(550), recovered_menu, recovered_menu]
    )
    real_coordinator = DeviceDataUpdateCoordinator(
        hass, device, 300, COORDINATOR, device.async_update_state
    )
    await real_coordinator.async_refresh()

    hass.data[DOMAIN] = {
        "entry-1": {
            COORDINATOR: real_coordinator,
            ENERGY_COORDINATOR: real_coordinator,
            BUS_ERRORS_COORDINATOR: real_coordinator,
        }
    }
    entry = MockConfigEntry(domain=DOMAIN, unique_id="entry-1", data={})
    entry.add_to_hass(hass)

    sensor_calls = []
    await sensor.async_setup_entry(hass, entry, lambda entities: sensor_calls.append(list(entities)))
    initial_sensor_keys = {e.entity_description.key for e in sensor_calls[0]}
    assert {
        str(MenuItemNames.CH_RETURN_TEMP),
        str(MENU_ITEM_HP_WATER_FLOW_TEMP),
        str(MENU_ITEM_HP_OUTSIDE_AIR_TEMP),
        str(MENU_ITEM_HP_MODE),
    }.isdisjoint(initial_sensor_keys)

    binary_calls = []
    await binary_sensor.async_setup_entry(hass, entry, lambda entities: binary_calls.append(list(entities)))
    initial_binary_keys = {e.entity_description.key for e in binary_calls[0]}
    assert str(MENU_ITEM_CH_BACKUP_RESISTANCE_1) not in initial_binary_keys

    # Next poll recovers from HTTP 550 and dynamically adds the newly supported entities
    await real_coordinator.async_refresh()
    assert len(sensor_calls) == 2
    recovered_sensor_keys = {e.entity_description.key for e in sensor_calls[1]}
    assert {
        str(MenuItemNames.CH_RETURN_TEMP),
        str(MENU_ITEM_HP_WATER_FLOW_TEMP),
        str(MENU_ITEM_HP_OUTSIDE_AIR_TEMP),
        str(MENU_ITEM_HP_MODE),
    }.issubset(recovered_sensor_keys)

    assert len(binary_calls) == 2
    recovered_binary_keys = {e.entity_description.key for e in binary_calls[1]}
    assert str(MENU_ITEM_CH_BACKUP_RESISTANCE_1) in recovered_binary_keys

    # Subsequent polls do not re-register already added entities
    await real_coordinator.async_refresh()
    assert len(sensor_calls) == 2
    assert len(binary_calls) == 2

    await real_coordinator.async_shutdown()

