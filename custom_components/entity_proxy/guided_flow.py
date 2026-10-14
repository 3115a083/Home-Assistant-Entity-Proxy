"""Form-based rule editing shared by setup and options flows.

All writes go through the same validation as the advanced editor. Existing
rules and entry IDs are preserved; JSON remains optional for complex sequences.
"""
from __future__ import annotations

from copy import deepcopy

import voluptuous as vol
from homeassistant.helpers import selector

from .rules import InvalidRules, validate_all

# These are the adapter methods, not the broader service allowlist.
ACTIONS = {
    "light": ["turn_on", "turn_off"],
    "switch": ["turn_on", "turn_off"],
    "climate": ["turn_on", "turn_off", "set_temperature", "set_hvac_mode", "set_humidity", "set_fan_mode", "set_preset_mode", "set_swing_mode", "set_swing_horizontal_mode", "set_aux_heat"],
    "fan": ["turn_on", "turn_off", "set_percentage", "set_preset_mode", "set_direction", "set_oscillating"],
    "cover": ["open_cover", "close_cover", "stop_cover", "set_cover_position", "open_cover_tilt", "close_cover_tilt", "stop_cover_tilt", "set_cover_tilt_position"],
    "number": ["set_value"],
    "select": ["select_option"],
}


def choice(options):
    return selector.SelectSelector(selector.SelectSelectorConfig(options=options))


def text():
    return selector.TextSelector()


def scalar(raw, kind):
    """Explicit types avoid interpreting ordinary text as executable content."""
    if kind == "number":
        return float(raw)
    if kind == "boolean":
        if raw.lower() not in ("true", "false"):
            raise ValueError("Use true or false")
        return raw.lower() == "true"
    return raw


