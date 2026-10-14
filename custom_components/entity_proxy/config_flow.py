"""UI setup and safe post-install editing for Entity Proxy."""

from __future__ import annotations

import json
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector

from .const import DOMAIN, SUPPORTED_DOMAINS
from .guided_flow import GuidedRulesMixin
from .rules import InvalidRules, RuleFieldError, parse_configuration, remap_source_references, validate_all

_LOGGER = logging.getLogger(__name__)


def _rules_schema(state: str, actions: str) -> vol.Schema:
    return vol.Schema({
        vol.Required("state_rules", default=state): selector.TextSelector(
            selector.TextSelectorConfig(multiline=True)
        ),
        vol.Required("action_rules", default=actions): selector.TextSelector(
            selector.TextSelectorConfig(multiline=True)
        ),
    })


def _load(raw: dict, source: str) -> dict:
    return parse_configuration(source, raw["state_rules"], raw["action_rules"])


def _no_proxy_refs(hass, source: str, rules: dict) -> bool:
    registry = er.async_get(hass)
    ids = {source}
    for rule in rules["state_rules"]:
        ids.update(rule[key] for key in ("source", "fallback") if rule.get(key))
    for rule in rules["action_rules"].values():
        ids.update(step["target"] for step in rule["steps"] + rule["fallback"])
    return not any(
        ent is not None and ent.platform == DOMAIN
        for entity_id in ids if (ent := registry.async_get(entity_id)) is not None
    )


def _effective_source(entry) -> str:
    """Old entries keep their original source; edited entries use options."""
    return entry.options.get("source", entry.data["source"])


def _preset_selection(action_rules: dict) -> tuple[str | None, str | None]:
    """Prefill the editor if a normal WLED-style off override exists."""
    off_rule = action_rules.get("turn_off", {})
    steps = off_rule.get("steps", [])
    if len(steps) != 1 or steps[0].get("service") != "select.select_option":
        return None, None
    step = steps[0]
    option = step.get("data", {}).get("option")
    target = step.get("target")
    if not isinstance(option, str) or not isinstance(target, str):
        return None, None
    return target, option


