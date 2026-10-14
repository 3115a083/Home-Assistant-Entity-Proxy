"""Climate proxy with arbitrary state overrides (e.g. current_temperature)."""

from homeassistant.components.climate import ClimateEntity
from .base import ProxyEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ProxyClimate(hass.data[DOMAIN][entry.entry_id])])


class ProxyClimate(ProxyEntity, ClimateEntity):
    @property
    def hvac_modes(self):
        return self.val("hvac_modes", [])

    @property
    def hvac_mode(self):
        return self.val("state")

    @property
    def hvac_action(self):
        return self.val("hvac_action")

    @property
    def supported_features(self):
        return int(self.val("supported_features", 0))

    @property
    def current_temperature(self):
        value = self.val("current_temperature")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def target_temperature(self):
        return self.val("temperature")

    @property
    def target_temperature_high(self):
        return self.val("target_temp_high")

    @property
    def target_temperature_low(self):
        return self.val("target_temp_low")

    @property
    def min_temp(self):
        return self.val("min_temp", 7)

    @property
    def max_temp(self):
        return self.val("max_temp", 35)

    @property
    def target_temperature_step(self):
        return self.val("target_temp_step", 0.5)

    @property
    def temperature_unit(self):
        return self.val("temperature_unit", self.hass.config.units.temperature_unit)

    @property
    def current_humidity(self):
        return self.val("current_humidity")

    @property
    def target_humidity(self):
        return self.val("humidity")

    @property
    def fan_mode(self):
        return self.val("fan_mode")

    @property
    def fan_modes(self):
        return self.val("fan_modes")

    @property
    def preset_mode(self):
        return self.val("preset_mode")

    @property
    def preset_modes(self):
        return self.val("preset_modes")

    @property
    def swing_mode(self):
        return self.val("swing_mode")

    @property
    def swing_modes(self):
        return self.val("swing_modes")

    @property
    def swing_horizontal_mode(self):
        return self.val("swing_horizontal_mode")

    @property
    def swing_horizontal_modes(self):
        return self.val("swing_horizontal_modes")

    @property
    def is_aux_heat(self):
        return self.val("aux_heat")

    async def async_turn_on(self):
        await self.runtime.async_action("turn_on")

    async def async_turn_off(self):
        await self.runtime.async_action("turn_off")

    async def async_set_temperature(self, **kwargs):
        await self.runtime.async_action("set_temperature", kwargs)

    async def async_set_hvac_mode(self, hvac_mode):
        await self.runtime.async_action("set_hvac_mode", {"hvac_mode": hvac_mode})

    async def async_set_humidity(self, humidity):
        await self.runtime.async_action("set_humidity", {"humidity": humidity})

    async def async_set_fan_mode(self, fan_mode):
        await self.runtime.async_action("set_fan_mode", {"fan_mode": fan_mode})

    async def async_set_preset_mode(self, preset_mode):
        await self.runtime.async_action("set_preset_mode", {"preset_mode": preset_mode})

    async def async_set_swing_mode(self, swing_mode):
        await self.runtime.async_action("set_swing_mode", {"swing_mode": swing_mode})

    async def async_set_swing_horizontal_mode(self, swing_horizontal_mode):
        await self.runtime.async_action("set_swing_horizontal_mode", {"swing_horizontal_mode": swing_horizontal_mode})

    async def async_set_aux_heat(self, aux_heat):
        await self.runtime.async_action("set_aux_heat", {"aux_heat": aux_heat})
