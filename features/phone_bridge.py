import cgi
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Queue
from threading import Lock, Thread
from urllib.parse import parse_qs
import html
import io
import json
from pathlib import Path
import re
import socket
import ssl
import subprocess

from config import APP_BACKGROUND_IMAGE, APP_LOGO_IMAGE, BASE_DIR, UPI_ID, UPI_PAYEE_NAME
from database import connect
from features.thermal_printer import print_bill
from services.billing_service import save_sale
from services.product_service import search_product

# when users add a barcode from the browser interface we place the
# raw value in this queue. `BillingUI.poll_phone_scans` periodically
# calls `pop_scanned_barcode` to pull new values and insert them into
# the main POS cart as if a hardware scanner had been used.
_barcode_queue = Queue()
_server = None
_thread = None
_bridge_scheme = "http"
_phone_cart = []
_phone_cart_payment_mode = "Cash"
_phone_cart_discount_percent = 0.0
_phone_cart_lock = Lock()


def _resolve_phone_bridge_background_image():
    raw = str(APP_BACKGROUND_IMAGE or "").strip()
    if not raw:
        return None

    image_path = Path(raw)
    if not image_path.is_absolute():
        image_path = BASE_DIR / image_path

    if not image_path.exists() or not image_path.is_file():
        return None
    return image_path


def _resolve_phone_bridge_logo_image():
    raw = str(APP_LOGO_IMAGE or "").strip()
    if not raw:
        return None

    image_path = Path(raw)
    if not image_path.is_absolute():
        image_path = BASE_DIR / image_path

    if not image_path.exists() or not image_path.is_file():
        return None
    return image_path


def _content_type_for_image(path_obj):
    extension = path_obj.suffix.lower()
    if extension == ".png":
        return "image/png"
    if extension in (".jpg", ".jpeg"):
        return "image/jpeg"
    if extension == ".webp":
        return "image/webp"
    if extension == ".bmp":
        return "image/bmp"
    if extension == ".gif":
        return "image/gif"
    if extension == ".svg":
        return "image/svg+xml"
    return "application/octet-stream"


def _local_ip():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ip = "127.0.0.1"
    try:
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
    except Exception:
        pass
    finally:
        probe.close()

    # if we only have loopback, attempt other lookups
    if ip.startswith("127.") or ip == "0.0.0.0":
        try:
            host = socket.gethostname()
            alt = socket.gethostbyname(host)
            if alt and not alt.startswith("127."):
                ip = alt
        except Exception:
            pass

    return ip


def _tls_paths():
    root_dir = Path(__file__).resolve().parents[1]
    tls_dir = root_dir / "data" / "phone_bridge_tls"
    cert_path = tls_dir / "cert.pem"
    key_path = tls_dir / "key.pem"
    return tls_dir, cert_path, key_path


def _ensure_tls_certificates(host_ip):
    tls_dir, cert_path, key_path = _tls_paths()
    if cert_path.exists() and key_path.exists():
        return str(cert_path), str(key_path), None

    tls_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "openssl",
        "req",
        "-x509",
        "-nodes",
        "-newkey",
        "rsa:2048",
        "-keyout",
        str(key_path),
        "-out",
        str(cert_path),
        "-days",
        "3650",
        "-subj",
        "/CN=POS Phone Bridge",
        "-addext",
        f"subjectAltName=IP:{host_ip},DNS:localhost",
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        return None, None, f"openssl is not installed: {exc}"
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        return None, None, f"TLS certificate generation failed: {stderr or exc}"

    return str(cert_path), str(key_path), None


def _wrap_server_tls(server, cert_path, key_path):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert_path, keyfile=key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)


