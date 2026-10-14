"""Dependency-free tests for policy and source fallback behavior."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "entity_proxy"
# Load pure-Python policy modules without importing the Home Assistant runtime.
package = types.ModuleType("entity_proxy")
package.__path__ = [str(ROOT)]
sys.modules["entity_proxy"] = package
for name in ("const", "rules"):
    spec = importlib.util.spec_from_file_location(f"entity_proxy.{name}", ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
from entity_proxy.rules import InvalidRules, parse_json, pick_value, validate_actions, validate_all, validate_states


class State:
    def __init__(self, state, attributes=None):
        self.state = state
        self.attributes = attributes or {}


class RulesTests(unittest.TestCase):
    def test_blank_configuration(self):
        self.assertEqual(validate_all("light.wled", [], {}), ([], {}))

    def test_all_supported_source_domains(self):
        for domain in ("light", "switch", "climate", "sensor", "binary_sensor", "fan", "cover", "number", "select"):
            validate_all(f"{domain}.example", [], {})

    def test_reject_unsafe_service(self):
        with self.assertRaises(InvalidRules):
            validate_actions({"turn_off": {"steps": [{"service": "shell_command.run", "target": "shell_command.test"}]}}, "light.demo")

    def test_reject_broad_target(self):
        with self.assertRaises(InvalidRules):
            validate_actions({"turn_off": {"steps": [{"service": "light.turn_off", "target": "all"}]}}, "light.demo")

    def test_reject_cross_domain_target(self):
        with self.assertRaises(InvalidRules):
            validate_actions({"turn_off": {"steps": [{"service": "light.turn_off", "target": "switch.other"}]}}, "light.demo")

    def test_reject_entity_override_in_payload(self):
        with self.assertRaises(InvalidRules):
            validate_actions({"turn_off": {"steps": [{"service": "light.turn_off", "target": "light.x", "data": {"entity_id": "light.y"}}]}}, "light.demo")

    def test_reject_state_rule_duplicates(self):
        with self.assertRaises(InvalidRules):
            validate_states([{"attribute": "state", "value": "on"}, {"attribute": "state", "value": "off"}], "light.demo")

    def test_reject_unbounded_json(self):
        with self.assertRaises(InvalidRules):
            parse_json(" " * 16001, list)

    def test_reject_code_execution_attempt(self):
        with self.assertRaises(InvalidRules):
            parse_json("__import__('os').system('true')", dict)

    def test_fallback_on_missing_state(self):
        rule = {"attribute": "current_temperature", "source": "sensor.a", "fallback": "sensor.b", "fallback_value": 21}
        value, issue = pick_value({"sensor.a": State("unavailable"), "sensor.b": State("23")}, rule)
        self.assertEqual(value, "23")
        self.assertIn("backup", issue)

    def test_literal_fallback_after_two_failures(self):
        rule = {"attribute": "state", "source": "sensor.a", "fallback": "sensor.b", "fallback_value": 20}
        value, issue = pick_value({}, rule)
        self.assertEqual(value, 20)
        self.assertIn("fallback value", issue)

    def test_direct_source_with_attribute(self):
        rule = {"attribute": "current_temperature", "source": "climate.a", "source_attribute": "current_temperature"}
        value, issue = pick_value({"climate.a": State("heat", {"current_temperature": 19.5})}, rule)
        self.assertEqual(value, 19.5)
        self.assertIsNone(issue)

    def test_many_rules_limit(self):
        with self.assertRaises(InvalidRules):
            validate_states([{"attribute": f"x{i}", "value": i} for i in range(49)], "sensor.a")

    def test_safe_wled_rule(self):
        actions = {"turn_off": {"steps": [{"service": "select.select_option", "target": "select.wled_preset", "data": {"option": "Light OFF"}}], "reported_state": "off"}}
        _states, parsed = validate_all("light.wled", [], actions)
        self.assertEqual(parsed["turn_off"]["reported_state"], "off")


if __name__ == "__main__":
    unittest.main()
