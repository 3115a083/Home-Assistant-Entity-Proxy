# Home Assistant Entity Proxy

A configurable, event-driven Home Assistant custom integration that wraps an existing entity, selectively overrides its reported state/attributes, and replaces individual service actions with safe, targeted Home Assistant services. Includes fallbacks and a per-proxy error sensor.

> **Status: v0.1.5, experimental.** Static checks and unit tests are provided, but this release has **not yet been tested against a live Home Assistant instance**. Do not use it for safety-critical heating, locks, alarms, or other essential control. No software can be guaranteed to be free of vulnerabilities.

## Supported entities

| Source domain | Proxy domain | Read/override state and attributes | Write actions |
| --- | --- | --- | --- |
| `light` | `light` | On/off, brightness, RGB/RGBW/RGBWW, color temperature, effects, etc. | On/off |
| `switch` | `switch` | On/off | On/off |
| `climate` | `climate` | HVAC state, current/target temperature, humidity, preset, fan, etc. | Temperature, HVAC/preset/fan/swing modes, on/off, humidity |
| `sensor` | `sensor` | Value, unit, device class, state class | Read only |
| `binary_sensor` | `binary_sensor` | On/off, device class | Read only |
| `fan` | `fan` | On/off, percentage, presets, oscillation, direction | On/off, percentage, presets, direction, oscillation |
| `cover` | `cover` | Open/closed, position, tilt, supported features | Open/close/stop, position and tilt |
| `number` | `number` | Value, min/max/step/unit | Set value |
| `select` | `select` | Current option, choices | Select option |

The goal is to preserve the **standard interface** of each supported entity, including its reported supported features. Not every vendor-specific attribute or extra device entity is cloned. For example, a WLED preset selector remains a separate entity, but you may reference it in an action rule. Device-level proprietary services are not automatically proxied.

## Installation

### HACS (custom repository)

1. Open HACS, choose **Custom repositories**, paste `https://github.com/3115a083/Home-Assistant-Entity-Proxy`, and select category **Integration**.
2. Install **Entity Proxy** and restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → Entity Proxy**.
4. Choose the source entity and a name.
5. Add rules using the multiline JSON editor, or leave the defaults `[]` and `{}` for a transparent proxy.
6. Use **Configure** on the integration later to change the source entity, edit the light-off preset, or edit advanced JSON rules. All changes apply after an automatic entry reload.

### Releases and HACS updates

Entity Proxy uses semantic versions. Each HACS-installable version has:

- An integration `manifest.json` version, such as `0.1.3`.
- A matching published GitHub Release tagged `v0.1.3`.
- English release notes derived from [CHANGELOG.md](CHANGELOG.md).

Releases are generated automatically from a version change on `main`, **only after checks pass**. Do not manually edit tags or overwrite published releases. The default branch is hidden in HACS to favor stable tagged versions.

**Migrating an older HACS installation that shows a short Git commit hash:** Open HACS → Entity Proxy → three-dot menu → **Redownload**, explicitly select the latest release (`v0.1.5` or newer), and restart Home Assistant. HACS does not always prompt for the first tagged release when transitioning from an earlier commit-based install. Existing Home Assistant integration entries and their settings are retained by a normal HACS reinstall; keep a backup before changing versions.

