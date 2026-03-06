import tkinter as tk
from tkinter import messagebox
import sqlite3
from services.product_service import add_product


def open_product_window():
    win = tk.Toplevel()
    win.title("Add Product")

    tk.Label(win, text="Barcode").pack()
    barcode = tk.Entry(win)
    barcode.pack()

    def scan_barcode():
        try:
            from features.barcode_camera import scan_barcode as scan_barcode_from_camera

            scanned_value = scan_barcode_from_camera()
        except Exception as exc:
            messagebox.showerror("Scanner Error", str(exc))
            return

        if not scanned_value:
            messagebox.showinfo("Scanner", "No barcode captured.")
            return

        barcode.delete(0, tk.END)
        barcode.insert(0, scanned_value)
        messagebox.showinfo("Scanner", f"Barcode captured: {scanned_value}")

    tk.Button(win, text="Scan Barcode", command=scan_barcode).pack(pady=(4, 6))

    tk.Label(win, text="Name").pack()
    name = tk.Entry(win)
    name.pack()

    tk.Label(win, text="Price").pack()
    price = tk.Entry(win)
    price.pack()

    tk.Label(win, text="Stock").pack()
    stock = tk.Entry(win)
    stock.pack()

    def focus_next_field(current_widget, next_widget):
        def on_enter(event):
            next_widget.focus_set()
            return "break"

        current_widget.bind("<Return>", on_enter)

    def save():
        bc = barcode.get().strip()
        nm = name.get().strip()
        try:
            pr = float(price.get().strip())
        except Exception:
            messagebox.showerror("Invalid Input", "Price must be a number.")
            return
        try:
            st = int(stock.get().strip())
        except Exception:
            messagebox.showerror("Invalid Input", "Stock must be a whole number.")
            return

        try:
            add_product(bc, nm, pr, st)
        except sqlite3.IntegrityError:
            # barcode exists – offer to adjust stock
            answer = messagebox.askyesno(
                "Barcode Exists",
                "Product with this barcode already exists.\n" \
                "Do you want to modify its stock by the entered amount?",
            )
            if answer:
                try:
                    from services.product_service import change_stock
                    new_stock = change_stock(bc, st)
                    messagebox.showinfo("Stock Updated", f"New stock level: {new_stock}")
                except Exception as exc:
                    messagebox.showerror("Update Failed", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Save Failed", str(exc))
            return

        # clear fields after successful add
        barcode.delete(0, tk.END)
        name.delete(0, tk.END)
        price.delete(0, tk.END)
        stock.delete(0, tk.END)
        barcode.focus_set()

    tk.Button(win, text="Save", command=save).pack(pady=8)

    focus_next_field(barcode, name)
    focus_next_field(name, price)
    focus_next_field(price, stock)

    def save_on_enter(_event):
        save()
        return "break"

    stock.bind("<Return>", save_on_enter)
    barcode.focus_set()
