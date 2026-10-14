"""Cover proxy."""

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from .base import ProxyEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ProxyCover(hass.data[DOMAIN][entry.entry_id])])


class ProxyCover(ProxyEntity, CoverEntity):
    @property
    def is_closed(self):
        return self.val("state") == "closed"

    @property
    def is_closing(self):
        return self.val("state") == "closing"

    @property
    def is_opening(self):
        return self.val("state") == "opening"

    @property
    def current_cover_position(self):
        return self.val("current_position")

    @property
    def current_cover_tilt_position(self):
        return self.val("current_tilt_position")

    @property
    def supported_features(self):
        return self.features(CoverEntityFeature)

    async def async_open_cover(self, **kwargs):
        await self.runtime.async_action("open_cover", kwargs)

    async def async_close_cover(self, **kwargs):
        await self.runtime.async_action("close_cover", kwargs)

    async def async_stop_cover(self, **kwargs):
        await self.runtime.async_action("stop_cover", kwargs)

    async def async_set_cover_position(self, **kwargs):
        await self.runtime.async_action("set_cover_position", kwargs)

    async def async_open_cover_tilt(self, **kwargs):
        await self.runtime.async_action("open_cover_tilt", kwargs)

    async def async_close_cover_tilt(self, **kwargs):
        await self.runtime.async_action("close_cover_tilt", kwargs)

    async def async_stop_cover_tilt(self, **kwargs):
        await self.runtime.async_action("stop_cover_tilt", kwargs)

    async def async_set_cover_tilt_position(self, **kwargs):
        await self.runtime.async_action("set_cover_tilt_position", kwargs)
