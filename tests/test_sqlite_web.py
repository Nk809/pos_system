import os
import unittest
from unittest.mock import patch

from features.sqlite_web import _find_free_port, _sqlite_web_command, start_sqlite_web


class SqliteWebTest(unittest.TestCase):
    def test_sqlite_web_command_falls_back_to_module(self):
        fake_spec = object()
        with patch("features.sqlite_web._which", return_value=None), patch(
            "features.sqlite_web.importlib.util.find_spec", return_value=fake_spec
        ), patch("features.sqlite_web.sys.executable", "/tmp/python"):
            command, error = _sqlite_web_command()

        self.assertEqual(command, ["/tmp/python", "-m", "sqlite_web"])
        self.assertIsNone(error)

    def test_start_returns_dict(self):
        result = start_sqlite_web(port=9999)
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)
        if result.get("success"):
            # if the package happens to be installed, we expect a url key
            self.assertIn("url", result)
            self.assertTrue(result["url"].startswith("http://"))
            # terminate subprocess to avoid resource warnings
            proc = result.get("process")
            if proc:
                proc.terminate()
                proc.wait(timeout=1)
        else:
            # failure should provide a message
            self.assertIn("message", result)
            self.assertIsInstance(result["message"], str)

    def test_find_port_skips_in_use(self):
        import socket

        # pick a dynamic base port so we don't conflict with services running
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        busy = s.getsockname()[1]
        s.listen(1)

        try:
            free = _find_free_port(busy, busy + 2)
            self.assertIn(free, (busy + 1, busy + 2))
        finally:
            s.close()

        # occupy two consecutive ports and check that ValueError is raised
        s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s1.bind(("127.0.0.1", busy))
            s1.listen(1)
            s2.bind(("127.0.0.1", busy + 1))
            s2.listen(1)
            with self.assertRaises(ValueError):
                _find_free_port(busy, busy + 1)
        finally:
            s1.close()
            s2.close()

    def test_env_port_override(self):
        os.environ["SQLITE_WEB_PORT"] = "12345"
        try:
            result = start_sqlite_web(port=None)
            if result.get("success"):
                self.assertIn("12345", result.get("url"))
                proc = result.get("process")
                if proc:
                    proc.terminate()
                    proc.wait(timeout=1)
            else:
                self.assertIn("message", result)
        finally:
            del os.environ["SQLITE_WEB_PORT"]


if __name__ == "__main__":
    unittest.main()
