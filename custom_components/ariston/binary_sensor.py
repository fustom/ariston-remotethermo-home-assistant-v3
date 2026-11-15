"""Support for Ariston sensors."""

from __future__ import annotations

import logging

import voluptuous as vol

from ariston.const import DeviceProperties, NuosSplitProperties
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

    # Register create_vacation whenever the device exposes a holiday setter
    # (Galevo natively, Velis Slp/Nuos via the library's async_set_holiday).
    if main_coordinator and hasattr(main_coordinator.device, "async_set_holiday"):

        async def async_create_vacation_service(service_call):
            """Create a vacation on the target device."""
            device_id = service_call.data.get(ATTR_DEVICE_ID)
            end_date = service_call.data.get(ATTR_END_DATE)

            device_registry = dr.async_get(hass)
            device = device_registry.devices[device_id]

            target_entry = hass.config_entries.async_get_entry(
                next(iter(device.config_entries))
            )
            target_coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][
                target_entry.unique_id
            ][COORDINATOR]
            await target_coordinator.device.async_set_holiday(end_date)
            # Pull the latest plant data so the holiday end-date sensor and any
            # other consumer of `device.data` reflect the change without
            # waiting for the next scheduled poll.
            await target_coordinator.async_request_refresh()
            for ariston_binary_sensor in ariston_binary_sensors:
                key = ariston_binary_sensor.entity_description.key
                if key in (DeviceProperties.HOLIDAY, NuosSplitProperties.HOLIDAY_UNTIL):
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
