"""Entity object for shared properties of Ariston entities."""
from __future__ import annotations

import logging

from abc import ABC

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .ariston import DeviceAttribute

_LOGGER = logging.getLogger(__name__)


class AristonEntity(CoordinatorEntity, ABC):
    """Generic Ariston entity (base class)."""

    def __init__(self, coordinator: DataUpdateCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device specific attributes."""
        return DeviceInfo(
            identifiers={
                (DOMAIN, self.coordinator.device.attributes[DeviceAttribute.GW_SERIAL])
            },
            manufacturer=DOMAIN,
            name=self.coordinator.device.attributes[DeviceAttribute.PLANT_NAME],
            sw_version=self.coordinator.device.attributes[DeviceAttribute.GW_FW_VER],
            model=self.coordinator.device.attributes[DeviceAttribute.PLANT_NAME],
        )
