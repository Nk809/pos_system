from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "data" / "pos.db")

PRINTER_VENDOR = 0x04b8
PRINTER_PRODUCT = 0x0202


UPI_ID = "Q973102140@ybl"
UPI_PAYEE_NAME = "MATCHLESS GIFT SHOP"

# Optional desktop billing background image path (absolute or relative to pos_system/).
# Example: "assets/bg.jpg"
APP_BACKGROUND_IMAGE = ""

# Optional app logo path (absolute or relative to pos_system/).
# Example: "assets/logo.jpeg", "assets/logo.png", or "assets/logo.svg"
APP_LOGO_IMAGE = "assets/logo.jpeg"

def connect():
    return sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
