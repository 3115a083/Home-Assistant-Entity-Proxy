"""Tests with real HA classes. Run separately from the stub unittest suite.

python -m pytest integration_tests -q
Test dependency: homeassistant==2026.10.1, pytest, pytest-asyncio (Python 3.14).
No physical devices or user Home Assistant instance are accessed.
"""
import logging
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest
from homeassistant import loader
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, device_registry as dr
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.components.light import LightEntityFeature
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.components.fan import FanEntityFeature

from custom_components.entity_proxy.light import ProxyLight
from custom_components.entity_proxy.climate import ProxyClimate
from custom_components.entity_proxy.cover import ProxyCover
from custom_components.entity_proxy.fan import ProxyFan
from custom_components.entity_proxy.runtime import ProxyRuntime
from custom_components.entity_proxy.config_flow import EntityProxyConfigFlow, ProxyOptionsFlow


async def make_hass(tmp_path):
    (tmp_path / "custom_components").symlink_to(Path(__file__).resolve().parents[1] / "custom_components", target_is_directory=True)
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = ConfigEntries(hass, {})
    loader.async_setup(hass)
    dr.async_setup(hass)
    await dr.async_load(hass)
    await er.async_load(hass)
    return hass


def entry(source="light.source", options=None):
    return ConfigEntry(domain="entity_proxy", title="Test", version=1, minor_version=1,
        source="user", data={"source": source, "name": "Test"}, options=options or {},
        unique_id=None, discovery_keys=MappingProxyType({}), subentries_data=None)


@pytest.mark.asyncio
async def test_light_registered_and_service_forwarded(tmp_path):
    hass = await make_hass(tmp_path)
    hass.states.async_set("light.source", "on", {"supported_features": 44,
        "supported_color_modes": ["rgbww"], "color_mode": "rgbww",
        "rgbww_color": [60, 20, 10, 5, 8], "brightness": 150,
        "effect_list": ["Solid", "Rainbow"], "effect": "Solid"})
    runtime = ProxyRuntime(hass, entry())
    await runtime.async_start()
    light = ProxyLight(runtime)
    component = EntityComponent(logging.getLogger(__name__), "light", hass)
    try:
        # Executes real helpers/entity_platform.py, including capability_attributes.
        await component.async_add_entities([light])
        assert runtime.proxy_entity_id == light.entity_id
        state = hass.states.get(light.entity_id)
        assert state is not None and state.state == "on"
        assert state.attributes["supported_features"] == 44
        assert state.attributes["effect_list"] == ["Solid", "Rainbow"]
        assert LightEntityFeature.EFFECT in light.supported_features
        calls = []
        async def service(call):
            calls.append(call.data)
        hass.services.async_register("light", "turn_on", service)
        await light.async_turn_on(brightness=123)
        assert calls == [{"brightness": 123, "entity_id": "light.source"}]
        hass.states.async_set("light.source", "off", {"supported_features": 44, "supported_color_modes": ["rgbww"]})
        await hass.async_block_till_done()
        assert hass.states.get(light.entity_id).state == "off"
        # Removing/readding keeps the unique ID and removes the old subscriber.
        unique_id = light.unique_id
        await component.async_remove_entity(light.entity_id)
        assert not runtime._callbacks
        restored = ProxyLight(runtime)
        await component.async_add_entities([restored])
        assert restored.unique_id == unique_id
    finally:
        for entity in list(component.entities):
            await component.async_remove_entity(entity.entity_id)
        runtime.stop()
        await hass.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("cls,flag,source", [(ProxyLight,LightEntityFeature,"light.source"),
    (ProxyClimate,ClimateEntityFeature,"climate.source"), (ProxyCover,CoverEntityFeature,"cover.source"),
    (ProxyFan,FanEntityFeature,"fan.source")])
