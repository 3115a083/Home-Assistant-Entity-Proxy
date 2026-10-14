"""Shared event-driven runtime for an Entity Proxy config entry."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import (
    ACTION_TIMEOUT, DOMAIN, MAX_ERRORS, RESTORE_COLOR_KEYS, SNAPSHOT_KEYS,
)
from .rules import dependencies, get_candidate, pick_value

_LOGGER = logging.getLogger(__name__)


def is_proxy(hass: HomeAssistant, entity_id: str) -> bool:
    """Disallow dependencies on any Entity Proxy entity to prevent cycles."""
    entity = er.async_get(hass).async_get(entity_id)
    return bool(entity and entity.platform == DOMAIN)


class ProxyRuntime:
    """Per-entry configuration, snapshot, diagnostics, and services."""

    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        self.hass = hass
        self.entry = entry
        self.source: str = entry.options.get("source", entry.data["source"])
        self.state_rules: list[dict] = entry.options.get("state_rules", [])
        self.action_rules: dict = entry.options.get("action_rules", {})
        self.tracked = dependencies(self.source, self.state_rules, self.action_rules)
        self.errors: dict[str, str] = {}
        self.virtual_state: str | None = None
        self.proxy_entity_id: str | None = None
        self.last_on: dict = {}
        self._callbacks: set[Callable[[], None]] = set()
        self._lock = asyncio.Lock()
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._unsub: Callable[[], None] | None = None
        self._dark_command_in_progress = False

    async def async_start(self) -> None:
        saved = await self._store.async_load() or {}
        if isinstance(saved, dict):
            if (saved.get("source", self.entry.data["source"]) == self.source
                and saved.get("virtual_state") in ("on", "off", None)):
                self.virtual_state = saved.get("virtual_state")
            if (saved.get("source", self.entry.data["source"]) == self.source
                and isinstance(saved.get("last_on"), dict)):
                self.last_on = {
                    k: v for k, v in saved["last_on"].items() if k in SNAPSHOT_KEYS
                }
        self._unsub = async_track_state_change_event(
            self.hass, sorted(self.tracked), self._source_changed
        )
        self._refresh_sources()
        if (initial := self.hass.states.get(self.source)) is not None and self.source.startswith("light.") and self.virtual_state != "off":
            self._remember_light(initial)

    def stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        self._callbacks.clear()

    @callback
    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._callbacks.add(listener)
        return lambda: self._callbacks.discard(listener)

    @callback
    def notify(self) -> None:
        for listener in tuple(self._callbacks):
            listener()

    @callback
    def _set_error(self, key: str, message: str | None) -> None:
        if message is None:
            if key in self.errors:
                del self.errors[key]
                self.notify()
        elif self.errors.get(key) != message:
            self.errors[key] = str(message)[:350]
            self.notify()

    @callback
    def _refresh_sources(self) -> None:
        primary = self.hass.states.get(self.source)
        self._set_error(
            "source", None if primary is not None and primary.state not in ("unknown", "unavailable")
            else f"Primary entity {self.source} unavailable",
        )
        states = {eid: self.hass.states.get(eid) for eid in self.tracked}
        for index, rule in enumerate(self.state_rules):
            _value, issue = pick_value(states, rule)
            self._set_error(f"state:{index}", issue)

    @callback
    def _source_changed(self, event: Any) -> None:
        # No polling; callbacks only when a configured dependency changes.
        if event.data.get("entity_id") == self.source:
            state = event.data.get("new_state")
            if state is not None and state.state not in ("unknown", "unavailable"):
                if self.source.startswith("light.") and not self._dark_command_in_progress:
                    self._remember_light(state)
        self._refresh_sources()
        self.notify()

    @callback
    def _remember_light(self, state: Any) -> None:
        if state.state != "on":
            return
        attrs = state.attributes
        # Never overwrite remembered appearance with the off/black preset.
        has_color = any(
            any(isinstance(v, (int, float)) and v > 0 for v in attrs.get(key, []))
            for key in ("rgb_color", "rgbw_color", "rgbww_color")
            if isinstance(attrs.get(key), (list, tuple))
        )
        has_explicit_color = any(
            isinstance(attrs.get(key), (list, tuple))
            for key in ("rgb_color", "rgbw_color", "rgbww_color")
        )
        is_lit = has_color or (
            not has_explicit_color
            and isinstance(attrs.get("brightness"), (int, float))
            and attrs["brightness"] > 0
        )
        if not is_lit:
            return
        snapshot = {k: list(v) if isinstance(v, tuple) else v for k, v in attrs.items() if k in SNAPSHOT_KEYS and v is not None}
        if snapshot:
            self.last_on = snapshot
            self._save()
        if self.virtual_state == "off":
            # Another client has taken the underlying light back to a lit state.
            self.virtual_state = None
            self._save()

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(
            lambda: {"source": self.source, "virtual_state": self.virtual_state, "last_on": self.last_on}, 2
        )

    def source_state(self) -> Any:
        return self.hass.states.get(self.source)

    def value(self, attribute: str, default: Any = None) -> Any:
        """Return configured virtual state/attribute, else native source property."""
        if attribute == "state" and self.virtual_state is not None:
            return self.virtual_state
        for rule in self.state_rules:
            if rule["attribute"] == attribute:
                states = {eid: self.hass.states.get(eid) for eid in (rule.get("source"), rule.get("fallback")) if eid}
                value, _error = pick_value(states, rule)
                return default if value is None else value
        source = self.source_state()
        value = get_candidate(source, attribute)
        return default if value is None else value

    @property
    def available(self) -> bool:
        # Read-only proxies can function even if primary is down when a fallback
        # rule provides the state. For controls require the original device.
        primary = self.source_state()
        if primary is not None and primary.state not in ("unavailable", "unknown"):
            return True
        return any(rule["attribute"] == "state" and self.value("state") is not None for rule in self.state_rules)

    def validate_references(self) -> None:
        for target in self.tracked:
            if is_proxy(self.hass, target):
                raise HomeAssistantError(
                    f"Entity {target} is another Entity Proxy; proxy chains are blocked"
                )

    async def _call(self, step: dict, arguments: dict) -> None:
        target = step["target"]
        if is_proxy(self.hass, target):
            raise HomeAssistantError(f"Recursive proxy target blocked: {target}")
        state = self.hass.states.get(target)
        if state is None or state.state in ("unavailable", "unknown"):
            raise HomeAssistantError(f"Action target {target} is unavailable")
        domain, service = step["service"].split(".")
        if not self.hass.services.has_service(domain, service):
            raise HomeAssistantError(f"Service {step['service']} is unavailable")
        payload = dict(arguments) if step["forward_arguments"] else {}
        for forbidden in ("entity_id", "area_id", "device_id"):
            payload.pop(forbidden, None)
        payload.update(step["data"])
        payload["entity_id"] = target  # Always force a single, checked target.
        async with asyncio.timeout(ACTION_TIMEOUT):
            await self.hass.services.async_call(domain, service, payload, blocking=True)

    async def _steps(self, steps: list[dict], arguments: dict) -> None:
        for step in steps:
            await self._call(step, arguments)

    def _restore_light(self) -> dict:
        """Restore a previously lit appearance, not the dark WLED preset."""
        result: dict[str, Any] = {}
        for key in RESTORE_COLOR_KEYS:
            if key in self.last_on:
                result[key] = self.last_on[key]
                break
        if "brightness" in self.last_on:
            result["brightness"] = self.last_on["brightness"]
        if "effect" in self.last_on:
            result["effect"] = self.last_on["effect"]
        return result

    async def async_action(self, action: str, arguments: dict | None = None) -> None:
        """Call a mapped service or forward to primary, with fallback and errors."""
        arguments = dict(arguments or {})
        async with self._lock:
            self.validate_references()
            rule = self.action_rules.get(action)
            if rule is None:
                if action == "turn_on" and self.virtual_state == "off" and not arguments and self.source.startswith("light."):
                    arguments = self._restore_light()
                primary_step = {"service": f"{self.source.split('.')[0]}.{action}", "target": self.source, "data": {}, "forward_arguments": True}
                steps, backup, reported = [primary_step], [], None
            else:
                steps, backup, reported = rule["steps"], rule["fallback"], rule["reported_state"]
                if action == "turn_on" and not arguments and self.virtual_state == "off" and self.source.startswith("light."):
                    arguments = self._restore_light()

            self._dark_command_in_progress = action == "turn_off" and bool(rule)
            try:
                try:
                    await self._steps(steps, arguments)
                except Exception as err:
                    primary_error = f"{type(err).__name__}: {err}"[:280]
                    self._set_error(f"action:{action}", f"Primary action failed: {primary_error}")
                    if not backup:
                        raise HomeAssistantError(f"Proxy action {action} failed: {primary_error}") from err
                    try:
                        await self._steps(backup, arguments)
                    except Exception as backup_err:
                        self._set_error(f"action:{action}", f"Primary: {primary_error}; backup failed: {backup_err}")
                        raise HomeAssistantError(f"Proxy action {action} and its backup failed") from backup_err
                    # Keep the primary error visible while backup is in use.
                else:
                    self._set_error(f"action:{action}", None)
                if reported is not None:
                    self.virtual_state = reported
                elif action == "turn_on":
                    self.virtual_state = None
                elif action == "turn_off":
                    self.virtual_state = None
                self._save()
            finally:
                self._dark_command_in_progress = False
                self.notify()
