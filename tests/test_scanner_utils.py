import unittest

from features.scanner_utils import extract_scanned_code, parse_scanned_payload


class ScannerUtilsTest(unittest.TestCase):
    def test_extract_scanned_code_from_plain_barcode(self):
        self.assertEqual(extract_scanned_code("ABC123"), "ABC123")

    def test_extract_scanned_code_from_json_payload(self):
        raw = '{"barcode": "8901234567890", "name": "Lamp"}'
        self.assertEqual(extract_scanned_code(raw), "8901234567890")

    def test_parse_scanned_payload_from_key_value_string(self):
        parsed = parse_scanned_payload("code=ITEM42;name=Incense;price=15.5;qty=9")
        self.assertEqual(parsed["barcode"], "ITEM42")
        self.assertEqual(parsed["name"], "Incense")
        self.assertEqual(parsed["price"], 15.5)
        self.assertEqual(parsed["qty"], 9)
        self.assertIsNone(parsed["stock"])

    def test_parse_scanned_payload_keeps_stock_separate_from_quantity(self):
        parsed = parse_scanned_payload('{"barcode":"ITEM42","qty":3,"stock":12}')
        self.assertEqual(parsed["barcode"], "ITEM42")
        self.assertEqual(parsed["qty"], 3)
        self.assertEqual(parsed["stock"], 12)


if __name__ == "__main__":
    unittest.main()
