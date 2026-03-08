import sqlite3
import time

from database import connect

MAX_DB_RETRIES = 5


def _is_db_locked(exc):
    text = str(exc).lower()
    return "database is locked" in text or "database table is locked" in text


def add_product(barcode, name, price, stock):
    for attempt in range(MAX_DB_RETRIES):
        conn = None

        try:
            conn = connect()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO products(barcode,name,price,stock) VALUES(?,?,?,?)",
                (barcode, name, price, stock)
            )
            conn.commit()
            return
        except sqlite3.OperationalError as exc:
            if conn is not None:
                conn.rollback()
            if _is_db_locked(exc) and attempt < MAX_DB_RETRIES - 1:
                time.sleep(0.15 * (attempt + 1))
                continue
            raise
        finally:
            if conn is not None:
                conn.close()


def search_product(keyword):
    pattern = f"%{keyword.strip()}%"

    for attempt in range(MAX_DB_RETRIES):
        conn = None
        try:
            conn = connect()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id,barcode,name,price,stock
                FROM products
                WHERE name LIKE ? OR barcode LIKE ?
                ORDER BY name
                """,
                (pattern, pattern)
            )
            return cur.fetchall()
        except sqlite3.OperationalError as exc:
            if _is_db_locked(exc) and attempt < MAX_DB_RETRIES - 1:
                time.sleep(0.1 * (attempt + 1))
                continue
            raise
        finally:
            if conn is not None:
                conn.close()

    return []


def find_product_by_scanned_barcode(scanned_barcode):
    normalized = str(scanned_barcode or "").strip()
    if not normalized:
        return None

    for attempt in range(MAX_DB_RETRIES):
        conn = None
        try:
            conn = connect()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, barcode, name, price, stock
                FROM products
                WHERE barcode = ?
                LIMIT 1
                """,
                (normalized,),
            )
            exact_match = cur.fetchone()
            if exact_match is not None:
                return exact_match

            cur.execute(
                """
                SELECT id, barcode, name, price, stock
                FROM products
                WHERE barcode IS NOT NULL
                  AND TRIM(barcode) != ''
                  AND ? LIKE barcode || '%'
                ORDER BY LENGTH(barcode) DESC, name
                LIMIT 1
                """,
                (normalized,),
            )
            return cur.fetchone()
        except sqlite3.OperationalError as exc:
            if _is_db_locked(exc) and attempt < MAX_DB_RETRIES - 1:
                time.sleep(0.1 * (attempt + 1))
                continue
            raise
        finally:
            if conn is not None:
                conn.close()

    return None


def delete_product(product_id):
    for attempt in range(MAX_DB_RETRIES):
        conn = None
        try:
            conn = connect()
            cur = conn.cursor()
            cur.execute("DELETE FROM products WHERE id = ?", (int(product_id),))
            deleted_rows = int(cur.rowcount or 0)
            conn.commit()
            return deleted_rows
        except sqlite3.OperationalError as exc:
            if conn is not None:
                conn.rollback()
            if _is_db_locked(exc) and attempt < MAX_DB_RETRIES - 1:
                time.sleep(0.15 * (attempt + 1))
                continue
            raise
        finally:
            if conn is not None:
                conn.close()

    return 0


def change_stock(barcode, delta):
    """Adjust stock for product matching *barcode* by *delta* (can be negative).
    Returns the new stock level or raises ValueError if the product is missing.
    """
    for attempt in range(MAX_DB_RETRIES):
        conn = None
        try:
            conn = connect()
            cur = conn.cursor()
            cur.execute(
                "SELECT stock FROM products WHERE barcode = ?",
                (barcode,),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError("Product not found for barcode: %s" % barcode)
            current = int(row[0] or 0)
            try:
                delta_val = int(delta)
            except (TypeError, ValueError):
                raise ValueError("Delta must be an integer.")
            new_stock = current + delta_val
            if new_stock < 0:
                new_stock = 0
            cur.execute(
                "UPDATE products SET stock = ? WHERE barcode = ?",
                (new_stock, barcode),
            )
            conn.commit()
            return new_stock
        except sqlite3.OperationalError as exc:
            if conn is not None:
                conn.rollback()
            if _is_db_locked(exc) and attempt < MAX_DB_RETRIES - 1:
                time.sleep(0.15 * (attempt + 1))
                continue
            raise
        finally:
            if conn is not None:
                conn.close()
    # should never reach here
    raise RuntimeError("Unable to change stock")
