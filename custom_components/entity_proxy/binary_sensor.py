"""Binary sensor proxy."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from .base import ProxyEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ProxyBinarySensor(hass.data[DOMAIN][entry.entry_id])])


class ProxyBinarySensor(ProxyEntity, BinarySensorEntity):
    @property
    def is_on(self):
        value = self.val("state")
        return value in ("on", True)

    @property
    def device_class(self):
        return self.val("device_class")
