import io
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, simpledialog
from pathlib import Path
from tkinter import messagebox
from config import APP_BACKGROUND_IMAGE, APP_LOGO_IMAGE, BASE_DIR
from services.billing_service import (
    clear_recent_receipts,
    get_daily_sales_summary,
    get_recent_receipts,
    get_today_sales_summary,
    save_sale,
)
from services.product_service import delete_product, search_product
from features.phonepe_ui import open_phonepe_payment_window
from features.thermal_printer import print_bill
from features.phone_bridge import pop_scanned_barcode
from features.stock_alert import low_stock
from ui.product_ui import open_product_window
from ui.reports_ui import reports_window


class BillingUI:
    def __init__(self, root):
        self.root = root
        self.root.configure(bg="#f5f5f5")

        main = tk.Frame(root, bg="#f5f5f5")
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.main_container = main

        self._watermark_canvas = tk.Canvas(main, bg="#f5f5f5", highlightthickness=0, bd=0)
        self._watermark_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._lower_watermark_widget()
        self.cart = []
        self.search_results = []
        self.payment_mode = tk.StringVar(value="Cash")
        self.total_var = tk.StringVar(value="Total: 0.00")
        self.status_var = tk.StringVar(value="Ready")
        self.today_sales_var = tk.StringVar(value="Today Sales: 0 bill(s) | Total: 0.00 | Online: 0.00 | Cash: 0.00")
        self.sales_updated_var = tk.StringVar(value="Updated: --")
        self._background_image_path = self._resolve_background_image_path()
        self._background_photo = None
        self._logo_image_path = self._resolve_logo_image_path()
        self._header_logo_photo = None
        self.root.bind("<Configure>", self._render_watermark_background)
        self.root.after(80, self._render_watermark_background)
        self.font_base = ("Arial", 11)
        self.font_heading = ("Arial", 12, "bold")
        self.font_big = ("Arial", 13, "bold")
        self.font_small = ("Arial", 10)

        header_row = tk.Frame(main, bg="#ffffff", bd=1, relief=tk.GROOVE)
        header_row.pack(fill=tk.X, pady=(0, 6))
        header_inner = tk.Frame(header_row, bg="#ffffff")
        header_inner.pack(pady=6)
        self.header_logo_label = tk.Label(
            header_inner,
            text="MG",
            font=("Arial", 12, "bold"),
            bg="#f2f4f7",
            fg="#1f2937",
            width=4,
            bd=2,
            relief=tk.GROOVE,
            padx=8,
            pady=4,
        )
        self.header_logo_label.pack(side=tk.LEFT, padx=(0, 8))
        self._apply_header_logo_image()
        tk.Label(
            header_inner,
            text="Matchless Gift Shop",
            font=("Arial", 16, "bold"),
            bg="#ffffff",
            fg="#1f2937",
        ).pack(side=tk.LEFT)

        nav_row = tk.Frame(main, bg="#ffffff", bd=1, relief=tk.GROOVE)
        nav_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(nav_row, text="Navigation", font=self.font_heading, bg="#ffffff").pack(side=tk.LEFT, padx=(10, 8))
        tk.Button(nav_row, text="Sales", font=self.font_base, command=self.open_sales_records_window).pack(
            side=tk.LEFT, padx=4, pady=6
        )
        tk.Button(nav_row, text="Add Product", font=self.font_base, command=open_product_window).pack(
            side=tk.LEFT, padx=4, pady=6
        )
        tk.Button(nav_row, text="Reports", font=self.font_base, command=reports_window).pack(side=tk.LEFT, padx=4, pady=6)
        tk.Button(nav_row, text="Low Stock", font=self.font_base, command=self.show_low_stock).pack(
            side=tk.LEFT, padx=4, pady=6
        )
        tk.Label(nav_row, textvariable=self.today_sales_var, fg="#0a7b24", bg="#ffffff", font=self.font_base).pack(
            side=tk.RIGHT, padx=(8, 12)
        )

        receipts_card = tk.LabelFrame(
            main,
            text="Recent Payment Receipts",
            font=self.font_heading,
            bg="#ffffff",
            bd=1,
            relief=tk.GROOVE,
            labelanchor="nw",
        )
        receipts_card.pack(fill=tk.X, pady=(0, 10))

        receipts_action_row = tk.Frame(receipts_card, bg="#ffffff")
        receipts_action_row.pack(fill=tk.X, padx=8, pady=(6, 4))
        tk.Button(
            receipts_action_row, text="Refresh Receipts", font=self.font_base, command=self.refresh_receipts_box
        ).pack(side=tk.RIGHT, padx=(0, 6))
        tk.Button(
            receipts_action_row, text="Clean Receipts", font=self.font_base, command=self.clear_recent_receipts_box
        ).pack(side=tk.RIGHT, padx=(0, 10))
        tk.Label(
            receipts_action_row, textvariable=self.sales_updated_var, fg="gray", bg="#ffffff", font=self.font_small
        ).pack(side=tk.RIGHT, padx=(0, 8))

        receipts_list_row = tk.Frame(receipts_card, bg="#ffffff")
        receipts_list_row.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.receipts_listbox = tk.Listbox(receipts_list_row, height=4, font=self.font_base)
        self.receipts_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        receipts_scroll = tk.Scrollbar(receipts_list_row, orient=tk.VERTICAL, command=self.receipts_listbox.yview)
        receipts_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.receipts_listbox.config(yscrollcommand=receipts_scroll.set)

        body_row = tk.Frame(main, bg="#f5f5f5")
        body_row.pack(fill=tk.BOTH, expand=True)
        body_row.grid_columnconfigure(0, weight=5)
        body_row.grid_columnconfigure(1, weight=4)
        body_row.grid_rowconfigure(0, weight=1)

        product_panel = tk.LabelFrame(
            body_row,
            text="Product Search And Scan",
            font=self.font_heading,
            bg="#ffffff",
            bd=1,
            relief=tk.GROOVE,
            labelanchor="nw",
            padx=10,
            pady=8,
        )
        product_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        product_panel.grid_columnconfigure(1, weight=1)
        product_panel.grid_rowconfigure(4, weight=1)

        tk.Label(
            product_panel, text="Scan Barcode (USB scanner or type + Enter)", font=self.font_base, bg="#ffffff"
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(2, 4))
        self.barcode_entry = tk.Entry(product_panel, font=self.font_base)
        self.barcode_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.barcode_entry.bind("<Return>", self.handle_scanned_barcode)
        self.barcode_entry.focus_set()

        tk.Label(product_panel, text="Search Product", font=self.font_base, bg="#ffffff").grid(
            row=2, column=0, sticky="w", pady=(0, 4)
        )
        search_box_row = tk.Frame(product_panel, bg="#ffffff")
        search_box_row.grid(row=2, column=1, sticky="ew", pady=(0, 4))
        search_box_row.grid_columnconfigure(0, weight=1)
        self.search_entry = tk.Entry(search_box_row, font=self.font_base)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        tk.Button(search_box_row, text="Search", font=self.font_base, command=self.search_products).grid(
            row=0, column=1, sticky="e"
        )

        quantity_row = tk.Frame(product_panel, bg="#ffffff")
        quantity_row.grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 6))
        tk.Label(quantity_row, text="Quantity", font=self.font_base, bg="#ffffff").pack(side=tk.LEFT, padx=(0, 6))
        self.quantity_entry = tk.Entry(quantity_row, width=6, font=self.font_base)
        self.quantity_entry.insert(0, "1")
        self.quantity_entry.pack(side=tk.LEFT)
        tk.Button(quantity_row, text="Add To Cart", font=self.font_base, command=self.add_to_cart).pack(
            side=tk.LEFT, padx=10
        )

        product_list_row = tk.Frame(product_panel, bg="#ffffff")
        product_list_row.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(2, 8))
        product_list_row.grid_columnconfigure(0, weight=1)
        product_list_row.grid_rowconfigure(0, weight=1)
        self.results_listbox = tk.Listbox(product_list_row, font=self.font_base)
        self.results_listbox.grid(row=0, column=0, sticky="nsew")
        self.results_listbox.bind("<Delete>", self.delete_selected_product_from_inventory)
        results_scroll = tk.Scrollbar(product_list_row, orient=tk.VERTICAL, command=self.results_listbox.yview)
        results_scroll.grid(row=0, column=1, sticky="ns")
        self.results_listbox.config(yscrollcommand=results_scroll.set)

        cart_panel = tk.LabelFrame(
            body_row,
            text="Current Cart And Checkout",
            font=self.font_heading,
            bg="#ffffff",
            bd=1,
            relief=tk.GROOVE,
            labelanchor="nw",
            padx=10,
            pady=8,
        )
        cart_panel.grid(row=0, column=1, sticky="nsew")
        cart_panel.grid_columnconfigure(0, weight=1)
        cart_panel.grid_rowconfigure(0, weight=1)

        cart_list_row = tk.Frame(cart_panel, bg="#ffffff")
        cart_list_row.grid(row=0, column=0, sticky="nsew")
        cart_list_row.grid_columnconfigure(0, weight=1)
        cart_list_row.grid_rowconfigure(0, weight=1)
        self.cart_listbox = tk.Listbox(cart_list_row, font=self.font_base)
        self.cart_listbox.grid(row=0, column=0, sticky="nsew")
        self.cart_listbox.bind("<Delete>", self.remove_selected_cart_item)
        cart_scroll = tk.Scrollbar(cart_list_row, orient=tk.VERTICAL, command=self.cart_listbox.yview)
        cart_scroll.grid(row=0, column=1, sticky="ns")
        self.cart_listbox.config(yscrollcommand=cart_scroll.set)

        cart_action_row = tk.Frame(cart_panel, bg="#ffffff")
        cart_action_row.grid(row=1, column=0, sticky="ew", pady=(8, 6))
        tk.Button(
            cart_action_row, text="Remove Selected Item", font=self.font_base, command=self.remove_selected_cart_item
        ).pack(side=tk.LEFT)
        tk.Button(
            cart_action_row, text="Add Manual Item", font=self.font_base, command=self.add_manual_item
        ).pack(side=tk.LEFT, padx=(10,0))

        tk.Label(cart_panel, textvariable=self.total_var, font=self.font_big, bg="#ffffff").grid(
            row=2, column=0, sticky="w", pady=(0, 6)
        )

        discount_row = tk.Frame(cart_panel, bg="#ffffff")
        discount_row.grid(row=3, column=0, sticky="w", pady=(0, 6))
        tk.Label(discount_row, text="Discount %", font=self.font_base, bg="#ffffff").pack(side=tk.LEFT, padx=(0, 8))
        self.discount_entry = tk.Entry(discount_row, width=8, font=self.font_base)
        self.discount_entry.pack(side=tk.LEFT)
        self.discount_entry.insert(0, "0")
        self.discount_entry.bind("<KeyRelease>", lambda _event: self.refresh_cart())
        self.discount_entry.bind("<FocusOut>", lambda _event: self.refresh_cart())

        payment_row = tk.Frame(cart_panel, bg="#ffffff")
        payment_row.grid(row=4, column=0, sticky="w", pady=(2, 6))
        tk.Label(payment_row, text="Payment Mode", font=self.font_base, bg="#ffffff").pack(side=tk.LEFT, padx=(0, 8))
        self.online_button = tk.Button(
            payment_row, text="Online", width=10, font=self.font_base, command=lambda: self.set_payment_mode("Online")
        )
        self.online_button.pack(side=tk.LEFT, padx=4)
        self.cash_button = tk.Button(
            payment_row, text="Cash", width=10, font=self.font_base, command=lambda: self.set_payment_mode("Cash")
        )
        self.cash_button.pack(side=tk.LEFT, padx=4)
        self._default_payment_button_bg = self.cash_button.cget("bg")

        # QR code display for online payments (must exist before setting mode)
        self.qr_holder = tk.Frame(cart_panel, bg="#ffffff")
        self.qr_holder.grid(row=5, column=0, sticky="ew", pady=(4,6))
        self.qr_label = tk.Label(self.qr_holder, bg="#ffffff")
        self.qr_label.pack()
        self.qr_hint = tk.Label(self.qr_holder, font=self.font_small, bg="#ffffff")
        self.qr_hint.pack()

        self.set_payment_mode("Cash")

        tk.Button(cart_panel, text="Complete Sale", font=self.font_heading, command=self.complete_sale).grid(
            row=6, column=0, sticky="ew", pady=(4, 6)
        )
        tk.Button(
            cart_panel, text="Receive In PhonePe", font=self.font_base, command=self.open_phonepe_collection
        ).grid(row=7, column=0, sticky="ew", pady=(0, 6))
        tk.Label(cart_panel, textvariable=self.status_var, font=self.font_base, bg="#ffffff", anchor="w").grid(
            row=8, column=0, sticky="ew", pady=(2, 0)
        )

        self.refresh_cart()
        self.refresh_receipts_box()
        self.root.after(500, self.poll_phone_scans)

    def _render_watermark_background(self, _event=None):
        width = max(self.main_container.winfo_width(), 900)
        height = max(self.main_container.winfo_height(), 700)
        self._watermark_canvas.place(x=0, y=0, width=width, height=height)
        self._watermark_canvas.delete("all")

        if self._draw_background_image(width, height):
            self._lower_watermark_widget()
            return

        # Keep a plain background when no image is configured.
        self._lower_watermark_widget()

    def _lower_watermark_widget(self):
        self.root.tk.call("lower", self._watermark_canvas._w)

    def _resolve_background_image_path(self):
        raw_path = str(APP_BACKGROUND_IMAGE or "").strip()
        if not raw_path:
            return None

        image_path = Path(raw_path)
        if not image_path.is_absolute():
            image_path = BASE_DIR / image_path
        return image_path

    def _resolve_logo_image_path(self):
        raw_path = str(APP_LOGO_IMAGE or "").strip()
        if not raw_path:
            return None

        image_path = Path(raw_path)
        if not image_path.is_absolute():
            image_path = BASE_DIR / image_path
        return image_path

    def _apply_header_logo_image(self):
        if not self._logo_image_path or not self._logo_image_path.exists():
            return False

        try:
            from PIL import Image, ImageTk
            logo_size = 62

            logo_path = str(self._logo_image_path)
            logo_ext = self._logo_image_path.suffix.lower()

            if logo_ext == ".svg":
                import cairosvg

                png_bytes = cairosvg.svg2png(url=logo_path, output_width=logo_size, output_height=logo_size)
                image_obj = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
            else:
                image_obj = Image.open(logo_path).convert("RGBA").resize((logo_size, logo_size), Image.LANCZOS)

            self._header_logo_photo = ImageTk.PhotoImage(image_obj)
            self.header_logo_label.config(
                image=self._header_logo_photo,
                text="",
                width=logo_size,
                height=logo_size,
                bg="#ffffff",
                padx=2,
                pady=2,
            )
            return True
        except Exception:
            return False

    def _draw_background_image(self, width, height):
        if not self._background_image_path:
            return False
        if not self._background_image_path.exists():
            return False

        try:
            from PIL import Image, ImageTk

            resized = Image.open(self._background_image_path).convert("RGB").resize((width, height), Image.LANCZOS)
            self._background_photo = ImageTk.PhotoImage(resized)
            self._watermark_canvas.create_image(0, 0, image=self._background_photo, anchor="nw", tags="bg")
            return True
        except Exception:
            return False

    def set_payment_mode(self, mode):
        selected_mode = "Online" if str(mode).strip().lower() == "online" else "Cash"
        self.payment_mode.set(selected_mode)

        if selected_mode == "Online":
            self.online_button.config(relief=tk.SUNKEN, bg="#bfe3ff")
            self.cash_button.config(relief=tk.RAISED, bg=self._default_payment_button_bg)
        else:
            self.cash_button.config(relief=tk.SUNKEN, bg="#c8f7c5")
            self.online_button.config(relief=tk.RAISED, bg=self._default_payment_button_bg)

        # ensure QR updates when mode changes
        self.refresh_cart()

    def _get_discount_percent(self, show_error=False):
        raw_text = self.discount_entry.get().strip()
        if not raw_text:
            return 0.0
        try:
            value = float(raw_text)
        except ValueError:
            if show_error:
                messagebox.showerror("Invalid Discount", "Discount must be a valid number.")
            return None

        if value < 0 or value > 100:
            if show_error:
                messagebox.showerror("Invalid Discount", "Discount must be between 0 and 100.")
            return None

        return round(float(value), 2)

    def _update_qr_display(self, total):
        mode = self.payment_mode.get()
        if mode == "Online" and total > 0:
            # build QR if UPI configured
            try:
                import qrcode
                from PIL import Image, ImageTk
                from features.phonepe_ui import _build_upi_uri

                uri = _build_upi_uri(total)
                img = qrcode.make(uri).resize((200, 200), Image.NEAREST)
                photo = ImageTk.PhotoImage(img)
                self.qr_label.config(image=photo)
                self.qr_label.image = photo
                self.qr_hint.config(text=f"UPI ID: {str(__import__('config').UPI_ID)}")
                self.qr_holder.grid()
            except Exception:
                self.qr_label.config(image="")
                self.qr_hint.config(text="QR unavailable (install qrcode/pillow)")
                self.qr_holder.grid()
        else:
            self.qr_holder.grid_remove()

    def _calculate_bill_totals(self, show_error=False):
        subtotal = round(sum(item["total"] for item in self.cart), 2)
        discount_percent = self._get_discount_percent(show_error=show_error)
        if discount_percent is None:
            if show_error:
                return None
            discount_percent = 0.0

        discount_amount = round(subtotal * (discount_percent / 100.0), 2)
        final_total = round(max(subtotal - discount_amount, 0.0), 2)
        return subtotal, discount_percent, discount_amount, final_total

    def show_low_stock(self):
        items = low_stock()
        if not items:
            messagebox.showinfo("Low Stock", "No low-stock items (threshold: stock < 5).")
            return

        lines = [f"{name}: {stock}" for name, stock in items]
        messagebox.showwarning("Low Stock Items", "\n".join(lines))

    def refresh_today_sales(self):
        try:
            summary = get_today_sales_summary()
            self.today_sales_var.set(
                f"Today Sales: {summary['count']} bill(s) | Total: {summary['total']:.2f} | "
                f"Online: {summary['online_total']:.2f} | Cash: {summary['cash_total']:.2f}"
            )
        except Exception:
            self.today_sales_var.set("Today Sales: unavailable")

    def refresh_receipts_box(self):
        self.refresh_today_sales()
        self.receipts_listbox.delete(0, tk.END)

        try:
            rows = get_recent_receipts(limit=300)
        except Exception:
            self.receipts_listbox.insert(tk.END, "Recent receipts unavailable.")
            self.sales_updated_var.set("Updated: failed")
            return

        if not rows:
            self.receipts_listbox.insert(tk.END, "No recent receipts yet.")
        else:
            for row in rows:
                self.receipts_listbox.insert(tk.END, row["line_text"])

        self.sales_updated_var.set(f"Updated: {datetime.now().strftime('%H:%M:%S')}")

    def refresh_sales_overview(self):
        self.refresh_receipts_box()

    def clear_recent_receipts_box(self):
        try:
            clear_recent_receipts()
            self.status_var.set("Recent receipts cleared.")
        except Exception as exc:
            self.status_var.set(f"Unable to clear receipts: {exc}")
        self.refresh_receipts_box()

    def refresh_sales_inputs(self):
        self.barcode_entry.delete(0, tk.END)
        self.search_entry.delete(0, tk.END)
        self.quantity_entry.delete(0, tk.END)
        self.quantity_entry.insert(0, "1")
        self.discount_entry.delete(0, tk.END)
        self.discount_entry.insert(0, "0")
        self.search_results = []
        self.results_listbox.delete(0, tk.END)
        self.cart = []
        self.status_var.set("Ready")
        self.refresh_cart()
        self.refresh_receipts_box()
        self.barcode_entry.focus_set()

    def _format_sales_date(self, date_text):
        try:
            date_obj = datetime.strptime(str(date_text), "%Y-%m-%d")
            return f"{date_obj.day} {date_obj.strftime('%b').lower()} {date_obj.year}"
        except Exception:
            return str(date_text)

    def open_sales_records_window(self):
        win = tk.Toplevel(self.root)
        win.title("Daily Sales Records")
        win.geometry("420x380")

        tk.Label(win, text="Everyday Sold Records", font=("Arial", 12, "bold")).pack(pady=(10, 6))

        sales_listbox = tk.Listbox(win, width=48, height=14)
        sales_listbox.pack(padx=10, pady=(4, 8), fill=tk.BOTH, expand=True)

        def fill_rows():
            sales_listbox.delete(0, tk.END)
            try:
                rows = get_daily_sales_summary(limit=3650)
            except Exception as exc:
                sales_listbox.insert(tk.END, f"Unable to load sales records: {exc}")
                return

            if not rows:
                sales_listbox.insert(tk.END, "No sales records found.")
                return

            for row in reversed(rows):
                date_label = self._format_sales_date(row["date"])
                sales_listbox.insert(
                    tk.END,
                    f"{date_label} || total = {row['total']:.2f} || "
                    f"Online = {row['online_total']:.2f} || Cash = {row['cash_total']:.2f}",
                )

        tk.Button(win, text="Refresh", command=fill_rows).pack(pady=(0, 10))
        fill_rows()

    def search_products(self):
        keyword = self.search_entry.get().strip()
        self.search_results = search_product(keyword)
        self.results_listbox.delete(0, tk.END)

        for product in self.search_results:
            product_id, barcode, name, price, stock = product
            barcode_text = barcode if barcode else "N/A"
            self.results_listbox.insert(
                tk.END,
                f"ID {product_id} | {name} | Barcode: {barcode_text} | Price: {price:.2f} | Stock: {stock}",
            )

    def add_to_cart(self):
        selected = self.results_listbox.curselection()
        if not selected:
            messagebox.showwarning("Selection Required", "Please select a product first.")
            return

        try:
            qty = int(self.quantity_entry.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Quantity", "Quantity must be a whole number.")
            return

        if qty <= 0:
            messagebox.showerror("Invalid Quantity", "Quantity must be greater than zero.")
            return

        product_id, _barcode, name, price, stock = self.search_results[selected[0]]
        self._add_product_to_cart(product_id, name, price, stock, qty)

    def delete_selected_product_from_inventory(self, _event=None):
        selected = self.results_listbox.curselection()
        if not selected:
            self.status_var.set("Select a product in the list to delete.")
            return

        selected_index = selected[0]
        product_id, barcode, name, _price, _stock = self.search_results[selected_index]
        barcode_text = (barcode or "N/A").strip()

        confirm = messagebox.askyesno(
            "Delete Product",
            "you want to delete this product ?",
        )
        if not confirm:
            return

        try:
            deleted_rows = delete_product(product_id)
        except Exception as exc:
            messagebox.showerror("Delete Failed", f"Unable to delete product: {exc}")
            return

        if deleted_rows <= 0:
            self.status_var.set("Product not found in database.")
            self.search_products()
            return

        self.search_results.pop(selected_index)
        self.results_listbox.delete(selected_index)

        original_cart_count = len(self.cart)
        self.cart = [item for item in self.cart if int(item["id"]) != int(product_id)]
        if len(self.cart) != original_cart_count:
            self.refresh_cart()

        self.status_var.set(f"Deleted product: {name} ({barcode_text})")

    def _add_product_to_cart(self, product_id, name, price, stock, qty):
        existing_item = next((item for item in self.cart if item["id"] == product_id), None)
        existing_qty = existing_item["qty"] if existing_item else 0

        if existing_qty + qty > stock:
            messagebox.showerror(
                "Insufficient Stock",
                f"Only {stock} unit(s) available for {name}.",
            )
            return False

        if existing_item:
            existing_item["qty"] += qty
            existing_item["total"] = round(existing_item["qty"] * existing_item["price"], 2)
        else:
            self.cart.append(
                {
                    "id": product_id,
                    "name": name,
                    "qty": qty,
                    "price": float(price),
                    "total": round(float(price) * qty, 2),
                }
            )

        self.refresh_cart()
        return True

    def handle_scanned_barcode(self, _event=None):
        barcode = self.barcode_entry.get().strip()
        self.barcode_entry.delete(0, tk.END)
        self._add_by_barcode(barcode)
        self.barcode_entry.focus_set()

    def add_manual_item(self):
        # prompt user for name, price and quantity
        name = tk.simpledialog.askstring("Manual Item", "Item name:", parent=self.root)
        if not name:
            return
        try:
            price_str = tk.simpledialog.askstring("Manual Item", "Item price:", parent=self.root)
            price = float(price_str)
        except Exception:
            messagebox.showerror("Invalid Price", "Price must be a number.")
            return
        try:
            qty_str = tk.simpledialog.askstring("Manual Item", "Quantity:", parent=self.root)
            qty = int(qty_str)
        except Exception:
            messagebox.showerror("Invalid Quantity", "Quantity must be a whole number.")
            return
        if qty <= 0 or price < 0:
            messagebox.showerror("Invalid Values", "Quantity must be positive and price cannot be negative.")
            return
        # insert with id zero
        existing = next((item for item in self.cart if item.get("id", 0) == 0 and item.get("name") == name and item.get("price") == price), None)
        if existing:
            existing["qty"] += qty
            existing["total"] = round(existing["qty"] * existing["price"], 2)
        else:
            self.cart.append({"id": 0, "name": name, "qty": qty, "price": price, "total": round(price * qty, 2)})
        self.refresh_cart()

    def _add_by_barcode(self, barcode):
        if not barcode:
            return

        candidates = search_product(barcode)
        if not candidates:
            self.status_var.set(f"Barcode not found: {barcode}")
            return

        exact = [row for row in candidates if (row[1] or "").strip() == barcode]
        product = exact[0] if exact else candidates[0]
        product_id, _barcode, name, price, stock = product

        if self._add_product_to_cart(product_id, name, price, stock, 1):
            self.status_var.set(f"Added by barcode: {name}")

    def poll_phone_scans(self):
        updated = False
        while True:
            barcode = pop_scanned_barcode()
            if barcode is None:
                break
            self._add_by_barcode(barcode)
            updated = True

        if updated:
            self.barcode_entry.focus_set()

        self.root.after(500, self.poll_phone_scans)

    def refresh_cart(self):
        self.cart_listbox.delete(0, tk.END)

        for item in self.cart:
            self.cart_listbox.insert(
                tk.END,
                f"{item['name']} | Qty: {item['qty']} | Price: {item['price']:.2f} | Line Total: {item['total']:.2f}",
            )

        subtotal, discount_percent, discount_amount, final_total = self._calculate_bill_totals(show_error=False)
        self.total_var.set(
            f"Subtotal: {subtotal:.2f} | Discount: {discount_percent:.2f}% ({discount_amount:.2f}) | Total: {final_total:.2f}"
        )
        # update QR area based on current payment mode & total
        self._update_qr_display(final_total)

    def remove_selected_cart_item(self, _event=None):
        selected = self.cart_listbox.curselection()
        if not selected:
            self.status_var.set("Select an item in cart to remove.")
            return

        item_index = selected[0]
        removed_item = self.cart.pop(item_index)
        self.refresh_cart()
        self.status_var.set(f"Removed from cart: {removed_item['name']}")

    def open_phonepe_collection(self):
        totals = self._calculate_bill_totals(show_error=True)
        if totals is None:
            return
        subtotal, discount_percent, discount_amount, total = totals
        if total <= 0:
            messagebox.showwarning("No Amount", "Add items to cart before collecting payment.")
            return

        def on_received(_amount):
            self.set_payment_mode("Online")
            self.status_var.set(
                f"Payment marked as received in PhonePe (Online). Discount: {discount_percent:.2f}%"
            )

        open_phonepe_payment_window(self.root, total, on_received=on_received)

    def complete_sale(self):
        if not self.cart:
            messagebox.showwarning("Empty Cart", "Add at least one product before checkout.")
            return

        totals = self._calculate_bill_totals(show_error=True)
        if totals is None:
            return
        _subtotal, discount_percent, _discount_amount, _final_total = totals

        try:
            sale_result = save_sale(
                self.cart,
                payment_mode=self.payment_mode.get(),
                discount_percent=discount_percent,
            )
        except ValueError as exc:
            messagebox.showerror("Checkout Failed", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Checkout Failed", f"Unexpected error: {exc}")
            return

        sale_id = int(sale_result.get("sale_id", 0))
        subtotal = float(sale_result.get("subtotal", 0.0))
        discount_percent = float(sale_result.get("discount_percent", 0.0))
        discount_amount = float(sale_result.get("discount_amount", 0.0))
        total = float(sale_result.get("total", 0.0))
        payment_mode = str(sale_result.get("payment_mode", self.payment_mode.get()))

        print_result = print_bill(
            self.cart,
            total,
            bill_no=sale_id,
            payment_mode=payment_mode,
            subtotal=subtotal,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
        )
        receipt_message = print_result.get("message", "Sale saved.")
        messagebox.showinfo(
            "Sale Completed",
            f"Bill #{sale_id} saved successfully.\n"
            f"Subtotal: {subtotal:.2f}\n"
            f"Discount: {discount_percent:.2f}% ({discount_amount:.2f})\n"
            f"Total: {total:.2f}\n"
            f"Payment: {payment_mode}\n{receipt_message}",
        )

        self.cart = []
        self.discount_entry.delete(0, tk.END)
        self.discount_entry.insert(0, "0")
        self.status_var.set("Ready")
        self.refresh_cart()
        self.search_products()
        self.refresh_receipts_box()
