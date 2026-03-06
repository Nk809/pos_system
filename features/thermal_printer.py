from datetime import datetime

from config import PRINTER_VENDOR, PRINTER_PRODUCT

LINE_EQ = "=" * 32
LINE_DASH = "-" * 32


def _format_item_line(name, qty, line_total):
    clean_name = str(name).strip()
    if len(clean_name) > 15:
        clean_name = clean_name[:15]
    qty_text = f"x{int(qty)}"
    return f"{clean_name:<15}{qty_text:>5}{float(line_total):>12.2f}"


def print_bill(
    cart,
    total,
    bill_no=None,
    payment_mode=None,
    subtotal=None,
    discount_percent=0.0,
    discount_amount=0.0,
):
    try:
        from escpos.printer import Usb
    except Exception:
        return {
            "success": False,
            "message": "Printer support package not installed. Sale saved; printing skipped.",
        }

    try:
        printer = Usb(PRINTER_VENDOR, PRINTER_PRODUCT)
        now = datetime.now()
        date_time_line = f"Date: {now:%Y-%m-%d}  Time: {now:%H:%M:%S}"

        printer.text(f"{LINE_EQ}\n")
        printer.text("     MATCHLESS GIFT SHOP\n")
        printer.text("        ISKCON BURLA\n")
        printer.text(f"{LINE_EQ}\n")
        printer.text(f"{date_time_line}\n")
        if bill_no is not None:
            printer.text(f"Bill No: {bill_no}\n")
        if payment_mode:
            printer.text(f"Payment: {payment_mode}\n")
        printer.text("        Thank you, visit again!\n")
        printer.text(f"{LINE_DASH}\n")
        printer.text("Item            Qty       Price\n")
        printer.text(f"{LINE_DASH}\n")

        for item in cart:
            printer.text(_format_item_line(item["name"], item["qty"], item["total"]) + "\n")

        printer.text(f"{LINE_DASH}\n")
        subtotal_value = round(float(subtotal), 2) if subtotal is not None else round(sum(item["total"] for item in cart), 2)
        discount_percent_value = round(float(discount_percent or 0.0), 2)
        discount_amount_value = round(float(discount_amount or 0.0), 2)
        total_value = round(float(total), 2)

        printer.text(f"{'SUBTOTAL':<22}{subtotal_value:>10.2f}\n")
        if discount_percent_value > 0 or discount_amount_value > 0:
            printer.text(f"{f'DISCOUNT({discount_percent_value:.2f}%)':<22}{discount_amount_value:>10.2f}\n")
        printer.text(f"{'TOTAL':<22}{total_value:>10.2f}\n")
        printer.text(f"{LINE_DASH}\n")
        printer.text("     🙏   Hare Krishna 🙏\n")
        printer.text(f"{LINE_EQ}\n")
        printer.cut()

        return {"success": True, "message": "Receipt printed successfully."}
    except Exception as exc:
        return {"success": False, "message": f"Printer unavailable ({exc}). Sale saved; printing skipped."}
