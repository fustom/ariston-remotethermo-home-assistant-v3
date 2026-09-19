"""Entity object for shared properties of Ariston entities."""

from __future__ import annotations

import logging
from abc import ABC
from typing import Any

from ariston.const import WheType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    EXTRA_STATE_ATTRIBUTE,
    EXTRA_STATE_DEVICE_METHOD,
    AristonBaseEntityDescription,
)
from .coordinator import DeviceDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def description_is_supported(
    coordinator: DeviceDataUpdateCoordinator,
    description: AristonBaseEntityDescription,
) -> bool:
    """Return whether a coordinator supports an entity description."""
    if not coordinator.device.are_device_features_available(
        description.device_features,
        description.system_types,
        description.whe_types,
    ):
        return False
    return (
        description.get_is_supported is None
        or description.get_is_supported(coordinator)
    )


def get_coordinator_for_description(
    hass: Any, entry: Any, description: AristonBaseEntityDescription
) -> DeviceDataUpdateCoordinator | None:
    """Return a supported coordinator or skip a missing optional data source."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.unique_id, {})
    coordinator = entry_data.get(description.coordinator)
    if (
        coordinator is None
        or getattr(coordinator, "device", None) is None
        or not description_is_supported(coordinator, description)
    ):
        return None
    return coordinator


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
    def available(self) -> bool:
        """Return whether coordinator data and entity-specific state are usable."""
        return super().available and (
            self.entity_description.get_is_available is None
            or self.entity_description.get_is_available(self)
        )

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
