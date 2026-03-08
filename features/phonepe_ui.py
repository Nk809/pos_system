import tkinter as tk
import sys
import math
import importlib
from tkinter import messagebox
from pathlib import Path
from urllib.parse import quote

from config import UPI_ID, UPI_PAYEE_NAME

try:
    import qrcode as _QRCODE_MODULE
except Exception as _qr_import_exc:
    _QRCODE_MODULE = None
    _QR_IMPORT_ERROR = _qr_import_exc
else:
    _QR_IMPORT_ERROR = None

try:
    from PIL import Image as _PIL_IMAGE
    from PIL import ImageTk as _PIL_IMAGETK
except Exception as _pil_import_exc:
    _PIL_IMAGE = None
    _PIL_IMAGETK = None
    _PIL_IMPORT_ERROR = _pil_import_exc
else:
    _PIL_IMPORT_ERROR = None


def _project_venv_site_dirs():
    project_root = Path(__file__).resolve().parent.parent
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    return [
        project_root / ".venv" / "lib" / f"python{py_ver}" / "site-packages",
        project_root / ".venv" / "Lib" / "site-packages",
    ]


def _clear_loaded_packages(package_roots):
    cleared_modules = {}
    for module_name in list(sys.modules):
        if any(module_name == root or module_name.startswith(f"{root}.") for root in package_roots):
            cleared_modules[module_name] = sys.modules.pop(module_name)
    return cleared_modules


def _restore_loaded_packages(cleared_modules):
    for module_name, module_obj in cleared_modules.items():
        if module_name not in sys.modules:
            sys.modules[module_name] = module_obj


def _import_runtime_module(module_name, package_roots):
    last_exc = None

    for venv_site in _project_venv_site_dirs():
        if not venv_site.is_dir():
            continue

        venv_site_text = str(venv_site)
        if venv_site_text in sys.path:
            sys.path.remove(venv_site_text)
        sys.path.insert(0, venv_site_text)

        cleared_modules = _clear_loaded_packages(package_roots)
        try:
            importlib.invalidate_caches()
            return importlib.import_module(module_name), None
        except Exception as exc:
            last_exc = exc
            _clear_loaded_packages(package_roots)
            _restore_loaded_packages(cleared_modules)
            try:
                sys.path.remove(venv_site_text)
            except ValueError:
                pass

    return None, last_exc


def _build_upi_uri(amount):
    note = "POS Bill Payment"
    return (
        "upi://pay?"
        f"pa={quote(UPI_ID)}&"
        f"pn={quote(UPI_PAYEE_NAME)}&"
        f"am={quote(f'{float(amount):.2f}')}&"
        "cu=INR&"
        f"tn={quote(note)}"
    )


def _upi_is_configured():
    raw = str(UPI_ID or "").strip().lower()
    return bool(raw) and "your-upi-id" not in raw and "example" not in raw


def _normalize_amount(amount):
    try:
        numeric_amount = float(amount)
    except (TypeError, ValueError):
        raise ValueError("Amount must be a valid number.")

    if not math.isfinite(numeric_amount):
        raise ValueError("Amount must be a finite number.")
    if numeric_amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    return round(numeric_amount, 2)


def get_upi_payment_details(amount):
    payable_amount = _normalize_amount(amount)
    upi_uri = _build_upi_uri(payable_amount)
    configured = _upi_is_configured()
    message = "Scan QR using PhonePe to pay."
    if not configured:
        message = "UPI QR is unavailable until UPI_ID is configured in config.py."

    return {
        "amount": payable_amount,
        "configured": configured,
        "upi_id": str(UPI_ID or "").strip(),
        "upi_uri": upi_uri,
        "message": message,
    }


def _load_pil_image_backend():
    if _PIL_IMAGE is not None:
        return _PIL_IMAGE, None

    first_exc = _PIL_IMPORT_ERROR
    if first_exc is None:
        first_exc = ImportError("Pillow Image backend is unavailable")

    image_module, import_error = _import_runtime_module("PIL.Image", ("PIL",))
    if image_module is not None:
        globals()["_PIL_IMAGE"] = image_module
        globals()["_PIL_IMPORT_ERROR"] = None
        return image_module, None

    return None, import_error or first_exc


def _load_qr_backends():
    qrcode_module = _QRCODE_MODULE
    qr_error = _QR_IMPORT_ERROR
    if qrcode_module is None:
        qrcode_module, qr_error = _import_runtime_module("qrcode", ("qrcode",))
        if qrcode_module is not None:
            globals()["_QRCODE_MODULE"] = qrcode_module
            globals()["_QR_IMPORT_ERROR"] = None

    image_module, pil_error = _load_pil_image_backend()
    if qrcode_module is not None and image_module is not None:
        return qrcode_module, image_module, None

    first_exc = qr_error or pil_error or _QR_IMPORT_ERROR or _PIL_IMPORT_ERROR
    if first_exc is None:
        first_exc = ImportError("qrcode or Pillow is unavailable")
    return None, None, first_exc