def _to_float(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        try:
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return None


def _first_non_empty(mapping, keys):
    for key in keys:
        if key not in mapping:
            continue
        value = mapping.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _first_number(mapping, keys, caster):
    for key in keys:
        if key not in mapping:
            continue
        value = mapping.get(key)
        converted = _to_float(value) if caster is float else _to_int(value)
        if converted is not None:
            return converted
    return None


def _parse_scanned_payload(raw_value):
    raw = (raw_value or "").strip()
    parsed = {"barcode": "", "name": "", "price": None, "stock": None}
    if not raw:
        return parsed

    details = {}

    try:
        loaded = json.loads(raw)
        if isinstance(loaded, dict):
            details = {str(key).strip().lower(): value for key, value in loaded.items()}
    except Exception:
        details = {}

    if not details:
        key_values = {}
        for block in re.split(r"[;\n|&]+", raw):
            chunk = block.strip()
            if not chunk:
                continue

            if "=" in chunk:
                key, value = chunk.split("=", 1)
            elif ":" in chunk:
                key, value = chunk.split(":", 1)
            else:
                continue

            key_values[key.strip().lower()] = value.strip()

        if key_values:
            details = key_values

    if details:
        parsed["barcode"] = _first_non_empty(details, ["barcode", "bar_code", "code", "sku", "ean", "upc", "item_code", "id"])
        parsed["name"] = _first_non_empty(details, ["name", "item", "product", "title"])
        parsed["price"] = _first_number(details, ["price", "mrp", "rate", "amount", "selling_price"], float)
        parsed["stock"] = _first_number(details, ["stock", "qty", "quantity"], int)
        return parsed

    for separator in (",", "|"):
        split_values = [part.strip() for part in raw.split(separator)]
        if len(split_values) in (3, 4):
            parsed["barcode"] = split_values[0]
            parsed["name"] = split_values[1]
            parsed["price"] = _to_float(split_values[2])
            if len(split_values) == 4:
                parsed["stock"] = _to_int(split_values[3])
            return parsed

    parsed["barcode"] = raw
    return parsed


def _decode_barcode_from_image(image_bytes):
    try:
        import cv2
        import numpy as np
        from pyzbar.pyzbar import decode
    except Exception as exc:
        raise RuntimeError("Scanner dependencies are missing. Install opencv-python and pyzbar.") from exc

    if not image_bytes:
        return None

    def _first_payload(decoded_rows):
        for item in decoded_rows or []:
            value = item.data.decode("utf-8").strip()
            if value:
                return value
        return None

    frame = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        try:
            from PIL import Image
        except Exception:
            return None
        try:
            pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception:
            return None
        frame = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    variants = [frame]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    variants.append(gray)
    variants.append(cv2.equalizeHist(gray))
    variants.append(cv2.GaussianBlur(gray, (3, 3), 0))
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(binary)
    variants.append(cv2.resize(frame, None, fx=1.6, fy=1.6, interpolation=cv2.INTER_CUBIC))
    variants.append(cv2.resize(gray, None, fx=1.8, fy=1.8, interpolation=cv2.INTER_CUBIC))

    for sample in variants:
        value = _first_payload(decode(sample))
        if value:
            return value

    try:
        qr_detector = cv2.QRCodeDetector()
        for sample in variants:
            text, _points, _straight = qr_detector.detectAndDecode(sample)
            if text and text.strip():
                return text.strip()
    except Exception:
        pass

    return None


def _find_product_by_barcode(barcode):
    matches = search_product(barcode)
    for row in matches:
        existing_barcode = (row[1] or "").strip()
        if existing_barcode == barcode:
            return row
    return None


def _get_product_by_id(product_id):
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, barcode, name, price, stock
            FROM products
            WHERE id = ?
            """,
            (int(product_id),),
        )
        return cur.fetchone()
    finally:
        conn.close()


def _normalize_payment_mode(mode_text):
    return "Online" if str(mode_text).strip().lower() == "online" else "Cash"


def _normalize_discount_percent(raw_value):
    parsed = _to_float(raw_value)
    if parsed is None:
        raise ValueError("Discount must be a valid number.")
    if parsed < 0 or parsed > 100:
        raise ValueError("Discount must be between 0 and 100.")
    return round(float(parsed), 2)


def _serialize_phone_cart_unlocked():
    items = []
    subtotal = 0.0

    for item in _phone_cart:
        qty = int(item["qty"])
        price = float(item["price"])
        line_total = round(qty * price, 2)
        subtotal += line_total

        items.append(
            {
                "id": int(item["id"]),
                "barcode": str(item["barcode"]),
                "name": str(item["name"]),
                "price": round(price, 2),
                "stock": int(item["stock"]),
                "qty": qty,
                "line_total": line_total,
            }
        )

    subtotal = round(subtotal, 2)
    discount_percent = round(float(_phone_cart_discount_percent), 2)
    discount_amount = round(subtotal * (discount_percent / 100.0), 2)
    total = round(max(subtotal - discount_amount, 0.0), 2)
    return {
        "items": items,
        "subtotal": subtotal,
        "discount_percent": discount_percent,
        "discount_amount": discount_amount,
        "total": total,
        "payment_mode": _phone_cart_payment_mode,
    }


def _phone_cart_success(message=""):
    with _phone_cart_lock:
        cart_data = _serialize_phone_cart_unlocked()
    return {"success": True, "message": message, "cart": cart_data}


def _phone_cart_error(message, status_code=400):
    return {"success": False, "message": message}, status_code


def _process_phone_cart_add_form(form):
    barcode = form.get("barcode", [""])[0].strip()
    qty = _to_int(form.get("qty", ["1"])[0])

    if not barcode:
        return _phone_cart_error("Barcode is required.")
    if qty is None or qty <= 0:
        return _phone_cart_error("Quantity must be a positive whole number.")

    product_row = _find_product_by_barcode(barcode)
    if product_row is None:
        return _phone_cart_error("Product not found in POS inventory.")

    product_id, product_barcode, name, price, stock = product_row
    product_id = int(product_id)
    stock = int(stock)
    price = float(price)

    with _phone_cart_lock:
        existing = next((item for item in _phone_cart if int(item["id"]) == product_id), None)
        existing_qty = int(existing["qty"]) if existing else 0
        added_qty = int(qty)
        new_qty = existing_qty + added_qty
        if new_qty > stock:
            return _phone_cart_error(f"Only {stock} unit(s) available for {name}.")

        if existing:
            existing["qty"] = new_qty
            existing["stock"] = stock
            existing["price"] = price
            existing["name"] = name
            existing["barcode"] = (product_barcode or barcode).strip()
        else:
            _phone_cart.append(
                {
                    "id": product_id,
                    "barcode": (product_barcode or barcode).strip(),
                    "name": (name or "").strip(),
                    "price": price,
                    "stock": stock,
                    "qty": added_qty,
                }
            )

        # also forward scanned barcodes to the desktop queue so the main POS UI picks them up
        # push once per unit added (mimics scanning multiple times)
        bridge_code = (product_barcode or barcode).strip()
        if bridge_code:
            for _ in range(added_qty):
                try:
                    _barcode_queue.put(bridge_code)
                except Exception:
                    pass

        cart_data = _serialize_phone_cart_unlocked()
    return {"success": True, "message": f"Added {name} x{qty}.", "cart": cart_data}, 200


def _process_phone_cart_add_manual_form(form):
    name = form.get("name", [""])[0].strip()
    price = _to_float(form.get("price", [""])[0])
    qty = _to_int(form.get("qty", ["1"])[0])

    if not name:
        return _phone_cart_error("Item name is required.")
    if price is None or price < 0:
        return _phone_cart_error("Price must be a non-negative number.")
    if qty is None or qty <= 0:
        return _phone_cart_error("Quantity must be a positive whole number.")

    with _phone_cart_lock:
        _phone_cart.append(
            {
                "id": 0,
                "barcode": "",
                "name": name,
                "price": price,
                "stock": 0,
                "qty": int(qty),
            }
        )
        cart_data = _serialize_phone_cart_unlocked()
    return {"success": True, "message": f"Added {name} x{qty}.", "cart": cart_data}, 200


def _process_phone_cart_set_qty_form(form):
    product_id = _to_int(form.get("product_id", [""])[0])
    qty = _to_int(form.get("qty", [""])[0])

    if product_id is None:
        return _phone_cart_error("Product id is required.")
    if qty is None or qty < 0:
        return _phone_cart_error("Quantity must be 0 or a positive whole number.")

    product_row = _get_product_by_id(product_id)
    if product_row is None:
        return _phone_cart_error("Product no longer exists in inventory.")

    db_product_id, db_barcode, db_name, db_price, db_stock = product_row
    db_stock = int(db_stock)
    db_price = float(db_price)

    with _phone_cart_lock:
        existing = next((item for item in _phone_cart if int(item["id"]) == int(db_product_id)), None)
        if existing is None:
            return _phone_cart_error("Product is not present in phone cart.")

        if qty == 0:
            _phone_cart.remove(existing)
            cart_data = _serialize_phone_cart_unlocked()
            return {"success": True, "message": f"Removed {db_name}.", "cart": cart_data}, 200

        if qty > db_stock:
            return _phone_cart_error(f"Only {db_stock} unit(s) available for {db_name}.")

        existing["qty"] = int(qty)
        existing["stock"] = db_stock
        existing["price"] = db_price
        existing["name"] = (db_name or "").strip()
        existing["barcode"] = (db_barcode or "").strip()
        cart_data = _serialize_phone_cart_unlocked()
    return {"success": True, "message": f"Updated {db_name} quantity to {qty}.", "cart": cart_data}, 200


def _process_phone_cart_remove_form(form):
    product_id = _to_int(form.get("product_id", [""])[0])
    if product_id is None:
        return _phone_cart_error("Product id is required.")

    with _phone_cart_lock:
        for item in list(_phone_cart):
            if int(item["id"]) == int(product_id):
                _phone_cart.remove(item)
                cart_data = _serialize_phone_cart_unlocked()
                return {"success": True, "message": f"Removed {item['name']}.", "cart": cart_data}, 200

    return _phone_cart_error("Product is not present in phone cart.", status_code=404)


def _process_phone_cart_clear():
    global _phone_cart_discount_percent
    with _phone_cart_lock:
        _phone_cart.clear()
        _phone_cart_discount_percent = 0.0
        cart_data = _serialize_phone_cart_unlocked()
    return {"success": True, "message": "Phone cart cleared.", "cart": cart_data}, 200


def _process_phone_cart_payment_mode(form):
    global _phone_cart_payment_mode
    mode = _normalize_payment_mode(form.get("payment_mode", ["Cash"])[0])
    with _phone_cart_lock:
        _phone_cart_payment_mode = mode
        cart_data = _serialize_phone_cart_unlocked()
    return {"success": True, "message": f"Payment mode set to {mode}.", "cart": cart_data}, 200


def _process_phone_cart_discount_form(form):
    global _phone_cart_discount_percent
    try:
        discount_percent = _normalize_discount_percent(form.get("discount_percent", ["0"])[0])
    except ValueError as exc:
        return _phone_cart_error(str(exc))

    with _phone_cart_lock:
        _phone_cart_discount_percent = discount_percent
        cart_data = _serialize_phone_cart_unlocked()
    return {
        "success": True,
        "message": f"Discount set to {discount_percent:.2f}%.",
        "cart": cart_data,
    }, 200


def _process_phone_cart_complete():
    global _phone_cart_discount_percent
    with _phone_cart_lock:
        if not _phone_cart:
            return _phone_cart_error("Phone cart is empty.")

        payment_mode = _phone_cart_payment_mode
        discount_percent = round(float(_phone_cart_discount_percent), 2)
        cart_for_sale = [
            {
                "id": int(item["id"]),
                "name": str(item["name"]),
                "qty": int(item["qty"]),
                "price": float(item["price"]),
                "total": round(int(item["qty"]) * float(item["price"]), 2),
            }
            for item in _phone_cart
        ]
        cart_for_print = [dict(item) for item in cart_for_sale]

    try:
        sale_result = save_sale(cart_for_sale, payment_mode=payment_mode, discount_percent=discount_percent)
    except ValueError as exc:
        return _phone_cart_error(str(exc))
    except Exception as exc:
        return _phone_cart_error(f"Checkout failed: {exc}", status_code=500)

    sale_id = int(sale_result.get("sale_id", 0))
    subtotal = float(sale_result.get("subtotal", 0.0))
    discount_percent = float(sale_result.get("discount_percent", 0.0))
    discount_amount = float(sale_result.get("discount_amount", 0.0))
    total = float(sale_result.get("total", 0.0))
    normalized_mode = str(sale_result.get("payment_mode", payment_mode))

    print_result = print_bill(
        cart_for_print,
        total,
        bill_no=sale_id,
        payment_mode=normalized_mode,
        subtotal=subtotal,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
    )
    print_message = print_result.get("message", "Sale saved.")

    with _phone_cart_lock:
        _phone_cart.clear()
        _phone_cart_discount_percent = 0.0
        cart_data = _serialize_phone_cart_unlocked()

    return {
        "success": True,
        "message": (
            f"Bill #{sale_id} completed ({normalized_mode}) | Subtotal: {subtotal:.2f} | "
            f"Discount: {discount_percent:.2f}% ({discount_amount:.2f}) | Total: {total:.2f}. {print_message}"
        ),
        "cart": cart_data,
    }, 200


def _lookup_product_form(form):
    barcode = form.get("barcode", [""])[0].strip()
    if not barcode:
        return {"success": False, "message": "Barcode is required."}, 400

    row = _find_product_by_barcode(barcode)
    if row is None:
        return {"success": True, "found": False, "product": None}, 200

    product_id, product_barcode, name, price, stock = row
    return {
        "success": True,
        "found": True,
        "product": {
            "id": int(product_id),
            "barcode": (product_barcode or barcode).strip(),
            "name": (name or "").strip(),
            "price": float(price),
            "stock": int(stock),
        },
    }, 200


def _render_page(message=""):
    safe_message = html.escape(message)
    safe_upi_id_js = json.dumps(str(UPI_ID or "").strip())
    safe_upi_name_js = json.dumps(str(UPI_PAYEE_NAME or "").strip())
    bg_image_available = _resolve_phone_bridge_background_image() is not None
    logo_image_available = _resolve_phone_bridge_logo_image() is not None
    logo_markup = (
        '<img src="/bridge-logo-image" class="logo-image" alt="Matchless Gift Shop logo" />'
        if logo_image_available
        else "MG"
    )
    body_background_css = (
        "background: linear-gradient(rgba(255,255,255,0.38), rgba(255,255,255,0.58)), "
        "url('/bridge-bg-image') center/cover no-repeat #f5f5f5;"
        if bg_image_available
        else "background: #f5f5f5;"
    )
    card_background_css = "background: rgba(255,255,255,0.90);" if bg_image_available else "background: #fff;"
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Matchless Gift Shop</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; padding: 14px; min-height: 100vh; box-sizing: border-box; {body_background_css} }}
    .page-shell {{ max-width: 540px; margin: 0 auto; }}
    .card {{ {card_background_css} border: 1px solid #d8d8d8; border-radius: 10px; padding: 12px; margin-bottom: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.08); }}
    input {{ width: 100%; padding: 10px; margin: 6px 0; box-sizing: border-box; }}
    button {{ padding: 10px 12px; border: 0; border-radius: 6px; background: #0a7cff; color: #fff; }}
    button.secondary {{ background: #5f6b7a; }}
    button.warn {{ background: #d9534f; }}
    button.success {{ background: #1b8f3a; }}
    .row {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
    .row > * {{ flex: 1 1 auto; }}
    .qty-input {{ width: 74px; padding: 6px; }}
    .payment-btn.active {{ background: #1b8f3a; }}
    .payment-btn.passive {{ background: #6b7280; }}
    .phone-cart-list {{ margin-top: 8px; border: 1px solid #e5e7eb; border-radius: 6px; background: #fafafa; }}
    .cart-item {{ border-bottom: 1px solid #e5e7eb; padding: 8px; }}
    .cart-item:last-child {{ border-bottom: none; }}
    .cart-top {{ font-weight: bold; }}
    .cart-meta {{ color: #555; font-size: 12px; margin: 2px 0 6px; }}
    .cart-empty {{ padding: 10px; color: #555; }}
    .phone-cart-total {{ margin-top: 8px; font-weight: bold; }}
    .discount-row {{ margin-top: 8px; }}
    .discount-row label {{ flex: 0 0 auto; font-size: 13px; color: #333; }}
    .discount-input {{ max-width: 110px; }}
    .phone-cart-status {{ min-height: 20px; margin-top: 8px; color: #333; }}

    .scan-status {{ min-height: 20px; margin: 6px 0; color: #333; }}
    .scan-actions {{ display: flex; gap: 8px; margin: 6px 0 8px; }}
    .scan-button {{ margin: 0; width: 100%; }}
    #preview {{ width: 100%; border-radius: 6px; border: 1px solid #ddd; display: none; background: #000; }}
    .header-bar {{ display: flex; align-items: center; justify-content: center; gap: 10px; margin: 0 0 10px; }}
    .logo-card {{
      width: 50px;
      height: 50px;
      border-radius: 10px;
      border: 2px solid #222;
      background: #ffffff;
      color: #1f2937;
      font-size: 14px;
      font-weight: 700;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 2px 8px rgba(0,0,0,0.18);
      flex: 0 0 auto;
    }}
    .logo-image {{ width: 42px; height: 42px; object-fit: contain; display: block; filter: contrast(1.25); }}
    .message {{ font-weight: bold; margin-bottom: 10px; }}
    .page-title {{ text-align: center; margin: 0; font-size: 24px; }}
    .phonepe-hint {{ font-size: 12px; color: #444; }}
    .phonepe-qr {{ display: block; width: 220px; height: 220px; margin: 6px auto; border: 1px solid #d6dce5; border-radius: 6px; background: #fff; object-fit: contain; }}
  </style>
</head>
<body>
  <div class="page-shell">
    <div class="header-bar">
      <div class="logo-card" aria-label="Matchless Gift Shop logo">{logo_markup}</div>
      <h2 class="page-title">Matchless Gift Shop</h2>
    </div>
    <div class="message">{safe_message}</div>
    <div style="font-size:12px;color:#555;margin-bottom:8px;">
      Open this page from your phone using the URL shown in the POS terminal. Make sure the phone is on the same local network as the POS.
    </div>
    <div class="card">
      <h3>Send Barcode To Billing</h3>
      <div class="scan-actions">
        <button id="scan-toggle" type="button" class="scan-button">Start Scanner</button>
      </div>
      <video id="preview" autoplay playsinline muted></video>
      <div id="scan-status" class="scan-status"></div>
      <form id="scan-form" method="POST" action="#">
        <input id="barcode-input" name="barcode" placeholder="Scan or type barcode manually" required />
        <div class="row">
          <input id="scan-qty" type="number" min="1" step="1" value="1" placeholder="Qty" />
          <button id="add-to-phone-cart" type="submit">Add To Cart (also send to POS)</button>
        </div>
        <button id="add-manual-item" type="button" class="secondary" style="margin-top:8px;">Add Manual Item</button>
      </form>
    </div>
    <div class="card">
      <h3>Phone Billing Cart</h3>
      <div class="row">
        <button id="pay-cash" type="button" class="payment-btn">Cash</button>
        <button id="pay-online" type="button" class="payment-btn">Online</button>
      </div>
      <div class="row discount-row">
        <label for="phone-discount">Discount %</label>
        <input id="phone-discount" class="discount-input" type="number" min="0" max="100" step="0.01" value="0" />
        <button id="phone-discount-apply" type="button" class="secondary">Apply</button>
      </div>
      <div id="phone-cart-total" class="phone-cart-total">Subtotal: 0.00 | Discount: 0.00% (0.00) | Total: 0.00</div>
      <div id="online-qr-container" style="display:none; margin-top:8px; text-align:center;">
        <img id="online-qr" class="phonepe-qr" alt="Payment QR" />
        <div id="online-qr-hint" class="phonepe-hint"></div>
      </div>
      <div id="phone-cart-list" class="phone-cart-list">
        <div class="cart-empty">No items in phone cart.</div>
      </div>
      <div class="row" style="margin-top: 8px;">
        <button id="phone-cart-refresh" type="button" class="secondary">Refresh Cart</button>
        <button id="phone-cart-clear" type="button" class="warn">Clear Cart</button>
        <button id="phone-cart-complete" type="button" class="success">Generate Bill</button>
      </div>
      <div id="phone-cart-status" class="phone-cart-status"></div>
    </div>
  </div>
  <script>
    (function () {{
      const PHONEPE_UPI_ID = {safe_upi_id_js};
      const PHONEPE_UPI_NAME = {safe_upi_name_js};

      const barcodeInput = document.getElementById("barcode-input");
      const scanForm = document.getElementById("scan-form");
      const scanToggle = document.getElementById("scan-toggle");
      const scanQtyInput = document.getElementById("scan-qty");
      const scanStatus = document.getElementById("scan-status");
      const preview = document.getElementById("preview");
      const addToPhoneCartBtn = document.getElementById("add-to-phone-cart");
      const phoneCartList = document.getElementById("phone-cart-list");
      const phoneCartTotal = document.getElementById("phone-cart-total");
      const phoneCartStatus = document.getElementById("phone-cart-status");
      const phoneCartRefreshBtn = document.getElementById("phone-cart-refresh");
      const phoneCartClearBtn = document.getElementById("phone-cart-clear");
      const phoneCartCompleteBtn = document.getElementById("phone-cart-complete");
      const phoneDiscountInput = document.getElementById("phone-discount");
      const phoneDiscountApplyBtn = document.getElementById("phone-discount-apply");
      const payCashBtn = document.getElementById("pay-cash");
      const payOnlineBtn = document.getElementById("pay-online");
      const addManualBtn = document.getElementById("add-manual-item");



      let stream = null;
      let detector = null;
      let intervalId = null;
      let scanning = false;
      let frameRequestInFlight = false;
      let scanCanvas = null;

      function setStatus(text) {{
        scanStatus.textContent = text;
      }}

      function setPhoneCartStatus(text) {{
        phoneCartStatus.textContent = text || "";
      }}

      function asPositiveInt(value, fallbackValue) {{
        const parsed = Number.parseInt(String(value || "").trim(), 10);
        if (Number.isInteger(parsed) && parsed > 0) {{
          return parsed;
        }}
        return fallbackValue;
      }}

      function asNonNegativeInt(value) {{
        const parsed = Number.parseInt(String(value || "").trim(), 10);
        if (Number.isInteger(parsed) && parsed >= 0) {{
          return parsed;
        }}
        return null;
      }}

      function asDiscountPercentOrNull(value) {{
        const parsed = Number.parseFloat(String(value || "").trim());
        if (Number.isFinite(parsed) && parsed >= 0 && parsed <= 100) {{
          return parsed;
        }}
        return null;
      }}

      function escapeHtml(text) {{
        return String(text || "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#39;");
      }}

      function setPaymentButtons(mode) {{
        const normalized = String(mode || "Cash").toLowerCase() === "online" ? "Online" : "Cash";
        const cashActive = normalized === "Cash";
        payCashBtn.classList.toggle("active", cashActive);
        payCashBtn.classList.toggle("passive", !cashActive);
        payOnlineBtn.classList.toggle("active", !cashActive);
        payOnlineBtn.classList.toggle("passive", cashActive);
      }}

      function buildUpiLink(amount) {{
        const params = new URLSearchParams();
        params.set("pa", String(PHONEPE_UPI_ID || "").trim());
        params.set("pn", String(PHONEPE_UPI_NAME || "MATCHLESS GIFT SHOP").trim());
        params.set("am", Number(amount || 0).toFixed(2));
        params.set("cu", "INR");
        params.set("tn", "POS Bill Payment");
        return "upi://pay?" + params.toString();
      }}

      function updateOnlineQr(total, mode) {{
        const amount = Number(total || 0);
        const container = document.getElementById("online-qr-container");
        const hint = document.getElementById("online-qr-hint");
        const qrImg = document.getElementById("online-qr");
        if (mode.toLowerCase() !== "online" || amount <= 0) {{
          container.style.display = "none";
          return;
        }}
        const upiConfigured = String(PHONEPE_UPI_ID || "").trim().length > 0 &&
          String(PHONEPE_UPI_ID || "").toLowerCase().indexOf("your-upi-id") === -1;
        if (!upiConfigured) {{
          hint.textContent = "UPI ID is not configured in POS config.";
          container.style.display = "none";
          return;
        }}
        const link = buildUpiLink(amount);
        qrImg.src = "https://quickchart.io/qr?size=220&text=" + encodeURIComponent(link);
        hint.textContent = "UPI ID: " + PHONEPE_UPI_ID;
        container.style.display = "block";
      }}



      async function postForm(url, keyValues) {{
        const params = new URLSearchParams();
        for (const key in keyValues) {{
          if (Object.prototype.hasOwnProperty.call(keyValues, key)) {{
            params.set(key, String(keyValues[key]));
          }}
        }}

        const response = await fetch(url, {{
          method: "POST",
          headers: {{
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          }},
          body: params.toString(),
        }});

        let payload = null;
        const rawText = await response.text();
        try {{
          payload = rawText ? JSON.parse(rawText) : {{}};
        }} catch (_parseErr) {{
          payload = {{}};
        }}

        if (!response.ok) {{
          if (!payload || typeof payload !== "object") {{
            payload = {{}};
          }}
          payload.success = false;
          if (!payload.message) {{
            payload.message = "Request failed (" + response.status + ").";
          }}
        }}

        if (!payload || typeof payload !== "object") {{
          payload = {{ success: false, message: "Unexpected response from POS bridge." }};
        }}
        return payload;
      }}

      function getBridgeNetworkErrorMessage(err) {{
        const raw = err && err.message ? String(err.message) : "";
        if (raw && raw !== "Failed to fetch") {{
          return "POS bridge connection error: " + raw;
        }}
        return "Cannot connect to POS bridge. Open the correct HTTPS link and accept certificate warning once.";
      }}

      function renderPhoneCart(payload) {{
        const cart = payload && payload.cart ? payload.cart : {{
          items: [],
          subtotal: 0,
          discount_percent: 0,
          discount_amount: 0,
          total: 0,
          payment_mode: "Cash",
        }};
        const items = Array.isArray(cart.items) ? cart.items : [];
        const subtotal = Number(cart.subtotal || 0);
        const discountPercent = Number(cart.discount_percent || 0);
        const discountAmount = Number(cart.discount_amount || 0);
        const total = Number(cart.total || 0);

        setPaymentButtons(cart.payment_mode || "Cash");
        phoneDiscountInput.value = discountPercent.toFixed(2);
        phoneCartTotal.textContent =
          "Subtotal: " + subtotal.toFixed(2) +
          " | Discount: " + discountPercent.toFixed(2) + "% (" + discountAmount.toFixed(2) + ")" +
          " | Total: " + total.toFixed(2);
        updateOnlineQr(total, cart.payment_mode || "Cash");

        if (items.length === 0) {{
          phoneCartList.innerHTML = '<div class="cart-empty">No items in phone cart.</div>';
          return;
        }}

        const htmlRows = items.map(function (item) {{
          const safeName = escapeHtml(item.name || "");
          const safeBarcode = escapeHtml(item.barcode || "");
          const stock = Number(item.stock || 0);
          const qty = Number(item.qty || 0);
          const price = Number(item.price || 0).toFixed(2);
          const lineTotal = Number(item.line_total || 0).toFixed(2);
          const id = Number(item.id || 0);

          return (
            '<div class="cart-item">' +
            '<div class="cart-top">' + safeName + ' | ' + lineTotal + "</div>" +
            '<div class="cart-meta">Barcode: ' + safeBarcode + " | Price: " + price + " | Stock: " + stock + "</div>" +
            '<div class="row">' +
            '<input class="qty-input" type="number" min="0" step="1" value="' + qty + '" data-qty-id="' + id + '" />' +
            '<button type="button" class="secondary" data-update-id="' + id + '">Update Qty</button>' +
            '<button type="button" class="warn" data-remove-id="' + id + '">Remove</button>' +
            "</div>" +
            "</div>"
          );
        }});

        phoneCartList.innerHTML = htmlRows.join("");
      }}

      async function refreshPhoneCart(optionalMessage) {{
        try {{
          const payload = await postForm("/phone-cart-state", {{}});
          if (!payload.success) {{
            setPhoneCartStatus(payload.message || "Unable to load phone cart.");
            return;
          }}

          renderPhoneCart(payload);
          if (optionalMessage) {{
            setPhoneCartStatus(optionalMessage);
          }}
        }} catch (err) {{
          setPhoneCartStatus(getBridgeNetworkErrorMessage(err));
        }}
      }}

      async function addToPhoneCartByBarcode(barcode, qty) {{
        if (!barcode) {{
          setPhoneCartStatus("Barcode is required.");
          return;
        }}

        try {{
          const payload = await postForm("/phone-cart-add", {{ barcode: barcode, qty: qty }});
          if (!payload.success) {{
            setPhoneCartStatus(payload.message || "Unable to add item to phone cart.");
            return;
          }}

          renderPhoneCart(payload);
          setPhoneCartStatus(payload.message || "Added to phone cart.");
        }} catch (err) {{
          setPhoneCartStatus(getBridgeNetworkErrorMessage(err));
        }}
      }}

      async function addCurrentBarcodeToPhoneCart() {{
        const barcode = String(barcodeInput.value || "").trim();
        const qty = asPositiveInt(scanQtyInput.value, 1);
        scanQtyInput.value = String(qty);

        if (!barcode) {{
          setPhoneCartStatus("Scan or type barcode first.");
          barcodeInput.focus();
          return;
        }}

        await addToPhoneCartByBarcode(barcode, qty);
      }}

      async function addManualItem() {{
        const name = prompt("Item name:");
        if (!name) {{
          return;
        }}
        const priceStr = prompt("Item price:");
        const price = Number(priceStr);
        if (!priceStr || isNaN(price) || price < 0) {{
          setPhoneCartStatus("Invalid price.");
          return;
        }}
        const qtyStr = prompt("Quantity:", "1");
        const qty = parseInt(qtyStr, 10);
        if (!qtyStr || isNaN(qty) || qty <= 0) {{
          setPhoneCartStatus("Invalid quantity.");
          return;
        }}

        try {{
          const payload = await postForm("/phone-cart-add-manual", {{ name: name, price: price, qty: qty }});
          if (!payload.success) {{
            setPhoneCartStatus(payload.message || "Unable to add manual item.");
            return;
          }}
          renderPhoneCart(payload);
          setPhoneCartStatus(payload.message || "Manual item added.");
        }} catch (err) {{
          setPhoneCartStatus(getBridgeNetworkErrorMessage(err));
        }}
      }}
      async function setPhoneCartQty(productId, qty) {{
        try {{
          const payload = await postForm("/phone-cart-set-qty", {{
            product_id: productId,
            qty: qty,
          }});
          if (!payload.success) {{
            setPhoneCartStatus(payload.message || "Unable to update quantity.");
            return;
          }}

          renderPhoneCart(payload);
          setPhoneCartStatus(payload.message || "Quantity updated.");
        }} catch (err) {{
          setPhoneCartStatus(getBridgeNetworkErrorMessage(err));
        }}
      }}

      async function removeFromPhoneCart(productId) {{
        try {{
          const payload = await postForm("/phone-cart-remove", {{ product_id: productId }});
          if (!payload.success) {{
            setPhoneCartStatus(payload.message || "Unable to remove item.");
            return;
          }}

          renderPhoneCart(payload);
          setPhoneCartStatus(payload.message || "Item removed.");
        }} catch (err) {{
          setPhoneCartStatus(getBridgeNetworkErrorMessage(err));
        }}
      }}

      async function setPhonePaymentMode(mode) {{
        try {{
          const payload = await postForm("/phone-cart-payment", {{ payment_mode: mode }});
          if (!payload.success) {{
            setPhoneCartStatus(payload.message || "Unable to set payment mode.");
            return;
          }}

          renderPhoneCart(payload);
          setPhoneCartStatus(payload.message || ("Payment mode set to " + mode + "."));
        }} catch (err) {{
          setPhoneCartStatus(getBridgeNetworkErrorMessage(err));
        }}
      }}

      async function setPhoneDiscount() {{
        const discountPercent = asDiscountPercentOrNull(phoneDiscountInput.value);
        if (discountPercent === null) {{
          setPhoneCartStatus("Discount must be between 0 and 100.");
          return;
        }}

        phoneDiscountInput.value = discountPercent.toFixed(2);

        try {{
          const payload = await postForm("/phone-cart-discount", {{
            discount_percent: discountPercent,
          }});
          if (!payload.success) {{
            setPhoneCartStatus(payload.message || "Unable to set discount.");
            return;
          }}

          renderPhoneCart(payload);
          setPhoneCartStatus(payload.message || ("Discount set to " + discountPercent.toFixed(2) + "%."));
        }} catch (err) {{
          setPhoneCartStatus(getBridgeNetworkErrorMessage(err));
        }}
      }}

      async function clearPhoneCart() {{
        try {{
          const payload = await postForm("/phone-cart-clear", {{}});
          if (!payload.success) {{
            setPhoneCartStatus(payload.message || "Unable to clear phone cart.");
            return;
          }}

          renderPhoneCart(payload);
          setPhoneCartStatus(payload.message || "Phone cart cleared.");
        }} catch (err) {{
          setPhoneCartStatus(getBridgeNetworkErrorMessage(err));
        }}
      }}

      async function completePhoneSale() {{
        phoneCartCompleteBtn.disabled = true;
        try {{
          const payload = await postForm("/phone-cart-complete", {{}});
          if (!payload.success) {{
            setPhoneCartStatus(payload.message || "Checkout failed.");
            return;
          }}

          renderPhoneCart(payload);
          setPhoneCartStatus(payload.message || "Sale completed.");
        }} catch (err) {{
          setPhoneCartStatus(getBridgeNetworkErrorMessage(err));
        }} finally {{
          phoneCartCompleteBtn.disabled = false;
        }}
      }}

      if (!window.isSecureContext) {{
        setStatus("Live camera requires HTTPS. Open the HTTPS bridge URL shown in POS terminal.");
      }}

      function toNumber(value) {{
        const numberValue = Number(value);
        if (Number.isFinite(numberValue)) {{
          return numberValue;
        }}
        return null;
      }}

      function normalizePayloadMap(details) {{
        const mapped = {{}};
        for (const key in details) {{
          if (Object.prototype.hasOwnProperty.call(details, key)) {{
            mapped[String(key).trim().toLowerCase()] = details[key];
          }}
        }}
        return mapped;
      }}

      function firstText(details, keys) {{
        for (const key of keys) {{
          if (!(key in details)) {{
            continue;
          }}
          const value = String(details[key] ?? "").trim();
          if (value) {{
            return value;
          }}
        }}
        return "";
      }}

      function firstNumber(details, keys) {{
        for (const key of keys) {{
          if (!(key in details)) {{
            continue;
          }}
          const converted = toNumber(details[key]);
          if (converted !== null) {{
            return converted;
          }}
        }}
        return null;
      }}

      function parseScannedPayload(rawValue) {{
        const raw = String(rawValue || "").trim();
        const parsed = {{ barcode: "", name: "", price: null, stock: null }};
        if (!raw) {{
          return parsed;
        }}

        let details = null;
        try {{
          const jsonPayload = JSON.parse(raw);
          if (jsonPayload && typeof jsonPayload === "object" && !Array.isArray(jsonPayload)) {{
            details = normalizePayloadMap(jsonPayload);
          }}
        }} catch (_err) {{
          details = null;
        }}

        if (!details) {{
          const pairMap = {{}};
          const parts = raw.split(/[;\\n|&]+/);
          for (const block of parts) {{
            const chunk = block.trim();
            if (!chunk) {{
              continue;
            }}

            const separator = chunk.includes("=") ? "=" : (chunk.includes(":") ? ":" : "");
            if (!separator) {{
              continue;
            }}

            const index = chunk.indexOf(separator);
            const key = chunk.slice(0, index).trim().toLowerCase();
            const value = chunk.slice(index + 1).trim();
            if (key) {{
              pairMap[key] = value;
            }}
          }}

          if (Object.keys(pairMap).length > 0) {{
            details = pairMap;
          }}
        }}

        if (details) {{
          parsed.barcode = firstText(details, ["barcode", "bar_code", "code", "sku", "ean", "upc", "item_code", "id"]);
          parsed.name = firstText(details, ["name", "item", "product", "title"]);
          parsed.price = firstNumber(details, ["price", "mrp", "rate", "amount", "selling_price"]);
          parsed.stock = firstNumber(details, ["stock", "qty", "quantity"]);
          return parsed;
        }}

        for (const separator of [",", "|"]) {{
          const parts = raw.split(separator).map((item) => item.trim());
          if (parts.length === 3 || parts.length === 4) {{
            parsed.barcode = parts[0];
            parsed.name = parts[1];
            parsed.price = toNumber(parts[2]);
            if (parts.length === 4) {{
              parsed.stock = toNumber(parts[3]);
            }}
            return parsed;
          }}
        }}

        parsed.barcode = raw;
        return parsed;
      }}

      async function lookupProductByBarcode(barcode) {{
        if (!barcode) {{
          return null;
        }}

        const params = new URLSearchParams();
        params.set("barcode", barcode);

        try {{
          const response = await fetch("/lookup-product", {{
            method: "POST",
            headers: {{
              "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            }},
            body: params.toString(),
          }});

          const payload = await response.json();
          if (!payload || !payload.success || !payload.found || !payload.product) {{
            return null;
          }}
          return payload.product;
        }} catch (_err) {{
          return null;
        }}
      }}

      async function applyParsedData(rawValue, parsedData) {{
        const parsed = parsedData || parseScannedPayload(rawValue);
        const barcode = (parsed.barcode || String(rawValue || "")).trim();

        if (!barcode) {{
          setStatus("No barcode detected.");
          return;
        }}

        barcodeInput.value = barcode;

        let name = parsed.name || "";
        let price = parsed.price;
        let stock = parsed.stock;

        if (!name || price === null || stock === null) {{
          const existingProduct = await lookupProductByBarcode(barcode);
          if (existingProduct) {{
            if (!name && existingProduct.name) {{
              name = existingProduct.name;
            }}
            if (price === null && Number.isFinite(Number(existingProduct.price))) {{
              price = Number(existingProduct.price);
            }}
            if (stock === null && Number.isFinite(Number(existingProduct.stock))) {{
              stock = Number(existingProduct.stock);
            }}
          }}
        }}

        const detailParts = [];
        if (name) {{
          detailParts.push("name: " + name);
        }}
        if (price !== null) {{
          detailParts.push("price: " + price);
        }}
        if (stock !== null) {{
          detailParts.push("stock: " + Math.trunc(stock));
        }}

        const detailSuffix = detailParts.length ? " | " + detailParts.join(", ") : "";
        if (detailParts.length > 0) {{
          setStatus("Scanned: " + barcode + detailSuffix + ". Click Add To Cart.");
        }} else {{
          setStatus("Scanned barcode: " + barcode + ". Product details not found in POS DB.");
        }}
      }}

      function stopScanner(statusText) {{
        if (intervalId) {{
          clearInterval(intervalId);
          intervalId = null;
        }}

        if (stream) {{
          for (const track of stream.getTracks()) {{
            track.stop();
          }}
          stream = null;
        }}

        preview.style.display = "none";
        preview.srcObject = null;
        scanning = false;
        frameRequestInFlight = false;
        scanToggle.textContent = "Start Scanner";
        if (statusText) {{
          setStatus(statusText);
        }}
      }}

      async function createDetector() {{
        if (!("BarcodeDetector" in window)) {{
          throw new Error("BarcodeDetector is not supported on this browser.");
        }}

        const desired = [
          "qr_code",
          "ean_13",
          "ean_8",
          "upc_a",
          "upc_e",
          "code_128",
          "code_39",
          "codabar",
          "itf",
        ];

        let formats = [];
        if (typeof BarcodeDetector.getSupportedFormats === "function") {{
          const supported = await BarcodeDetector.getSupportedFormats();
          formats = desired.filter((format) => supported.includes(format));
        }}

        if (formats.length > 0) {{
          return new BarcodeDetector({{ formats }});
        }}

        return new BarcodeDetector();
      }}

      async function captureFrameBlob() {{
        if (!preview.videoWidth || !preview.videoHeight) {{
          return null;
        }}

        if (!scanCanvas) {{
          scanCanvas = document.createElement("canvas");
        }}

        scanCanvas.width = preview.videoWidth;
        scanCanvas.height = preview.videoHeight;
        const context = scanCanvas.getContext("2d");
        context.drawImage(preview, 0, 0, scanCanvas.width, scanCanvas.height);

        return await new Promise((resolve) => {{
          scanCanvas.toBlob((blob) => resolve(blob || null), "image/jpeg", 0.92);
        }});
      }}

      async function decodeLiveFrameOnServer() {{
        if (frameRequestInFlight) {{
          return null;
        }}
        frameRequestInFlight = true;

        try {{
          const frameBlob = await captureFrameBlob();
          if (!frameBlob) {{
            return null;
          }}

          const formData = new FormData();
          formData.append("image", frameBlob, "live-frame.jpg");

          const response = await fetch("/scan-image", {{
            method: "POST",
            body: formData,
          }});
          const payload = await response.json();
          if (payload && payload.success) {{
            return payload;
          }}
          return null;
        }} catch (_err) {{
          return null;
        }} finally {{
          frameRequestInFlight = false;
        }}
      }}

      async function startScanner() {{
        if (scanning) {{
          return;
        }}

        if (!window.isSecureContext) {{
          setStatus("Live camera requires HTTPS. Open the HTTPS bridge URL shown in POS terminal.");
          return;
        }}

        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
          setStatus("Live camera is blocked in this browser. Allow camera permission and reload.");
          return;
        }}

        try {{
          try {{
            detector = await createDetector();
          }} catch (_err) {{
            detector = null;
          }}

          stream = await navigator.mediaDevices.getUserMedia({{
            video: {{
              facingMode: {{ ideal: "environment" }},
            }},
            audio: false,
          }});

          preview.srcObject = stream;
          preview.style.display = "block";
          await preview.play();
          scanning = true;
          scanToggle.textContent = "Stop Scanner";
          if (detector) {{
            setStatus("Scanner running. Point camera to barcode/QR.");
          }} else {{
            setStatus("Scanner running with server decode. Point camera to barcode/QR.");
          }}

          intervalId = setInterval(async () => {{
            if (!scanning) {{
              return;
            }}

            try {{
              if (detector) {{
                const barcodes = await detector.detect(preview);
                if (barcodes && barcodes.length > 0) {{
                  const rawValue = (barcodes[0].rawValue || "").trim();
                  if (rawValue) {{
                    await applyParsedData(rawValue);
                    stopScanner("Scanned successfully.");
                    addToPhoneCartBtn.focus();
                    return;
                  }}
                }}
              }}
            }} catch (_err) {{
            }}

            const serverDecoded = await decodeLiveFrameOnServer();
            if (serverDecoded && serverDecoded.raw_value) {{
              await applyParsedData(serverDecoded.raw_value, serverDecoded.parsed || null);
              stopScanner("Scanned successfully.");
              addToPhoneCartBtn.focus();
            }}
          }}, 650);
        }} catch (err) {{
          stopScanner();
          setStatus("Scanner error: " + err.message);
        }}
      }}

      scanToggle.addEventListener("click", function () {{
        if (scanning) {{
          stopScanner("Scanner stopped.");
          return;
        }}
        startScanner();
      }});

      scanForm.addEventListener("submit", async function (event) {{
        event.preventDefault();
        addCurrentBarcodeToPhoneCart();
      }});

      addToPhoneCartBtn.addEventListener("click", function () {{
        addCurrentBarcodeToPhoneCart();
      }});

      scanQtyInput.addEventListener("keydown", function (event) {{
        if (event.key !== "Enter") {{
          return;
        }}
        event.preventDefault();
        addCurrentBarcodeToPhoneCart();
      }});

      phoneCartList.addEventListener("click", function (event) {{
        const updateId = event.target.getAttribute("data-update-id");
        if (updateId) {{
          const qtyInput = phoneCartList.querySelector('input[data-qty-id="' + updateId + '"]');
          const qty = asNonNegativeInt(qtyInput ? qtyInput.value : "");
          if (qty === null) {{
            setPhoneCartStatus("Quantity must be 0 or greater.");
            return;
          }}
          setPhoneCartQty(updateId, qty);
          return;
        }}

        const removeId = event.target.getAttribute("data-remove-id");
        if (removeId) {{
          removeFromPhoneCart(removeId);
        }}
      }});

      payCashBtn.addEventListener("click", function () {{
        setPhonePaymentMode("Cash");
      }});

      payOnlineBtn.addEventListener("click", function () {{
        setPhonePaymentMode("Online");
      }});

      phoneDiscountApplyBtn.addEventListener("click", function () {{
        setPhoneDiscount();
      }});

      phoneDiscountInput.addEventListener("keydown", function (event) {{
        if (event.key !== "Enter") {{
          return;
        }}
        event.preventDefault();
        setPhoneDiscount();
      }});

      phoneDiscountInput.addEventListener("blur", function () {{
        if (!String(phoneDiscountInput.value || "").trim()) {{
          phoneDiscountInput.value = "0";
        }}
      }});

      addManualBtn.addEventListener("click", function () {{
        addManualItem();
      }});
      phoneCartRefreshBtn.addEventListener("click", function () {{
        refreshPhoneCart("Phone cart refreshed.");
      }});

      phoneCartClearBtn.addEventListener("click", function () {{
        clearPhoneCart();
      }});

      phoneCartCompleteBtn.addEventListener("click", function () {{
        completePhoneSale();
      }});

      refreshPhoneCart();
    }})();
  </script>
</body>
</html>"""


class _PhoneBridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, _fmt, *_args):
        return

    def do_GET(self):
        if self.path == "/bridge-bg-image":
            image_path = _resolve_phone_bridge_background_image()
            if image_path is None:
                self.send_error(404)
                return

            try:
                data = image_path.read_bytes()
            except Exception:
                self.send_error(500)
                return

            self._send_bytes(data, _content_type_for_image(image_path), status_code=200)
            return

        if self.path == "/bridge-logo-image":
            image_path = _resolve_phone_bridge_logo_image()
            if image_path is None:
                self.send_error(404)
                return

            try:
                data = image_path.read_bytes()
            except Exception:
                self.send_error(500)
                return

            self._send_bytes(data, _content_type_for_image(image_path), status_code=200)
            return

        self._send_html(_render_page("Connected."))

    def do_POST(self):
        if self.path == "/scan-image":
            self._handle_scan_image()
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length).decode("utf-8")
        form = parse_qs(body)

        if self.path == "/lookup-product":
            result, status_code = _lookup_product_form(form)
            self._send_json(result, status_code=status_code)
            return

        if self.path == "/phone-cart-state":
            self._send_json(_phone_cart_success())
            return

        if self.path == "/phone-cart-add":
            result, status_code = _process_phone_cart_add_form(form)
            self._send_json(result, status_code=status_code)
            return

        if self.path == "/phone-cart-add-manual":
            result, status_code = _process_phone_cart_add_manual_form(form)
            self._send_json(result, status_code=status_code)
            return

        if self.path == "/phone-cart-set-qty":
            result, status_code = _process_phone_cart_set_qty_form(form)
            self._send_json(result, status_code=status_code)
            return

        if self.path == "/phone-cart-remove":
            result, status_code = _process_phone_cart_remove_form(form)
            self._send_json(result, status_code=status_code)
            return

        if self.path == "/phone-cart-clear":
            result, status_code = _process_phone_cart_clear()
            self._send_json(result, status_code=status_code)
            return

        if self.path == "/phone-cart-payment":
            result, status_code = _process_phone_cart_payment_mode(form)
            self._send_json(result, status_code=status_code)
            return

        if self.path == "/phone-cart-discount":
            result, status_code = _process_phone_cart_discount_form(form)
            self._send_json(result, status_code=status_code)
            return

        if self.path == "/phone-cart-complete":
            result, status_code = _process_phone_cart_complete()
            self._send_json(result, status_code=status_code)
            return

        self._send_html(_render_page("Unknown endpoint."))

    def _handle_scan_image(self):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send_json({"success": False, "message": "Expected multipart/form-data upload."}, status_code=400)
            return

        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": content_type,
                    "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
                },
            )
        except Exception as exc:
            self._send_json({"success": False, "message": f"Upload parse failed: {exc}"}, status_code=400)
            return

        if "image" not in form:
            self._send_json({"success": False, "message": "Image file is required."}, status_code=400)
            return

        file_item = form["image"]
        file_obj = getattr(file_item, "file", None)
        if file_obj is None:
            self._send_json({"success": False, "message": "Invalid upload payload."}, status_code=400)
            return

        image_data = file_obj.read()
        try:
            raw_value = _decode_barcode_from_image(image_data)
        except RuntimeError as exc:
            self._send_json({"success": False, "message": str(exc)}, status_code=500)
            return

        if not raw_value:
            self._send_json({"success": False, "message": "No barcode/QR detected in image."}, status_code=200)
            return

        parsed = _parse_scanned_payload(raw_value)
        self._send_json({"success": True, "raw_value": raw_value, "parsed": parsed}, status_code=200)

    def _send_html(self, payload):
        data = payload.encode("utf-8")
        self._send_bytes(data, "text/html; charset=utf-8", status_code=200)

    def _send_bytes(self, data, content_type, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload, status_code=200):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_phone_bridge(host="0.0.0.0", port=8765, prefer_https=True):
    global _server, _thread, _bridge_scheme

    if _server is not None:
        bound_port = _server.server_address[1]
        return {
            "success": True,
            "url": f"{_bridge_scheme}://{_local_ip()}:{bound_port}",
            "message": "Phone bridge already running.",
        }

    candidate_ports = [port] + list(range(port + 1, port + 20))
    last_error = None
    ip = _local_ip()

    cert_path = None
    key_path = None
    tls_warning = None

    if prefer_https:
        cert_path, key_path, tls_warning = _ensure_tls_certificates(ip)

    for candidate_port in candidate_ports:
        try:
            server = ThreadingHTTPServer((host, candidate_port), _PhoneBridgeHandler)

            scheme = "http"
            if prefer_https and cert_path and key_path:
                try:
                    _wrap_server_tls(server, cert_path, key_path)
                    scheme = "https"
                except Exception as exc:
                    tls_warning = f"TLS setup failed: {exc}"

            _server = server
            _bridge_scheme = scheme
            _thread = Thread(target=_server.serve_forever, daemon=True)
            _thread.start()

            bound_port = _server.server_address[1]
            bridge_url = f"{scheme}://{ip}:{bound_port}"

            message_bits = []
            if scheme == "https":
                message_bits.append("Phone bridge started in HTTPS mode.")
            else:
                message_bits.append("Phone bridge started in HTTP mode.")

            if tls_warning:
                message_bits.append(f"HTTPS unavailable: {tls_warning}")

            if bound_port == port:
                return {"success": True, "url": bridge_url, "message": " ".join(message_bits)}

            return {
                "success": True,
                "url": bridge_url,
                "message": " ".join(
                    message_bits + [f"Using alternate port {bound_port} because default port {port} was busy."]
                ),
            }
        except OSError as exc:
            last_error = exc
            if getattr(exc, "errno", None) == 98:
                continue
            return {"success": False, "url": None, "message": f"Phone bridge failed to start: {exc}"}

    return {
        "success": False,
        "url": None,
        "message": f"Phone bridge failed to start: all ports from {candidate_ports[0]} to {candidate_ports[-1]} are busy. Last error: {last_error}",
    }


def pop_scanned_barcode():
    try:
        return _barcode_queue.get_nowait()
    except Empty:
        return None
