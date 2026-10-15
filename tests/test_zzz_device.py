"""Test source-device attachment and read-only configuration diagnostics.

No running Home Assistant instance is needed for these isolated unit checks.
"""

import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "entity_proxy"

helpers = sys.modules["homeassistant.helpers"]
entity_mod = types.ModuleType("homeassistant.helpers.entity")
entity_mod.Entity = type("Entity", (), {})
entity_mod.EntityCategory = types.SimpleNamespace(DIAGNOSTIC="diagnostic")
sys.modules[entity_mod.__name__] = entity_mod
helpers.entity = entity_mod

device_mod = types.ModuleType("homeassistant.helpers.device")
device_mod.async_entity_id_to_device = lambda hass, entity_id: hass.devices.get(entity_id)
sys.modules[device_mod.__name__] = device_mod
helpers.device = device_mod

components_mod = types.ModuleType("homeassistant.components")
sensor_mod = types.ModuleType("homeassistant.components.sensor")
sensor_mod.SensorEntity = type("SensorEntity", (), {})
sys.modules[components_mod.__name__] = components_mod
sys.modules[sensor_mod.__name__] = sensor_mod

for modname in ("base", "sensor"):
    spec = importlib.util.spec_from_file_location(
        f"entity_proxy.{modname}", ROOT / f"{modname}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

from entity_proxy.base import ProxyEntity
from entity_proxy.sensor import ProxyConfigurationSensor, ProxyErrorSensor


class DeviceTests(unittest.TestCase):
    def make_runtime(self, source="light.wled"):
        old_device = object()
        new_device = object()
        return types.SimpleNamespace(
            hass=types.SimpleNamespace(
                devices={"light.wled": old_device, "light.new": new_device}
            ),
            source=source,
            entry=types.SimpleNamespace(
                options={},
                entry_id="existing-entry",
                data={"name": "Bedroom Proxy", "source": "light.wled"},
            ),
            errors={},
            state_rules=[{"attribute": "brightness", "source": "sensor.lux"}],
            action_rules={
                "turn_off": {
                    "steps": [
                        {
                            "service": "select.select_option",
                            "target": "select.wled_presets",
                            "data": {"option": "Dark"},
                        }
                    ]
                }
            },
            virtual_state="off",
            proxy_entity_id=None,
            notify=lambda: None,
        )

    def test_proxy_and_diagnostics_link_to_source_device(self):
        runtime = self.make_runtime()
        source_device = runtime.hass.devices["light.wled"]
        for entity_type in (ProxyEntity, ProxyErrorSensor, ProxyConfigurationSensor):
            entity = entity_type(runtime)
            self.assertIs(entity.device_entry, source_device)
            self.assertEqual(entity.runtime.source, "light.wled")

    def test_renamed_source_relinks_after_reload(self):
        runtime = self.make_runtime("light.new")
        proxy = ProxyEntity(runtime)
        self.assertIs(proxy.device_entry, runtime.hass.devices["light.new"])

    def test_missing_device_does_not_create_a_fake_device(self):
        runtime = self.make_runtime("light.unregistered")
        self.assertIsNone(ProxyEntity(runtime).device_entry)
        self.assertIsNone(ProxyErrorSensor(runtime).device_entry)

    def test_config_sensor_shows_safe_action_summary(self):
        runtime = self.make_runtime()
        config = ProxyConfigurationSensor(runtime)
        self.assertEqual(config.native_value, "control_missing")
        runtime.proxy_entity_id = "light.bedroom_proxy"
        self.assertEqual(config.native_value, "registered")
        attrs = config.extra_state_attributes
        self.assertEqual(attrs["source_entity"], "light.wled")
        self.assertEqual(attrs["proxy_entity_id"], "light.bedroom_proxy")
        self.assertEqual(attrs["proxy_domain"], "light")
        self.assertEqual(attrs["off_preset_name"], "Dark")
        self.assertEqual(attrs["off_preset_entity"], "select.wled_presets")
        self.assertEqual(attrs["action_overrides"], ["turn_off"])
        self.assertEqual(attrs["virtual_state"], "off")
        self.assertNotIn("steps", attrs)
        self.assertNotIn("data", attrs)

    def test_control_name_is_distinct_from_source(self):
        proxy = ProxyEntity(self.make_runtime())
        self.assertEqual(proxy._attr_name, "Entity Proxy: Bedroom Proxy")

    def test_errors_sensor_is_device_linked_and_always_available(self):
        runtime = self.make_runtime()
        runtime.errors["source"] = "Source unreachable"
        sensor = ProxyErrorSensor(runtime)
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, 1)
        self.assertIn("Source unreachable", sensor.extra_state_attributes["issues"])


if __name__ == "__main__":
    unittest.main()
