"""Entity object for shared properties of Ariston entities."""
from __future__ import annotations

import logging

from abc import ABC


from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    EXTRA_STATE_ATTRIBUTE,
    EXTRA_STATE_METHOD_NAME,
    AristonBaseEntityDescription,
)
from .ariston import DeviceAttribute, GalevoDeviceAttribute, SystemType
from .coordinator import DeviceDataUpdateCoordinator, DeviceEnergyUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class AristonEntity(CoordinatorEntity, ABC):
    """Generic Ariston entity (base class)."""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator or DeviceEnergyUpdateCoordinator,
        description: AristonBaseEntityDescription,
        zone: int = None,
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
            identifiers={(DOMAIN, self.device.attributes.get(DeviceAttribute.SN))},
            manufacturer=DOMAIN,
            name=self.device.attributes.get(DeviceAttribute.NAME),
            sw_version=self.device.attributes.get(GalevoDeviceAttribute.FW_VER),
            model=SystemType(self.device.attributes.get(DeviceAttribute.SYS)).name,
        )

    @property
    def extra_state_attributes(self):
        """Return the holiday end date."""
        state_attributes = {}

        if self.entity_description.extra_states is None:
            return None

        for extra_state in self.entity_description.extra_states:
            method_name = extra_state.get(EXTRA_STATE_METHOD_NAME)
            if method_name is not None:
                method = getattr(self.device, method_name)
                state_attributes[extra_state.get(EXTRA_STATE_ATTRIBUTE)] = (
                    method() if self.zone is None else method(self.zone)
                )

        return state_attributes

    @property
    def unique_id(self):
        """Return the unique id."""
        return f"{self.device.attributes.get(DeviceAttribute.GW)}-{self.name}"
