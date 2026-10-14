"""Read-only sensor proxy and an independent per-entry error sensor."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory
from .base import ProxyEntity
from .const import DOMAIN, MAX_ERRORS


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = hass.data[DOMAIN][entry.entry_id]
    entities = [ProxyErrorSensor(runtime)]
    if entry.data["source"].startswith("sensor."):
        entities.insert(0, ProxySensor(runtime))
    async_add_entities(entities)


class ProxySensor(ProxyEntity, SensorEntity):
    @property
    def native_value(self):
        value = self.val("state")
        if value is None:
            return None
        if self.val("state_class") is not None or self.val("device_class") in ("temperature", "humidity", "power", "energy", "voltage", "current"):
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        return value

    @property
    def native_unit_of_measurement(self):
        return self.val("unit_of_measurement")

    @property
    def device_class(self):
        return self.val("device_class")

    @property
    def state_class(self):
        return self.val("state_class")


class ProxyErrorSensor(ProxyEntity, SensorEntity):
    """Diagnostics: 0 healthy, >0 active errors (including backup-in-use)."""

    _attr_icon = "mdi:alert-circle-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "issues"

    def __init__(self, runtime):
        super().__init__(runtime, role="errors")
        self._attr_name = f"{runtime.entry.data['name']} Errors"

    @property
    def available(self):
        return True

    @property
    def native_value(self):
        return len(self.runtime.errors)

    @property
    def extra_state_attributes(self):
        return {
            "issues": list(self.runtime.errors.values())[:MAX_ERRORS],
            "issue_count": len(self.runtime.errors),
        }