Find release notes at [GitHub Releases](https://github.com/3115a083/Home-Assistant-Entity-Proxy/releases).

### Manual

Copy `custom_components/entity_proxy` into `<config>/custom_components/entity_proxy`, restart Home Assistant and proceed with step 3 above.

**Keep the source entity enabled.** You may hide it from dashboards, but disabling it will prevent the proxy from working.

## Editing an existing proxy (no re-creation required)

Go to **Settings → Devices & services → Integrations → Entity Proxy**, open the **Entity Proxy integration entry/card** (not the WLED device or individual entity) and choose **Configure**. Choose:

- **Change source entity:** Select the renamed or replacement entity. Only entities in the *same domain* are allowed, so the proxy keeps its original type and entity ID. Literal references to the previous source in state and action rules are migrated automatically. References to other entities, such as WLED preset selectors, are unchanged. Historical virtual light state and saved color snapshots are reset when the source changes. The original integration data is never rewritten; the new source is saved in the entry options.
- **Edit off preset** (lights only): Choose the `select` entity and the exact preset name. This updates the `turn_off` action while preserving all other action rules and state overrides. **Any previous `turn_off` fallback is replaced.** The editor intentionally does not add a power-cutting fallback.
- **Edit advanced rules:** Edit or add state and action overrides using JSON. The current values are prefilled and input is retained when validation fails.

The source entity and the preset select entity must remain enabled in Home Assistant. Hide the original *from dashboards* if desired, but do not disable it. Changing the source domain (e.g. `light` to `switch`) requires creating a new proxy.

**If Configure is missing:** First verify the files under `/config/custom_components/entity_proxy/` are from release v0.1.5 (see `manifest.json`), not merely that HACS displays the latest available version. Redownload the tagged release in HACS, restart Home Assistant, refresh the browser and open the **integration entry's** menu. `Configure` is an *options flow* at the integration level, not a button on the source device. If it remains missing, collect the Home Assistant version and config-entry diagnostics/logs and report a bug. Do not delete the proxy to fix a missing menu, since that may change its entity IDs.

## Device association

Proxy entities now appear on **the same Home Assistant device page as their source entity**, including the associated diagnostics error sensor. The normal proxy light/switch/climate controls stay under their standard device controls section; the error sensor is categorized as Diagnostics.

The source integration remains the only owner of the physical device. Entity Proxy attaches through Home Assistant's official helper device link (`device_entry`), not by copying the source's device identifiers. This avoids duplicate devices and is compatible with the device registry changes introduced in Home Assistant 2026.8.

- The source entity must already belong to a device in the Home Assistant entity registry. Sources without devices remain standalone proxy entities.
- Changing the source in **Settings → Devices & services → Entity Proxy → Configure → Source** reloads the proxy and updates its device association without changing the proxy's entity unique ID or its existing rules.
- If the source integration changes a device assignment without reconfiguring Entity Proxy, reload the Entity Proxy integration so the device link is refreshed.
- Do not disable the source entity. You can hide it from your dashboards.
- Do not set `device_info` or manually alter the source device registry's config entries: these patterns are unsupported for helper integrations.

## How rules work

Advanced rules are configured in two UI text boxes. They use **strict JSON**, not Jinja or executable Python. Add as many state/action rules as needed within the documented limits. An action not overridden is forwarded to the original entity. A state property not overridden mirrors its original source value.

### Troubleshooting: Invalid Entity Proxy rules

The two editors have **different JSON types**:

- **State overrides** must contain a JSON **array** (`[]`). An individual rule looks like `[{"attribute":"current_temperature","source":"sensor.room_temperature"}]`.
- **Action overrides** must contain a JSON **object** (`{}`). WLED `turn_off`, `steps`, `fallback` and `reported_state` belong here, **not** in state overrides.

Messages such as `Rules must contain a list` and `Unsupported state rule keys` usually mean an action rule was entered into the state editor. Version 0.1.1 highlights the affected field, shows a more specific validation error, preserves the user's input, and avoids writing normal form-validation failures into the warning log. No malformed configuration is silently accepted or executed.

### Example 1: WLED, suppress the white flash on switch-on

Use the existing WLED light as the source (for example `light.wled`). Create a WLED preset named `Light OFF` with RGB **and all white channels** set to black/zero, while keeping the underlying WLED power state **on**.

**State overrides**:

```json
[]
```

**Action overrides**:

```json
{
  "turn_off": {
    "steps": [
      {
        "service": "select.select_option",
        "target": "select.wled_preset",
        "data": {"option": "Light OFF"}
      }
    ],
    "fallback": [
      {
        "service": "light.turn_off",
        "target": "light.wled"
      }
    ],
    "reported_state": "off"
  }
}
```

When Home Assistant calls `turn_off` on the **proxy**, the WLED preset is selected and the proxy reports `off`, while WLED stays powered. When the proxy is turned back on, the integration tries to restore the last non-black color and brightness captured from the original light. The source is never renamed or disabled. The fallback really powers off WLED if the preset selector is unavailable; **in that exceptional case, the next power-on can still flash white**. To prevent that, remove the fallback and accept a failed off action instead.

Notes:

- The preset must be truly black on all channels and keep WLED on.
- Some WLED effects and color modes may require explicit testing; power restoration is best-effort.
- Avoid using the original WLED power toggle in automations; use the proxy entity.
- Disabling the source entity or its preset select entity breaks this setup.

### Example 2: Thermostat using another temperature sensor and backup

Choose `climate.living_room` as the source. Enter these **state overrides**:

```json
[
  {
    "attribute": "current_temperature",
    "source": "sensor.living_room_temperature",
    "fallback": "sensor.backup_room_temperature",
    "fallback_value": 19.0
  },
  {
    "attribute": "current_humidity",
    "source": "sensor.living_room_humidity",
    "fallback_value": 45
  }
]
```

The proxy's UI will display the selected sensor's `current_temperature`. If it is unavailable, the proxy tries the backup sensor, then the literal fallback. An issue is added to the error sensor while a fallback is in use.

**This overrides the reported temperature only.** It does not alter the physical thermostat's internal control algorithm. Changing that requires device support or a separate thermostat control solution.

### Example 3: Switch with alternate off behavior and backup

Choose `switch.lamp` as source. The action override below turns off a different switch, falling back to the original source switch if the first target fails:

```json
{
  "turn_off": {
    "steps": [
      {"service": "switch.turn_off", "target": "switch.lamp_relay"}
    ],
    "fallback": [
      {"service": "switch.turn_off", "target": "switch.lamp"}
    ],
    "reported_state": "off"
  }
}
```

The source state is still tracked. A virtual `off` state is stored while the original device may remain `on`. Virtual `off` is cleared on a normal `turn_on` action or when this light example detects external non-black output.

## Rule reference

### State rules: a JSON array

Each item supports:

| Key | Meaning |
| --- | --- |
| `attribute` | Proxy property to override: `state`, `current_temperature`, `brightness`, `temperature`, etc. |
| `source` | Primary entity ID to read from. |
| `source_attribute` | Attribute of that entity; defaults to `state`. |
| `fallback` | Backup entity ID, optional. |
| `fallback_attribute` | Attribute of the backup entity; defaults to `state`. |
| `fallback_value` | Constant if both primary and backup are unavailable. |
| `value` | Constant override instead of `source`. |

Rules that have no valid value fall back to the proxy property's ordinary default. Each overridden property can have one rule. For non-`state` fields, use the property's **actual Home Assistant attribute name**. Some attributes (e.g. `supported_features`) cannot be overridden by design.

### Action rules: a JSON object

Keys are supported entity actions such as `turn_off`, `turn_on`, `set_temperature`, `set_percentage`, `open_cover`, or `select_option`. Each rule supports:

| Key | Meaning |
| --- | --- |
| `steps` | Required list of 1 to 12 sequential service actions. |
| `fallback` | Optional list of 1 to 12 services, attempted if a primary step fails. |
| `reported_state` | Optional virtual state (`on` or `off`) after the action succeeds. |

Each step supports:

| Key | Meaning |
| --- | --- |
| `service` | Explicit allowlisted entity control service, e.g. `select.select_option`. |
| `target` | Exactly one target `entity_id`; defaults to the source entity. |
| `data` | Static JSON service payload, e.g. `{"option":"Light OFF"}`. |
| `forward_arguments` | Optional boolean; copy incoming service arguments to the target before applying `data`. Defaults to false for custom steps. |

Service targets must match the service domain, and the integration never accepts `area_id`, `device_id`, entity lists, scripts, templates, REST URLs, shell commands, or arbitrary Python. Services remain restricted to an explicit allowlist. HA can still reject data that does not fit a particular service schema.

### Automatic pass-through

If an action has **no** override, the proxy passes the original parameters to the same action on its source entity. If a source light was virtually switched off through a custom action, a plain `turn_on` restores its remembered lit appearance when possible. User-supplied `turn_on` parameters take precedence.

## Diagnostics and fallbacks

Find both diagnostic entities under **Settings → Devices & services → Entities**, searching for your proxy's name plus `Errors` or `Configuration`. When the source has a registered physical device (such as a WLED controller), both diagnostics are linked to **that existing device's Diagnostics section**. Depending on Home Assistant's display filters, you may need to show diagnostic or hidden entities. The exact `sensor.*` entity IDs depend on the entity registry, not just the display name.

**Configuration sensor:** `sensor.<name>_configuration` reports `configured` and safe, read-only attributes including `source_entity`, `state_overrides`, `action_overrides`, `off_preset_entity`, `off_preset_name`, `virtual_state` and `active_errors`. This shows what the entry is **actually using** after its reload. It deliberately does not expose raw service data or secrets.

**Errors sensor:** `sensor.<name>_errors` reports the number of active issues. Open its attributes to see the `issues` list; an error count of `0` means no errors are currently recorded, not proof that the physical device behaved correctly.


Every config entry creates a `sensor.<name>_errors` entity:

- State `0`: no active issues.
- State `1` or greater: number of active issues.
- `issues` attribute: up to 20 messages describing unavailable sources, failed action targets and backup use.
- Issues clear when a primary sensor/action succeeds again. A failed action cannot be considered successful just because the proxy's displayed state was changed.

Sources are monitored with `async_track_state_change_event`; there is no polling. Action commands for each proxy are serialized. The integration stores only the last light appearance and virtual on/off status using Home Assistant's local storage. Each instance has limits: 48 state rules, 30 overridden actions, 12 steps per action and 16 kB per JSON editor field.

**Fallback semantics:** If an action has multiple primary steps and the third step fails, the first two are **not rolled back**. The backup sequence then runs. Home Assistant services are not transactional. A service timing out after 15 seconds may still complete later on some devices; check diagnostics before retrying a potentially dangerous action. Avoid using this integration to control safety-critical equipment.

## Security and design

- All config is validated using bounded JSON parsing and an explicit service whitelist. No eval, Python expressions, Jinja templates, URL fetching or shell execution.
- No broad entity/area/device targets, wildcard IDs or global integration services.
- Target calls are checked for availability and their target is always forcibly set to the configured single entity ID.
- Proxy-to-proxy references are blocked to prevent cycles and infinite event loops, both during configuration and before service execution.
- State changes subscribe only to the configured source, backup and action-target entities. No polling threads or background HTTP requests.
- Errors and stored light snapshots are bounded. No additional Python dependencies are installed.

A Home Assistant administrator who can edit a rule can still control other **allowlisted entities**. Treat rule editing as a privileged activity. No codebase can guarantee zero vulnerabilities or compatibility with every device integration.

## Development and verification

```bash
python -m compileall -q custom_components/entity_proxy
python -m unittest discover -s tests -v
```

These checks validate syntax and standalone rule logic. **An integration smoke test on a real Home Assistant installation is still required**, especially for attribute schema differences between vendors. Please open a GitHub issue with logs and a minimal example configuration when reporting a problem.

## Limitations and roadmap

- Setup and editing are available in a UI, but the rule builder currently uses JSON text fields. A point-and-click rule editor is planned.
- Proxy support is intentionally limited to the nine listed standard domains. Additional domains need a small platform adapter.
- Not all vendor-specific attributes, special services or multi-entity device controls can be transparently copied.
- Only a single source entity is wrapped per config entry. Create multiple proxies for additional devices.
- Sensor units and supported features follow the source unless explicitly documented otherwise.
- This release does not change any device's native internal control loop, only its Home Assistant representation and forwarded actions.

## License

MIT. See [LICENSE](LICENSE).
