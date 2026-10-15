"""Isolated dispatcher tests using lightweight HA service/store stubs."""

import importlib.util
import asyncio
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "entity_proxy"
pkg = sys.modules.get("entity_proxy")
if pkg is None:
    pkg = types.ModuleType("entity_proxy")
    pkg.__path__ = [str(ROOT)]
    sys.modules["entity_proxy"] = pkg
for name in ("const", "rules"):
    if f"entity_proxy.{name}" not in sys.modules:
        spec = importlib.util.spec_from_file_location(f"entity_proxy.{name}", ROOT / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)

homeassistant = types.ModuleType("homeassistant")
ha_core = types.ModuleType("homeassistant.core")
ha_core.HomeAssistant = object
ha_core.callback = lambda fn: fn
ha_exceptions = types.ModuleType("homeassistant.exceptions")
ha_exceptions.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
helpers = types.ModuleType("homeassistant.helpers")
registry = types.ModuleType("homeassistant.helpers.entity_registry")
registry.async_get = lambda hass: hass.registry
events = types.ModuleType("homeassistant.helpers.event")
events.async_track_state_change_event = lambda hass, ids, callback: (lambda: None)
storage = types.ModuleType("homeassistant.helpers.storage")


class Store:
    def __init__(self, *args):
        self.data = None

    def async_delay_save(self, get_data, seconds):
        self.data = get_data()

    async def async_load(self):
        return self.data


storage.Store = Store
sys.modules.update({
    "homeassistant": homeassistant,
    "homeassistant.core": ha_core,
    "homeassistant.exceptions": ha_exceptions,
    "homeassistant.helpers": helpers,
    "homeassistant.helpers.entity_registry": registry,
    "homeassistant.helpers.event": events,
    "homeassistant.helpers.storage": storage,
})
spec = importlib.util.spec_from_file_location("entity_proxy.runtime", ROOT / "runtime.py")
runtime_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime_module
spec.loader.exec_module(runtime_module)
Runtime = runtime_module.ProxyRuntime


class State:
    def __init__(self, value="on", attributes=None):
        self.state = value
        self.attributes = attributes or {}


class States:
    def __init__(self, states):
        self.states = states

    def get(self, key):
        return self.states.get(key)


class Registry:
    def __init__(self):
        self.proxies = set()

    def async_get(self, entity_id):
        return types.SimpleNamespace(platform="entity_proxy") if entity_id in self.proxies else None


