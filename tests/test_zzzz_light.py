"""Regression tests for light proxies that could disappear on bad color modes.

Uses lightweight entity-platform stubs; hardware / full HA tests still needed.
"""
import enum
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "entity_proxy"

class ColorMode(str, enum.Enum):
    UNKNOWN = "unknown"
    ONOFF = "onoff"
    BRIGHTNESS = "brightness"
    COLOR_TEMP = "color_temp"
    HS = "hs"
    XY = "xy"
    RGB = "rgb"
    RGBW = "rgbw"
    RGBWW = "rgbww"
    WHITE = "white"

light_module = types.ModuleType("homeassistant.components.light")
light_module.LightEntity = type("LightEntity", (), {})
light_module.ColorMode = ColorMode
class LightEntityFeature(enum.IntFlag):
    EFFECT = 4
    FLASH = 8
    TRANSITION = 32
light_module.LightEntityFeature = LightEntityFeature
sys.modules["homeassistant.components.light"] = light_module

spec = importlib.util.spec_from_file_location(
    "entity_proxy.light", ROOT / "light.py"
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
ProxyLight = module.ProxyLight


class LightTests(unittest.IsolatedAsyncioTestCase):
    def make_light(self, state="on", attributes=None):
        from types import SimpleNamespace
        state_map = {"state": state}
        state_map.update(attributes or {})
        runtime = SimpleNamespace(
            entry=SimpleNamespace(entry_id="configured", data={"name": "Desk"}),
            hass=SimpleNamespace(devices={"light.source": object()}),
            source="light.source",
            proxy_entity_id=None,
            notify=lambda: None,
            _set_error=lambda *args: None,
            value=lambda name, default=None: state_map.get(name, default),
            subscribe=lambda fn: (lambda: None),
        )
        return ProxyLight(runtime)

    async def test_feature_membership_matches_home_assistant(self):
        for raw in (0, 4, 44, "44", None, "broken", -1, float("inf")):
            with self.subTest(raw=raw):
                light = self.make_light(attributes={"supported_features": raw})
                self.assertIsInstance(light.supported_features, LightEntityFeature)
                self.assertEqual(LightEntityFeature.EFFECT in light.supported_features, raw in (4, 44, "44"))

    async def test_white_requires_color_and_cannot_mix_with_temperature(self):
        for modes, expected in [(["white"], {ColorMode.ONOFF}), (["white", "color_temp"], {ColorMode.COLOR_TEMP}), (["white", "rgb"], {ColorMode.WHITE, ColorMode.RGB})]:
            self.assertEqual(self.make_light(attributes={"supported_color_modes": modes}).supported_color_modes, expected)

    async def test_source_rgbww_usable(self):
        light = self.make_light(attributes={
            "supported_color_modes": ["rgbww", "color_temp"],
            "color_mode": "rgbww",
        })
        self.assertEqual(light.color_mode, ColorMode.RGBWW)
        self.assertIn(ColorMode.RGBWW, light.supported_color_modes)

    async def test_missing_color_mode_does_not_raise(self):
        light = self.make_light(attributes={
            "supported_color_modes": ["rgbww"],
            "color_mode": None,
        })
        self.assertEqual(light.color_mode, ColorMode.RGBWW)

    async def test_none_and_invalid_mode_list(self):
        light = self.make_light(attributes={
            "supported_color_modes": None,
            "color_mode": None,
            "supported_features": None,
        })
        self.assertEqual(light.supported_color_modes, {ColorMode.ONOFF})
        self.assertEqual(light.color_mode, ColorMode.ONOFF)
        self.assertEqual(light.supported_features, 0)

    async def test_mixed_modes_filtered_for_ha(self):
        light = self.make_light(attributes={
            "supported_color_modes": ["onoff", "brightness", "rgbww", "broken"],
            "color_mode": "rgbww",
        })
        self.assertEqual(light.supported_color_modes, {ColorMode.RGBWW})

    async def test_off_light_allows_null_mode(self):
        light = self.make_light(state="off", attributes={
            "supported_color_modes": ["rgbww"],
            "color_mode": None,
        })
        self.assertIsNone(light.color_mode)

    async def test_light_platform_exposes_one_control_entity(self):
        light = self.make_light()
        added = []
        hass = types.SimpleNamespace(data={"entity_proxy": {"configured": light.runtime}})
        entry = types.SimpleNamespace(entry_id="configured")
        await module.async_setup_entry(hass, entry, lambda entities: added.extend(entities))
        self.assertEqual(len(added), 1)
        self.assertIsInstance(added[0], ProxyLight)
        self.assertEqual(added[0]._attr_unique_id, "configured_proxy")

    async def test_unique_control_name_and_assigned_entity_id(self):
        light = self.make_light()
        self.assertEqual(light._attr_name, "Entity Proxy: Desk")
        light.entity_id = "light.desk_entity_proxy"
        light.async_on_remove = lambda callback: None
        await light.async_added_to_hass()
        self.assertEqual(light.runtime.proxy_entity_id, "light.desk_entity_proxy")


if __name__ == "__main__":
    unittest.main()
