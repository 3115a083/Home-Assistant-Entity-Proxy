"""Workflow hardening regression tests."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "entity_proxy_security", Path(__file__).resolve().parents[1] / "scripts" / "security_check.py"
)
security = importlib.util.module_from_spec(spec)
spec.loader.exec_module(security)


class WorkflowPolicyTests(unittest.TestCase):
    def test_current_workflows(self):
        self.assertEqual(security.main(), 0)

    def test_reject_unpinned_action(self):
        self.assertTrue(security.check_workflow(
            "permissions:\\n  contents: read\\nsteps:\\n  - uses: actions/checkout@v4\\n"
            "    with:\\n      persist-credentials: false\\n", "unsafe"
        ))

    def test_reject_privileged_fork_trigger(self):
        self.assertTrue(security.check_workflow(
            "permissions:\\n  contents: read\\non:\\n  pull_request_target:\\n",
            "unsafe"
        ))

    def test_reject_missing_permissions(self):
        self.assertTrue(security.check_workflow("on: push\\n", "unsafe"))


if __name__ == "__main__":
    unittest.main()
