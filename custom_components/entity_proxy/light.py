"""Light proxy preserving source color modes, brightness, and effects."""

from homeassistant.components.light import ColorMode, LightEntity

from .base import ProxyEntity
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ProxyLight(hass.data[DOMAIN][entry.entry_id])])


class ProxyLight(ProxyEntity, LightEntity):
    @property
    def is_on(self):
        return self.val("state") == "on"

    @property
    def supported_color_modes(self):
        """Mirror valid source modes without crashing on incomplete updates."""
        raw = self.val("supported_color_modes")
        result = set()
        for mode in raw if isinstance(raw, (list, tuple, set)) else []:
            try:
                parsed = ColorMode(mode)
            except (TypeError, ValueError):
                continue
            if parsed != ColorMode.UNKNOWN:
                result.add(parsed)
        # HA rejects mixing simple on/off or brightness with color modes.
        if len(result) > 1:
            result.discard(ColorMode.ONOFF)
            result.discard(ColorMode.BRIGHTNESS)
        # WHITE cannot be the only supported mode.
        if result == {ColorMode.WHITE}:
            result.clear()
        return result or {ColorMode.ONOFF}

    @property
    def color_mode(self):
        """A null or stale source color mode must not prevent registration."""
        if not self.is_on:
            return None
        raw = self.val("color_mode")
        try:
            current = ColorMode(raw)
        except (TypeError, ValueError):
            current = None
        supported = self.supported_color_modes
        if current in supported:
            return current
        # Active effects can report a more restrictive mode.
        if current in (ColorMode.ONOFF, ColorMode.BRIGHTNESS):
            return current
        # Deterministic safe fallback if the source temporarily has no mode.
        return sorted(supported, key=lambda item: item.value)[0]

    @property
    def supported_features(self):
        raw = self.val("supported_features", 0)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    @property
    def brightness(self):
        return self.val("brightness")

    @property
    def rgb_color(self):
        return self.val("rgb_color")

    @property
    def rgbw_color(self):
        return self.val("rgbw_color")

    @property
    def rgbww_color(self):
        return self.val("rgbww_color")

    @property
    def hs_color(self):
        return self.val("hs_color")

    @property
    def xy_color(self):
        return self.val("xy_color")

    @property
    def color_temp_kelvin(self):
        return self.val("color_temp_kelvin")

    @property
    def min_color_temp_kelvin(self):
        return self.val("min_color_temp_kelvin", 2000)

    @property
    def max_color_temp_kelvin(self):
        return self.val("max_color_temp_kelvin", 6500)

    @property
    def effect(self):
        return self.val("effect")

    @property
    def effect_list(self):
        return self.val("effect_list")

    async def async_turn_on(self, **kwargs):
        await self.runtime.async_action("turn_on", kwargs)

    async def async_turn_off(self, **kwargs):
        await self.runtime.async_action("turn_off", kwargs)
