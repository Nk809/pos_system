# POS System (Matchless Gift Shop)

Desktop POS billing application with:
- Inventory management
- Cart and checkout
- Cash/Online payment mode
- Thermal receipt printing
- Phone bridge (mobile browser) for barcode scanning and cart billing

## Tech Stack
- Python 3
- Tkinter (desktop UI)
- SQLite (local database)
- HTTP/HTTPS phone bridge (built-in Python server)

## Project Structure
- `main.py` -> app entry point
- `ui/` -> desktop UI screens
- `services/` -> billing/product business logic
- `features/` -> phone bridge, printing, reports, export, scanner helpers
- `data/` -> runtime database and TLS files
- `assets/` -> logo/image assets

## Requirements
Tested on Ubuntu with Python `3.12`.

### System packages (Ubuntu)
```bash
sudo apt update
sudo apt install -y python3-tk libzbar0 libgl1 openssl
```

### Python packages
Create and activate virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:
```bash
pip install -r requirements.txt
pip install matplotlib pandas pillow qrcode python-escpos cairosvg
```

## Configuration
Edit `config.py` if needed:
- `UPI_ID`, `UPI_PAYEE_NAME`
- `PRINTER_VENDOR`, `PRINTER_PRODUCT` (USB thermal printer)
- `APP_LOGO_IMAGE` (currently `assets/logo.jpeg`)
- `APP_BACKGROUND_IMAGE` (currently empty/disabled)

## Run
```bash
cd /home/nk809/Desktop/new_pro/pos_system
source .venv/bin/activate
python3 main.py
```

On startup, terminal shows:
- Desktop app starts
- Phone bridge URL, for example: `https://192.168.1.19:8765`

## Phone Bridge Usage
1. Connect phone and laptop to same Wi-Fi.
2. Open the exact URL shown in terminal on phone.
3. For HTTPS self-signed certificate warning, open **Advanced** and proceed once.
4. Use scanner + barcode input to add items to phone cart.  When you tap the **Add To Cart** button the barcode is also forwarded to the desktop POS, so the main billing window will receive the scanned code automatically (quantity times if >1).
5. Select payment mode (Cash/Online), then generate bill.

## Receipt Format
Receipt includes:
- Shop name and location
- Date and time
- Bill number
- Payment mode
- Item lines with qty and totals
- Discount/subtotal/total (if applicable)

## Data Files
- Database: `data/pos.db`
- Phone bridge TLS cert/key: `data/phone_bridge_tls/`

## Troubleshooting

### 1) `Address already in use`
Another process is using the same port.
```bash
ss -ltnp | grep 8765
kill <PID>
python3 main.py
```

### 2) Phone cannot open bridge URL
- Confirm both devices are on same network
- Use exact IP and port printed by app
- Allow firewall port:
```bash
sudo ufw allow 8765/tcp
```

### 3) Camera blocked in browser
- Open HTTPS bridge URL (not HTTP)
- Allow camera permission in mobile browser site settings

### 4) `ModuleNotFoundError`
Install missing package in active venv:
```bash
pip install <package-name>
```

## Git
Initialize and push to GitHub:
```bash
git init
git add .
git commit -m "Initial commit: POS system"
git branch -M main
git remote add origin https://github.com/<your-username>/pos_system.git
git push -u origin main
```

