import unittest
from unittest.mock import patch

from features import thermal_printer


class ThermalPrinterWindowsTest(unittest.TestCase):
    def test_invalid_printer_mode_falls_back_to_auto(self):
        with patch.object(thermal_printer, "PRINTER_MODE", "unsupported"):
            self.assertEqual(thermal_printer._normalized_printer_mode(), "auto")

    def test_wifi_alias_maps_to_network_mode(self):
        with patch.object(thermal_printer, "PRINTER_MODE", "wifi"):
            self.assertEqual(thermal_printer._normalized_printer_mode(), "network")

    def test_get_printer_status_prefers_windows_spooler(self):
        with patch.object(thermal_printer, "PRINTER_MODE", "windows"), patch.object(
            thermal_printer, "_is_windows", return_value=True
        ), patch.object(thermal_printer, "_windows_target_printers", return_value=["POS-58"]):
            status = thermal_printer.get_printer_status()

        self.assertTrue(status["success"])
        self.assertEqual(status["transport"], "winspool")
        self.assertEqual(status["mode"], "windows")
        self.assertIn("POS-58", status["message"])

    def test_print_bill_uses_windows_spooler_when_available(self):
        cart = [{"id": 1, "name": "Item", "qty": 1, "price": 10.0, "total": 10.0}]
        expected = {"success": True, "message": "Receipt printed successfully on POS-58."}
        with patch.object(thermal_printer, "PRINTER_MODE", "windows"), patch.object(
            thermal_printer, "_is_windows", return_value=True
        ), patch.object(
            thermal_printer, "_print_with_windows_spooler", return_value=expected
        ):
            result = thermal_printer.print_bill(cart, 10.0, bill_no=1, payment_mode="Cash")

        self.assertEqual(result, expected)

    def test_network_mode_requires_address(self):
        with patch.object(thermal_printer, "PRINTER_MODE", "network"), patch.object(
            thermal_printer, "PRINTER_NETWORK_ADDR", ""
        ), patch.object(
            thermal_printer, "get_printer_setting", return_value=""
        ):
            status = thermal_printer.get_printer_status()

        self.assertFalse(status["success"])
        self.assertEqual(status["transport"], "network")
        self.assertIn("PRINTER_NETWORK_ADDR", status["message"])

    def test_network_mode_uses_saved_runtime_address(self):
        with patch.object(thermal_printer, "PRINTER_MODE", "network"), patch.object(
            thermal_printer, "PRINTER_NETWORK_ADDR", ""
        ), patch.object(
            thermal_printer, "get_printer_setting", return_value="192.168.0.25:9100"
        ), patch.object(
            thermal_printer, "_probe_tcp_endpoint", return_value=(True, None)
        ):
            status = thermal_printer.get_printer_status()

        self.assertTrue(status["success"])
        self.assertEqual(status["transport"], "network")
        self.assertIn("192.168.0.25:9100", status["message"])

    def test_bluetooth_mode_requires_address(self):
        with patch.object(thermal_printer, "PRINTER_MODE", "bluetooth"), patch.object(
            thermal_printer, "PRINTER_BLUETOOTH_ADDRESS", ""
        ), patch.object(
            thermal_printer, "get_printer_setting", return_value=""
        ):
            status = thermal_printer.get_printer_status()

        self.assertFalse(status["success"])
        self.assertEqual(status["transport"], "bluetooth")
        self.assertIn("PRINTER_BLUETOOTH_ADDRESS", status["message"])

    def test_bluetooth_mode_uses_windows_spooler_for_paired_printer(self):
        with patch.object(thermal_printer, "PRINTER_MODE", "bluetooth"), patch.object(
            thermal_printer, "_is_windows", return_value=True
        ), patch.object(
            thermal_printer, "_bluetooth_windows_target_printers", return_value=["BT-POS-58"]
        ), patch.object(
            thermal_printer, "_print_with_windows_spooler", return_value={"success": True, "message": "Printed."}
        ):
            result = thermal_printer.print_bill(
                [{"id": 1, "name": "Item", "qty": 1, "price": 10.0, "total": 10.0}],
                10.0,
                bill_no=1,
                payment_mode="Cash",
            )

        self.assertTrue(result["success"])

    def test_bluetooth_status_uses_windows_spooler_when_configured(self):
        with patch.object(thermal_printer, "PRINTER_MODE", "bluetooth"), patch.object(
            thermal_printer, "PRINTER_BLUETOOTH_ADDRESS", ""
        ), patch.object(
            thermal_printer, "get_printer_setting", return_value=""
        ), patch.object(
            thermal_printer, "_is_windows", return_value=True
        ), patch.object(
            thermal_printer, "_bluetooth_windows_target_printers", return_value=["BT-POS-58"]
        ):
            status = thermal_printer.get_printer_status()

        self.assertTrue(status["success"])
        self.assertIn("Windows spooler", status["message"])


if __name__ == "__main__":
    unittest.main()
