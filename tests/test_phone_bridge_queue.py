import unittest

from features.phone_bridge import _process_phone_cart_add_form, pop_scanned_barcode, _phone_cart
from features import phone_bridge


class PhoneBridgeQueueTest(unittest.TestCase):
    def setUp(self):
        # clear any existing items and reset phone cart
        while pop_scanned_barcode() is not None:
            pass
        _phone_cart.clear()

    def test_phone_cart_add_queues_barcode(self):
        # stub search_product to return a matching entry
        phone_bridge.search_product = lambda barcode: [(1, barcode, "Test", 10.0, 100)]
        form = {"barcode": ["ABC123"], "qty": ["2"]}
        result, status = _process_phone_cart_add_form(form)
        self.assertEqual(status, 200)
        self.assertTrue(result.get("success", False))
        # two barcodes should be queued
        first = pop_scanned_barcode()
        second = pop_scanned_barcode()
        self.assertEqual(first, "ABC123")
        self.assertEqual(second, "ABC123")
        self.assertIsNone(pop_scanned_barcode())

    def test_phone_cart_add_with_existing_item_queues_added_qty(self):
        # stub search_product
        phone_bridge.search_product = lambda barcode: [(1, barcode, "Product", 15.0, 50)]
        # first add 1 then add 3 more
        form1 = {"barcode": ["XYZ"], "qty": ["1"]}
        _process_phone_cart_add_form(form1)
        pop_scanned_barcode()
        form2 = {"barcode": ["XYZ"], "qty": ["3"]}
        _process_phone_cart_add_form(form2)
        # should queue 3 more
        self.assertEqual(pop_scanned_barcode(), "XYZ")
        self.assertEqual(pop_scanned_barcode(), "XYZ")
        self.assertEqual(pop_scanned_barcode(), "XYZ")
        self.assertIsNone(pop_scanned_barcode())


if __name__ == "__main__":
    unittest.main()
