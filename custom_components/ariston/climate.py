"""Support for Ariston boilers."""
from __future__ import annotations

import logging

from .coordinator import DeviceDataUpdateCoordinator
from .ariston import PlantMode, ZoneMode
from .const import DOMAIN

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    ATTR_TEMPERATURE,
)
from homeassistant.components.climate import ClimateEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.climate.const import (
    HVAC_MODE_AUTO,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    HVAC_MODE_COOL,
    CURRENT_HVAC_OFF,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_COOL,
    CURRENT_HVAC_IDLE,
    SUPPORT_PRESET_MODE,
    SUPPORT_TARGET_TEMPERATURE,
)

_LOGGER = logging.getLogger(__name__)

SUPPORT_FLAGS = SUPPORT_TARGET_TEMPERATURE | SUPPORT_PRESET_MODE


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the Ariston device from config entry."""
    coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id]
    devs = []
    for thermostat in coordinator.device.thermostats:
        ariston_thermostat = AristonBoiler(thermostat.zone, coordinator)
        devs.append(ariston_thermostat)
    async_add_entities(devs)


class AristonBoiler(CoordinatorEntity, ClimateEntity):
    """Representation of a base Ariston discovery device."""

    def __init__(
        self,
        zone: int,
        coordinator: DeviceDataUpdateCoordinator,
    ) -> None:
        """Initialize the entity"""
        # Pass coordinator to CoordinatorEntity.
        super().__init__(coordinator)

        self.coordinator = coordinator
        self.zone: int = zone

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return f"{self.coordinator.device.plant_name}"

    @property
    def unique_id(self) -> str:
        """Return a unique id for the device."""
        return f"{self.coordinator.device.gw_id}_{self.zone}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device specific attributes."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device.gw_serial)},
            manufacturer=DOMAIN,
            name=self.coordinator.device.plant_name,
            sw_version=self.coordinator.device.gw_fw_ver,
            model=self.coordinator.device.model,
        )

    @property
    def icon(self):
        """Return the name of the Climate device."""
        if PlantMode(self.coordinator.device.plant_mode) in [
            PlantMode.WINTER,
            PlantMode.HEATING_ONLY,
        ]:
            return "mdi:radiator"
        else:
            return "mdi:radiator-off"

    @property
    def temperature_unit(self) -> str:
        """Return the temperature units for the device."""
        return self.coordinator.device.thermostat(self.zone).measured_temp_unit

    @property
    def precision(self) -> float:
        """Return the precision of temperature for the device."""
        return (
            1
            / 10 ** self.coordinator.device.thermostat(self.zone).measured_temp_decimals
        )

    @property
    def min_temp(self):
        """Return minimum temperature."""
        return self.coordinator.device.thermostat(self.zone).comfort_temp_min

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self.coordinator.device.thermostat(self.zone).comfort_temp_max

    @property
    def target_temperature_step(self) -> float:
        """Return the target temperature step support by the device."""
        return self.coordinator.device.thermostat(self.zone).comfort_temp_step

    @property
    def current_temperature(self) -> float:
        """Return the reported current temperature for the device."""
        return self.coordinator.device.thermostat(self.zone).measured_temp

    @property
    def target_temperature(self) -> float:
        """Return the target temperature for the device."""
        return self.coordinator.device.thermostat(self.zone).comfort_temp

    @property
    def supported_features(self) -> int:
        """Return the supported features for this device integration."""
        return SUPPORT_FLAGS

    @property
    def hvac_mode(self) -> str:
        """Return the current HVAC mode for the device."""
        plant_mode = PlantMode(self.coordinator.device.plant_mode)
        zone_mode = ZoneMode(self.coordinator.device.thermostat(self.zone).mode)

        curr_hvac_mode = HVAC_MODE_OFF
        if plant_mode in [PlantMode.WINTER, PlantMode.HEATING_ONLY]:
            if zone_mode is ZoneMode.MANUAL or zone_mode is ZoneMode.MANUAL2:
                curr_hvac_mode = HVAC_MODE_HEAT
            elif zone_mode is ZoneMode.TIME_PROGRAM:
                curr_hvac_mode = HVAC_MODE_AUTO
        if plant_mode in [PlantMode.COOLING]:
            if zone_mode is ZoneMode.MANUAL or zone_mode is ZoneMode.MANUAL2:
                curr_hvac_mode = HVAC_MODE_COOL
            elif zone_mode is ZoneMode.TIME_PROGRAM:
                curr_hvac_mode = HVAC_MODE_AUTO
        return curr_hvac_mode

    @property
    def hvac_modes(self) -> list[str]:
        """Return the HVAC modes support by the device."""
        plant_modes = self.coordinator.device.plant_modes
        zone_modes = self.coordinator.device.thermostat(self.zone).modes

        supported_modes = []
        if ZoneMode.MANUAL in zone_modes or ZoneMode.MANUAL2 in zone_modes:
            supported_modes.append(HVAC_MODE_HEAT)
            if PlantMode.COOLING in plant_modes:
                supported_modes.append(HVAC_MODE_COOL)
        if ZoneMode.TIME_PROGRAM in zone_modes:
            supported_modes.append(HVAC_MODE_AUTO)
        if ZoneMode.OFF in zone_modes:
            supported_modes.append(HVAC_MODE_OFF)

        return supported_modes

    @property
    def hvac_action(self):
        """Return the current running hvac operation."""
        plant_mode = PlantMode(self.coordinator.device.plant_mode)
        if_flame_on = self.coordinator.device.is_flame_on == 1

        curr_hvac_action = CURRENT_HVAC_OFF
        if plant_mode in [PlantMode.WINTER, PlantMode.HEATING_ONLY]:
            if if_flame_on:
                curr_hvac_action = CURRENT_HVAC_HEAT
            else:
                curr_hvac_action = CURRENT_HVAC_IDLE
        if plant_mode in [PlantMode.COOLING]:
            if if_flame_on:
                curr_hvac_action = CURRENT_HVAC_COOL
            else:
                curr_hvac_action = CURRENT_HVAC_IDLE
        return curr_hvac_action

    @property
    def preset_mode(self) -> str:
        """Return the current preset mode, e.g., home, away, temp."""
        res = self.coordinator.device.plant_modes.index(
            self.coordinator.device.plant_mode
        )
        return self.coordinator.device.plant_mode_texts[res]

    @property
    def preset_modes(self) -> list[str]:
        """Return a list of available preset modes."""
        return self.coordinator.device.plant_mode_texts

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        plant_modes = self.coordinator.device.plant_modes
        current_plant_mode = PlantMode(self.coordinator.device.plant_mode)

        if hvac_mode is HVAC_MODE_OFF:
            if PlantMode.OFF in plant_modes:
                await self.coordinator.async_set_plant_mode(PlantMode.OFF)
            else:
                await self.coordinator.async_set_plant_mode(PlantMode.SUMMER)

        elif hvac_mode is HVAC_MODE_AUTO:
            if current_plant_mode in [
                PlantMode.WINTER,
                PlantMode.HEATING_ONLY,
                PlantMode.COOLING,
            ]:
                # if already heating or cooling just change CH mode
                await self.coordinator.async_set_zone_mode(
                    self.zone, ZoneMode.TIME_PROGRAM
                )
            elif current_plant_mode is PlantMode.SUMMER:
                # DHW is working, so use Winter where CH and DHW are active
                await self.coordinator.async_set_plant_mode(PlantMode.WINTER)
                await self.coordinator.async_set_zone_mode(
                    self.zone, ZoneMode.TIME_PROGRAM
                )

            else:
                # hvac is OFF, so use heating only, if not supported then winter
                if PlantMode.HEATING_ONLY in plant_modes:
                    await self.coordinator.async_set_plant_mode(PlantMode.HEATING_ONLY)
                    await self.coordinator.async_set_zone_mode(
                        self.zone, ZoneMode.TIME_PROGRAM
                    )

                else:
                    await self.coordinator.async_set_plant_mode(PlantMode.WINTER)
                    await self.coordinator.async_set_zone_mode(
                        self.zone, ZoneMode.TIME_PROGRAM
                    )

        elif hvac_mode is HVAC_MODE_HEAT:
            zone_mode = ZoneMode.MANUAL
            if ZoneMode.MANUAL2 in self.coordinator.device.thermostat(self.zone).modes:
                zone_mode = ZoneMode.MANUAL2
            if current_plant_mode in [PlantMode.WINTER, PlantMode.HEATING_ONLY]:
                # if already heating, change CH mode
                await self.coordinator.async_set_zone_mode(self.zone, zone_mode)
            elif current_plant_mode in [PlantMode.SUMMER, PlantMode.COOLING]:
                # DHW is working, so use Winter and change mode
                await self.coordinator.async_set_plant_mode(PlantMode.WINTER)
                await self.coordinator.async_set_zone_mode(self.zone, zone_mode)
            else:
                # hvac is OFF, so use heating only, if not supported then winter
                if PlantMode.HEATING_ONLY in plant_modes:
                    await self.coordinator.async_set_plant_mode(PlantMode.HEATING_ONLY)
                    await self.coordinator.async_set_zone_mode(self.zone, zone_mode)
                else:
                    await self.coordinator.async_set_plant_mode(PlantMode.WINTER)
                    await self.coordinator.async_set_zone_mode(self.zone, zone_mode)
        elif hvac_mode is HVAC_MODE_COOL:
            zone_mode = ZoneMode.MANUAL
            if ZoneMode.MANUAL2 in self.coordinator.device.thermostat(self.zone).modes:
                zone_mode = ZoneMode.MANUAL2
            await self.coordinator.async_set_plant_mode(PlantMode.COOLING)
            await self.coordinator.async_set_zone_mode(self.zone, zone_mode)
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        _LOGGER.debug(
            "Setting preset mode to %s for %s",
            preset_mode,
            self.name,
        )

        await self.coordinator.async_set_plant_mode(
            PlantMode(self.coordinator.device.plant_mode_texts.index(preset_mode))
        )
        self.async_write_ha_state()

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

        await self.coordinator.async_set_temperature(self.zone, temperature)
        self.async_write_ha_state()
