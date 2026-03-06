import sqlite3
import time
from pathlib import Path
from config import DB_PATH


def _is_db_locked(exc):
    return "database is locked" in str(exc).lower()


def _column_exists(cur, table_name, column_name):
    cur.execute(f"PRAGMA table_info({table_name})")
    columns = cur.fetchall()
    return any(str(row[1]).lower() == column_name.lower() for row in columns)


def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def create_tables():
    retries = 6
    for attempt in range(retries):
        conn = None
        try:
            conn = connect()
            cur = conn.cursor()
            try:
                cur.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError as exc:
                if not _is_db_locked(exc):
                    raise

            cur.execute("""
            CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode TEXT UNIQUE,
            name TEXT,
            price REAL,
            stock INTEGER
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS sales(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            total REAL,
            payment_mode TEXT DEFAULT 'Cash'
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS sale_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            price REAL
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS recent_receipts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            sale_id INTEGER,
            line_text TEXT
            )
            """)

            if not _column_exists(cur, "sales", "payment_mode"):
                cur.execute("ALTER TABLE sales ADD COLUMN payment_mode TEXT DEFAULT 'Cash'")

            conn.commit()
            return
        except sqlite3.OperationalError as exc:
            if _is_db_locked(exc) and attempt < retries - 1:
                time.sleep(0.25 * (attempt + 1))
                continue
            raise
        finally:
            if conn is not None:
                conn.close()
