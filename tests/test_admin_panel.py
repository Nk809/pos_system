import unittest
from pathlib import Path
from unittest.mock import patch

from features import admin_panel


class AdminPanelDialogDirTest(unittest.TestCase):
    def test_default_dialog_dir_uses_home_directory(self):
        home_dir = Path("/tmp/pos-home")
        with patch.object(admin_panel.Path, "home", return_value=home_dir):
            with patch.object(Path, "is_dir", return_value=True):
                self.assertEqual(admin_panel._default_dialog_dir(), str(home_dir))

    def test_default_dialog_dir_falls_back_to_database_directory(self):
        db_dir = Path(admin_panel.DB_PATH).resolve().parent
        with patch.object(admin_panel.Path, "home", return_value=Path("/tmp/missing-home")):
            with patch.object(Path, "is_dir", return_value=False):
                self.assertEqual(admin_panel._default_dialog_dir(), str(db_dir))


if __name__ == "__main__":
    unittest.main()