async def test_platform_features_are_real_flags(tmp_path, cls, flag, source):
    hass = await make_hass(tmp_path)
    try:
        for raw in (0, 4, 44, None, "bad", -1):
            hass.states.async_set(source, "off", {"supported_features": raw})
            entity = cls(ProxyRuntime(hass, entry(source)))
            assert isinstance(entity.supported_features, flag)
            assert flag(4) in entity.supported_features or not (entity.supported_features & 4)
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
async def test_gui_setup_and_options_preserve_rules(tmp_path):
    hass = await make_hass(tmp_path)
    try:
        flow = EntityProxyConfigFlow()
        flow.hass = hass
        flow.context = {}
        result = await flow.async_step_user({"name": "GUI test", "source": "light.source"})
        assert result["step_id"] == "setup"
        result = await flow.async_step_guided()
        assert "state" in result["menu_options"]
        form = await flow.async_step_state()
        raw = {"attribute": "brightness", "mode": "entity", "value_source": "sensor.primary",
            "fallback": "sensor.backup", "fallback_value": "100"}
        checked = form["data_schema"](raw)
        result = await flow.async_step_state(checked)
        assert result["step_id"] == "guided"
        result = await flow.async_step_preset({"preset_entity": "select.presets", "preset_name": "Light OFF"})
        assert result["step_id"] == "guided"
        result = await flow.async_step_finish({})
        assert result["type"] == "create_entry"
        assert result["options"]["action_rules"]["turn_off"]["fallback"] == []
        existing = entry(options=result["options"])
        # HA OptionsFlow's config_entry is read-only, supplied via flow manager.
        await hass.config_entries.async_add(existing)
        options = ProxyOptionsFlow()
        options.hass = hass
        options.handler = existing.entry_id
        options.context = {"entry_id": existing.entry_id}
        await options.async_step_guided()
        form = await options.async_step_action()
        raw = {"action":"turn_on", "service":"light.turn_on", "target":"light.source", "forward_arguments":True}
        result = await options.async_step_action(form["data_schema"](raw))
        assert result["step_id"] == "guided"
        result = await options.async_step_finish({})
        assert result["data"]["state_rules"] == existing.options["state_rules"]
        assert result["data"]["action_rules"]["turn_off"] == existing.options["action_rules"]["turn_off"]
        assert "turn_on" not in existing.options["action_rules"]
    finally:
        await hass.async_stop()

from custom_components.entity_proxy.switch import ProxySwitch
from custom_components.entity_proxy.binary_sensor import ProxyBinarySensor
from custom_components.entity_proxy.sensor import ProxySensor, ProxyConfigurationSensor
from custom_components.entity_proxy.number import ProxyNumber
from custom_components.entity_proxy.select import ProxySelect


@pytest.mark.asyncio
@pytest.mark.parametrize("cls,domain,state,attrs", [
    (ProxyLight,"light","on",{"supported_features":44,"supported_color_modes":["rgbww"],"color_mode":"rgbww","rgbww_color":[1,2,3,4,5],"brightness":100}),
    (ProxyClimate,"climate","heat",{"supported_features":1,"hvac_modes":["off","heat"],"temperature":21,"current_temperature":20}),
    (ProxyCover,"cover","open",{"supported_features":15,"current_position":60}),
    (ProxyFan,"fan","on",{"supported_features":1,"percentage":60}),
    (ProxySwitch,"switch","on",{}),
    (ProxyBinarySensor,"binary_sensor","on",{"device_class":"motion"}),
    (ProxySensor,"sensor","21.5",{"device_class":"temperature","state_class":"measurement","unit_of_measurement":"°C"}),
    (ProxyNumber,"number","5",{"min":0,"max":10,"step":1}),
    (ProxySelect,"select","Normal",{"options":["Normal","Light OFF"]}),
])
async def test_each_domain_registers_and_recovers(tmp_path,cls,domain,state,attrs):
    hass = await make_hass(tmp_path)
    source=f"{domain}.source"
    hass.states.async_set(source,state,attrs)
    runtime=ProxyRuntime(hass,entry(source))
    await runtime.async_start()
    component=EntityComponent(logging.getLogger(__name__),domain,hass)
    entity=cls(runtime)
    try:
        await component.async_add_entities([entity])
        assert hass.states.get(entity.entity_id) is not None
        assert runtime.proxy_entity_id == entity.entity_id
        assert ProxyConfigurationSensor(runtime).native_value == "registered"
        hass.states.async_set(source,"unavailable")
        await hass.async_block_till_done()
        assert hass.states.get(entity.entity_id).state == "unavailable"
        hass.states.async_set(source,state,attrs)
        await hass.async_block_till_done()
        assert hass.states.get(entity.entity_id).state != "unavailable"
    finally:
        for added in list(component.entities):
            await component.async_remove_entity(added.entity_id)
        runtime.stop()
        await hass.async_stop()


