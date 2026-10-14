"""Number proxy."""

from homeassistant.components.number import NumberEntity
from .base import ProxyEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ProxyNumber(hass.data[DOMAIN][entry.entry_id])])


class ProxyNumber(ProxyEntity, NumberEntity):
    @property
    def native_value(self):
        value = self.val("state")
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def native_min_value(self):
        return self.val("min", 0)

    @property
    def native_max_value(self):
        return self.val("max", 100)

    @property
    def native_step(self):
        return self.val("step", 1)

    @property
    def native_unit_of_measurement(self):
        return self.val("unit_of_measurement")

    async def async_set_native_value(self, value):
        await self.runtime.async_action("set_value", {"value": value})
