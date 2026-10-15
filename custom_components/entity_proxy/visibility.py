"""Reversible source hiding with persistent, shared ownership.

Only visible registry entries are changed. Sources remain enabled and directly
addressable. A journal survives restart so options changes/removal can restore
sources even when a previous runtime did not unload cleanly.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import DOMAIN

DATA_KEY = f"{DOMAIN}_source_visibility"


class SourceVisibility:
    """Serialize registry changes and share claims across proxies."""

    def __init__(self, hass):
        self.hass = hass
        self._store = Store(hass, 1, f"{DOMAIN}.source_visibility")
        self._lock = asyncio.Lock()
        self._records = None

    async def _load(self):
        if self._records is not None:
            return
        saved = await self._store.async_load() or {}
        self._records = {
            key: {"owners": list(value["owners"])}
            for key, value in saved.items()
            if isinstance(key, str) and isinstance(value, dict)
            and isinstance(value.get("owners"), list)
            and all(isinstance(owner, str) for owner in value["owners"])
        } if isinstance(saved, dict) else {}

    async def _save(self):
        await self._store.async_save(self._records)

    async def async_sync(self, entry, *, hide=False):
        """Release outdated claims, then optionally hide this entry's source.

        Returns a diagnostic when hiding cannot be applied. Passing hide=False
        explicitly releases this entry, including during unload or removal.
        """
        async with self._lock:
            await self._load()
            before = deepcopy(self._records)
            registry = er.async_get(self.hass)
            entries = {item.entry_id: item for item in self.hass.config_entries.async_entries(DOMAIN)}
            source = entry.options.get("source", entry.data["source"])
            target = registry.async_get(source) if hide else None
            # Reconcile the journal against current options, stable registry IDs
            # and explicit unloads. Do not overwrite a user's visibility change.
            for registry_id, record in list(self._records.items()):
                entity = registry.async_get(registry_id)
                owners = []
                for owner in record["owners"]:
                    candidate = entries.get(owner)
                    if owner == entry.entry_id and not hide:
                        continue
                    if candidate is None or candidate.disabled_by is not None or candidate.options.get("hide_source") is not True:
                        continue
                    current = registry.async_get(candidate.options.get("source", candidate.data["source"]))
                    if entity is not None and current is not None and current.id == entity.id:
                        owners.append(owner)
                if entity is None or entity.hidden_by != er.RegistryEntryHider.INTEGRATION:
                    del self._records[registry_id]
                elif owners:
                    record["owners"] = owners
                else:
                    registry.async_update_entity(entity.entity_id, hidden_by=None)
                    del self._records[registry_id]
            if self._records != before:
                await self._save()
            if not hide:
                return None
            if target is None:
                return "Source cannot be hidden because it has no entity registry entry"
            if target.platform == DOMAIN or target.disabled_by is not None:
                return "Source cannot be hidden: it must be an enabled original entity"
            # Fetch again: reconciliation may have restored this same source.
            target = registry.async_get(target.id)
            if target.hidden_by is not None:
                if (record := self._records.get(target.id)) and entry.entry_id not in record["owners"]:
                    record["owners"] = sorted(set(record["owners"]) | {entry.entry_id})
                    await self._save()
                return None  # Pre-existing hides belong to their original owner.
            self._records[target.id] = {"owners": [entry.entry_id]}
            try:
                await self._save()  # Persist ownership before changing the registry.
            except Exception:
                del self._records[target.id]
                raise
            # Saving yields to HA. Recheck identity, user edits and options before
            # the atomic registry write, rather than acting on the old snapshot.
            current = registry.async_get(target.id)
            if (current is None or current.hidden_by is not None
                or current.disabled_by is not None
                or entry.options.get("hide_source") is not True
                or entry.options.get("source", entry.data["source"]) != current.entity_id):
                del self._records[target.id]
                await self._save()
                return "Source visibility changed during setup; review the source and retry"
            registry.async_update_entity(current.entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION)
            return None


def async_get_visibility(hass):
    """Get the shared manager without awaiting, preventing initialization races."""
    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = SourceVisibility(hass)
    return hass.data[DATA_KEY]
