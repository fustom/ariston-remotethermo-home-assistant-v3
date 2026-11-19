"""Entity object for shared properties of Ariston entities."""

from __future__ import annotations

from abc import ABC
from collections.abc import Callable, Sequence
import logging
from typing import Any

from ariston.const import WheType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    EXTRA_STATE_ATTRIBUTE,
    EXTRA_STATE_DEVICE_METHOD,
    AristonBaseEntityDescription,
)
from .coordinator import DeviceDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def is_entity_description_available(
    coordinator: DeviceDataUpdateCoordinator | None,
    description: AristonBaseEntityDescription,
) -> bool:
    """Return True if the entity description is supported by the device."""
    return bool(
        coordinator
        and coordinator.device
        and coordinator.device.are_device_features_available(
            description.device_features,
            description.system_types,
            description.whe_types,
        )
    )


def register_supported_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    descriptions: Sequence[AristonBaseEntityDescription],
    create_entity: Callable[[DeviceDataUpdateCoordinator, Any, int], CoordinatorEntity],
    async_add_entities: AddEntitiesCallback,
    registered_entities: list[Any] | None = None,
) -> None:
    """Register currently supported entities and add newly discovered ones on future refreshes."""
    entry_data = hass.data[DOMAIN][entry.unique_id]
    added_keys: set[tuple[str, int]] = set()

    def _collect_new_entities() -> list[Any]:
        new_entities: list[Any] = []
        for description in descriptions:
            coordinator: DeviceDataUpdateCoordinator | None = entry_data.get(
                description.coordinator
            )
            if not is_entity_description_available(coordinator, description):
                continue
            zones = (
                coordinator.device.zone_numbers
                if getattr(description, "zone", False)
                else (0,)
            )
            for zone_number in zones:
                entity_key = (description.key, zone_number)
                if entity_key in added_keys:
                    continue
                added_keys.add(entity_key)
                new_entities.append(
                    create_entity(coordinator, description, zone_number)
                )
        return new_entities

    initial_entities = _collect_new_entities()
    if registered_entities is not None:
        registered_entities.extend(initial_entities)
    async_add_entities(initial_entities)

    @callback
    def _async_add_newly_supported_entities() -> None:
        new_entities = _collect_new_entities()
        if new_entities:
            if registered_entities is not None:
                registered_entities.extend(new_entities)
            async_add_entities(new_entities)

    seen_coordinators: set[int] = set()
    for description in descriptions:
        coordinator: DeviceDataUpdateCoordinator | None = entry_data.get(
            description.coordinator
        )
        if (
            coordinator is None
            or id(coordinator) in seen_coordinators
            or not hasattr(coordinator, "async_add_listener")
        ):
            continue
        seen_coordinators.add(id(coordinator))
        entry.async_on_unload(
            coordinator.async_add_listener(_async_add_newly_supported_entities)
        )


async def async_refresh_after_set(entity: CoordinatorEntity) -> None:
    """Refresh state after a write call, then publish the latest known state."""
    await entity.coordinator.async_request_refresh()
    entity.async_write_ha_state()


class AristonEntity(CoordinatorEntity, ABC):
    """Generic Ariston entity (base class)."""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonBaseEntityDescription,
        zone: int = 0,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)

        self.device = coordinator.device
        self.entity_description: AristonBaseEntityDescription = description
        self.zone = zone

    @property
    def device_info(self) -> DeviceInfo:
        """Return device specific attributes."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device.serial_number or "")},
            manufacturer=DOMAIN,
            name=self.device.name,
            sw_version=self.device.firmware_version,
            model=self.model,
        )

    @property
    def name(self) -> str:
        """Return the description name, falling back to the device name."""
        description_name = self.entity_description.name
        if isinstance(description_name, str) and description_name:
            return description_name
        return self.device.name or ""

    @property
    def model(self) -> str:
        """Return the model of the entity."""
        if self.device.whe_model_type == 0:
            if self.device.whe_type is WheType.Unknown:
                return f"{self.device.system_type.name}"
            return f"{self.device.system_type.name} {self.device.whe_type.name}"
        return f"{self.device.system_type.name} {self.device.whe_type.name} | Model {self.device.whe_model_type}"

    @property
    def extra_state_attributes(self):
        """Return the holiday end date."""
        state_attributes = {}

        if self.entity_description.extra_states is None:
            return None

        for extra_state in self.entity_description.extra_states:
            device_method = extra_state.get(EXTRA_STATE_DEVICE_METHOD)

            if device_method is None:
                continue

            state_attribute = device_method(self)

            if state_attribute is None:
                continue

            state_attributes[extra_state.get(EXTRA_STATE_ATTRIBUTE)] = state_attribute

        return state_attributes

    @property
    def unique_id(self):
        """Return the unique id."""
        return (
            f"{self.device.gateway}-{self.name}-{self.zone}"
            if self.zone
            else f"{self.device.gateway}-{self.name}"
        )
