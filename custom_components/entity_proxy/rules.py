"""Strict, pure-Python validation and source resolution of proxy rules.

No eval, executable templates, filesystem paths, Python code, or external URLs.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .const import (
    ALLOWED_SERVICES, MAX_ACTION_RULES, MAX_RULE_TEXT,
    MAX_STATE_RULES, MAX_STEPS, SUPPORTED_DOMAINS,
)

ENTITY_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")
FIELD_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ACTION_RE = re.compile(r"^[a-z][a-z0-9_]*$")
BAD_STATES = frozenset({"unavailable", "unknown"})
RESERVED_ATTRIBUTES = frozenset({"entity_id", "friendly_name", "supported_features"})


class InvalidRules(ValueError):
    """Invalid or unsafe proxy configuration."""


def valid_entity(entity_id: Any) -> bool:
    """Prevent broad calls, wildcard selectors, and malformed entity IDs."""
    return isinstance(entity_id, str) and bool(ENTITY_RE.fullmatch(entity_id)) and len(entity_id) <= 255


def parse_json(value: str, expected: type) -> Any:
    """Read bounded JSON instead of evaluating user-supplied code."""
    if not isinstance(value, str) or len(value) > MAX_RULE_TEXT:
        raise InvalidRules("Rule configuration exceeds size limit")
    try:
        result = json.loads(value)
    except (TypeError, ValueError) as err:
        raise InvalidRules("Rules must be valid JSON") from err
    if not isinstance(result, expected):
        raise InvalidRules(f"Rules must contain a {expected.__name__}")
    return result


def _source(raw: Any) -> None:
    if raw is not None and not valid_entity(raw):
        raise InvalidRules("Invalid source or backup entity ID")


def validate_states(raw: Any, primary: str) -> list[dict[str, Any]]:
    """Validate arbitrary attribute overrides with optional fallback."""
    if not isinstance(raw, list) or len(raw) > MAX_STATE_RULES:
        raise InvalidRules("state_rules must be an array of at most 48 rules")
    seen: set[str] = set()
    cleaned = []
    for item in raw:
        if not isinstance(item, dict) or set(item) - {
            "attribute", "source", "source_attribute", "fallback", "fallback_attribute", "value", "fallback_value"
        }:
            raise InvalidRules("Unsupported state rule keys")
        attr = item.get("attribute")
        if not isinstance(attr, str) or not FIELD_RE.fullmatch(attr) or attr in RESERVED_ATTRIBUTES or attr in seen:
            raise InvalidRules("Invalid, reserved, or duplicate target attribute")
        seen.add(attr)
        for k in ("source", "fallback"):
            _source(item.get(k))
        for k in ("source_attribute", "fallback_attribute"):
            if k in item and (not isinstance(item[k], str) or (item[k] != "state" and not FIELD_RE.fullmatch(item[k]))):
                raise InvalidRules("Invalid source attribute")
        if "source" not in item and "value" not in item:
            raise InvalidRules("A rule must have source or value")
        if "source" in item and "value" in item:
            raise InvalidRules("Use either source or constant value, not both")
        if "fallback_attribute" in item and "fallback" not in item:
            raise InvalidRules("fallback_attribute requires fallback")
        for value_key in ("value", "fallback_value"):
            if value_key in item and not isinstance(item[value_key], (str, int, float, bool, type(None))):
                raise InvalidRules("Constant overrides must be simple scalar values")
        cleaned.append(dict(item))
    return cleaned


def _step(step: Any, source: str) -> dict[str, Any]:
    if not isinstance(step, dict) or set(step) - {"service", "target", "data", "forward_arguments"}:
        raise InvalidRules("Unsupported action step format")
    service = step.get("service")
    target = step.get("target", source)
    if not isinstance(service, str) or service.count(".") != 1:
        raise InvalidRules("Action service must look like light.turn_on")
    domain, command = service.split(".")
    if command not in ALLOWED_SERVICES.get(domain, ()):
        raise InvalidRules(f"Service {service} is not on the safe allowlist")
    if not valid_entity(target) or target.split(".")[0] != domain:
        raise InvalidRules("Action target must be a single entity matching the service domain")
    data = step.get("data", {})
    if not isinstance(data, dict) or len(data) > 32:
        raise InvalidRules("Service data must be an object")
    for k, v in data.items():
        if not isinstance(k, str) or not FIELD_RE.fullmatch(k) or k in ("entity_id", "area_id", "device_id"):
            raise InvalidRules("Invalid or broad-targeting service data")
        if not isinstance(v, (str, int, float, bool, type(None), list)):
            raise InvalidRules("Only scalar and simple list service data is allowed")
        if isinstance(v, list) and (len(v) > 8 or not all(isinstance(x, (str, int, float, bool)) for x in v)):
            raise InvalidRules("List service data must have at most eight scalar items")
    forward = step.get("forward_arguments", False)
    if not isinstance(forward, bool):
        raise InvalidRules("forward_arguments must be true or false")
    return {"service": service, "target": target, "data": dict(data), "forward_arguments": forward}


def validate_actions(raw: Any, primary: str) -> dict[str, dict[str, Any]]:
    """Validate bounded, sequential primary and fallback service steps."""
    if not isinstance(raw, dict) or len(raw) > MAX_ACTION_RULES:
        raise InvalidRules("action_rules must be an object with at most 30 actions")
    allowed_actions = {
        "light": {"turn_on", "turn_off"},
        "switch": {"turn_on", "turn_off"},
        "climate": {"turn_on", "turn_off", "set_temperature", "set_hvac_mode", "set_humidity", "set_fan_mode", "set_preset_mode", "set_swing_mode", "set_swing_horizontal_mode", "set_aux_heat"},
        "fan": {"turn_on", "turn_off", "set_percentage", "set_preset_mode", "set_direction", "set_oscillating"},
        "cover": {"open_cover", "close_cover", "stop_cover", "set_cover_position", "open_cover_tilt", "close_cover_tilt", "stop_cover_tilt", "set_cover_tilt_position"},
        "number": {"set_value"},
        "select": {"select_option"},
    }.get(primary.split(".")[0], set())
    output = {}
    for action, item in raw.items():
        if action not in allowed_actions or not isinstance(item, dict) or set(item) - {"steps", "fallback", "reported_state"}:
            raise InvalidRules(f"Unsupported action or keys: {action}")
        steps = item.get("steps")
        backup = item.get("fallback", [])
        if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
            raise InvalidRules("Each overridden action needs 1 to 12 steps")
        if not isinstance(backup, list) or len(backup) > MAX_STEPS:
            raise InvalidRules("Fallback can contain up to 12 steps")
        reported = item.get("reported_state")
        if reported is not None and (not isinstance(reported, str) or reported not in {"on", "off"}):
            raise InvalidRules("reported_state must be on or off")
        output[action] = {
            "steps": [_step(s, primary) for s in steps],
            "fallback": [_step(s, primary) for s in backup],
            "reported_state": reported,
        }
    return output


def dependencies(primary: str, states: list[dict], actions: dict) -> set[str]:
    """Only subscribe to states the proxy actually needs."""
    result = {primary}
    for rule in states:
        result.update(rule[k] for k in ("source", "fallback") if rule.get(k))
    for rule in actions.values():
        for step in rule["steps"] + rule["fallback"]:
            result.add(step["target"])
    return result


def get_candidate(state: Any, attr: str) -> Any:
    """A None return indicates a missing/unusable state."""
    if state is None or state.state in BAD_STATES:
        return None
    return state.state if attr == "state" else state.attributes.get(attr)


def pick_value(states: dict[str, Any], rule: dict[str, Any]) -> tuple[Any, str | None]:
    """Select live source, fallback sensor, then fallback literal."""
    if "value" in rule:
        return rule["value"], None
    source = rule["source"]
    attr = rule.get("source_attribute", "state")
    value = get_candidate(states.get(source), attr)
    if value is not None:
        return value, None
    message = f"Source {source} / {attr} unavailable"
    if fallback := rule.get("fallback"):
        value = get_candidate(states.get(fallback), rule.get("fallback_attribute", "state"))
        if value is not None:
            return value, message + "; using backup"
        message += f"; backup {fallback} unavailable"
    if "fallback_value" in rule:
        return rule["fallback_value"], message + "; using fallback value"
    return None, message


def validate_all(primary: str, states: Any, actions: Any) -> tuple[list[dict], dict]:
    """Apply policy consistently to flows and persisted configuration."""
    if not valid_entity(primary) or primary.split(".")[0] not in SUPPORTED_DOMAINS:
        raise InvalidRules("Unsupported primary entity")
    state_rules = validate_states(states, primary)
    action_rules = validate_actions(actions, primary)
    return state_rules, action_rules
