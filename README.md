# POS System (Matchless Gift Shop)

Offline desktop POS billing application with:
- Inventory management
- Barcode scanner input through USB / wireless dongle keyboard-wedge mode
- Cash / online payment handling
- Thermal receipt printing through Windows spooler, Wi-Fi, Bluetooth, serial, or USB
- Local SQLite database with optional local `sqlite-web` browser

## Tech Stack
- Python 3
- Tkinter
- SQLite

## Configuration
Edit `config.py` for device setup:
- `PRINTER_MODE`: `auto`, `windows`, `network`, `wifi`, `bluetooth`, `serial`, `usb`
- `PRINTER_WINDOWS_NAME`
- `PRINTER_NETWORK_ADDR`
- `PRINTER_BLUETOOTH_ADDRESS`
- `PRINTER_BLUETOOTH_CHANNEL`
- `PRINTER_BLUETOOTH_NAME`
- `PRINTER_SERIAL_PORT`
- `PRINTER_VENDOR`, `PRINTER_PRODUCT`
- `SCANNER_NAME_HINTS`

`network` and `wifi` use the same TCP printer target. Example: `192.168.0.50:9100`

## Run
```bash
cd /home/nk809/Desktop/new_pro/pos_system
source .venv/bin/activate
python3 main.py
```

Windows PowerShell:
```powershell
cd C:\path\to\pos_system
.\.venv\Scripts\Activate.ps1
python main.py
```

## Windows Build
Build the desktop executable on a real Windows machine:
```powershell
cd C:\path\to\pos_system
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python build_windows.py
```

Notes:
- `build_windows.py` bundles `assets/` and `data/` into the executable.
- Runtime data is stored under `%LOCALAPPDATA%\MatchlessGiftPOS`.
- A relative `APP_LOGO_IMAGE` such as `assets/logo.jpeg` now resolves correctly in both source runs and PyInstaller builds.

## Scanner Notes
- Barcode scanners connected through USB or a 2.4 GHz dongle are handled as keyboard input.
- The desktop UI now shows scanner listener state and the last captured scan.
- If a generic dongle does not expose a model name, add a custom hint in `SCANNER_NAME_HINTS`.

## Printer Notes
- `auto` prefers the first working route for the current machine.
- Wi-Fi printers are probed over TCP before the UI marks them connected.
- Bluetooth printers use RFCOMM when supported by the OS/Python build.
- Windows paired printers can still be used through the Windows spooler.

## Optional Database Browser
The app can launch a local `sqlite-web` process for database inspection. If it is not installed, the POS still runs normally in offline mode.
