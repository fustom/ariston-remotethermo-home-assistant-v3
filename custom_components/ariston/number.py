"""Support for Ariston sensors."""

from __future__ import annotations

import logging
from math import isfinite
from typing import Any

from ariston.const import ThermostatProperties
from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    ARISTON_NUMBER_TYPES,
    DOMAIN,
    AristonNumberEntityDescription,
    get_flow_fallback_zones,
)
from .coordinator import DeviceDataUpdateCoordinator
from .entity import (
    AristonEntity,
    async_refresh_after_set,
    is_entity_description_available,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston binary sensors from config entry."""
    ariston_numbers: list[AristonNumber] = []
    registered_unique_ids: set[str] = set()
    fallback_descriptions_by_coordinator: dict[
        DeviceDataUpdateCoordinator, list[AristonNumberEntityDescription]
    ] = {}

    def add_number(entity: AristonNumber) -> None:
        if entity.unique_id not in registered_unique_ids:
            registered_unique_ids.add(entity.unique_id)
            ariston_numbers.append(entity)

    for description in ARISTON_NUMBER_TYPES:
        coordinator: DeviceDataUpdateCoordinator | None = hass.data[DOMAIN][
            entry.unique_id
        ].get(description.coordinator)
        if is_entity_description_available(coordinator, description):
            if description.zone:
                for zone_number in coordinator.device.zone_numbers:
                    add_number(
                        AristonNumber(coordinator, description, zone_number)
                    )
                if description.key in (
                    ThermostatProperties.HEATING_FLOW_TEMP,
                    ThermostatProperties.HEATING_FLOW_OFFSET,
                ):
                    fallback_descriptions_by_coordinator.setdefault(
                        coordinator, []
                    ).append(description)
                    for zone_number in get_flow_fallback_zones(
                        coordinator.device.zone_numbers
                    ):
                        entity = AristonNumber(coordinator, description, zone_number)
                        if _is_valid_flow_zone(entity):
                            add_number(entity)
            else:
                add_number(AristonNumber(coordinator, description))

    async_add_entities(ariston_numbers)

    for coordinator, descriptions in fallback_descriptions_by_coordinator.items():

        def add_new_fallback_numbers(
            coordinator=coordinator,
            descriptions=descriptions,
        ) -> None:
            new_entities = []
            for description in descriptions:
                for zone_number in get_flow_fallback_zones(
                    coordinator.device.zone_numbers
                ):
                    entity = AristonNumber(coordinator, description, zone_number)
                    if (
                        entity.unique_id not in registered_unique_ids
                        and _is_valid_flow_zone(entity)
                    ):
                        registered_unique_ids.add(entity.unique_id)
                        new_entities.append(entity)
            if new_entities:
                async_add_entities(new_entities)

        entry.async_on_unload(coordinator.async_add_listener(add_new_fallback_numbers))


def _is_valid_flow_zone(entity: AristonNumber) -> bool:
    """Require complete, valid API data before adding a fallback flow control."""
    try:
        values = (
            entity.native_min_value,
            entity.native_max_value,
            entity.native_step,
            entity.native_value,
        )
    except Exception:
        _LOGGER.exception(
            "Unable to read %s for zone %s", entity.entity_description.key, entity.zone
        )
        return False

    try:
        minimum, maximum, step, value = (float(item) for item in values)
    except (TypeError, ValueError, OverflowError):
        return False

    return (
        all(isfinite(item) for item in (minimum, maximum, step, value))
        and minimum <= maximum
        and step > 0
        and minimum <= value <= maximum
    )


def _finite_float(value: Any) -> float | None:
    """Return finite number values as floats, rejecting invalid API data."""
    if value is None:
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric_value if isfinite(numeric_value) else None


class AristonNumber(AristonEntity, NumberEntity):
    """Base class for specific ariston binary sensors."""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonNumberEntityDescription,
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
    def native_value(self):
        """Return the current value."""
        return self.entity_description.get_native_value(self)

    @property
    def native_min_value(self):
        """Return the minimum value."""
        if self.entity_description.get_native_min_value is not None:
            value = self.entity_description.get_native_min_value(self)
        else:
            value = self.entity_description.native_min_value

        return _finite_float(value)

    @property
    def native_max_value(self):
        """Return the maximum value."""
        if self.entity_description.get_native_max_value is not None:
            value = self.entity_description.get_native_max_value(self)
        else:
            value = self.entity_description.native_max_value

        return _finite_float(value)

    @property
    def native_step(self):
        """Return the step value."""
        if self.entity_description.get_native_step is not None:
            value = self.entity_description.get_native_step(self)
        else:
            value = self.entity_description.native_step

        return _finite_float(value)

    async def async_set_native_value(self, value: float):
        """Update the current value."""
        await self.entity_description.set_native_value(self, value)
        await async_refresh_after_set(self)
