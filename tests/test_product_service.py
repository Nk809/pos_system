import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import product_service


class ProductServiceScannedBarcodeTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "pos.db"
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE products(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    barcode TEXT UNIQUE,
                    name TEXT,
                    price REAL,
                    stock INTEGER
                )
                """
            )
            conn.executemany(
                "INSERT INTO products(barcode, name, price, stock) VALUES(?,?,?,?)",
                [
                    ("MGB", "Generic Prefix", 50.0, 8),
                    ("MGB0001", "Mirror", 200.0, 1000),
                    ("SOAP01", "Soap", 35.0, 25),
                ],
            )
            conn.commit()
        finally:
            conn.close()

        self.connect_patch = patch.object(product_service, "connect", side_effect=self._connect)
        self.connect_patch.start()

    def tearDown(self):
        self.connect_patch.stop()
        self.temp_dir.cleanup()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def test_find_product_by_scanned_barcode_returns_exact_match(self):
        product = product_service.find_product_by_scanned_barcode("SOAP01")

        self.assertIsNotNone(product)
        self.assertEqual(product[1], "SOAP01")
        self.assertEqual(product[2], "Soap")

    def test_find_product_by_scanned_barcode_matches_longest_prefix(self):
        product = product_service.find_product_by_scanned_barcode("MGB00010001")

        self.assertIsNotNone(product)
        self.assertEqual(product[1], "MGB0001")
        self.assertEqual(product[2], "Mirror")

    def test_find_product_by_scanned_barcode_returns_none_for_unknown_code(self):
        product = product_service.find_product_by_scanned_barcode("UNKNOWN9999")

        self.assertIsNone(product)


if __name__ == "__main__":
    unittest.main()
