import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from features import runtime_settings


class RuntimeSettingsTest(unittest.TestCase):
    def test_update_and_get_printer_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "runtime_settings.json"
            with patch.object(runtime_settings, "SETTINGS_PATH", settings_path):
                runtime_settings.update_printer_settings(
                    bluetooth_name="BT POS",
                    network_address="192.168.0.50:9100",
                    windows_name="POS-58",
                )

                self.assertEqual(runtime_settings.get_printer_setting("bluetooth_name"), "BT POS")
                self.assertEqual(runtime_settings.get_printer_setting("network_address"), "192.168.0.50:9100")
                self.assertEqual(runtime_settings.get_printer_setting("windows_name"), "POS-58")
                self.assertTrue(settings_path.exists())


if __name__ == "__main__":
    unittest.main()