class GuidedRulesMixin:
    """Host supplies source, staged options, validation and save behavior."""

    async def async_step_guided(self, user_input=None):
        self._begin_guided()
        self._guided_active = True
        menu = ["state"]
        if self._guided_source().split(".")[0] in ACTIONS:
            menu.append("action")
        if self._guided_source().startswith("light."):
            menu.append("preset")
        options = self._guided_options
        if options.get("state_rules") or options.get("action_rules"):
            menu.append("remove")
        menu.append("finish")
        return self.async_show_menu(step_id="guided", menu_options=menu)

    def _validate_guided(self, options):
        source = self._guided_source()
        states, actions = validate_all(source, options.get("state_rules", []), options.get("action_rules", {}))
        updated = {**options, "state_rules": states, "action_rules": actions}
        if not self._guided_refs(source, updated):
            raise InvalidRules("Proxy dependencies are blocked")
        self._guided_options = updated

    async def async_step_state(self, user_input=None):
        self._begin_guided()
        errors = {}
        if user_input is not None:
            try:
                rule = {"attribute": user_input["attribute"].strip()}
                if user_input["mode"] == "entity":
                    if not user_input.get("value_source"):
                        raise InvalidRules("Select a value source")
                    rule["source"] = user_input["value_source"]
                    rule["source_attribute"] = user_input.get("source_attribute", "state").strip() or "state"
                    if user_input.get("fallback"):
                        rule["fallback"] = user_input["fallback"]
                        rule["fallback_attribute"] = user_input.get("fallback_attribute", "state").strip() or "state"
                    if user_input.get("fallback_value", "") != "":
                        rule["fallback_value"] = scalar(user_input["fallback_value"], user_input["value_type"])
                else:
                    rule["value"] = scalar(user_input.get("value", ""), user_input["value_type"])
                updated = deepcopy(self._guided_options)
                updated["state_rules"] = [r for r in updated.get("state_rules", []) if r["attribute"] != rule["attribute"]] + [rule]
                self._validate_guided(updated)
            except (InvalidRules, ValueError, TypeError, OverflowError):
                errors["base"] = "invalid_rules"
            else:
                return await self.async_step_guided()
        raw = user_input or {}
        return self.async_show_form(step_id="state", errors=errors, data_schema=vol.Schema({
            vol.Required("attribute", default=raw.get("attribute", "state")): text(),
            vol.Required("mode", default=raw.get("mode", "entity")): choice(["entity", "constant"]),
            vol.Optional("value_source", **({"default": raw["value_source"]} if raw.get("value_source") else {})): selector.EntitySelector(),
            vol.Optional("source_attribute", default=raw.get("source_attribute", "state")): text(),
            vol.Optional("fallback", **({"default": raw["fallback"]} if raw.get("fallback") else {})): selector.EntitySelector(),
            vol.Optional("fallback_attribute", default=raw.get("fallback_attribute", "state")): text(),
            vol.Required("value_type", default=raw.get("value_type", "number")): choice(["number", "text", "boolean"]),
            vol.Optional("value", default=raw.get("value", "")): text(),
            vol.Optional("fallback_value", default=raw.get("fallback_value", "")): text(),
        }))

    async def async_step_action(self, user_input=None):
        """A single service step with a typed parameter; sequences use advanced UI."""
        from .const import ALLOWED_SERVICES
        self._begin_guided()
        source = self._guided_source()
        actions = ACTIONS.get(source.split(".")[0], [])
        if not actions:
            return self.async_abort(reason="read_only")
        errors = {}
        if user_input is not None:
            try:
                data = {}
                if user_input.get("parameter", "").strip():
                    data[user_input["parameter"].strip()] = scalar(user_input.get("parameter_value", ""), user_input["value_type"])
                rule = {"steps": [{"service": user_input["service"], "target": user_input["target"], "data": data, "forward_arguments": user_input["forward_arguments"]}]}
                if user_input["reported_state"] != "source":
                    rule["reported_state"] = user_input["reported_state"]
                updated = deepcopy(self._guided_options)
                updated.setdefault("action_rules", {})[user_input["action"]] = rule
                self._validate_guided(updated)
            except (InvalidRules, ValueError, TypeError, OverflowError):
                errors["base"] = "invalid_rules"
            else:
                return await self.async_step_guided()
        raw = user_input or {}
        # The legacy rule name set_oscillating is not a real HA service.
        services = sorted(f"{domain}.{name}" for domain, names in ALLOWED_SERVICES.items() for name in names if name != "set_oscillating")
        return self.async_show_form(step_id="action", errors=errors, data_schema=vol.Schema({
            vol.Required("action", default=raw.get("action", actions[0])): choice(actions),
            vol.Required("service", default=raw.get("service", services[0])): choice(services),
            vol.Required("target", default=raw.get("target", source)): selector.EntitySelector(selector.EntitySelectorConfig(domain=sorted(ALLOWED_SERVICES))),
            vol.Required("forward_arguments", default=raw.get("forward_arguments", False)): selector.BooleanSelector(),
            vol.Optional("parameter", default=raw.get("parameter", "")): text(),
            vol.Optional("parameter_value", default=raw.get("parameter_value", "")): text(),
            vol.Required("value_type", default=raw.get("value_type", "text")): choice(["text", "number", "boolean"]),
            vol.Required("reported_state", default=raw.get("reported_state", "source")): choice(["source", "on", "off"]),
        }))

    async def async_step_remove(self, user_input=None):
        self._begin_guided()
        options = self._guided_options
        keys = [f"state:{r['attribute']}" for r in options.get("state_rules", [])] + [f"action:{a}" for a in options.get("action_rules", {})]
        if not keys:
            return await self.async_step_guided()
        errors = {}
        if user_input is not None:
            if user_input["rule"] not in keys:
                errors["base"] = "invalid_rules"
            else:
                updated = deepcopy(options)
                kind, key = user_input["rule"].split(":", 1)
                if kind == "state":
                    updated["state_rules"] = [r for r in updated["state_rules"] if r["attribute"] != key]
                else:
                    del updated["action_rules"][key]
                self._validate_guided(updated)
                return await self.async_step_guided()
        return self.async_show_form(step_id="remove", errors=errors, data_schema=vol.Schema({vol.Required("rule"): choice(keys)}))

    async def async_step_finish(self, user_input=None):
        self._begin_guided()
        # Explicit final save keeps all intermediate changes staged.
        if user_input is not None:
            self._validate_guided(self._guided_options)
            return self._save_guided()
        return self.async_show_form(
            step_id="finish", data_schema=vol.Schema({}),
            description_placeholders={
                "source": self._guided_source(),
                "states": ", ".join(r["attribute"] for r in self._guided_options.get("state_rules", [])) or "0",
                "actions": ", ".join(self._guided_options.get("action_rules", {})) or "0",
            },
        )
