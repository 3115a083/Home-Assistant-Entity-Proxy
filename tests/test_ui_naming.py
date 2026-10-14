"""Regression tests for translated options menus and identifiable diagnostic names.

These checks protect Home Assistant's expected `menu_options` translation
structure and per-proxy sensor naming, including German settings labels.
"""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "entity_proxy"
TRANSLATIONS = [
    COMPONENT / "strings.json",
    COMPONENT / "translations" / "en.json",
    COMPONENT / "translations" / "de.json",
]
MENU_KEYS = {"source", "preset", "rules"}
SENSOR_KEYS = {"errors", "configuration"}


class UINamingTests(unittest.TestCase):
    def test_menu_labels_exist_for_all_languages(self):
        for path in TRANSLATIONS:
            with self.subTest(path=str(path)):
                values = json.loads(path.read_text(encoding="utf-8"))
                init = values["options"]["step"]["init"]
                options = init["menu_options"]
                descriptions = init["menu_option_descriptions"]
                self.assertEqual(set(options), MENU_KEYS)
                self.assertEqual(set(descriptions), MENU_KEYS)
                for key in MENU_KEYS:
                    self.assertTrue(options[key].strip())
                    self.assertTrue(descriptions[key].strip())
                # Labels must NOT be placed only under "step.source.title".
                self.assertNotEqual(options["source"], "")
                self.assertNotEqual(options["preset"], "")
                self.assertNotEqual(options["rules"], "")

    def test_german_integration_name_is_explicit(self):
        doc = json.loads(
            (COMPONENT / "translations" / "de.json").read_text(encoding="utf-8")
        )
        self.assertEqual(doc["options"]["step"]["init"]["title"], "Entity Proxy Einstellungen")
        self.assertEqual(doc["options"]["step"]["init"]["menu_options"]["source"], "Quellentität ändern")
        self.assertIn("Ausschalt-Preset", doc["options"]["step"]["init"]["menu_options"]["preset"])

    def test_diagnostics_have_per_proxy_translated_names(self):
        for path in TRANSLATIONS:
            with self.subTest(path=str(path)):
                values = json.loads(path.read_text(encoding="utf-8"))
                sensors = values["entity"]["sensor"]
                self.assertTrue(SENSOR_KEYS.issubset(sensors.keys()))
                for key in SENSOR_KEYS:
                    name = sensors[key]["name"]
                    self.assertIn("{proxy_name}", name)
                    rendered = name.format(proxy_name="Schlafzimmer WLED")
                    self.assertIn("Schlafzimmer WLED", rendered)
                    self.assertIn("Entity Proxy", rendered)
                self.assertNotEqual(
                    sensors["errors"]["name"], sensors["configuration"]["name"]
                )

    def test_proxy_diagnostic_unique_ids_stay_unchanged(self):
        source = (COMPONENT / "base.py").read_text(encoding="utf-8")
        self.assertIn('f"{runtime.entry.entry_id}_{role}"', source)
        diagnostics = (COMPONENT / "sensor.py").read_text(encoding="utf-8")
        self.assertIn('role="errors"', diagnostics)
        self.assertIn('role="configuration"', diagnostics)


if __name__ == "__main__":
    unittest.main()
