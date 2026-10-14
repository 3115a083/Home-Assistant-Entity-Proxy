"""Common entity behavior for state and service proxy platforms."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import Entity
from homeassistant.helpers.device import async_entity_id_to_device

from .const import DOMAIN


class ProxyEntity(Entity):
    """Thin event-based frontend for the source entity."""

    _attr_should_poll = False

    def __init__(self, runtime: Any, role: str = "proxy") -> None:
        self.runtime = runtime
        self._attr_unique_id = f"{runtime.entry.entry_id}_{role}"
        self._attr_name = runtime.entry.data["name"]
        # HA 2026.8: helper entities link directly to the source device.
        # Never copy device_info or identifiers across config entries.
        self.device_entry = async_entity_id_to_device(runtime.hass, runtime.source)

    @property
    def available(self) -> bool:
        return self.runtime.available

    @property
    def extra_state_attributes(self) -> dict:
        # Expose only source ID; errors belong to a separate diagnostic sensor.
        return {"proxy_source": self.runtime.source}

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.runtime.subscribe(self._changed))

    def _changed(self) -> None:
        self.async_write_ha_state()

    def val(self, name: str, default: Any = None) -> Any:
        return self.runtime.value(name, default)

    @property
    def icon(self) -> str | None:
        return getattr(self, "_attr_icon", None) or self.val("icon")

    @property
    def assumed_state(self) -> bool:
        return False
