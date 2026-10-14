"""Validate Entity Proxy release metadata and build release notes.

This module intentionally accepts no external command, path or network input.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
HEADER_PATTERN = re.compile(r"^## \[(?P<version>[^\]]+)\] - (?P<date>\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)


def extract_release_notes(changelog: str, version: str) -> str:
    """Require a unique, nonempty entry for exactly this semantic version."""
    if VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError("Manifest version must use MAJOR.MINOR.PATCH without a v prefix")
    headers = list(HEADER_PATTERN.finditer(changelog))
    relevant = [(index, match) for index, match in enumerate(headers) if match.group("version") == version]
    if len(relevant) != 1:
        raise ValueError(f"CHANGELOG.md must have exactly one entry for {version}")
    index, match = relevant[0]
    end = headers[index + 1].start() if index + 1 < len(headers) else len(changelog)
    notes = changelog[match.end():end].strip()
    if not notes or not re.search(r"(?m)^- ", notes):
        raise ValueError(f"Changelog entry {version} has no change notes")
    return notes


def read_release(root: Path = ROOT) -> tuple[str, str]:
    """Read the manifest and matching release notes from repository files."""
    manifest = json.loads((root / "custom_components/entity_proxy/manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    if not isinstance(version, str) or VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError("Invalid manifest version")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    return f"v{version}", extract_release_notes(changelog, version)


def main() -> int:
    try:
        tag, notes = read_release()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"Release validation failed: {error}", file=sys.stderr)
        return 1
    print(f"Validated release metadata for {tag}")
    if "--check" not in sys.argv[1:]:
        (ROOT / ".release-notes.md").write_text(notes + "\n", encoding="utf-8")
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as file:
                file.write(f"tag={tag}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
