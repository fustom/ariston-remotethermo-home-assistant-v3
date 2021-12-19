"""Support for Ariston water heaters."""
from __future__ import annotations

import logging

from .ariston import DeviceAttribute, DeviceFeatures, DeviceProperties, PropertyType
from .const import DOMAIN
from .coordinator import DeviceDataUpdateCoordinator

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.water_heater import (
    SUPPORT_OPERATION_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    WaterHeaterEntity,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the Ariston water heater device from config entry."""
    coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id]
    async_add_entities([AristonWaterHeater(coordinator)])
    return


class AristonWaterHeater(CoordinatorEntity, WaterHeaterEntity):
    """Ariston Water Heater Device."""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
    ) -> None:
        """Initialize the thermostat."""

        # Pass coordinator to CoordinatorEntity.
        super().__init__(coordinator)

        self.coordinator = coordinator

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self.coordinator.device.attributes[DeviceAttribute.PLANT_NAME]

    @property
    def unique_id(self) -> str:
        """Return a unique id for the device."""
        return (
            f"{self.coordinator.device.attributes[DeviceAttribute.GW_ID]}-water_heater"
        )

    @property
    def icon(self):
        return "mdi:water-pump"

    @property
    def current_temperature(self):
        """Return the temperature"""
        return self.coordinator.device.get_item_by_id(
            DeviceProperties.DHW_TEMP, PropertyType.VALUE
        )

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self.coordinator.device.get_item_by_id(
            DeviceProperties.DHW_TEMP, PropertyType.MIN
        )

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.coordinator.device.get_item_by_id(
            DeviceProperties.DHW_TEMP, PropertyType.VALUE
        )

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self.coordinator.device.get_item_by_id(
            DeviceProperties.DHW_TEMP, PropertyType.MAX
        )

    @property
    def precision(self) -> float:
        """Return the precision of temperature for the device."""
        return 1 / 10 ** self.coordinator.device.get_item_by_id(
            DeviceProperties.DHW_TEMP, PropertyType.DECIMALS
        )

    @property
    def target_temperature_step(self):
        """Return the target temperature step support by the device.
        !!! WaterHeaterEntity does not support this property. I don't really understand why."""
        return self.coordinator.device.get_item_by_id(
            DeviceProperties.DHW_TEMP, PropertyType.STEP
        )

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self.coordinator.device.get_item_by_id(
            DeviceProperties.DHW_TEMP, PropertyType.UNIT
        )

    @property
    def supported_features(self) -> int:
        """Return the supported features for this device integration."""
        if self.coordinator.device.features[DeviceFeatures.DHW_MODE_CHANGEABLE]:
            return SUPPORT_TARGET_TEMPERATURE | SUPPORT_OPERATION_MODE
        return SUPPORT_TARGET_TEMPERATURE

    @property
    def operation_list(self):
        """List of available operation modes."""
        return self.coordinator.device.get_item_by_id(
            DeviceProperties.DHW_MODE, PropertyType.OPT_TEXTS
        )

    @property
    def current_operation(self):
        """Return current operation"""
        res = self.coordinator.device.get_item_by_id(
            DeviceProperties.DHW_MODE, PropertyType.OPTIONS
        ).index(
            self.coordinator.device.get_item_by_id(
                DeviceProperties.DHW_MODE, PropertyType.VALUE
            )
        )

        return self.coordinator.device.get_item_by_id(
            DeviceProperties.DHW_MODE, PropertyType.OPT_TEXTS
        )[res]

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            raise ValueError(f"Missing parameter {ATTR_TEMPERATURE}")

        temperature = kwargs[ATTR_TEMPERATURE]
        _LOGGER.debug(
            "Setting temperature to %d for %s",
            temperature,
            self.name,
        )

        await self.coordinator.device.set_item_by_id(
            DeviceProperties.DHW_TEMP, temperature
        )
        self.async_write_ha_state()

    async def async_set_operation_mode(self, operation_mode):
        """Set operation mode."""
        await self.coordinator.device.set_item_by_id(
            DeviceProperties.DHW_MODE, operation_mode
        )
        self.async_write_ha_state()
