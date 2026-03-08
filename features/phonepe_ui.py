import tkinter as tk
import sys
from tkinter import messagebox
from pathlib import Path
from urllib.parse import quote

from config import UPI_ID, UPI_PAYEE_NAME


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


def get_upi_payment_details(amount):
    payable_amount = round(float(amount), 2)
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


def _load_qr_backends():
    try:
        import qrcode
        from PIL import Image

        return qrcode, Image, None
    except Exception as first_exc:
        project_root = Path(__file__).resolve().parent.parent
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        candidate_sites = [
            project_root / ".venv" / "lib" / f"python{py_ver}" / "site-packages",
            project_root / ".venv" / "Lib" / "site-packages",
        ]
        for venv_site in candidate_sites:
            if not venv_site.is_dir():
                continue
            venv_site_text = str(venv_site)
            if venv_site_text not in sys.path:
                sys.path.append(venv_site_text)
            try:
                import qrcode
                from PIL import Image

                return qrcode, Image, None
            except Exception:
                continue
        return None, None, first_exc


def build_upi_qr_image(amount, size=290):
    details = get_upi_payment_details(amount)
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
        qr_img = qrcode.make(details["upi_uri"]).resize((int(size), int(size)), Image.NEAREST)
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
        from PIL import ImageTk

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