def _load_image_tk_backend():
    if _PIL_IMAGETK is not None:
        return _PIL_IMAGETK, None

    first_exc = _PIL_IMPORT_ERROR
    if first_exc is None:
        first_exc = ImportError("Pillow ImageTk backend is unavailable")

    imagetk_module, import_error = _import_runtime_module("PIL.ImageTk", ("PIL",))
    if imagetk_module is not None:
        globals()["_PIL_IMAGETK"] = imagetk_module
        globals()["_PIL_IMPORT_ERROR"] = None
        pil_image_module = sys.modules.get("PIL.Image")
        if pil_image_module is not None:
            globals()["_PIL_IMAGE"] = pil_image_module
        return imagetk_module, None

    return None, import_error or first_exc


def build_upi_qr_image(amount, size=290):
    try:
        details = get_upi_payment_details(amount)
    except ValueError as exc:
        return {
            "amount": amount,
            "configured": _upi_is_configured(),
            "upi_id": str(UPI_ID or "").strip(),
            "upi_uri": "",
            "message": str(exc),
            "success": False,
            "image": None,
        }

    if not details["configured"]:
        return {**details, "success": False, "image": None}

    qrcode, Image, import_error = _load_qr_backends()
    if qrcode is None or Image is None:
        return {
            **details,
            "success": False,
            "image": None,
            "message": f"QR preview unavailable. Install qrcode and pillow. Details: {import_error}",
        }

    try:
        qr_size = max(int(size), 120)
        qr_builder = qrcode.QRCode(
            version=None,
            error_correction=getattr(qrcode.constants, "ERROR_CORRECT_M", 0),
            box_size=12,
            border=4,
        )
        qr_builder.add_data(details["upi_uri"])
        qr_builder.make(fit=True)
        qr_img = qr_builder.make_image(fill_color="black", back_color="white").convert("RGB")
        qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)
        return {**details, "success": True, "image": qr_img}
    except Exception as exc:
        return {
            **details,
            "success": False,
            "image": None,
            "message": f"QR generation failed. Details: {exc}",
        }


def open_phonepe_payment_window(parent, amount, on_received=None):
    payment_details = get_upi_payment_details(amount)
    payable_amount = payment_details["amount"]
    upi_uri = payment_details["upi_uri"]

    win = tk.Toplevel(parent)
    win.title("Receive Payment - PhonePe / UPI")
    win.geometry("430x520")
    win.resizable(False, False)

    tk.Label(win, text="Collect Payment", font=("Arial", 14, "bold")).pack(pady=(10, 6))
    tk.Label(win, text="PhonePe / Any UPI App", font=("Arial", 11)).pack(pady=(0, 10))

    amount_box = tk.Frame(win)
    amount_box.pack(fill=tk.X, padx=14)
    tk.Label(amount_box, text="Payable Amount", font=("Arial", 11)).pack(anchor="w")
    amount_text = tk.Entry(amount_box, font=("Arial", 12, "bold"))
    amount_text.pack(fill=tk.X, pady=(4, 8))
    amount_text.insert(0, f"{payable_amount:.2f}")
    amount_text.config(state="readonly")

    config_state = "Configured" if payment_details["configured"] else "Not configured (update UPI_ID in config.py)"
    config_color = "#1b8f3a" if payment_details["configured"] else "#b45309"
    tk.Label(win, text=f"UPI ID: {UPI_ID}", fg=config_color, font=("Arial", 10)).pack(pady=(0, 2))
    tk.Label(win, text=config_state, fg=config_color, font=("Arial", 10, "bold")).pack(pady=(0, 8))

    qr_holder = tk.Frame(win, bd=1, relief=tk.GROOVE)
    qr_holder.pack(padx=14, pady=(4, 8), fill=tk.BOTH, expand=True)

    qr_message = payment_details["message"]
    qr_photo = None
    qr_result = build_upi_qr_image(payable_amount, size=290)
    if qr_result.get("success"):
        ImageTk, imagetk_error = _load_image_tk_backend()
        if ImageTk is None:
            qr_message = f"QR preview unavailable. Install pillow. Details: {imagetk_error}"
        else:
            qr_img = qr_result["image"]
            qr_photo = ImageTk.PhotoImage(qr_img)
            qr_label = tk.Label(qr_holder, image=qr_photo)
            qr_label.image = qr_photo
            qr_label.pack(pady=(10, 6))
    else:
        qr_message = qr_result.get("message", qr_message)

    tk.Label(qr_holder, text=qr_message, font=("Arial", 10)).pack(pady=(0, 8))

    action_row = tk.Frame(win)
    action_row.pack(fill=tk.X, padx=14, pady=(0, 8))

    def copy_upi_link():
        win.clipboard_clear()
        win.clipboard_append(upi_uri)
        messagebox.showinfo("Copied", "UPI payment link copied.")

    def mark_received():
        if callable(on_received):
            on_received(payable_amount)
        messagebox.showinfo("Payment", "Payment marked as received (Online).")
        win.destroy()

    tk.Button(action_row, text="Copy UPI Link", command=copy_upi_link).pack(side=tk.LEFT)
    tk.Button(action_row, text="Mark As Received", command=mark_received, bg="#1b8f3a", fg="white").pack(side=tk.RIGHT)

    uri_box = tk.Text(win, height=4, wrap="word")
    uri_box.pack(fill=tk.X, padx=14, pady=(0, 10))
    uri_box.insert("1.0", upi_uri)
    uri_box.config(state="disabled")

    if qr_photo is not None:
        win._qr_photo = qr_photo
