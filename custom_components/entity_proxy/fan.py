"""Fan proxy."""

from homeassistant.components.fan import FanEntity
from .base import ProxyEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ProxyFan(hass.data[DOMAIN][entry.entry_id])])


class ProxyFan(ProxyEntity, FanEntity):
    @property
    def is_on(self):
        return self.val("state") == "on"

    @property
    def supported_features(self):
        return int(self.val("supported_features", 0))

    @property
    def percentage(self):
        return self.val("percentage")

    @property
    def percentage_step(self):
        return self.val("percentage_step", 1)

    @property
    def preset_mode(self):
        return self.val("preset_mode")

    @property
    def preset_modes(self):
        return self.val("preset_modes")

    @property
    def oscillating(self):
        return self.val("oscillating")

    @property
    def current_direction(self):
        return self.val("direction")

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        data = dict(kwargs)
        if percentage is not None:
            data["percentage"] = percentage
        if preset_mode is not None:
            data["preset_mode"] = preset_mode
        await self.runtime.async_action("turn_on", data)

    async def async_turn_off(self, **kwargs):
        await self.runtime.async_action("turn_off", kwargs)

    async def async_set_percentage(self, percentage):
        await self.runtime.async_action("set_percentage", {"percentage": percentage})

    async def async_set_preset_mode(self, preset_mode):
        await self.runtime.async_action("set_preset_mode", {"preset_mode": preset_mode})

    async def async_set_direction(self, direction):
        await self.runtime.async_action("set_direction", {"direction": direction})

    async def async_oscillate(self, oscillating):
        await self.runtime.async_action("set_oscillating", {"oscillating": oscillating})
