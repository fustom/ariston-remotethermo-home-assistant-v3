"""Support for Ariston sensors."""

from __future__ import annotations

import logging

import voluptuous as vol

from ariston.const import DeviceProperties, SystemType
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    ARISTON_BINARY_SENSOR_TYPES,
    COORDINATOR,
    DOMAIN,
    AristonBinarySensorEntityDescription,
)
from .coordinator import DeviceDataUpdateCoordinator
from .entity import AristonEntity, is_entity_description_available

_LOGGER = logging.getLogger(__name__)

SERVICE_CREATE_VACATION = "create_vacation"
ATTR_END_DATE = "end_date"

CREATE_VACATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_END_DATE): cv.date,
    }
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston binary sensors from config entry."""
    ariston_binary_sensors: list[AristonBinarySensor] = []
    main_coordinator: DeviceDataUpdateCoordinator | None = hass.data[DOMAIN][
        entry.unique_id
    ].get(COORDINATOR)

    for description in ARISTON_BINARY_SENSOR_TYPES:
        coordinator: DeviceDataUpdateCoordinator | None = hass.data[DOMAIN][
            entry.unique_id
        ].get(description.coordinator)
        if is_entity_description_available(coordinator, description):
            if description.zone:
                for zone_number in coordinator.device.zone_numbers:
                    ariston_binary_sensors.append(
                        AristonBinarySensor(coordinator, description, zone_number)
                    )
            else:
                ariston_binary_sensors.append(
                    AristonBinarySensor(coordinator, description)
                )

    async_add_entities(ariston_binary_sensors)

    if main_coordinator and main_coordinator.device.system_type == SystemType.GALEVO:

        async def async_create_vacation_service(service_call):
            """Create a vacation on the target device."""
            device_id = service_call.data.get(ATTR_DEVICE_ID)
            end_date = service_call.data.get(ATTR_END_DATE)

            device_registry = dr.async_get(hass)
            device = device_registry.devices[device_id]

            entry = hass.config_entries.async_get_entry(
                next(iter(device.config_entries))
            )
            coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][
                entry.unique_id
            ][COORDINATOR]
            await coordinator.device.async_set_holiday(end_date)
            await coordinator.async_request_refresh()
            for ariston_binary_sensor in ariston_binary_sensors:
                if (
                    ariston_binary_sensor.entity_description.key
                    is DeviceProperties.HOLIDAY
                ):
                    ariston_binary_sensor.async_write_ha_state()

        hass.services.async_register(
            DOMAIN,
            SERVICE_CREATE_VACATION,
            async_create_vacation_service,
            schema=CREATE_VACATION_SCHEMA,
        )


class AristonBinarySensor(AristonEntity, BinarySensorEntity):
    """Base class for specific ariston binary sensors."""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonBinarySensorEntityDescription,
        zone: int = 0,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description, zone)

    @property
    def name(self):
        """Return the name of the entity."""
        if self.zone:
            return f"{self.entity_description.name} {self.zone}"
        return self.entity_description.name

    @property
    def is_on(self):
        """Return True if the binary sensor is on."""
        return self.entity_description.get_is_on(self)
