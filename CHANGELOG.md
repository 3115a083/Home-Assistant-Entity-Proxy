# Changelog

All notable changes to Entity Proxy are documented here.

The project uses [Semantic Versioning](https://semver.org/). GitHub Releases use a `v` prefix (for example `v0.1.3`); the Home Assistant integration manifest uses the same version without the prefix.

## [0.1.6] - 2026-10-14

### Fixed
- Restore readable labels for the three Entity Proxy options-menu entries. The translations now use Home Assistant's required `options.step.init.menu_options` schema.
- Rename the German options dialog to **Entity Proxy Einstellungen** to clearly identify the integration.
- Show distinct, translated diagnostic entity names for each proxy instance instead of repeated `Configuration` and `Errors` labels.
- Use translated entity-name placeholders with the configured proxy name, and disable the legacy device-prefix stripping on diagnostic entities.
- Remove the unlocalized `issues` unit from the error count, keeping the numeric count and detailed issue attributes.

### Compatibility
- Existing proxy unique IDs, entity registry IDs, rule configurations and source-device associations remain unchanged.
- Add regression tests for menu translations, German labels, diagnostic names and stable entity IDs.
- Restart Home Assistant and refresh the frontend after upgrading; a user-customized entity name takes precedence over the generated name.

## [0.1.5] - 2026-10-14

### Added
- Expose a device-linked, read-only per-proxy Configuration diagnostic sensor showing the active source, state and action overrides, virtual state, off-preset entity and preset name, and active issue count.
- Add tests for device association, missing device links, diagnostics, source changes, and the Home Assistant options-flow entry point.
- Document where to find Configure, the Errors sensor, and the Configuration sensor, with a safe troubleshooting path for stale HACS installations.

### Fixed
- Remove duplicate device-link initialization while keeping 2026.8+ source-device association.
- Make the distinction between the original entity, the proxy entity, and diagnostic entities explicit in the English README.

### Notes
- The proxy does not intercept calls made directly to the original light entity. Use the proxy in dashboards and automations.
- A real Home Assistant installation test is still required; device-specific behavior must be validated before relying on fallback actions.

## [0.1.4] - 2026-10-14

### Added
- Automatically associate each Entity Proxy entity with the original source device in Home Assistant's device registry.
- Show the per-proxy error sensor under the source device's diagnostics section.
- Re-link to the new source device when changing the source through integration options and reloading.
- Add regression tests for WLED, other device types, missing device registry entries, and stable proxy IDs.

### Security and compatibility
- Use Home Assistant's supported helper entity device link (`device_entry`), not copied `device_info` identifiers or device registry modifications. Compatible with the device ownership model in Home Assistant Core 2026.8+.
- Preserve the original device, integration ownership, configuration, proxy entry IDs and existing rule behavior.
- Harden repository development controls with a security policy, agent guidelines, CODEOWNERS, Dependabot and pinned GitHub Actions. Administrative branch and tag rulesets must still be enabled separately by the repository owner.

### Notes
- An existing proxy is linked after installing this release and restarting Home Assistant.
- A source entity with no device registry association cannot be shown on a device page.
- If Home Assistant reassigns a source entity's device independently, reload the proxy integration to refresh its link.

## [0.1.3] - 2026-10-14

### Changed
- Publish versioned GitHub Releases with human-readable release notes for HACS.
- Add automated release metadata validation and a protected publication workflow.
- Align integration version, release tag and documentation.
- Document the one-time HACS migration from commit-hash installations.

### Notes
- No changes to entity proxy runtime behavior or saved configuration.
- The integration remains experimental; live Home Assistant validation is still recommended.

## [0.1.2] - 2026-10-14

### Added
- Change the wrapped source entity from integration options without recreating the proxy.
- Edit a WLED-style off preset target and preset name through an options dialog.
- Preserve existing rule configuration when changing a source, with reference remapping.

## [0.1.1] - 2026-10-14

### Fixed
- Preserve submitted JSON when validation fails.
- Return field-specific errors for invalid state and action rules.
- Improve validation messages and tests.

## [0.1.0] - 2026-10-14

### Added
- Initial experimental Home Assistant Entity Proxy integration.
- State/attribute overrides for supported entities, with fallback sources and values.
- Action overrides with allowlisted services, backup actions and virtual states.
- Event-driven updates and per-proxy error sensors.
- UI installation with structured JSON rule configuration.