class Services:
    def __init__(self):
        self.calls = []
        self.fail = set()

    def has_service(self, domain, service):
        return True

    async def async_call(self, domain, service, data, blocking):
        key = f"{domain}.{service}"
        self.calls.append((key, data))
        if data["entity_id"] in self.fail:
            raise ha_exceptions.HomeAssistantError("device offline")


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def make_runtime(self, action_rules=None):
        services = Services()
        hass = types.SimpleNamespace(
            states=States({
                "light.wled": State("on", {"rgbww_color": [60, 20, 10, 5, 8], "brightness": 150, "color_mode": "rgbww"}),
                "select.wled_preset": State("Normal"),
                "light.backup": State("on"),
            }),
            registry=Registry(),
            services=services,
        )
        entry = types.SimpleNamespace(
            entry_id="testing", data={"source": "light.wled", "name": "Test"},
            options={"state_rules": [], "action_rules": action_rules or {}},
        )
        return Runtime(hass, entry), services

    async def test_restore_with_brightness_and_explicit_color(self):
        runtime, services = self.make_runtime()
        runtime._remember_light(runtime.source_state())
        runtime.virtual_state = "off"
        await runtime.async_action("turn_on", {"brightness": 70})
        self.assertEqual(services.calls[-1][1]["brightness"], 70)
        self.assertEqual(services.calls[-1][1]["rgbww_color"], [60, 20, 10, 5, 8])
        runtime.virtual_state = "off"
        await runtime.async_action("turn_on", {"rgb_color": [1, 2, 3]})
        self.assertNotIn("rgbww_color", services.calls[-1][1])
        self.assertEqual(services.calls[-1][1]["rgb_color"], [1, 2, 3])

    async def test_fan_oscillation_uses_actual_service(self):
        runtime, services = self.make_runtime()
        runtime.source = "fan.source"
        runtime.hass.states.states["fan.source"] = State("on")
        await runtime.async_action("set_oscillating", {"oscillating": True})
        self.assertEqual(services.calls[-1][0], "fan.oscillate")
        await runtime._call({"service": "fan.set_oscillating", "target": "fan.source", "data": {}, "forward_arguments": True}, {"oscillating": False})
        self.assertEqual(services.calls[-1][0], "fan.oscillate")

    async def test_unavailable_target_fails_without_service_call(self):
        runtime, services = self.make_runtime()
        runtime.hass.states.states["light.wled"] = State("unavailable")
        with self.assertRaises(ha_exceptions.HomeAssistantError):
            await runtime.async_action("turn_off")
        self.assertFalse(services.calls)
        self.assertIn("action:turn_off", runtime.errors)

    async def test_unknown_preset_repeated_off_restore(self):
        rule = {"turn_off": {"steps": [{"service": "select.select_option", "target": "select.wled_preset", "data": {"option": "Light OFF"}, "forward_arguments": False}], "fallback": [], "reported_state": "off"}}
        runtime, services = self.make_runtime(rule)
        runtime.hass.states.states["select.wled_preset"] = State("unknown", {"options": ["Normal", "Light OFF"]})
        runtime._remember_light(runtime.source_state())
        for _ in range(2):
            await runtime.async_action("turn_off")
            self.assertEqual(runtime.virtual_state, "off")
            self.assertEqual(services.calls[-1], ("select.select_option", {"option": "Light OFF", "entity_id": "select.wled_preset"}))
            await runtime.async_action("turn_on")
            self.assertIsNone(runtime.virtual_state)
            self.assertEqual(services.calls[-1][0], "light.turn_on")
        self.assertNotIn("light.turn_off", [call[0] for call in services.calls])

    async def test_unknown_targets_fail_closed(self):
        for value, attrs, data, message in (
            ("unknown", {}, {"option": "Light OFF"}, "reports unknown"),
            ("unknown", {"options": ["Normal"]}, {"option": "Light OFF"}, "reports unknown"),
            ("unknown", {"options": "Light OFF"}, {"option": "OFF"}, "reports unknown"),
            ("unknown", {"options": ["Light OFF"]}, {}, "reports unknown"),
            ("unavailable", {"options": ["Light OFF"]}, {"option": "Light OFF"}, "reports unavailable"),
            (None, {}, {"option": "Light OFF"}, "was not found"),
        ):
            with self.subTest(value=value, attrs=attrs, data=data):
                rule = {"turn_off": {"steps": [{"service": "select.select_option", "target": "select.wled_preset", "data": data, "forward_arguments": False}], "fallback": [], "reported_state": "off"}}
                runtime, services = self.make_runtime(rule)
                runtime.hass.states.states["select.wled_preset"] = State(value, attrs) if value else None
                with self.assertRaisesRegex(ha_exceptions.HomeAssistantError, message):
                    await runtime.async_action("turn_off")
                self.assertFalse(services.calls)
                self.assertIsNone(runtime.virtual_state)
        runtime, services = self.make_runtime()
        runtime.hass.states.states["light.wled"] = State("unknown")
        with self.assertRaisesRegex(ha_exceptions.HomeAssistantError, "reports unknown"):
            await runtime.async_action("turn_off")
        self.assertFalse(services.calls)

    async def test_unknown_select_uses_effective_option_and_propagates_failure(self):
        runtime, services = self.make_runtime()
        runtime.hass.states.states["select.wled_preset"] = State("unknown", {"options": ["Light OFF"]})
        step = {"service": "select.select_option", "target": "select.wled_preset", "data": {"option": "Light OFF"}, "forward_arguments": True}
        await runtime._call(step, {"option": "Wrong", "entity_id": "light.backup", "area_id": "all"})
        self.assertEqual(services.calls[-1][1], {"option": "Light OFF", "entity_id": "select.wled_preset"})
        services.fail.add("select.wled_preset")
        with self.assertRaisesRegex(ha_exceptions.HomeAssistantError, "device offline"):
            await runtime._call(step, {})

    async def test_concurrent_actions_are_serialized(self):
        runtime, services = self.make_runtime()
        active = 0
        maximum = 0
        async def call(domain, service, data, blocking):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0)
            services.calls.append((service, data))
            active -= 1
        services.async_call = call
        await asyncio.gather(*(runtime.async_action("turn_off") for _ in range(4)))
        self.assertEqual(maximum, 1)
        self.assertEqual(len(services.calls), 4)

    async def test_restart_preserves_virtual_off_and_snapshot(self):
        runtime, _ = self.make_runtime()
        runtime._remember_light(runtime.source_state())
        runtime.virtual_state = "off"
        runtime._save()
        restored, _ = self.make_runtime()
        restored._store.data = runtime._store.data
        await restored.async_start()
        self.assertEqual(restored.virtual_state, "off")
        self.assertEqual(restored.last_on["brightness"], 150)
        restored.stop()
        self.assertIsNone(restored._unsub)

    async def test_source_override_is_used_for_event_subscription_and_actions(self):
        runtime, services = self.make_runtime()
        runtime.entry.options["source"] = "light.backup"
        renamed = Runtime(runtime.hass, runtime.entry)
        self.assertEqual(renamed.source, "light.backup")
        self.assertIn("light.backup", renamed.tracked)
        self.assertNotIn("light.wled", renamed.tracked)
        await renamed.async_action("turn_off")
        self.assertEqual(services.calls[0][1]["entity_id"], "light.backup")

    async def test_snapshot_does_not_leak_to_new_source(self):
        runtime, _ = self.make_runtime()
        runtime._store.data = {"source": "light.wled", "virtual_state": "off", "last_on": {"brightness": 255}}
        runtime.entry.options["source"] = "light.backup"
        other = Runtime(runtime.hass, runtime.entry)
        other._store.data = dict(runtime._store.data)
        await other.async_start()
        self.assertIsNone(other.virtual_state)
        self.assertFalse(other.last_on)

    async def test_virtual_off_then_restore_light(self):
        rule = {"turn_off": {"steps": [{"service": "select.select_option", "target": "select.wled_preset", "data": {"option": "Light OFF"}, "forward_arguments": False}], "fallback": [], "reported_state": "off"}}
        runtime, services = self.make_runtime(rule)
        runtime._remember_light(runtime.source_state())
        await runtime.async_action("turn_off")
        self.assertEqual(runtime.virtual_state, "off")
        self.assertEqual(services.calls[0][0], "select.select_option")
        await runtime.async_action("turn_on")
        self.assertIsNone(runtime.virtual_state)
        self.assertEqual(services.calls[1][0], "light.turn_on")
        self.assertEqual(services.calls[1][1]["rgbww_color"], [60, 20, 10, 5, 8])
        self.assertEqual(services.calls[1][1]["brightness"], 150)

    async def test_fallback_and_issue_reporting(self):
        rule = {"turn_off": {"steps": [{"service": "select.select_option", "target": "select.wled_preset", "data": {}, "forward_arguments": False}], "fallback": [{"service": "light.turn_off", "target": "light.backup", "data": {}, "forward_arguments": False}], "reported_state": "off"}}
        runtime, services = self.make_runtime(rule)
        services.fail.add("select.wled_preset")
        await runtime.async_action("turn_off")
        self.assertEqual([c[0] for c in services.calls], ["select.select_option", "light.turn_off"])
        self.assertIn("action:turn_off", runtime.errors)

    async def test_all_actions_fail_do_not_change_state(self):
        rule = {"turn_off": {"steps": [{"service": "select.select_option", "target": "select.wled_preset", "data": {}, "forward_arguments": False}], "fallback": [], "reported_state": "off"}}
        runtime, services = self.make_runtime(rule)
        services.fail.add("select.wled_preset")
        with self.assertRaises(ha_exceptions.HomeAssistantError):
            await runtime.async_action("turn_off")
        self.assertIsNone(runtime.virtual_state)

    async def test_reject_proxy_cycle_before_call(self):
        runtime, services = self.make_runtime()
        runtime.hass.registry.proxies.add("light.wled")
        with self.assertRaises(ha_exceptions.HomeAssistantError):
            await runtime.async_action("turn_off")
        self.assertEqual(services.calls, [])


if __name__ == "__main__":
    unittest.main()
