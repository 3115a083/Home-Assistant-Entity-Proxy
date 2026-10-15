"""Entity Proxy: configurable state overlays and safe service substitution."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .rules import validate_all
from .runtime import ProxyRuntime
from .visibility import async_get_visibility

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.LIGHT, Platform.SWITCH, Platform.CLIMATE, Platform.SENSOR,
    Platform.BINARY_SENSOR, Platform.FAN, Platform.COVER, Platform.NUMBER,
    Platform.SELECT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Release persisted hiding if any part of setup fails."""
    try:
        return await _async_setup_entry(hass, entry)
    except Exception:
        try:
            await async_get_visibility(hass).async_sync(entry)
        except OSError:
            _LOGGER.warning("Could not restore source visibility after failed setup; check storage")
        raise


async def _async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Start one proxy with only the source domain and its error sensor."""
    source = entry.options.get("source", entry.data["source"])
    if source.split(".", 1)[0] != entry.data["source"].split(".", 1)[0]:
        raise ValueError("The proxy source domain cannot change after creation")
    validate_all(source, entry.options.get("state_rules", []), entry.options.get("action_rules", {}))
    runtime = ProxyRuntime(hass, entry)
    runtime.validate_references()
    await runtime.async_start()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    active = [Platform(entry.data["source"].split(".")[0])]
    if Platform.SENSOR not in active:
        active.append(Platform.SENSOR)
    try:
        await hass.config_entries.async_forward_entry_setups(entry, active)
    except Exception:
        runtime.stop()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    if runtime.proxy_entity_id is None:
        # Missing control entities must be visible as an error, not silently
        # hidden behind healthy-looking configuration diagnostic sensors.
        runtime._set_error(
            "proxy_registration",
            f"Control entity for {source} was not registered. "
            "Check Settings > Entities (including disabled entities) "
            "and Home Assistant logs for the Entity Proxy platform.",
        )
    # Hide only after the replacement entity was actually registered and enabled.
    proxy_entry = er.async_get(hass).async_get(runtime.proxy_entity_id) if runtime.proxy_entity_id else None
    try:
        issue = await async_get_visibility(hass).async_sync(
            entry, hide=entry.options.get("hide_source") is True
            and runtime.proxy_entity_id is not None
            and (proxy_entry is None or proxy_entry.disabled_by is None),
        )
        runtime._set_error("source_visibility", issue)
    except OSError:
        runtime._set_error("source_visibility", "Source visibility could not be saved; check Home Assistant storage")
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove listeners and platforms on unload."""
    active = [Platform(entry.data["source"].split(".")[0])]
    if Platform.SENSOR not in active:
        active.append(Platform.SENSOR)
    success = await hass.config_entries.async_unload_platforms(entry, active)
    if success:
        runtime = hass.data[DOMAIN].pop(entry.entry_id, None)
        try:
            await async_get_visibility(hass).async_sync(entry)
        finally:
            if runtime is not None:
                runtime.stop()
    return success


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Restore a source even if a previously loaded entry is now disabled."""
    await async_get_visibility(hass).async_sync(entry)
