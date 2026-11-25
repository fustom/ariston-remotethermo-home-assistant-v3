"""Regression tests for the Nuos Split plant mode (Manual / Program) selector."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ariston.const import (
    DeviceAttribute,
    NuosSplitPlantMode,
    NuosSplitProperties,
    SystemType,
    VelisDeviceAttribute,
    WheType,
)
from ariston.evo_one_device import AristonEvoOneDevice
from ariston.lydos_hybrid_device import AristonLydosHybridDevice
from ariston.nuos_split_device import AristonNuosSplitDevice
from pytest_homeassistant.common import MockConfigEntry

from custom_components.ariston import select
from custom_components.ariston.const import (
    BUS_ERRORS_COORDINATOR,
    COORDINATOR,
    DOMAIN,
    ENERGY_COORDINATOR,
)
from custom_components.ariston.coordinator import DeviceDataUpdateCoordinator
from custom_components.ariston.select import AristonSelect

PLANT_MODE_NAME = "plant mode"


def _make_velis_device(device_cls, whe_type: WheType):
    """Build a real library device with a mocked cloud API."""
    api = MagicMock()
    api.async_set_nuos_plant_mode_via_r2 = AsyncMock()
    return device_cls(
        api,
        {
            DeviceAttribute.GW: "gateway-1",
            DeviceAttribute.NAME: "Test water heater",
            DeviceAttribute.SN: "serial-1",
            DeviceAttribute.SYS: SystemType.VELIS.value,
            VelisDeviceAttribute.WHE_TYPE: whe_type.value,
        },
    )


async def _setup_selects(hass, device) -> list[AristonSelect]:
    """Run select.async_setup_entry for one device and return the entities."""
    coordinator = DeviceDataUpdateCoordinator(hass, device, 300, "test", AsyncMock())
    coordinator.async_request_refresh = AsyncMock()
    hass.data[DOMAIN] = {
        "entry-1": {
            COORDINATOR: coordinator,
            ENERGY_COORDINATOR: coordinator,
            BUS_ERRORS_COORDINATOR: coordinator,
        }
    }
    entry = MockConfigEntry(domain=DOMAIN, unique_id="entry-1", data={})
    entry.add_to_hass(hass)

    added: list[AristonSelect] = []
    await select.async_setup_entry(hass, entry, added.extend)
    return added


def _plant_mode_selects(entities: list[AristonSelect]) -> list[AristonSelect]:
    return [entity for entity in entities if entity.name.endswith(PLANT_MODE_NAME)]


async def test_nuos_split_gets_plant_mode_selector(hass):
    device = _make_velis_device(AristonNuosSplitDevice, WheType.NuosSplit)
    device.data[NuosSplitProperties.MODE] = NuosSplitPlantMode.MANUAL.value

    entities = await _setup_selects(hass, device)
    plant_mode = _plant_mode_selects(entities)

    assert len(plant_mode) == 1
    entity = plant_mode[0]
    assert entity.entity_description.key == NuosSplitProperties.MODE
    assert entity.options == ["MANUAL", "PROGRAM"]
    assert entity.current_option == "MANUAL"


async def test_selecting_program_calls_plant_mode_setter(hass):
    device = _make_velis_device(AristonNuosSplitDevice, WheType.NuosSplit)
    device.data[NuosSplitProperties.MODE] = NuosSplitPlantMode.MANUAL.value
    entity = _plant_mode_selects(await _setup_selects(hass, device))[0]

    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_select_option("PROGRAM")

    device.api.async_set_nuos_plant_mode_via_r2.assert_awaited_once_with(
        "gateway-1", NuosSplitPlantMode.PROGRAM
    )
    assert entity.current_option == "PROGRAM"
    entity.coordinator.async_request_refresh.assert_awaited_once()
    write_state.assert_called_once()


@pytest.mark.parametrize(
    ("device_cls", "whe_type"),
    [
        (AristonEvoOneDevice, WheType.Evo),
        (AristonLydosHybridDevice, WheType.LydosHybrid),
    ],
)
async def test_other_velis_models_do_not_get_plant_mode_selector(
    hass, device_cls, whe_type
):
    device = _make_velis_device(device_cls, whe_type)

    entities = await _setup_selects(hass, device)

    assert _plant_mode_selects(entities) == []
    device.api.async_set_nuos_plant_mode_via_r2.assert_not_called()
