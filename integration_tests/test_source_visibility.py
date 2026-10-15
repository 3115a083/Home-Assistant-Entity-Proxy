"""Source hiding with real HA registry, config entries, storage and targets."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers import entity_registry as er, area_registry as ar
from homeassistant.helpers.target import async_extract_referenced_entity_ids, TargetSelection

from custom_components.entity_proxy.visibility import SourceVisibility, DATA_KEY
from custom_components.entity_proxy.config_flow import EntityProxyConfigFlow, ProxyOptionsFlow
from integration_tests.test_home_assistant import make_hass, entry


async def add_proxy(hass, source="light.source", **options):
    registry = er.async_get(hass)
    original = registry.async_get(source) or registry.async_get_or_create(
        "light", "test", source, suggested_object_id=source.split(".")[1])
    hass.states.async_set(source, "on", {"supported_color_modes": ["rgb"], "rgb_color": [1, 2, 3]})
    proxy = entry(source, options)
    await hass.config_entries.async_add(proxy)
    await hass.async_block_till_done()
    return proxy, original


@pytest.mark.asyncio
async def test_hide_reload_option_off_and_area_target(tmp_path):
    hass = await make_hass(tmp_path)
    registry = er.async_get(hass)
    try:
        proxy, original = await add_proxy(hass, hide_source=True)
        runtime = hass.data["entity_proxy"][proxy.entry_id]
        proxy_id = runtime.proxy_entity_id
        assert registry.async_get(original.id).hidden_by is er.RegistryEntryHider.INTEGRATION
        assert registry.async_get(original.id).disabled_by is None
        assert hass.states.get(original.entity_id).state == "on"
        calls = []
        async def turn_on(call):
            calls.append(call.data)
        hass.services.async_register("light", "turn_on", turn_on)
        await runtime.async_action("turn_on", {"brightness": 99})
        assert calls == [{"brightness": 99, "entity_id": original.entity_id}]
        area_registry = ar.async_get(hass)
        await area_registry.async_load()
        area = area_registry.async_create("Test room")
        registry.async_update_entity(original.entity_id, area_id=area.id)
        registry.async_update_entity(proxy_id, area_id=area.id)
        targets = async_extract_referenced_entity_ids(hass, TargetSelection({"area_id": area.id}))
        assert original.entity_id not in targets.indirectly_referenced
        assert proxy_id in targets.indirectly_referenced
        explicit = async_extract_referenced_entity_ids(hass, TargetSelection({"entity_id": original.entity_id}))
        assert original.entity_id in explicit.referenced
        assert await hass.config_entries.async_reload(proxy.entry_id)
        await hass.async_block_till_done()
        assert hass.data["entity_proxy"][proxy.entry_id].proxy_entity_id == proxy_id
        assert registry.async_get(original.id).hidden_by is er.RegistryEntryHider.INTEGRATION
        hass.config_entries.async_update_entry(proxy, options={**proxy.options, "hide_source": False})
        await hass.async_block_till_done()
        assert registry.async_get(original.id).hidden_by is None
        assert hass.data["entity_proxy"][proxy.entry_id].proxy_entity_id == proxy_id
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
async def test_shared_source_stays_hidden_until_last_proxy_removed(tmp_path):
    hass = await make_hass(tmp_path)
    try:
        first, source = await add_proxy(hass, hide_source=True)
        second, _ = await add_proxy(hass, hide_source=True)
        await hass.config_entries.async_remove(first.entry_id)
        assert er.async_get(hass).async_get(source.id).hidden_by is er.RegistryEntryHider.INTEGRATION
        await hass.config_entries.async_remove(second.entry_id)
        assert er.async_get(hass).async_get(source.id).hidden_by is None
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("hidden_by", [er.RegistryEntryHider.USER, er.RegistryEntryHider.INTEGRATION])
async def test_existing_hides_preserved(tmp_path, hidden_by):
    hass = await make_hass(tmp_path)
    registry = er.async_get(hass)
    try:
        source = registry.async_get_or_create("light", "test", "source", suggested_object_id="source", hidden_by=hidden_by)
        proxy, _ = await add_proxy(hass, hide_source=True)
        await hass.config_entries.async_remove(proxy.entry_id)
        assert registry.async_get(source.id).hidden_by is hidden_by
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("hidden_by", [None, er.RegistryEntryHider.USER])
async def test_user_visibility_changes_preserved_on_removal(tmp_path, hidden_by):
    hass = await make_hass(tmp_path)
    try:
        proxy, source = await add_proxy(hass, hide_source=True)
        er.async_get(hass).async_update_entity(source.entity_id, hidden_by=hidden_by)
        await hass.config_entries.async_remove(proxy.entry_id)
        assert er.async_get(hass).async_get(source.id).hidden_by is hidden_by
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
async def test_switch_source_restores_old_and_hides_new(tmp_path):
    hass = await make_hass(tmp_path)
    registry = er.async_get(hass)
    try:
        proxy, old = await add_proxy(hass, hide_source=True)
        new = registry.async_get_or_create("light", "test", "new", suggested_object_id="new")
        hass.states.async_set(new.entity_id, "on", {"supported_color_modes": ["rgb"]})
        old_proxy_id = hass.data["entity_proxy"][proxy.entry_id].proxy_entity_id
        hass.config_entries.async_update_entry(proxy, options={**proxy.options, "source": new.entity_id})
        await hass.async_block_till_done()
        assert registry.async_get(old.id).hidden_by is None
        assert registry.async_get(new.id).hidden_by is er.RegistryEntryHider.INTEGRATION
        assert hass.data["entity_proxy"][proxy.entry_id].proxy_entity_id == old_proxy_id
        assert await hass.config_entries.async_unload(proxy.entry_id)
        assert registry.async_get(new.id).hidden_by is None
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
async def test_journal_restart_stale_claims_and_registry_identity(tmp_path):
    hass = await make_hass(tmp_path)
    registry = er.async_get(hass)
    try:
        proxy, source = await add_proxy(hass, hide_source=True)
        # Recreate the manager and read its real on-disk HA Store journal.
        manager = SourceVisibility(hass)
        await manager.async_sync(proxy, hide=True)
        assert registry.async_get(source.id).hidden_by is er.RegistryEntryHider.INTEGRATION
        registry.async_update_entity(source.entity_id, new_entity_id="light.renamed")
        # Old ID no longer resolves, but the journal's stable UUID still does.
        await manager.async_sync(proxy)
        assert registry.async_get(source.id).hidden_by is None
        # Crash left a claim whose config entry has since disappeared.
        registry.async_update_entity("light.renamed", hidden_by=er.RegistryEntryHider.INTEGRATION)
        await manager._store.async_save({source.id: {"owners": ["removed-entry"]}})
        manager = SourceVisibility(hass)
        await manager.async_sync(proxy)
        assert registry.async_get(source.id).hidden_by is None
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
async def test_hiding_requires_registered_proxy_and_source(tmp_path):
    from homeassistant.config_entries import ConfigEntryState
    hass = await make_hass(tmp_path)
    try:
        proxy, source = await add_proxy(hass, hide_source=False)
        proxy_id = hass.data["entity_proxy"][proxy.entry_id].proxy_entity_id
        await hass.config_entries.async_unload(proxy.entry_id)
        registry = er.async_get(hass)
        registry.async_update_entity(proxy_id, disabled_by=er.RegistryEntryDisabler.USER)
        hass.config_entries.async_update_entry(proxy, options={"hide_source": True})
        await hass.config_entries.async_setup(proxy.entry_id)
        await hass.async_block_till_done()
        assert registry.async_get(source.id).hidden_by is None
        await hass.config_entries.async_unload(proxy.entry_id)
        registry.async_update_entity(proxy_id, disabled_by=None)
        with patch.object(hass.config_entries, "async_forward_entry_setups", new=AsyncMock(side_effect=RuntimeError("setup failed"))):
            await hass.config_entries.async_setup(proxy.entry_id)
        assert proxy.state is ConfigEntryState.SETUP_ERROR
        assert registry.async_get(source.id).hidden_by is None
        missing = entry("light.missing", {"hide_source": True})
        assert "no entity registry entry" in await SourceVisibility(hass).async_sync(missing, hide=True)
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
async def test_save_failure_and_user_edit_during_save_do_not_hide(tmp_path):
    hass = await make_hass(tmp_path)
    try:
        proxy, source = await add_proxy(hass, hide_source=True)
        manager = hass.data[DATA_KEY]
        await manager.async_sync(proxy)
        with patch.object(manager._store, "async_save", new=AsyncMock(side_effect=OSError("disk full"))):
            with pytest.raises(OSError):
                await manager.async_sync(proxy, hide=True)
        assert er.async_get(hass).async_get(source.id).hidden_by is None
        save = manager._store.async_save
        async def user_change(data):
            await save(data)
            er.async_get(hass).async_update_entity(source.entity_id, hidden_by=er.RegistryEntryHider.USER)
        with patch.object(manager._store, "async_save", new=user_change):
            assert "changed during setup" in await manager.async_sync(proxy, hide=True)
        assert er.async_get(hass).async_get(source.id).hidden_by is er.RegistryEntryHider.USER
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("advanced", [False, True])
async def test_setup_checkbox_and_options_form_preserve_rules(tmp_path, advanced):
    hass = await make_hass(tmp_path)
    try:
        flow = EntityProxyConfigFlow()
        flow.hass = hass
        form = await flow.async_step_user()
        checked = form["data_schema"]({"source": "light.source", "name": "Test", "hide_source": True})
        await flow.async_step_user(checked)
        if advanced:
            result = await flow.async_step_rules({"state_rules": "[]", "action_rules": "{}"})
        else:
            await flow.async_step_transparent()
            result = await flow.async_step_finish({})
        assert result["options"]["hide_source"] is True
        proxy, source = await add_proxy(hass, **result["options"])
        options = ProxyOptionsFlow()
        options.hass = hass
        options.handler = proxy.entry_id
        options.context = {"entry_id": proxy.entry_id}
        form = await options.async_step_visibility()
        assert form["data_schema"]({}) == {"hide_source": True}
        result = await options.async_step_visibility({"hide_source": False})
        assert result["data"] == {**proxy.options, "hide_source": False}
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
async def test_disabling_live_proxy_restores_original(tmp_path):
    hass = await make_hass(tmp_path)
    try:
        proxy, source = await add_proxy(hass, hide_source=True)
        runtime = hass.data["entity_proxy"][proxy.entry_id]
        registry = er.async_get(hass)
        registry.async_update_entity(runtime.proxy_entity_id, disabled_by=er.RegistryEntryDisabler.USER)
        await hass.async_block_till_done()
        assert runtime.proxy_entity_id is None
        assert registry.async_get(source.id).hidden_by is None
        assert registry.async_get(source.id).disabled_by is None
    finally:
        await hass.async_stop()
