import unittest
from unittest.mock import patch

from features import device_status


class DeviceStatusTest(unittest.TestCase):
    @patch("features.device_status._matching_scanner_lines", return_value=["Barcode Scanner Dongle"])
    def test_scanner_status_reports_connected_device(self, _mock_matches):
        status = device_status.get_scanner_status()

        self.assertTrue(status["connected"])
        self.assertEqual(status["state"], "Connected")
        self.assertIn("Dongle", status["message"])

    @patch("features.device_status.shutil.which", return_value="nmcli")
    @patch("features.device_status._run_command", return_value="enabled")
    def test_wifi_radio_uses_nmcli_when_available(self, _mock_run, _mock_which):
        status = device_status.get_wifi_radio_status()

        self.assertTrue(status["connected"])
        self.assertEqual(status["state"], "On")

    @patch("features.device_status.shutil.which", return_value="bluetoothctl")
    @patch("features.device_status._run_command_with_input", return_value="Connection successful\nConnected: yes")
    def test_connect_bluetooth_device_reports_success(self, _mock_run, _mock_which):
        result = device_status.connect_bluetooth_device("AA:BB:CC:DD:EE:FF")

        self.assertTrue(result["success"])
        self.assertIn("AA:BB:CC:DD:EE:FF", result["message"])


if __name__ == "__main__":
    unittest.main()
