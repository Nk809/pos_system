import tkinter as tk
from tkinter import messagebox
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


def open_phonepe_payment_window(parent, amount, on_received=None):
    payable_amount = round(float(amount), 2)
    upi_uri = _build_upi_uri(payable_amount)

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

    config_state = "Configured" if _upi_is_configured() else "Not configured (update UPI_ID in config.py)"
    config_color = "#1b8f3a" if _upi_is_configured() else "#b45309"
    tk.Label(win, text=f"UPI ID: {UPI_ID}", fg=config_color, font=("Arial", 10)).pack(pady=(0, 2))
    tk.Label(win, text=config_state, fg=config_color, font=("Arial", 10, "bold")).pack(pady=(0, 8))

    qr_holder = tk.Frame(win, bd=1, relief=tk.GROOVE)
    qr_holder.pack(padx=14, pady=(4, 8), fill=tk.BOTH, expand=True)

    qr_message = "Scan QR using PhonePe to pay."
    qr_photo = None
    try:
        import qrcode
        from PIL import Image, ImageTk

        qr_img = qrcode.make(upi_uri).resize((290, 290), Image.NEAREST)
        qr_photo = ImageTk.PhotoImage(qr_img)
        qr_label = tk.Label(qr_holder, image=qr_photo)
        qr_label.image = qr_photo
        qr_label.pack(pady=(10, 6))
    except Exception:
        qr_message = "QR preview unavailable. Install: pip install qrcode pillow"

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
