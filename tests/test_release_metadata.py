"""Regression tests for HACS/GitHub release metadata validation."""

from pathlib import Path
import importlib.util
import tempfile
import json
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "release_metadata.py"
spec = importlib.util.spec_from_file_location("entity_proxy_release_metadata", MODULE)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseMetadataTests(unittest.TestCase):
    def test_current_manifest_and_changelog_agree(self):
        tag, notes = release.read_release()
        self.assertRegex(tag, r"^v[0-9]+\.[0-9]+\.[0-9]+$")
        self.assertIn("- ", notes)

    def test_reject_missing_release_notes(self):
        with self.assertRaises(ValueError):
            release.extract_release_notes("## [0.9.0] - 2026-10-14\n- Other change\n", "0.9.1")

    def test_reject_duplicate_release_heading(self):
        notes = "## [1.0.0] - 2026-10-14\n- A\n\n## [1.0.0] - 2026-10-15\n- B\n"
        with self.assertRaises(ValueError):
            release.extract_release_notes(notes, "1.0.0")

    def test_reject_nonsemantic_version(self):
        with self.assertRaises(ValueError):
            release.extract_release_notes("## [1.2.3] - 2026-10-14\n- A", "main")
        with self.assertRaises(ValueError):
            release.extract_release_notes("## [1.2.3] - 2026-10-14\n- A", "v1.2.3")

    def test_release_notes_scope(self):
        changelog = (
            "## [0.2.0] - 2026-10-14\n- New feature\n"
            "\n## [0.1.0] - 2026-10-12\n- Old feature\n"
        )
        self.assertEqual(release.extract_release_notes(changelog, "0.2.0"), "- New feature")

    def test_reject_manifest_without_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "custom_components/entity_proxy").mkdir(parents=True)
            (root / "custom_components/entity_proxy/manifest.json").write_text(
                json.dumps({"version": "1.2.3"}), encoding="utf-8"
            )
            (root / "CHANGELOG.md").write_text(
                "## [1.2.2] - 2026-10-14\n- Previous", encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                release.read_release(root)


if __name__ == "__main__":
    unittest.main()
