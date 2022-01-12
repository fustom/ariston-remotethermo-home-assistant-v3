"""Support for Ariston boilers."""
from __future__ import annotations

import logging

from .entity import AristonEntity
from .const import ARISTON_CLIMATE_TYPE, COORDINATOR, DOMAIN
from .coordinator import DeviceDataUpdateCoordinator
from .ariston import (
    DeviceAttribute,
    DeviceFeatures,
    DeviceProperties,
    PlantMode,
    PropertyType,
    ThermostatProperties,
    ZoneAttribute,
    ZoneMode,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.components.climate import ClimateEntity
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
    coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id][
        COORDINATOR
    ]
    devs = []
    for zone in coordinator.device.features.get(DeviceFeatures.ZONES):
        ariston_zone = AristonThermostat(zone[ZoneAttribute.NUM], coordinator)
        devs.append(ariston_zone)
    async_add_entities(devs)


class AristonThermostat(AristonEntity, ClimateEntity):
    """Ariston Thermostat Device."""

    def __init__(
        self,
        zone: int,
        coordinator: DeviceDataUpdateCoordinator,
    ) -> None:
        """Initialize the thermostat"""
        super().__init__(coordinator, ARISTON_CLIMATE_TYPE, zone)

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return f"{self.device.attributes.get(DeviceAttribute.NAME)}"

    @property
    def unique_id(self) -> str:
        """Return a unique id for the device."""
        return f"{self.device.attributes.get(DeviceAttribute.GW)}_{self.zone}"

    @property
    def icon(self):
        """Return the icon of the thermostat device."""
        if PlantMode(
            self.device.get_item_by_id(DeviceProperties.PLANT_MODE, PropertyType.VALUE)
        ) in [
            PlantMode.WINTER,
            PlantMode.HEATING_ONLY,
        ]:
            return "mdi:radiator"
        else:
            return "mdi:radiator-off"

    @property
    def temperature_unit(self) -> str:
        """Return the temperature units for the device."""
        return self.device.get_item_by_id(
            ThermostatProperties.ZONE_MEASURED_TEMP, PropertyType.UNIT, self.zone
        )

    @property
    def precision(self) -> float:
        """Return the precision of temperature for the device."""
        return 1 / 10 ** self.device.get_item_by_id(
            ThermostatProperties.ZONE_MEASURED_TEMP, PropertyType.DECIMALS, self.zone
        )

    @property
    def min_temp(self):
        """Return minimum temperature."""
        return self.device.get_item_by_id(
            ThermostatProperties.ZONE_COMFORT_TEMP, PropertyType.MIN, self.zone
        )

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self.device.get_item_by_id(
            ThermostatProperties.ZONE_COMFORT_TEMP, PropertyType.MAX, self.zone
        )

    @property
    def target_temperature_step(self) -> float:
        """Return the target temperature step support by the device."""
        return self.device.get_item_by_id(
            ThermostatProperties.ZONE_COMFORT_TEMP, PropertyType.STEP, self.zone
        )

    @property
    def current_temperature(self) -> float:
        """Return the reported current temperature for the device."""
        return self.device.get_item_by_id(
            ThermostatProperties.ZONE_MEASURED_TEMP, PropertyType.VALUE, self.zone
        )

    @property
    def target_temperature(self) -> float:
        """Return the target temperature for the device."""
        return self.device.get_item_by_id(
            ThermostatProperties.ZONE_COMFORT_TEMP, PropertyType.VALUE, self.zone
        )

    @property
    def supported_features(self) -> int:
        """Return the supported features for this device integration."""
        return SUPPORT_FLAGS

    @property
    def hvac_mode(self) -> str:
        """Return the current HVAC mode for the device."""
        plant_mode = PlantMode(
            self.device.get_item_by_id(DeviceProperties.PLANT_MODE, PropertyType.VALUE)
        )
        zone_mode = ZoneMode(
            self.device.get_item_by_id(
                ThermostatProperties.ZONE_MODE, PropertyType.VALUE, self.zone
            )
        )

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
        plant_modes = self.device.get_item_by_id(
            DeviceProperties.PLANT_MODE, PropertyType.OPTIONS
        )
        zone_modes = self.device.get_item_by_id(
            ThermostatProperties.ZONE_MODE, PropertyType.OPTIONS, self.zone
        )

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
        plant_mode = PlantMode(
            self.device.get_item_by_id(DeviceProperties.PLANT_MODE, PropertyType.VALUE)
        )
        if_flame_on = (
            self.device.get_item_by_id(DeviceProperties.IS_FLAME_ON, PropertyType.VALUE)
            == 1
        )

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
        res = self.device.get_item_by_id(
            DeviceProperties.PLANT_MODE, PropertyType.OPTIONS
        ).index(
            self.device.get_item_by_id(DeviceProperties.PLANT_MODE, PropertyType.VALUE)
        )

        return self.device.get_item_by_id(
            DeviceProperties.PLANT_MODE, PropertyType.OPT_TEXTS
        )[res]

    @property
    def preset_modes(self) -> list[str]:
        """Return a list of available preset modes."""
        return self.device.get_item_by_id(
            DeviceProperties.PLANT_MODE, PropertyType.OPT_TEXTS
        )

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        plant_modes = self.device.get_item_by_id(
            DeviceProperties.PLANT_MODE, PropertyType.OPTIONS
        )
        zone_modes = self.device.get_item_by_id(
            ThermostatProperties.ZONE_MODE, PropertyType.OPTIONS, self.zone
        )
        current_plant_mode = PlantMode(
            self.device.get_item_by_id(DeviceProperties.PLANT_MODE, PropertyType.VALUE)
        )

        if hvac_mode == HVAC_MODE_OFF:
            if PlantMode.OFF in plant_modes:
                await self.device.async_set_item_by_id(
                    DeviceProperties.PLANT_MODE, PlantMode.OFF
                )
            else:
                await self.device.async_set_item_by_id(
                    DeviceProperties.PLANT_MODE, PlantMode.SUMMER
                )
        elif hvac_mode == HVAC_MODE_AUTO:
            if current_plant_mode in [
                PlantMode.WINTER,
                PlantMode.HEATING_ONLY,
                PlantMode.COOLING,
            ]:
                # if already heating or cooling just change CH mode
                pass
            elif current_plant_mode == PlantMode.SUMMER:
                # DHW is working, so use Winter where CH and DHW are active
                await self.device.async_set_item_by_id(
                    DeviceProperties.PLANT_MODE, PlantMode.WINTER
                )
            else:
                # hvac is OFF, so use heating only, if not supported then winter
                if PlantMode.HEATING_ONLY in plant_modes:
                    await self.device.async_set_item_by_id(
                        DeviceProperties.PLANT_MODE, PlantMode.HEATING_ONLY
                    )
                else:
                    await self.device.async_set_item_by_id(
                        DeviceProperties.PLANT_MODE, PlantMode.WINTER
                    )
            await self.device.async_set_item_by_id(
                ThermostatProperties.ZONE_MODE, ZoneMode.TIME_PROGRAM, self.zone
            )
        elif hvac_mode == HVAC_MODE_HEAT:
            if current_plant_mode in [PlantMode.WINTER, PlantMode.HEATING_ONLY]:
                # if already heating, change CH mode
                pass
            elif current_plant_mode in [PlantMode.SUMMER, PlantMode.COOLING]:
                # DHW is working, so use Winter and change mode
                await self.device.async_set_item_by_id(
                    DeviceProperties.PLANT_MODE, PlantMode.WINTER
                )
            else:
                # hvac is OFF, so use heating only, if not supported then winter
                if PlantMode.HEATING_ONLY in plant_modes:
                    await self.device.async_set_item_by_id(
                        DeviceProperties.PLANT_MODE, PlantMode.HEATING_ONLY
                    )
                else:
                    await self.device.async_set_item_by_id(
                        DeviceProperties.PLANT_MODE, PlantMode.WINTER
                    )
            if ZoneMode.MANUAL2 in zone_modes:
                await self.device.async_set_item_by_id(
                    ThermostatProperties.ZONE_MODE, ZoneMode.MANUAL2, self.zone
                )
            else:
                await self.device.async_set_item_by_id(
                    ThermostatProperties.ZONE_MODE, ZoneMode.MANUAL, self.zone
                )
        elif hvac_mode == HVAC_MODE_COOL:
            await self.device.async_set_item_by_id(
                DeviceProperties.PLANT_MODE, PlantMode.COOLING
            )
            if ZoneMode.MANUAL2 in zone_modes:
                await self.device.async_set_item_by_id(
                    ThermostatProperties.ZONE_MODE, ZoneMode.MANUAL2, self.zone
                )
            else:
                await self.device.async_set_item_by_id(
                    ThermostatProperties.ZONE_MODE, ZoneMode.MANUAL, self.zone
                )
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        _LOGGER.debug(
            "Setting preset mode to %s for %s",
            preset_mode,
            self.name,
        )

        await self.device.async_set_item_by_id(
            DeviceProperties.PLANT_MODE,
            PlantMode(
                self.device.get_item_by_id(
                    DeviceProperties.PLANT_MODE, PropertyType.OPT_TEXTS
                ).index(preset_mode)
            ),
        )
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            raise ValueError(f"Missing parameter {ATTR_TEMPERATURE}")

        temperature = kwargs[ATTR_TEMPERATURE]
        _LOGGER.debug(
            "Setting temperature to %s for %s",
            temperature,
            self.name,
        )

        await self.device.async_set_item_by_id(
            ThermostatProperties.ZONE_COMFORT_TEMP, temperature, self.zone
        )
        self.async_write_ha_state()
