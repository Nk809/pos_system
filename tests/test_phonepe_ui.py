import unittest
from unittest.mock import patch

from features import phonepe_ui


class FakeQrImage:
    def __init__(self):
        self.convert_mode = None
        self.resize_args = None

    def convert(self, mode):
        self.convert_mode = mode
        return self

    def resize(self, size, resample):
        self.resize_args = (size, resample)
        return self


class FakeQrCode:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.data = []
        self.fit_value = None
        self.image = FakeQrImage()

    def add_data(self, value):
        self.data.append(value)

    def make(self, fit=True):
        self.fit_value = fit

    def make_image(self, fill_color=None, back_color=None):
        self.fill_color = fill_color
        self.back_color = back_color
        return self.image


class FakeQrcodeModule:
    class constants:
        ERROR_CORRECT_M = "medium"

    def __init__(self):
        self.instances = []

    def QRCode(self, **kwargs):
        instance = FakeQrCode(**kwargs)
        self.instances.append(instance)
        return instance


class FakeImageModule:
    NEAREST = "nearest"


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

    def test_build_qr_image_rejects_invalid_amount(self):
        result = phonepe_ui.build_upi_qr_image(0)

        self.assertFalse(result["success"])
        self.assertEqual(result["upi_uri"], "")
        self.assertIn("greater than zero", result["message"].lower())

    def test_build_qr_image_returns_resized_qr_image(self):
        fake_qrcode = FakeQrcodeModule()
        with patch.object(phonepe_ui, "_upi_is_configured", return_value=True), patch.object(
            phonepe_ui, "UPI_ID", "merchant@upi"
        ), patch.object(
            phonepe_ui, "UPI_PAYEE_NAME", "Merchant"
        ), patch.object(
            phonepe_ui,
            "_load_qr_backends",
            return_value=(fake_qrcode, FakeImageModule, None),
        ):
            result = phonepe_ui.build_upi_qr_image(42.75, size=210)

        self.assertTrue(result["success"])
        self.assertEqual(result["amount"], 42.75)
        self.assertEqual(len(fake_qrcode.instances), 1)
        qr_instance = fake_qrcode.instances[0]
        self.assertEqual(qr_instance.kwargs["error_correction"], "medium")
        self.assertEqual(qr_instance.data, [result["upi_uri"]])
        self.assertTrue(qr_instance.fit_value)
        self.assertEqual(qr_instance.image.convert_mode, "RGB")
        self.assertEqual(qr_instance.image.resize_args, ((210, 210), "nearest"))


if __name__ == "__main__":
    unittest.main()
