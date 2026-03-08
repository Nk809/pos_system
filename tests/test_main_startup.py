import unittest
from unittest.mock import MagicMock, patch

import main


class MainStartupTest(unittest.TestCase):
    @patch("main.BillingUI")
    @patch("main.tk.Tk")
    @patch("main.start_sqlite_web")
    @patch("main.create_tables")
    def test_main_passes_sqlite_web_info_to_billing_ui(
        self,
        mock_create_tables,
        mock_start_sqlite_web,
        mock_tk,
        mock_billing_ui,
    ):
        sqlite_web = {"success": True, "url": "http://127.0.0.1:8080"}
        mock_start_sqlite_web.return_value = sqlite_web
        root = MagicMock()
        mock_tk.return_value = root

        main.main()

        mock_create_tables.assert_called_once_with()
        mock_billing_ui.assert_called_once_with(root, sqlite_web=sqlite_web)
        root.mainloop.assert_called_once_with()

    @patch("main.BillingUI")
    @patch("main.tk.Tk")
    @patch("main.start_sqlite_web")
    @patch("main.create_tables")
    def test_main_starts_offline_when_sqlite_web_is_unavailable(
        self,
        _mock_create_tables,
        mock_start_sqlite_web,
        mock_tk,
        mock_billing_ui,
    ):
        sqlite_web = {"success": False, "message": "sqlite_web command not found"}
        mock_start_sqlite_web.return_value = sqlite_web
        root = MagicMock()
        mock_tk.return_value = root

        main.main()

        mock_billing_ui.assert_called_once_with(root, sqlite_web=sqlite_web)
        root.mainloop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
