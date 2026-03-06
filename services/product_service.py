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
