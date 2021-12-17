"""Suppoort for Ariston sensors."""
from __future__ import annotations

import logging
from homeassistant.components.sensor import SensorEntity

from homeassistant.const import (
    DEVICE_CLASS_PRESSURE,
    DEVICE_CLASS_TEMPERATURE,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from .coordinator import DeviceDataUpdateCoordinator


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston sensors from config entry."""
    coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id]

    ariston_sensors = []
    ariston_sensors.append(HeatingCircuitPressureSensor(coordinator))
    ariston_sensors.append(ChFlowSetpointTempSensor(coordinator))

    async_add_entities(ariston_sensors)


class AristonSensor(CoordinatorEntity, SensorEntity):
    """Base class for specific ariston sensors"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        name: str,
        device_class: str,
    ) -> None:
        """Initialize the sensor."""

        # Pass coordinator to CoordinatorEntity.
        super().__init__(coordinator)

        self.coordinator = coordinator
        self._name = name
        self._device_class = device_class

    @property
    def unique_id(self):
        """Return the unique id."""
        return f"{self.coordinator.device.gw_id}-{self.name}"

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def device_class(self):
        return self._device_class


class ChFlowSetpointTempSensor(AristonSensor):
    """Ch flow setpoint temperature sensor class"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator, "Ch flow setpoint temp", DEVICE_CLASS_TEMPERATURE)

    @property
    def native_value(self):
        """Return value of sensor."""
        return self.coordinator.device.ch_flow_setpoint_temp

    @property
    def native_unit_of_measurement(self):
        return self.coordinator.device.ch_flow_setpoint_temp_unit


class HeatingCircuitPressureSensor(AristonSensor):
    """Heating circuit pressure sensor class"""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
    ) -> None:
        super().__init__(coordinator, "Heating circuit pressure", DEVICE_CLASS_PRESSURE)

    @property
    def native_value(self):
        """Return value of sensor."""
        return self.coordinator.device.heating_circuit_pressure

    @property
    def native_unit_of_measurement(self):
        return self.coordinator.device.heating_circuit_pressure_unit
