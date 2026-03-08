import unittest
from unittest.mock import MagicMock, patch

from ui.billing_ui import BillingUI


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeWidget:
    def __init__(self):
        self.options = {}
        self.image = "sentinel"
        self.visible = None

    def config(self, **kwargs):
        self.options.update(kwargs)

    def grid(self):
        self.visible = True

    def grid_remove(self):
        self.visible = False

    def focus_set(self):
        self.options["focused"] = True

    def pack_forget(self):
        self.visible = False


class BillingUiBehaviourTest(unittest.TestCase):
    def test_update_qr_display_reports_missing_imagetk_backend(self):
        ui = object.__new__(BillingUI)
        ui.payment_mode = FakeVar("Online")
        ui.qr_label = FakeWidget()
        ui.qr_hint = FakeWidget()
        ui.qr_holder = FakeWidget()

        with patch("ui.billing_ui.build_upi_qr_image", return_value={"success": True, "image": object(), "upi_id": "shop@upi"}):
            with patch("ui.billing_ui._load_image_tk_backend", return_value=(None, ImportError("missing imagetk"))):
                ui._update_qr_display(125.0)

        self.assertEqual(ui.qr_label.options["image"], "")
        self.assertIsNone(ui.qr_label.image)
        self.assertIn("QR preview unavailable", ui.qr_hint.options["text"])
        self.assertTrue(ui.qr_holder.visible)

    def test_refresh_system_state_reloads_runtime_assets(self):
        ui = object.__new__(BillingUI)
        ui._scanner_buffer = "123"
        ui._scanner_last_char_at = 10.0
        ui.service_links_visible = True
        ui.service_links_unlocked = True
        ui._refresh_runtime_assets = MagicMock()
        ui.refresh_device_status = MagicMock()
        ui.refresh_cart = MagicMock()
        ui.refresh_receipts_box = MagicMock()
        ui.search_products = MagicMock()
        ui._rebuild_service_links_panel = MagicMock()
        ui._build_system_status_text = MagicMock(return_value="System status")
        ui.service_links_panel = FakeWidget()
        ui.service_toggle_button = FakeWidget()
        ui.root = MagicMock()
        ui.system_status_var = FakeVar()
        ui.status_var = FakeVar()
        ui.barcode_entry = FakeWidget()

        result = ui.refresh_system_state()

        self.assertEqual(result, "break")
        self.assertEqual(ui._scanner_buffer, "")
        self.assertEqual(ui._scanner_last_char_at, 0.0)
        self.assertFalse(ui.service_links_visible)
        self.assertFalse(ui.service_links_unlocked)
        self.assertFalse(ui.service_links_panel.visible)
        self.assertEqual(ui.service_toggle_button.options["text"], "...")
        ui._refresh_runtime_assets.assert_called_once_with()
        ui.refresh_device_status.assert_called_once_with(update_status=False)
        ui.refresh_cart.assert_called_once_with()
        ui.refresh_receipts_box.assert_called_once_with()
        ui.search_products.assert_called_once_with()
        ui._rebuild_service_links_panel.assert_called_once_with()
        ui.root.update_idletasks.assert_called_once_with()
        self.assertEqual(ui.system_status_var.get(), "System status")
        self.assertEqual(ui.status_var.get(), "System refreshed.")
        self.assertTrue(ui.barcode_entry.options["focused"])

    def test_hide_service_links_panel_relocks_access(self):
        ui = object.__new__(BillingUI)
        ui.service_links_visible = True
        ui.service_links_unlocked = True
        ui.service_links_panel = FakeWidget()
        ui.service_toggle_button = FakeWidget()

        ui._hide_service_links_panel()

        self.assertFalse(ui.service_links_visible)
        self.assertFalse(ui.service_links_unlocked)
        self.assertFalse(ui.service_links_panel.visible)
        self.assertEqual(ui.service_toggle_button.options["text"], "...")


if __name__ == "__main__":
    unittest.main()
