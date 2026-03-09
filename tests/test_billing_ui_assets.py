import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ui.billing_ui import BillingUI


class BillingUiAssetResolutionTest(unittest.TestCase):
    def setUp(self):
        self.ui = object.__new__(BillingUI)

    def test_relative_logo_path_prefers_bundled_asset_when_present(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundled_root = Path(temp_dir) / "bundle"
            source_root = Path(temp_dir) / "source"
            bundled_asset = bundled_root / "assets" / "logo.jpeg"
            source_asset = source_root / "assets" / "logo.jpeg"
            bundled_asset.parent.mkdir(parents=True, exist_ok=True)
            source_asset.parent.mkdir(parents=True, exist_ok=True)
            bundled_asset.write_bytes(b"bundled")
            source_asset.write_bytes(b"source")

            with patch("ui.billing_ui.APP_LOGO_IMAGE", "assets/logo.jpeg"), patch(
                "ui.billing_ui.BUNDLED_BASE_DIR", bundled_root
            ), patch("ui.billing_ui.BASE_DIR", source_root):
                resolved = self.ui._resolve_logo_image_path()

        self.assertEqual(resolved, bundled_asset)

    def test_relative_logo_path_falls_back_to_matching_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundled_root = Path(temp_dir) / "bundle"
            source_root = Path(temp_dir) / "source"
            bundled_asset = bundled_root / "assets" / "logo.jpg"
            bundled_asset.parent.mkdir(parents=True, exist_ok=True)
            bundled_asset.write_bytes(b"bundled")

            with patch("ui.billing_ui.APP_LOGO_IMAGE", "assets/logo.jpeg"), patch(
                "ui.billing_ui.BUNDLED_BASE_DIR", bundled_root
            ), patch("ui.billing_ui.BASE_DIR", source_root):
                resolved = self.ui._resolve_logo_image_path()

        self.assertEqual(resolved, bundled_asset)

    def test_relative_background_path_falls_back_to_source_tree(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundled_root = Path(temp_dir) / "bundle"
            source_root = Path(temp_dir) / "source"
            source_asset = source_root / "assets" / "bg.jpg"
            source_asset.parent.mkdir(parents=True, exist_ok=True)
            source_asset.write_bytes(b"source")

            with patch("ui.billing_ui.APP_BACKGROUND_IMAGE", "assets/bg.jpg"), patch(
                "ui.billing_ui.BUNDLED_BASE_DIR", bundled_root
            ), patch("ui.billing_ui.BASE_DIR", source_root):
                resolved = self.ui._resolve_background_image_path()

        self.assertEqual(resolved, source_asset)


if __name__ == "__main__":
    unittest.main()
