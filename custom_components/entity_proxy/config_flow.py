"""UI configuration and editing for Entity Proxy."""

from __future__ import annotations

import json
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector

from .const import DOMAIN, SUPPORTED_DOMAINS
from .rules import InvalidRules, parse_json, validate_all

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
    state = parse_json(raw["state_rules"], list)
    actions = parse_json(raw["action_rules"], dict)
    state, actions = validate_all(source, state, actions)
    return {"state_rules": state, "action_rules": actions}


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


class EntityProxyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
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
            else:
                self._source = source
                self._name = user_input["name"].strip()
                return await self.async_step_rules()
        return self.async_show_form(
            step_id="user", errors=errors,
            data_schema=vol.Schema({
                vol.Required("name"): selector.TextSelector(),
                vol.Required("source"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=sorted(SUPPORTED_DOMAINS))
                ),
            }),
        )

    async def async_step_rules(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                rules = _load(user_input, self._source)
                if not _no_proxy_refs(self.hass, self._source, rules):
                    raise InvalidRules("Other Entity Proxy entities cannot be used in rules")
            except InvalidRules as err:
                _LOGGER.warning("Invalid Entity Proxy rules: %s", err)
                errors["base"] = "invalid_rules"
            else:
                return self.async_create_entry(
                    title=self._name,
                    data={"source": self._source, "name": self._name},
                    options=rules,
                )
        return self.async_show_form(
            step_id="rules", errors=errors,
            data_schema=_rules_schema("[]", "{}"),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ProxyOptionsFlow()


class ProxyOptionsFlow(config_entries.OptionsFlow):
    """Edit rules in the UI, applying changes through a reload."""

    async def async_step_init(self, user_input=None):
        entry = self.config_entry
        errors = {}
        if user_input is not None:
            try:
                rules = _load(user_input, entry.data["source"])
                if not _no_proxy_refs(self.hass, entry.data["source"], rules):
                    raise InvalidRules("Other Entity Proxy entities cannot be used in rules")
            except InvalidRules as err:
                _LOGGER.warning("Invalid Entity Proxy options: %s", err)
                errors["base"] = "invalid_rules"
            else:
                return self.async_create_entry(title="", data=rules)
        return self.async_show_form(
            step_id="init", errors=errors,
            data_schema=_rules_schema(
                json.dumps(entry.options.get("state_rules", []), indent=2),
                json.dumps(entry.options.get("action_rules", {}), indent=2),
            ),
        )
