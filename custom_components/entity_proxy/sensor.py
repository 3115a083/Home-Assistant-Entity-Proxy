"""Read-only sensor proxy and an independent per-entry error sensor."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import EntityCategory
from .base import ProxyEntity
from .const import DOMAIN, MAX_ERRORS


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = hass.data[DOMAIN][entry.entry_id]
    entities = [ProxyErrorSensor(runtime), ProxyConfigurationSensor(runtime)]
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
    _attr_has_entity_name = True
    _attr_translation_key = "errors"

    def __init__(self, runtime):
        super().__init__(runtime, role="errors")
        self._attr_translation_placeholders = {
            "proxy_name": runtime.entry.data["name"],
        }

    @property
    def available(self):
        return True

    @property
    def native_value(self):
        return len(self.runtime.errors)

    @property
    def extra_state_attributes(self):
        return {
            "proxy_name": self.runtime.entry.data["name"],
            "source_entity": self.runtime.source,
            "issues": list(self.runtime.errors.values())[:MAX_ERRORS],
            "issue_count": len(self.runtime.errors),
        }


class ProxyConfigurationSensor(ProxyEntity, SensorEntity):
    """Read-only, low-sensitivity summary of active proxy settings.

    Never expose full action payloads: they could contain user-supplied values.
    """

    _attr_icon = "mdi:cog-check-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_translation_key = "configuration"

    def __init__(self, runtime):
        super().__init__(runtime, role="configuration")
        self._attr_translation_placeholders = {
            "proxy_name": runtime.entry.data["name"],
        }

    @property
    def available(self):
        return True

    @property
    def native_value(self):
        return "configured"

    @property
    def extra_state_attributes(self):
        off = self.runtime.action_rules.get("turn_off", {})
        steps = off.get("steps", [])
        preset = next(
            (step for step in steps if step.get("service") == "select.select_option"),
            None,
        )
        result = {
            "proxy_name": self.runtime.entry.data["name"],
            "source_entity": self.runtime.source,
            "state_override_count": len(self.runtime.state_rules),
            "state_overrides": [
                rule["attribute"] for rule in self.runtime.state_rules
            ],
            "action_override_count": len(self.runtime.action_rules),
            "action_overrides": sorted(self.runtime.action_rules),
            "virtual_state": self.runtime.virtual_state,
            "active_errors": len(self.runtime.errors),
        }
        if preset is not None:
            result["off_preset_entity"] = preset["target"]
            # Only show the option name, never arbitrary other service payloads.
            result["off_preset_name"] = preset["data"].get("option")
        return result
