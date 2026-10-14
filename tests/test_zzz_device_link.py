"""Device-link regressions for Home Assistant Entity Proxy helpers.

Core 2026.8+ requires linking to the source device via device_entry.
A proxy MUST NOT register a second device or join another integration's
device by copying its device_info identifiers.
"""

import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "entity_proxy"

device_helper = types.ModuleType("homeassistant.helpers.device")
device_helper.async_entity_id_to_device = lambda hass, entity_id: hass.devices.get(entity_id)
sys.modules["homeassistant.helpers.device"] = device_helper

entity_helper = types.ModuleType("homeassistant.helpers.entity")
entity_helper.Entity = type("Entity", (), {})
entity_helper.EntityCategory = types.SimpleNamespace(DIAGNOSTIC="diagnostic")
sys.modules["homeassistant.helpers.entity"] = entity_helper

sensor_component = types.ModuleType("homeassistant.components.sensor")
sensor_component.SensorEntity = type("SensorEntity", (), {})
sys.modules["homeassistant.components.sensor"] = sensor_component

for name in ("base", "sensor"):
    spec = importlib.util.spec_from_file_location(
        f"entity_proxy.{name}", ROOT / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

from entity_proxy.base import ProxyEntity
from entity_proxy.sensor import ProxyErrorSensor


class DeviceLinkTests(unittest.TestCase):
    def make_runtime(self, source="light.wled"):
        wled = types.SimpleNamespace(id="device-wled", name="WLED Controller")
        fritz = types.SimpleNamespace(id="device-fritz", name="FRITZ!Box")
        hass = types.SimpleNamespace(
            devices={"light.wled": wled, "switch.router": fritz}
        )
        entry = types.SimpleNamespace(
            entry_id="same-proxy-config-entry",
            data={"name": "Virtual light", "source": "light.wled"},
        )
        return types.SimpleNamespace(
            hass=hass, source=source, entry=entry, errors={}
        ), wled, fritz

    def test_proxy_links_to_source_device(self):
        runtime, wled, _ = self.make_runtime()
        proxy = ProxyEntity(runtime)
        self.assertIs(proxy.device_entry, wled)
        self.assertEqual(proxy._attr_unique_id, "same-proxy-config-entry_proxy")
        self.assertNotIn("device_info", proxy.__dict__)

    def test_error_sensor_links_to_same_device_and_is_diagnostic(self):
        runtime, wled, _ = self.make_runtime()
        sensor = ProxyErrorSensor(runtime)
        self.assertIs(sensor.device_entry, wled)
        self.assertEqual(sensor._attr_entity_category, "diagnostic")
        self.assertEqual(sensor._attr_unique_id, "same-proxy-config-entry_errors")

    def test_change_source_changes_link_but_not_proxy_unique_id(self):
        runtime, _, fritz = self.make_runtime()
        first = ProxyEntity(runtime)
        runtime.source = "switch.router"  # Source changed through options/reload.
        second = ProxyEntity(runtime)
        self.assertIs(second.device_entry, fritz)
        self.assertEqual(first._attr_unique_id, second._attr_unique_id)

    def test_source_without_registered_device_is_unattached(self):
        runtime, _, _ = self.make_runtime("sensor.no_device")
        proxy = ProxyEntity(runtime)
        self.assertIsNone(proxy.device_entry)
        self.assertEqual(proxy._attr_unique_id, "same-proxy-config-entry_proxy")

    def test_error_sensor_uses_current_source_after_reload(self):
        runtime, wled, fritz = self.make_runtime()
        initial = ProxyErrorSensor(runtime)
        runtime.source = "switch.router"
        updated = ProxyErrorSensor(runtime)
        self.assertIs(initial.device_entry, wled)
        self.assertIs(updated.device_entry, fritz)
        self.assertEqual(initial._attr_unique_id, updated._attr_unique_id)


if __name__ == "__main__":
    unittest.main()
