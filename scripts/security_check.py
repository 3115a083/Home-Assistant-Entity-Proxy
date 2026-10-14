"""Fail CI on common GitHub Actions supply-chain security regressions.

This static policy complements GitHub branch/ruleset settings; it does not
replace them or a complete security review.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PINNED_ACTION = re.compile(r"^\s*-\s*uses:\s*([^\s#]+)")
SHA = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_TRIGGERS = ("pull_request_target:", "workflow_run:")
FORBIDDEN_PERMISSIONS = ("write-all",)
REMOTE_SHELL = re.compile(r"(?:curl|wget)\b[^\n|]*\|\s*(?:sh|bash)\b")


def check_workflow(text: str, name: str) -> list[str]:
    """Report obvious dangerous patterns with actionable file-specific messages."""
    errors: list[str] = []
    for line in text.splitlines():
        match = PINNED_ACTION.match(line)
        if match:
            action = match.group(1)
            if action.startswith("./"):
                continue
            if "@" not in action or not SHA.fullmatch(action.rsplit("@", 1)[-1]):
                errors.append(f"{name}: non-SHA-pinned action: {action}")
    for trigger in FORBIDDEN_TRIGGERS:
        if re.search(r"(?m)^\s*" + re.escape(trigger), text):
            errors.append(f"{name}: forbidden privileged trigger: {trigger}")
    for permission in FORBIDDEN_PERMISSIONS:
        if permission in text:
            errors.append(f"{name}: forbidden broad permission: {permission}")
    if REMOTE_SHELL.search(text):
        errors.append(f"{name}: remote script piping to shell")
    if not re.search(r"(?m)^permissions:\s*$", text):
        errors.append(f"{name}: no explicit top-level permissions")
    if "actions/checkout@" in text and "persist-credentials: false" not in text:
        errors.append(f"{name}: checkout must disable persisted credentials")
    return errors


def main() -> int:
    errors = []
    for p in sorted(WORKFLOWS.glob("*.yml")):
        errors.extend(check_workflow(p.read_text(encoding="utf-8"), str(p.relative_to(ROOT))))
    for message in errors:
        print("SECURITY: " + message, file=sys.stderr)
    if errors:
        return 1
    print("Workflow security checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
