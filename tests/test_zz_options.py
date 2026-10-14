"""Smoke-test option flows without importing a complete Home Assistant instance.

The real UI selectors are provided by Home Assistant. These tests exercise the
validation and config-entry mutations independently of frontend rendering.
"""

import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "entity_proxy"

# Rules have already been imported by the preceding unit-test modules.
from entity_proxy.rules import validate_all


class ConfigFlow:
    def __init_subclass__(cls, **kwargs):
        pass


class OptionsFlow:
    def async_show_form(self, **kwargs):
        return {"kind": "form", **kwargs}

    def async_show_menu(self, **kwargs):
        return {"kind": "menu", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"kind": "entry", **kwargs}


ha_config = types.ModuleType("homeassistant.config_entries")
ha_config.ConfigFlow = ConfigFlow
ha_config.OptionsFlow = OptionsFlow
sys.modules["homeassistant.config_entries"] = ha_config
sys.modules["homeassistant"].config_entries = ha_config

vol = types.ModuleType("voluptuous")
vol.Required = lambda value, default=None: value
vol.Schema = lambda value: value
sys.modules["voluptuous"] = vol

selector = types.ModuleType("homeassistant.helpers.selector")
selector.EntitySelectorConfig = lambda **kwargs: kwargs
selector.EntitySelector = lambda config: config
selector.TextSelectorConfig = lambda **kwargs: kwargs
selector.TextSelector = lambda config=None: config
sys.modules["homeassistant.helpers.selector"] = selector
sys.modules["homeassistant.helpers"].selector = selector

spec = importlib.util.spec_from_file_location("entity_proxy.config_flow", ROOT / "config_flow.py")
flow_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = flow_module
spec.loader.exec_module(flow_module)


class Registry:
    def __init__(self, proxies=None):
        self.proxies = set(proxies or ())

    def async_get(self, entity_id):
        if entity_id in self.proxies:
            return types.SimpleNamespace(platform="entity_proxy")
        return None


class EditTests(unittest.IsolatedAsyncioTestCase):
    def make_flow(self, source="light.old", rules=None, proxy_entities=None):
        entry = types.SimpleNamespace(
            entry_id="unchanged-id",
            data={"source": source, "name": "My proxy"},
            options={"state_rules": [], "action_rules": {}} if rules is None else rules,
        )
        flow = flow_module.ProxyOptionsFlow()
        flow.config_entry = entry
        flow.hass = types.SimpleNamespace(registry=Registry(proxy_entities))
        return flow

    async def test_options_flow_factory_exposed_to_home_assistant(self):
        # HA uses ConfigFlow.async_get_options_flow to display Configure.
        options = flow_module.EntityProxyConfigFlow.async_get_options_flow(
            types.SimpleNamespace(entry_id="existing")
        )
        self.assertIsInstance(options, flow_module.ProxyOptionsFlow)

    async def test_chooser_offers_preset_for_lights(self):
        flow = self.make_flow()
        result = await flow.async_step_init()
        self.assertEqual(result["menu_options"], ["source", "preset", "rules"])
        self.assertEqual((await self.make_flow("climate.a").async_step_init())["menu_options"], ["source", "rules"])

    async def test_rename_source_keeps_other_rules(self):
        rules = {"state_rules": [{"attribute": "brightness", "source": "light.old"}],
                 "action_rules": {"turn_off": {"steps": [{"service": "light.turn_off", "target": "light.old", "data": {}, "forward_arguments": False}],
                                               "fallback": [], "reported_state": "off"}}}
        flow = self.make_flow(rules=rules)
        result = await flow.async_step_source({"source": "light.renamed"})
        self.assertEqual(result["kind"], "entry")
        self.assertEqual(result["data"]["source"], "light.renamed")
        self.assertEqual(result["data"]["state_rules"][0]["source"], "light.renamed")
        self.assertEqual(result["data"]["action_rules"]["turn_off"]["steps"][0]["target"], "light.renamed")
        self.assertEqual(flow.config_entry.entry_id, "unchanged-id")
        self.assertEqual(flow.config_entry.data["source"], "light.old")
        self.assertEqual(flow.config_entry.options["state_rules"][0]["source"], "light.old")

    async def test_rename_rejects_change_of_domain_or_proxy_source(self):
        flow = self.make_flow(proxy_entities={"light.proxy_entity"})
        bad_domain = await flow.async_step_source({"source": "switch.other"})
        self.assertEqual(bad_domain["errors"]["base"], "source_domain")
        recursion = await flow.async_step_source({"source": "light.proxy_entity"})
        self.assertEqual(recursion["errors"]["base"], "proxy_source")

    async def test_edit_preset_preserves_other_rules(self):
        rules = {
            "source": "light.renamed", "state_rules": [{"attribute": "brightness", "value": 200}],
            "action_rules": {
                "turn_on": {"steps": [{"service": "light.turn_on", "target": "light.renamed", "data": {}, "forward_arguments": False}], "fallback": [], "reported_state": "on"},
                "turn_off": {"steps": [{"service": "select.select_option", "target": "select.old", "data": {"option": "Old"}, "forward_arguments": False}], "fallback": [], "reported_state": "off"},
            },
        }
        flow = self.make_flow(rules=rules)
        result = await flow.async_step_preset({"preset_entity": "select.renamed", "preset_name": "Night black"})
        self.assertEqual(result["kind"], "entry")
        self.assertEqual(result["data"]["source"], "light.renamed")
        self.assertEqual(result["data"]["state_rules"], rules["state_rules"])
        self.assertEqual(result["data"]["action_rules"]["turn_on"], rules["action_rules"]["turn_on"])
        validate_all("light.renamed", result["data"]["state_rules"], result["data"]["action_rules"])
        self.assertEqual(result["data"]["action_rules"]["turn_off"]["steps"][0]["data"], {"option": "Night black"})

    async def test_blank_preset_is_rejected(self):
        flow = self.make_flow()
        result = await flow.async_step_preset({"preset_entity": "select.wled", "preset_name": "  "})
        self.assertEqual(result["errors"], {"preset_name": "empty_preset"})


if __name__ == "__main__":
    unittest.main()
