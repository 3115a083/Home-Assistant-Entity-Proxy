# Changelog

All notable changes to Entity Proxy are documented here.

The project uses [Semantic Versioning](https://semver.org/). GitHub Releases use a `v` prefix (for example `v0.1.3`); the Home Assistant integration manifest uses the same version without the prefix.

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
