"""Select proxy."""

from homeassistant.components.select import SelectEntity
from .base import ProxyEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ProxySelect(hass.data[DOMAIN][entry.entry_id])])


class ProxySelect(ProxyEntity, SelectEntity):
    @property
    def options(self):
        return self.val("options", [])

    @property
    def current_option(self):
        return self.val("state")

    async def async_select_option(self, option):
        await self.runtime.async_action("select_option", {"option": option})
