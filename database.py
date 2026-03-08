import sqlite3
import time
import shutil
from pathlib import Path
from config import DB_PATH, SEED_DB_PATH


def _is_db_locked(exc):
    return "database is locked" in str(exc).lower()


def _column_exists(cur, table_name, column_name):
    cur.execute(f"PRAGMA table_info({table_name})")
    columns = cur.fetchall()
    return any(str(row[1]).lower() == column_name.lower() for row in columns)


def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    _ensure_db_seed()
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


def _ensure_db_seed():
    db_path = Path(DB_PATH)
    if db_path.exists():
        return

    seed_path = Path(SEED_DB_PATH)
    if not seed_path.exists():
        return

    try:
        shutil.copy2(seed_path, db_path)
    except Exception:
        # fall back to empty database creation if the bundled seed cannot be copied
        return


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

            cur.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name COLLATE NOCASE)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(date)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sale_items_sale_id ON sale_items(sale_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_recent_receipts_created_at ON recent_receipts(created_at DESC)")

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
