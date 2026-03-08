import os
import sys
from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
BUNDLED_BASE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
APP_DATA_FOLDER = "MatchlessGiftPOS"


def _runtime_data_dir():
    custom_dir = str(os.environ.get("POS_SYSTEM_DATA_DIR") or "").strip()
    if custom_dir:
        return Path(custom_dir).expanduser()

    if getattr(sys, "frozen", False):
        if os.name == "nt":
            root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
            return root / APP_DATA_FOLDER
        return Path.home() / ".local" / "share" / APP_DATA_FOLDER

    return BASE_DIR / "data"


DATA_DIR = _runtime_data_dir()
DB_PATH = str(DATA_DIR / "pos.db")
SEED_DB_PATH = str(BUNDLED_BASE_DIR / "data" / "pos.db")

# vendor/product IDs only used by Usb printer mode
# detected via `lsusb`: STMicroelectronics GP-58 thermal printer
PRINTER_VENDOR = 0x0483
PRINTER_PRODUCT = 0x5840

# printer selection strategy:
# - "auto": choose the best available backend for the current OS
# - "windows": use Windows spooler/default printer or PRINTER_WINDOWS_NAME
# - "network" / "wifi": use PRINTER_NETWORK_ADDR only
# - "bluetooth": use PRINTER_BLUETOOTH_ADDRESS only
# - "serial": use PRINTER_SERIAL_PORT only
# - "usb": use PRINTER_VENDOR/PRINTER_PRODUCT raw USB only
PRINTER_MODE = "auto"

# alternative connection methods; leave blank to ignore
PRINTER_SERIAL_PORT = ""   # e.g. "/dev/ttyUSB0"
PRINTER_NETWORK_ADDR = ""  # e.g. "192.168.0.50" or "192.168.0.50:9100"
PRINTER_BLUETOOTH_ADDRESS = ""  # e.g. "01:23:45:67:89:AB"
PRINTER_BLUETOOTH_CHANNEL = 1
PRINTER_BLUETOOTH_NAME = ""  # optional label shown in UI
PRINTER_WINDOWS_NAME = ""  # e.g. "EPSON TM-T82 Receipt"

# Extra USB name hints for barcode scanner / 2.4G receiver detection in the UI.
# Keep blank if you do not need custom matching.
SCANNER_NAME_HINTS = (
    "scanner",
    "barcode",
    "honeywell",
    "zebra",
    "symbol",
    "datalogic",
    "newland",
)


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
