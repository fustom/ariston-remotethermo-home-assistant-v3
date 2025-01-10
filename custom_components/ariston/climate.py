"""Support for Ariston boilers."""

from __future__ import annotations

import logging

from ariston.const import PlantMode, ZoneMode, BsbZoneMode
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant

from .const import ARISTON_CLIMATE_TYPES, DOMAIN, AristonClimateEntityDescription
from .coordinator import DeviceDataUpdateCoordinator
from .entity import AristonEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the Ariston device from config entry."""
    ariston_climates: list[AristonThermostat] = []

    for description in ARISTON_CLIMATE_TYPES:
        coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id][
            description.coordinator
        ]
        if (
            coordinator
            and coordinator.device
            and coordinator.device.are_device_features_available(
                description.device_features,
                description.system_types,
                description.whe_types,
            )
        ):
            for zone_number in coordinator.device.zone_numbers:
                ariston_climates.append(
                    AristonThermostat(
                        zone_number,
                        coordinator,
                        description,
                    )
                )

    async_add_entities(ariston_climates)


class AristonThermostat(AristonEntity, ClimateEntity):
    """Ariston Thermostat Device."""

    def __init__(
        self,
        zone: int,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonClimateEntityDescription,
    ) -> None:
        """Initialize the thermostat."""
        super().__init__(coordinator, description, zone)

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return f"{self.device.name}"

    @property
    def unique_id(self) -> str:
        """Return a unique id for the device."""
        return f"{self.device.gateway}_{self.zone}"

    @property
    def icon(self):
        """Return the icon of the thermostat device."""
        if self.device.is_plant_in_heat_mode:
            return "mdi:radiator"
        return "mdi:radiator-off"

    @property
    def temperature_unit(self) -> str:
        """Return the temperature units for the device."""
        return self.device.get_measured_temp_unit(self.zone)

    @property
    def precision(self) -> float:
        """Return the precision of temperature for the device."""
        return 1 / 10 ** self.device.get_measured_temp_decimals(self.zone)

    @property
    def min_temp(self):
        """Return minimum temperature."""
        return self.device.get_comfort_temp_min(self.zone)

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self.device.get_comfort_temp_max(self.zone)

    @property
    def target_temperature_step(self) -> float:
        """Return the target temperature step support by the device."""
        return self.device.get_target_temp_step(self.zone)

    @property
    def current_temperature(self) -> float:
        """Return the reported current temperature for the device."""
        return self.device.get_measured_temp_value(self.zone)

    @property
    def target_temperature(self) -> float:
        """Return the target temperature for the device."""
        return self.device.get_target_temp_value(self.zone)

    @property
    def supported_features(self) -> int:
        """Return the supported features for this device integration."""
        features = ClimateEntityFeature.TARGET_TEMPERATURE
        if hasattr(ClimateEntityFeature, "TURN_OFF"):
            features |= ClimateEntityFeature.TURN_OFF
        if hasattr(ClimateEntityFeature, "TURN_ON"):
            features |= ClimateEntityFeature.TURN_ON
        return (
            features | ClimateEntityFeature.PRESET_MODE
            if self.device.plant_mode_supported
            else features
        )

    @property
    def hvac_mode(self) -> str:
        """Return the current HVAC mode for the device."""
        curr_hvac_mode = HVACMode.OFF

        if self.device.is_plant_in_heat_mode:
            if self.device.is_zone_in_manual_mode(self.zone):
                curr_hvac_mode = HVACMode.HEAT
            elif self.device.is_zone_in_time_program_mode(self.zone):
                curr_hvac_mode = HVACMode.AUTO
        if self.device.is_plant_in_cool_mode:
            if self.device.is_zone_in_manual_mode(self.zone):
                curr_hvac_mode = HVACMode.COOL
            elif self.device.is_zone_in_time_program_mode(self.zone):
                curr_hvac_mode = HVACMode.AUTO
        return curr_hvac_mode

    @property
    def hvac_modes(self) -> list[str]:
        """Return the HVAC modes support by the device."""
        supported_modes = []
        if self.device.is_zone_mode_options_contains_manual(self.zone):
            supported_modes.append(HVACMode.HEAT)
            if self.device.plant_mode_supported:
                if self.device.is_plant_mode_options_contains_cooling:
                    supported_modes.append(HVACMode.COOL)
        if self.device.is_zone_mode_options_contains_time_program(self.zone):
            supported_modes.append(HVACMode.AUTO)
        if self.device.is_zone_mode_options_contains_off(self.zone):
            supported_modes.append(HVACMode.OFF)

        return supported_modes

    @property
    def hvac_action(self):
        """Return the current running hvac operation."""
        if_flame_on = bool(self.device.is_flame_on_value)

        curr_hvac_action = HVACAction.OFF
        if self.device.is_plant_in_heat_mode:
            if if_flame_on:
                curr_hvac_action = HVACAction.HEATING
            else:
                curr_hvac_action = HVACAction.IDLE
        if self.device.is_plant_in_cool_mode:
            if if_flame_on:
                curr_hvac_action = HVACAction.COOLING
            else:
                curr_hvac_action = HVACAction.IDLE
        return curr_hvac_action

    @property
    def preset_mode(self) -> str:
        """Return the current preset mode, e.g., home, away, temp."""
        return self.device.plant_mode_text

    @property
    def preset_modes(self) -> list[str]:
        """Return a list of available preset modes."""
        return self.device.plant_mode_opt_texts

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        if self.device.plant_mode_supported:
            plant_modes = self.device.plant_mode_options
            zone_modes = self.device.get_zone_mode_options(self.zone)
            current_plant_mode = self.device.plant_mode

            if hvac_mode == HVACMode.OFF:
                if self.device.is_plant_mode_options_contains_off:
                    await self.device.async_set_plant_mode(PlantMode.OFF)
                else:
                    await self.device.async_set_plant_mode(PlantMode.SUMMER)
            elif hvac_mode == HVACMode.AUTO:
                if current_plant_mode in [
                    PlantMode.WINTER,
                    PlantMode.HEATING_ONLY,
                    PlantMode.COOLING,
                ]:
                    # if already heating or cooling just change CH mode
                    pass
                elif current_plant_mode == PlantMode.SUMMER:
                    # DHW is working, so use Winter where CH and DHW are active
                    await self.device.async_set_plant_mode(PlantMode.WINTER)
                # hvac is OFF, so use heating only, if not supported then winter
                elif PlantMode.HEATING_ONLY in plant_modes:
                    await self.device.async_set_plant_mode(PlantMode.HEATING_ONLY)
                else:
                    await self.device.async_set_plant_mode(PlantMode.WINTER)
                await self.device.async_set_zone_mode(ZoneMode.TIME_PROGRAM, self.zone)
            elif hvac_mode == HVACMode.HEAT:
                if current_plant_mode in [PlantMode.WINTER, PlantMode.HEATING_ONLY]:
                    # if already heating, change CH mode
                    pass
                elif current_plant_mode in [PlantMode.SUMMER, PlantMode.COOLING]:
                    # DHW is working, so use Winter and change mode
                    await self.device.async_set_plant_mode(PlantMode.WINTER)
                # hvac is OFF, so use heating only, if not supported then winter
                elif PlantMode.HEATING_ONLY in plant_modes:
                    await self.device.async_set_plant_mode(PlantMode.HEATING_ONLY)
                else:
                    await self.device.async_set_plant_mode(PlantMode.WINTER)
                if ZoneMode.MANUAL_NIGHT in zone_modes:
                    await self.device.async_set_zone_mode(
                        ZoneMode.MANUAL_NIGHT, self.zone
                    )
                else:
                    await self.device.async_set_zone_mode(ZoneMode.MANUAL, self.zone)
            elif hvac_mode == HVACMode.COOL:
                await self.device.async_set_plant_mode(PlantMode.COOLING)
                if ZoneMode.MANUAL_NIGHT in zone_modes:
                    await self.device.async_set_zone_mode(
                        ZoneMode.MANUAL_NIGHT, self.zone
                    )
                else:
                    await self.device.async_set_zone_mode(ZoneMode.MANUAL, self.zone)
        # Plant mode is not supported (BSB device)
        elif hvac_mode == HVACMode.OFF:
            await self.device.async_set_zone_mode(BsbZoneMode.OFF, self.zone)
        elif hvac_mode == HVACMode.AUTO:
            await self.device.async_set_zone_mode(BsbZoneMode.TIME_PROGRAM, self.zone)
        elif hvac_mode == HVACMode.HEAT:
            await self.device.async_set_zone_mode(BsbZoneMode.MANUAL, self.zone)

        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        _LOGGER.debug(
            "Setting preset mode to %s for %s",
            preset_mode,
            self.name,
        )

        await self.device.async_set_plant_mode(
            PlantMode(self.device.plant_mode_opt_texts.index(preset_mode)),
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

        await self.device.async_set_comfort_temp(temperature, self.zone)
        self.async_write_ha_state()
