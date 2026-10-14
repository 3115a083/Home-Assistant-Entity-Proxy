"""Common entity behavior for state and service proxy platforms."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device import async_entity_id_to_device
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class ProxyEntity(Entity):
    """Thin event-based frontend for the source entity."""

    _attr_should_poll = False

    def __init__(self, runtime: Any, role: str = "proxy") -> None:
        self.runtime = runtime
        self._proxy_role = role
        self._attr_unique_id = f"{runtime.entry.entry_id}_{role}"
        # Diagnostic sensors use Home Assistant translated names with a
        # per-proxy placeholder. A hard-coded _attr_name would override them.
        if role not in ("errors", "configuration"):
            self._attr_name = f"Entity Proxy: {runtime.entry.data['name']}"
        # Link the helper directly to the *source device*, not to a new
        # Entity Proxy device. HA 2026.8+ allows only one config entry per
        # device; copying source device_info would create a duplicate device.
        # All proxy platforms, including the diagnostics sensor, inherit this.
        # The source is taken from current config options, so changing the
        # source via the options flow relocates entities on entry reload.
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
        if self._proxy_role == "proxy":
            # HA assigns the actual ID at registration; names are not IDs.
            self.runtime.proxy_entity_id = self.entity_id
            self.runtime._set_error("proxy_registration", None)
            self.runtime.notify()

    def _changed(self) -> None:
        self.async_write_ha_state()

    def val(self, name: str, default: Any = None) -> Any:
        return self.runtime.value(name, default)

    def features(self, feature_type):
        """Convert serialized state flags back to the platform's IntFlag."""
        try:
            raw = int(self.val("supported_features", 0))
            return feature_type(raw if raw >= 0 else 0)
        except (TypeError, ValueError, OverflowError):
            return feature_type(0)

    @property
    def icon(self) -> str | None:
        return getattr(self, "_attr_icon", None) or self.val("icon")

    @property
    def assumed_state(self) -> bool:
        return False
