from database import connect
from datetime import date, datetime

REQUIRED_CART_KEYS = {"id", "name", "qty", "price", "total"}


def _normalize_discount_percent(discount_percent):
    if discount_percent is None:
        return 0.0
    try:
        value = float(str(discount_percent).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("Discount must be a valid number.") from exc

    if value < 0 or value > 100:
        raise ValueError("Discount must be between 0 and 100.")
    return round(value, 2)


def _build_receipt_line(sale_id, total, payment_mode, discount_percent=0.0):
    timestamp = datetime.now().strftime("%d %b %Y %I:%M %p")
    if float(discount_percent) > 0:
        return (
            f"{timestamp} | Bill #{sale_id} | {payment_mode} | "
            f"Disc: {float(discount_percent):.2f}% | Total: {total:.2f}"
        )
    return f"{timestamp} | Bill #{sale_id} | {payment_mode} | Total: {total:.2f}"


def _normalize_cart(cart):
    if not cart:
        raise ValueError("Cart is empty.")

    normalized = []

    for index, item in enumerate(cart, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Cart item {index} is invalid.")

        missing = REQUIRED_CART_KEYS - item.keys()
        if missing:
            raise ValueError(f"Cart item {index} is missing keys: {', '.join(sorted(missing))}.")

        try:
            product_id = int(item["id"])
            quantity = int(item["qty"])
            price = float(item["price"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Cart item {index} has invalid numeric values.") from exc

        if quantity <= 0:
            raise ValueError(f"Cart item {index} quantity must be greater than zero.")

        if price < 0:
            raise ValueError(f"Cart item {index} price must be zero or greater.")

        normalized.append(
            {
                "id": product_id,
                "name": str(item["name"]),
                "qty": quantity,
                "price": price,
                "total": round(quantity * price, 2),
            }
        )

    return normalized


def save_sale(cart, payment_mode="Cash", discount_percent=0.0):
    normalized_cart = _normalize_cart(cart)
    normalized_mode = "Online" if str(payment_mode).strip().lower() == "online" else "Cash"
    normalized_discount_percent = _normalize_discount_percent(discount_percent)

    conn = connect()
    cur = conn.cursor()

    try:
        subtotal = round(sum(item["total"] for item in normalized_cart), 2)
        discount_amount = round(subtotal * (normalized_discount_percent / 100.0), 2)
        total = round(max(subtotal - discount_amount, 0.0), 2)
        today = str(date.today())

        cur.execute(
            "INSERT INTO sales(date,total,payment_mode) VALUES(?,?,?)",
            (today, total, normalized_mode)
        )

        sale_id = cur.lastrowid

        for item in normalized_cart:
            cur.execute("SELECT stock FROM products WHERE id = ?", (item["id"],))
            stock_row = cur.fetchone()

            if stock_row is None:
                raise ValueError(f"Product ID {item['id']} was not found.")

            available_stock = int(stock_row[0])
            if available_stock < item["qty"]:
                raise ValueError(f"Insufficient stock for {item['name']}.")

            cur.execute(
                "INSERT INTO sale_items(sale_id,product_id,quantity,price) VALUES(?,?,?,?)",
                (sale_id, item["id"], item["qty"], item["price"])
            )

            cur.execute(
                "UPDATE products SET stock = stock - ? WHERE id=?",
                (item["qty"], item["id"])
            )

        cur.execute(
            "INSERT INTO recent_receipts(created_at,sale_id,line_text) VALUES(?,?,?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                sale_id,
                _build_receipt_line(sale_id, total, normalized_mode, normalized_discount_percent),
            ),
        )

        conn.commit()
        return {
            "sale_id": int(sale_id),
            "subtotal": round(float(subtotal), 2),
            "discount_percent": normalized_discount_percent,
            "discount_amount": round(float(discount_amount), 2),
            "total": round(float(total), 2),
            "payment_mode": normalized_mode,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_today_sales_summary():
    conn = connect()
    cur = conn.cursor()

    try:
        today = str(date.today())
        cur.execute(
            """
            SELECT
                COUNT(*),
                COALESCE(SUM(total), 0),
                COALESCE(SUM(CASE WHEN payment_mode = 'Online' THEN total ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN payment_mode = 'Cash' OR payment_mode IS NULL THEN total ELSE 0 END), 0)
            FROM sales
            WHERE date = ?
            """,
            (today,),
        )
        row = cur.fetchone() or (0, 0, 0, 0)
        sales_count = int(row[0] or 0)
        sales_total = float(row[1] or 0)
        online_total = float(row[2] or 0)
        cash_total = float(row[3] or 0)
        return {
            "count": sales_count,
            "total": round(sales_total, 2),
            "online_total": round(online_total, 2),
            "cash_total": round(cash_total, 2),
        }
    finally:
        conn.close()


def get_daily_sales_summary(limit=14):
    conn = connect()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT
                date,
                COUNT(*),
                COALESCE(SUM(total), 0),
                COALESCE(SUM(CASE WHEN payment_mode = 'Online' THEN total ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN payment_mode = 'Cash' OR payment_mode IS NULL THEN total ELSE 0 END), 0)
            FROM sales
            GROUP BY date
            ORDER BY date DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        rows = cur.fetchall()
        return [
            {
                "date": str(day),
                "count": int(count or 0),
                "total": round(float(total or 0), 2),
                "online_total": round(float(online_total or 0), 2),
                "cash_total": round(float(cash_total or 0), 2),
            }
            for day, count, total, online_total, cash_total in rows
        ]
    finally:
        conn.close()


def get_recent_receipts(limit=100):
    conn = connect()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT id, created_at, sale_id, line_text
            FROM recent_receipts
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        rows = cur.fetchall()
        return [
            {
                "id": int(receipt_id),
                "created_at": str(created_at),
                "sale_id": int(sale_id or 0),
                "line_text": str(line_text or ""),
            }
            for receipt_id, created_at, sale_id, line_text in rows
        ]
    finally:
        conn.close()


def clear_recent_receipts():
    conn = connect()
    cur = conn.cursor()

    try:
        cur.execute("DELETE FROM recent_receipts")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
