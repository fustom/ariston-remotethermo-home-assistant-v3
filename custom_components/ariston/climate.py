"""Support for Ariston boilers."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import math
from typing import Any

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
from .entity import (
    AristonEntity,
    async_refresh_after_set,
    is_entity_description_available,
)

_LOGGER = logging.getLogger(__name__)

BSB_PRESET_ZONE_MODES: dict[str, BsbZoneMode] = {
    "protection": BsbZoneMode.OFF,
    "automatic": BsbZoneMode.TIME_PROGRAM,
    "reduced": BsbZoneMode.MANUAL_NIGHT,
    "comfort": BsbZoneMode.MANUAL,
}
BSB_ZONE_MODE_PRESETS: dict[BsbZoneMode, str] = {
    mode: preset for preset, mode in BSB_PRESET_ZONE_MODES.items()
}

BSB_DESIRED_ROOM_TEMP = "desiredRoomTemp"

BSB_SETPOINT_COMFORT = "comfort"
BSB_SETPOINT_REDUCED = "reduced"

# Tolerance used when comparing the desired temp against the reduced setpoint.
BSB_TEMP_COMPARE_TOLERANCE = 0.05

def _normalize_temp(raw: Any) -> float | None:
    """Normalize a temperature value to float.
    
    Accepts either a scalar (int / float / numeric str) or a mapping 
    containing a "value" key (e.g. {"value": 18.5, "min": 10, ...}).
    Returns None if the value is missing or not numeric."""
    if isinstance(raw, Mapping):
        raw = raw.get("value", None)
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the Ariston device from config entry."""
    ariston_climates: list[AristonThermostat] = []

    for description in ARISTON_CLIMATE_TYPES:
        coordinator: DeviceDataUpdateCoordinator | None = hass.data[DOMAIN][
            entry.unique_id
        ].get(description.coordinator)
        if is_entity_description_available(coordinator, description):
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

    _attr_translation_key = "ariston_thermostat"

    def __init__(
        self,
        zone: int,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonClimateEntityDescription,
    ) -> None:
        """Initialize the thermostat."""
        super().__init__(coordinator, description, zone)
        self._bsb_last_setpoint: str = BSB_SETPOINT_COMFORT

    def _get_bsb_zone_mode(self) -> BsbZoneMode:
        """Return the BSB zone mode; UNDEFINED for unknown API values."""
        try:
            return self.device.get_zone_mode(self.zone)
        except:
            return BsbZoneMode.UNDEFINED

    def _get_bsb_presets(self) -> dict[str, BsbZoneMode]:
        """Return the presets offered by the API that we know how to handle"""
        presets: dict[str, BsbZoneMode] = {}
        for option in self.device.get_zone_mode_options(self.zone) or []:
            try:
                mode = BsbZoneMode(option)
            except ValueError:
                continue
            if (preset := BSB_ZONE_MODE_PRESETS.get(mode)) is not None:
                presets[preset] = mode
        return presets

    def _get_bsb_desired_temp(self) -> float | None:
        """Return the normalized desiredRoomTemp for BSB devices, else None."""
        if self.device.plant_mode_supported:
            return None
        zone_data = self.device.get_zone(self.zone) or {}
        return _normalize_temp(zone_data.get(BSB_DESIRED_ROOM_TEMP))

    def _match_bsb_setpoint(self) -> str | None:
        """"Match desiredRoomTemp against comfort and reduced setpoints

        Returns None when there is no unique match: desiredRoomTemp missing,
        both setpoints equal, or the cache is tale right after a write.        
        """
        desired = self._get_bsb_desired_temp()
        if desired is None:
            return None
        comfort = _normalize_temp(self.device.get_zone_ch_comf_temp(self.zone))
        reduced = _normalize_temp(self.device.get_zone_ch_red_temp(self.zone))
        is_comfort = comfort is not None and math.isclose(
            desired, comfort, abs_tol=BSB_TEMP_COMPARE_TOLERANCE
        )
        is_reduced = reduced is not None and math.isclose(
            desired, reduced, abs_tol=BSB_TEMP_COMPARE_TOLERANCE
        )
        if is_comfort == is_reduced:
            return None
        return BSB_SETPOINT_REDUCED if is_reduced else BSB_SETPOINT_COMFORT

    def _get_bsb_active_setpoint(self) -> str | None:
        """Return the setpoint a temperature change applies to.

        Returns None for non-BSB (plant mode) devices.
        Manual modes use the zone mode explicitly. Protection always uses
        comfort. Automatic (and unknown modes) match desiredRoomTemp and
        keep the last known setpoint when there is no unique match.
        """
        if self.device.plant_mode_supported:
            return None
        mode = self._get_bsb_zone_mode()
        if mode is BsbZoneMode.MANUAL:
            setpoint = BSB_SETPOINT_COMFORT
        elif mode is BsbZoneMode.MANUAL_NIGHT:
            setpoint = BSB_SETPOINT_REDUCED
        elif mode is BsbZoneMode.OFF:
            setpoint = BSB_SETPOINT_COMFORT
        else:
            setpoint = self._match_bsb_setpoint() or self._bsb_last_setpoint
        self._bsb_last_setpoint = setpoint
        return setpoint

    def _is_bsb_currently_reduced(self) -> bool:
        """Return True if temperature change currently target the reduced setpoint."""
        return self._get_bsb_active_setpoint() == BSB_SETPOINT_REDUCED

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
    def native_temperature_unit(self) -> str:
        """Return the temperature units for the device."""
        return self.device.get_measured_temp_unit(self.zone)

    @property
    def precision(self) -> float:
        """Return the precision of temperature for the device."""
        return 1 / 10 ** self.device.get_measured_temp_decimals(self.zone)

    @property
    def min_temp(self):
        """Return minimum temperature."""
        if self._is_bsb_currently_reduced():
            return self.device.get_reduced_temp_min(self.zone)
        return self.device.get_comfort_temp_min(self.zone)

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        if self._is_bsb_currently_reduced():
            return self.device.get_reduced_temp_max(self.zone)
        return self.device.get_comfort_temp_max(self.zone)

    @property
    def target_temperature_step(self) -> float:
        """Return the target temperature step support by the device."""
        if self._is_bsb_currently_reduced():
            return self.device.get_reduced_temp_step(self.zone)
        return self.device.get_target_temp_step(self.zone)

    @property
    def native_current_temperature(self) -> float:
        """Return the reported current temperature for the device."""
        return self.device.get_measured_temp_value(self.zone)

    @property
    def native_target_temperature(self) -> float:
        """Return the target temperature for the device.

        For BSB devices, use the normalized desiredRoomTemp as the source of
        truth. If it is missing or invalid, fall back to the value of the 
        active setpoint, then to the library's target temp.
        """
        desired = self._get_bsb_desired_temp()
        if desired is not None:
            return desired
        setpoint = self._get_bsb_active_setpoint()
        if setpoint is not None:
            getter = (
                self.device.get_zone_ch_red_temp
                if setpoint == BSB_SETPOINT_REDUCED
                else self.device.get_zone_ch_comf_temp
            )
            value = _normalize_temp(getter(self.zone))
            if value is not None:
                return value
        return self.device.get_target_temp_value(self.zone)

    # Backward compatibility with Home Assistant < 2026.11, which only reads
    # the non-native property names. On 2026.11+, when an entity provides
    # both, the native_* members take precedence without deprecation warning.
    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement (HA < 2026.11)."""
        return self.native_temperature_unit

    @property
    def current_temperature(self) -> float:
        """Return the current temperature (HA < 2026.11)."""
        return self.native_current_temperature

    @property
    def target_temperature(self) -> float:
        """Return the target temperature (HA < 2026.11)."""
        return self.native_target_temperature

    @property
    def supported_features(self) -> int:
        """Return the supported features for this device integration."""
        features = ClimateEntityFeature.TARGET_TEMPERATURE
        if hasattr(ClimateEntityFeature, "TURN_OFF"):
            features |= ClimateEntityFeature.TURN_OFF
        if hasattr(ClimateEntityFeature, "TURN_ON"):
            features |= ClimateEntityFeature.TURN_ON
        if self.device.plant_mode_supported or hasattr(self.device, 'get_zone_mode'):
            features |= ClimateEntityFeature.PRESET_MODE
        return features

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
        if_heating_pump_on = bool(getattr(self.device, 'is_heating_pump_on_value', False))

        if_not_idle = if_flame_on or if_heating_pump_on

        curr_hvac_action = HVACAction.OFF
        if self.device.is_plant_in_heat_mode:
            if if_not_idle:
                curr_hvac_action = HVACAction.HEATING
            else:
                curr_hvac_action = HVACAction.IDLE
        if self.device.is_plant_in_cool_mode:
            if if_not_idle:
                curr_hvac_action = HVACAction.COOLING
            else:
                curr_hvac_action = HVACAction.IDLE
        return curr_hvac_action

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., home, away, temp."""
        if self.device.plant_mode_supported:
            return self.device.plant_mode_text
        # BSB device — map zone mode value to text
        mode = self._get_bsb_zone_mode()
        if mode is BsbZoneMode.UNDEFINED:
            return None
        return BSB_ZONE_MODE_PRESETS.get(self._get_bsb_zone_mode())

    @property
    def preset_modes(self) -> list[str]:
        """Return a list of available preset modes."""
        if self.device.plant_mode_supported:
            return self.device.plant_mode_opt_texts
        return list(self._get_bsb_presets())

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

        await async_refresh_after_set(self)

    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        _LOGGER.debug(
            "Setting preset mode to %s for %s",
            preset_mode,
            self.name,
        )

        if not self.device.plant_mode_supported:
            zone_mode = self._get_bsb_presets().get(preset_mode)
            if zone_mode is None:
                _LOGGER.error(
                    "Unsupported preset mode %s for %s", preset_mode, self.name
                )
                return
            await self.device.async_set_zone_mode(zone_mode, self.zone)
            await async_refresh_after_set(self)            
            return

        # Don't assume index maps to enum value directly
        preset_index = self.device.plant_mode_opt_texts.index(preset_mode)
        plant_mode = PlantMode(self.device.plant_mode_options[preset_index])

        # Get current states
        current_plant_in_cool = self.device.is_plant_in_cool_mode
        zone_modes = self.device.get_zone_mode_options(self.zone)

        # When switching away from cooling mode, ensure zone is in appropriate state
        if current_plant_in_cool and plant_mode != PlantMode.COOLING:
            # Set zone to manual heat mode before changing plant mode
            if ZoneMode.MANUAL in zone_modes:
                await self.device.async_set_zone_mode(ZoneMode.MANUAL, self.zone)

        # Set the plant mode
        await self.device.async_set_plant_mode(plant_mode)

        # Special handling for OFF mode
        if plant_mode == PlantMode.OFF:
            if self.device.is_zone_mode_options_contains_off(self.zone):
                await self.device.async_set_zone_mode(BsbZoneMode.OFF, self.zone)

        await async_refresh_after_set(self)

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

        if self._is_bsb_currently_reduced():
            await self.device.async_set_reduced_temp(temperature, self.zone)
        else:
            await self.device.async_set_comfort_temp(temperature, self.zone)
        await async_refresh_after_set(self)
