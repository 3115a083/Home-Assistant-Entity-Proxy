"""Switch proxy."""

from homeassistant.components.switch import SwitchEntity
from .base import ProxyEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ProxySwitch(hass.data[DOMAIN][entry.entry_id])])


class ProxySwitch(ProxyEntity, SwitchEntity):
    @property
    def is_on(self):
        return self.val("state") == "on"

    async def async_turn_on(self, **kwargs):
        await self.runtime.async_action("turn_on", kwargs)

    async def async_turn_off(self, **kwargs):
        await self.runtime.async_action("turn_off", kwargs)
