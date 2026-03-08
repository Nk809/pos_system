import unittest
from unittest.mock import patch

from features import phonepe_ui


class PhonePeUiTest(unittest.TestCase):
    def test_payment_details_report_unconfigured_upi(self):
        with patch.object(phonepe_ui, "UPI_ID", "your-upi-id@example"):
            details = phonepe_ui.get_upi_payment_details(125.5)

        self.assertFalse(details["configured"])
        self.assertIn("config.py", details["message"])

    def test_build_qr_image_reports_missing_dependencies(self):
        with patch.object(phonepe_ui, "_upi_is_configured", return_value=True), patch.object(
            phonepe_ui,
            "_load_qr_backends",
            return_value=(None, None, ImportError("missing package")),
        ):
            result = phonepe_ui.build_upi_qr_image(42.0)

        self.assertFalse(result["success"])
        self.assertIn("qrcode", result["message"].lower())


if __name__ == "__main__":
    unittest.main()
