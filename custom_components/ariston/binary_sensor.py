"""Support for Ariston sensors."""

from __future__ import annotations

import logging

import voluptuous as vol

from ariston.const import DeviceProperties, NuosSplitProperties
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    ARISTON_BINARY_SENSOR_TYPES,
    COORDINATOR,
    DOMAIN,
    AristonBinarySensorEntityDescription,
)
from .coordinator import DeviceDataUpdateCoordinator
from .entity import AristonEntity, register_supported_entities

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

    register_supported_entities(
        hass,
        entry,
        ARISTON_BINARY_SENSOR_TYPES,
        lambda coordinator, description, zone=0: AristonBinarySensor(
            coordinator, description, zone
        ),
        async_add_entities,
        registered_entities=ariston_binary_sensors,
    )

    # Register create_vacation whenever the device exposes a holiday setter
    # (Galevo natively, Velis Slp/Nuos via the library's async_set_holiday).
    if main_coordinator and hasattr(main_coordinator.device, "async_set_holiday"):

        async def async_create_vacation_service(service_call):
            """Create a vacation on the target device."""
            device_id = service_call.data.get(ATTR_DEVICE_ID)
            end_date = service_call.data.get(ATTR_END_DATE)

            device_registry = dr.async_get(hass)
            device = device_registry.devices.get(device_id)
            if device is None:
                raise ServiceValidationError(f"Device {device_id} not found")

            target_coordinator: DeviceDataUpdateCoordinator | None = None
            for entry_id in device.config_entries:
                target_entry = hass.config_entries.async_get_entry(entry_id)
                if target_entry is None or target_entry.domain != DOMAIN:
                    continue
                target_coordinator = (
                    hass.data.get(DOMAIN, {})
                    .get(target_entry.unique_id, {})
                    .get(COORDINATOR)
                )
                if target_coordinator is not None:
                    break

            set_holiday = getattr(
                getattr(target_coordinator, "device", None),
                "async_set_holiday",
                None,
            )
            if set_holiday is None:
                raise ServiceValidationError(
                    f"Device {device.name_by_user or device.name or device_id} "
                    "does not support holiday mode"
                )
            await set_holiday(end_date)
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