@pytest.mark.asyncio
async def test_forms_reject_invalid_and_recursive_rules(tmp_path):
    hass=await make_hass(tmp_path)
    try:
        flow=EntityProxyConfigFlow()
        flow.hass=hass
        flow.context={}
        await flow.async_step_user({"source":"light.source","name":"Test"})
        er.async_get(hass).async_get_or_create("sensor","entity_proxy","other",suggested_object_id="proxy")
        before={"state_rules":[],"action_rules":{}}
        for candidate in (
            {"attribute":"supported_features","mode":"constant","value":"4","value_type":"number"},
            {"attribute":"brightness","mode":"constant","value":"nan","value_type":"number"},
            {"attribute":"brightness","mode":"entity","value_source":"sensor.proxy","value_type":"number"},
        ):
            result=await flow.async_step_state(candidate)
            assert result["errors"]
            assert flow._guided_options == before
        form=await flow.async_step_action()
        bad=form["data_schema"]({"action":"turn_off","service":"light.turn_off","target":"switch.source","forward_arguments":False})
        result=await flow.async_step_action(bad)
        assert result["errors"]
        assert flow._guided_options == before
    finally:
        await hass.async_stop()

@pytest.mark.asyncio
async def test_complete_entry_setup_reload_unload(tmp_path):
    from homeassistant.config_entries import ConfigEntryState
    hass=await make_hass(tmp_path)
    hass.states.async_set("light.source","on",{"supported_features":44,"supported_color_modes":["rgbww"],"color_mode":"rgbww","rgbww_color":[1,2,3,4,5],"brightness":100})
    existing=entry()
    try:
        await hass.config_entries.async_add(existing)
        await hass.async_block_till_done()
        assert existing.state is ConfigEntryState.LOADED
        runtime=hass.data["entity_proxy"][existing.entry_id]
        assert runtime.proxy_entity_id
        entity_id=runtime.proxy_entity_id
        assert hass.states.get(entity_id).state == "on"
        diagnostics=[s for s in hass.states.async_all("sensor") if s.attributes.get("proxy_entity_id")==entity_id]
        assert len(diagnostics)==1 and diagnostics[0].state == "registered"
        assert await hass.config_entries.async_reload(existing.entry_id)
        await hass.async_block_till_done()
        assert not runtime._callbacks and runtime._unsub is None
        reloaded=hass.data["entity_proxy"][existing.entry_id]
        assert reloaded.proxy_entity_id == entity_id
        assert await hass.config_entries.async_unload(existing.entry_id)
        assert existing.entry_id not in hass.data["entity_proxy"]
        assert not reloaded._callbacks and reloaded._unsub is None
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
async def test_unknown_select_accepts_off_preset_via_real_service(tmp_path):
    """An available SelectEntity with current_option=None has state unknown."""
    from homeassistant.components.select import SelectEntity
    from homeassistant.setup import async_setup_component
    from homeassistant.exceptions import HomeAssistantError

    class PresetSelect(SelectEntity):
        _attr_name = "WLED preset"
        _attr_should_poll = False
        _attr_options = ["Normal", "Light OFF"]
        calls = 0

        async def async_select_option(self, option):
            self.calls += 1
            self._attr_current_option = option
            self.async_write_ha_state()

    hass = await make_hass(tmp_path)
    runtime = None
    component = None
    try:
        assert await async_setup_component(hass, "select", {})
        component = hass.data["select"]
        selector = PresetSelect()
        await component.async_add_entities([selector])
        state = hass.states.get(selector.entity_id)
        assert selector.available
        assert state.state == "unknown"
        assert state.attributes["options"] == ["Normal", "Light OFF"]
        hass.states.async_set("light.source", "on", {"supported_color_modes": ["rgb"]})
        runtime = ProxyRuntime(hass, entry(options={"action_rules": {"turn_off": {
            "steps": [{"service": "select.select_option", "target": selector.entity_id,
                "data": {"option": "Light OFF"}, "forward_arguments": False}],
            "fallback": [], "reported_state": "off"}}}))
        await runtime.async_start()
        for count in (1, 2):
            selector._attr_current_option = None
            selector.async_write_ha_state()
            assert hass.states.get(selector.entity_id).state == "unknown"
            await runtime.async_action("turn_off")
            assert selector.calls == count
            assert hass.states.get(selector.entity_id).state == "Light OFF"
            assert runtime.virtual_state == "off"
        selector._attr_available = False
        selector.async_write_ha_state()
        runtime.virtual_state = None
        with pytest.raises(HomeAssistantError, match="reports unavailable"):
            await runtime.async_action("turn_off")
        assert selector.calls == 2
        assert runtime.virtual_state is None
    finally:
        if runtime:
            runtime.stop()
        if component:
            for entity in list(component.entities):
                await component.async_remove_entity(entity.entity_id)
        await hass.async_stop()