class EntityProxyConfigFlow(GuidedRulesMixin, config_entries.ConfigFlow, domain=DOMAIN):
    """Create a proxy from a source entity and editable JSON rules."""

    VERSION = 1

    def __init__(self) -> None:
        self._source = ""
        self._name = ""

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            source = user_input["source"]
            registry_ent = er.async_get(self.hass).async_get(source)
            if registry_ent is not None and registry_ent.platform == DOMAIN:
                errors["base"] = "proxy_source"
            elif source.split(".")[0] not in SUPPORTED_DOMAINS:
                errors["base"] = "unsupported"
            elif not user_input["name"].strip():
                errors["name"] = "empty_name"
            else:
                self._source = source
                self._name = user_input["name"].strip()
                return await self.async_step_setup()
        return self.async_show_form(
            step_id="user", errors=errors,
            data_schema=vol.Schema({
                vol.Required("name"): selector.TextSelector(),
                vol.Required("source"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=sorted(SUPPORTED_DOMAINS))
                ),
            }),
        )

    def _begin_guided(self):
        if not hasattr(self, "_guided_options"):
            self._guided_options = {"state_rules": [], "action_rules": {}}

    def _guided_source(self):
        return self._source

    def _guided_refs(self, source, rules):
        return _no_proxy_refs(self.hass, source, rules)

    def _save_guided(self):
        return self.async_create_entry(title=self._name, data={"source": self._source, "name": self._name}, options=self._guided_options)

    async def async_step_setup(self, user_input=None):
        return self.async_show_menu(step_id="setup", menu_options=["transparent", "guided", "rules"])

    async def async_step_transparent(self, user_input=None):
        self._begin_guided()
        return await self.async_step_finish(user_input)

    async def async_step_preset(self, user_input=None):
        return await _preset_step(self, user_input)

    async def async_step_rules(self, user_input=None):
        errors = {}
        problem = ""
        if user_input is not None:
            try:
                rules = _load(user_input, self._source)
                if not _no_proxy_refs(self.hass, self._source, rules):
                    raise InvalidRules("Other Entity Proxy entities cannot be used in rules")
            except RuleFieldError as err:
                errors[err.field] = "invalid_state_rules" if err.field == "state_rules" else "invalid_action_rules"
                problem = str(err)[:300]
                _LOGGER.debug("Invalid Entity Proxy configuration: %s", problem)
            except InvalidRules as err:
                errors["base"] = "invalid_rules"
                problem = str(err)[:300]
                _LOGGER.debug("Invalid Entity Proxy configuration: %s", problem)
            else:
                return self.async_create_entry(
                    title=self._name,
                    data={"source": self._source, "name": self._name},
                    options=rules,
                )
        return self.async_show_form(
            step_id="rules", errors=errors,
            description_placeholders={"problem": f"\n\n**Validation error:** {problem}" if problem else ""},
            data_schema=_rules_schema(
                (user_input or {}).get("state_rules", "[]"),
                (user_input or {}).get("action_rules", "{}"),
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ProxyOptionsFlow()


class ProxyOptionsFlow(GuidedRulesMixin, config_entries.OptionsFlow):
    """Edit source, off preset and advanced rules without losing the proxy ID."""

    def _begin_guided(self):
        if not hasattr(self, "_guided_options"):
            from copy import deepcopy
            self._guided_options = deepcopy(dict(self.config_entry.options))

    def _guided_source(self):
        return _effective_source(self.config_entry)

    def _guided_refs(self, source, rules):
        return _no_proxy_refs(self.hass, source, rules)

    def _save_guided(self):
        return self.async_create_entry(title="", data=self._guided_options)

    async def async_step_init(self, user_input=None):
        menu = ["source", "guided", "rules"]
        if _effective_source(self.config_entry).startswith("light."):
            menu.insert(1, "preset")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_source(self, user_input=None):
        entry = self.config_entry
        current = _effective_source(entry)
        domain = entry.data["source"].split(".", 1)[0]
        errors = {}
        if user_input is not None:
            new_source = user_input["source"]
            registry_ent = er.async_get(self.hass).async_get(new_source)
            if new_source.split(".", 1)[0] != domain:
                errors["base"] = "source_domain"
            elif registry_ent is not None and registry_ent.platform == DOMAIN:
                errors["base"] = "proxy_source"
            else:
                options = remap_source_references(entry.options, current, new_source)
                try:
                    states, actions = validate_all(new_source, options.get("state_rules", []), options.get("action_rules", {}))
                    options.update({"state_rules": states, "action_rules": actions})
                    if not _no_proxy_refs(self.hass, new_source, options):
                        raise InvalidRules("Proxy entities are not valid dependencies")
                except InvalidRules:
                    errors["base"] = "invalid_rules"
                else:
                    return self.async_create_entry(title="", data=options)
        return self.async_show_form(
            step_id="source", errors=errors,
            data_schema=vol.Schema({
                vol.Required("source", default=(user_input or {}).get("source", current)):
                    selector.EntitySelector(selector.EntitySelectorConfig(domain=[domain]))
            }),
        )

    async def async_step_preset(self, user_input=None):
        return await _preset_step(self, user_input)

    async def async_step_rules(self, user_input=None):
        entry = self.config_entry
        source = _effective_source(entry)
        errors = {}
        problem = ""
        if user_input is not None:
            try:
                rules = _load(user_input, source)
                if not _no_proxy_refs(self.hass, source, rules):
                    raise InvalidRules("Other Entity Proxy entities cannot be used in rules")
            except RuleFieldError as err:
                errors[err.field] = "invalid_state_rules" if err.field == "state_rules" else "invalid_action_rules"
                problem = str(err)[:300]
                _LOGGER.debug("Invalid Entity Proxy options: %s", problem)
            except InvalidRules as err:
                errors["base"] = "invalid_rules"
                problem = str(err)[:300]
                _LOGGER.debug("Invalid Entity Proxy options: %s", problem)
            else:
                return self.async_create_entry(title="", data={**entry.options, **rules})
        return self.async_show_form(
            step_id="rules", errors=errors,
            description_placeholders={"problem": f"\n\n**Validation error:** {problem}" if problem else ""},
            data_schema=_rules_schema(
                (user_input or {}).get("state_rules", json.dumps(entry.options.get("state_rules", []), indent=2)),
                (user_input or {}).get("action_rules", json.dumps(entry.options.get("action_rules", {}), indent=2)),
            ),
        )


async def _preset_step(self, user_input=None):
    staged = getattr(self, "_guided_active", False) or isinstance(self, EntityProxyConfigFlow)
    self._begin_guided()
    source = self._guided_source()
    options = self._guided_options
    if not source.startswith("light."):
        return self.async_abort(reason="not_light")
    actions = options.get("action_rules", {})
    preset_entity, preset_name = _preset_selection(actions)
    errors = {}
    if user_input is not None:
        target = user_input["preset_entity"]
        option = user_input["preset_name"].strip()
        if not option:
            errors["preset_name"] = "empty_preset"
        else:
            updated_actions = dict(actions)
            updated_actions["turn_off"] = {
                "steps": [{
                    "service": "select.select_option",
                    "target": target,
                    "data": {"option": option},
                }],
                "reported_state": "off",
            }
            try:
                states, actions_clean = validate_all(source, options.get("state_rules", []), updated_actions)
                updated = {**options, "state_rules": states, "action_rules": actions_clean}
                if not _no_proxy_refs(self.hass, source, updated):
                    raise InvalidRules("Proxy entities are not valid dependencies")
            except InvalidRules:
                errors["base"] = "invalid_rules"
            else:
                self._guided_options = updated
                if staged:
                    return await self.async_step_guided()
                return self._save_guided()
    preset_schema = {
        vol.Required("preset_entity", default=(user_input or {}).get("preset_entity", preset_entity))
        if (user_input or {}).get("preset_entity", preset_entity) else vol.Required("preset_entity"):
            selector.EntitySelector(selector.EntitySelectorConfig(domain=["select"])),
        vol.Required("preset_name", default=(user_input or {}).get("preset_name", preset_name or "Light OFF")):
            selector.TextSelector(),
    }
    return self.async_show_form(
        step_id="preset", errors=errors, data_schema=vol.Schema(preset_schema),
    )
