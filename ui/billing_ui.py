import io
import tkinter as tk
import webbrowser
from datetime import datetime
from time import monotonic
from tkinter import messagebox, simpledialog
from pathlib import Path
from config import (
    APP_BACKGROUND_IMAGE,
    APP_LOGO_IMAGE,
    BASE_DIR,
    BUNDLED_BASE_DIR,
    DB_PATH,
    PRINTER_BLUETOOTH_ADDRESS,
    PRINTER_BLUETOOTH_CHANNEL,
    PRINTER_BLUETOOTH_NAME,
    PRINTER_NETWORK_ADDR,
)
from services.billing_service import (
    clear_recent_receipts,
    get_daily_sales_summary,
    get_recent_receipts,
    get_today_sales_summary,
    save_sale,
)
from services.product_service import delete_product, find_product_by_scanned_barcode, search_product
from features.admin_panel import open_admin_panel
from features.device_status import (
    connect_bluetooth_device,
    get_device_status_snapshot,
    set_bluetooth_radio_enabled,
    set_wifi_radio_enabled,
)
from features.phonepe_ui import build_upi_qr_image, open_phonepe_payment_window
from features.runtime_settings import get_printer_setting, update_printer_settings
from features.scanner_utils import extract_scanned_code, parse_scanned_payload
from features.thermal_printer import print_bill, print_test_receipt
from features.stock_alert import low_stock
from ui.product_ui import open_product_window
from ui.reports_ui import reports_window

class BillingUI:
    SERVICE_PANEL_PASSCODE = "harekrishna"

    def __init__(self, root, sqlite_web=None):
        self.root = root
        self.root.configure(bg="#eef2f6")
        self.root.geometry("1320x820")
        self.root.minsize(1080, 700)
        self.sqlite_web_info = sqlite_web or {}
        self.printer_info = {}
        self.device_snapshot = {}
        self.service_links_visible = False
        self.service_links_unlocked = False
        self._scanner_buffer = ""
        self._scanner_last_char_at = 0.0
        self._scanner_max_gap_seconds = 0.08
        self._last_scan_at = None
        self._last_scan_value = ""
        self.admin_panel = None

        main = tk.Frame(root, bg="#eef2f6")
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.main_container = main

        self._watermark_canvas = tk.Canvas(main, bg="#eef2f6", highlightthickness=0, bd=0)
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
        self.root.bind_all("<KeyPress>", self._capture_usb_scanner_input, add="+")
        self.root.after(80, self._render_watermark_background)
        self.font_base = ("Arial", 11)
        self.font_heading = ("Arial", 12, "bold")
        self.font_big = ("Arial", 13, "bold")
        self.font_small = ("Arial", 10)
        self.font_tiny = ("Arial", 8)
        self.system_status_var = tk.StringVar(value=self._build_system_status_text())

        header_row = tk.Frame(main, bg="#ffffff", bd=1, relief=tk.GROOVE)
        header_row.pack(fill=tk.X, pady=(0, 6))
        header_row.grid_columnconfigure(0, weight=1)
        header_inner = tk.Frame(header_row, bg="#ffffff")
        header_inner.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
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
        header_copy = tk.Frame(header_inner, bg="#ffffff")
        header_copy.pack(side=tk.LEFT)
        self.header_title_label = tk.Label(
            header_copy,
            text="Matchless Gift Shop",
            font=("Arial", 16, "bold"),
            bg="#ffffff",
            fg="#1f2937",
        )
        self.header_title_label.pack(anchor="w")
        tk.Label(
            header_copy,
            text="Offline billing, stock, scanner input and local printing in one screen.",
            font=self.font_small,
            bg="#ffffff",
            fg="#5b6472",
        ).pack(anchor="w", pady=(2, 0))

        header_actions = tk.Frame(header_row, bg="#ffffff")
        header_actions.grid(row=0, column=1, sticky="e", padx=12, pady=(10, 4))
        tk.Button(
            header_actions,
            text="Refresh System",
            font=self.font_base,
            command=self.refresh_system_state,
            bg="#13315c",
            fg="#ffffff",
            activebackground="#1f4b88",
            activeforeground="#ffffff",
            padx=12,
        ).pack(side=tk.RIGHT, padx=(6, 0))
        self.service_toggle_button = tk.Button(
            header_actions,
            text="...",
            width=4,
            font=self.font_base,
            command=self.toggle_service_links,
            bg="#edf2f7",
            fg="#243b53",
        )
        self.service_toggle_button.pack(side=tk.RIGHT)

        tk.Label(
            header_row,
            textvariable=self.system_status_var,
            font=self.font_small,
            bg="#ffffff",
            fg="#4b5563",
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 10))

        self.header_logo_label.bind("<Double-Button-1>", self.toggle_service_links)
        self.header_title_label.bind("<Double-Button-1>", self.toggle_service_links)
        self.root.bind("<Control-Shift-L>", self.toggle_service_links)

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

        self.service_links_panel = tk.LabelFrame(
            main,
            text="Database Panel",
            font=self.font_heading,
            bg="#f8fafc",
            bd=1,
            relief=tk.GROOVE,
            labelanchor="nw",
        )
        self.service_links_body = tk.Frame(self.service_links_panel, bg="#f8fafc")
        self.service_links_body.pack(fill=tk.X, padx=10, pady=(8, 10))
        self._rebuild_service_links_panel()

        self.device_status_panel = tk.LabelFrame(
            main,
            text="Offline Device Status",
            font=self.font_heading,
            bg="#ffffff",
            bd=1,
            relief=tk.GROOVE,
            labelanchor="nw",
        )
        self.device_status_panel.pack(fill=tk.X, pady=(0, 8))
        self.device_status_grid = tk.Frame(self.device_status_panel, bg="#ffffff")
        self.device_status_grid.pack(fill=tk.X, padx=8, pady=(6, 6))
        self.device_cards = {}
        self._build_device_status_cards()

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
        self.receipts_card = receipts_card

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
        self.receipts_listbox = tk.Listbox(
            receipts_list_row,
            height=4,
            font=self.font_base,
            bg="#fbfdff",
            activestyle="none",
        )
        self.receipts_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        receipts_scroll = tk.Scrollbar(receipts_list_row, orient=tk.VERTICAL, command=self.receipts_listbox.yview)
        receipts_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.receipts_listbox.config(yscrollcommand=receipts_scroll.set)

        body_row = tk.Frame(main, bg="#eef2f6")
        body_row.pack(fill=tk.BOTH, expand=True)
        body_row.grid_columnconfigure(0, weight=11)
        body_row.grid_columnconfigure(1, weight=10)
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
        self.barcode_entry.bind("<KP_Enter>", self.handle_scanned_barcode)
        self.barcode_entry.bind("<Tab>", self.handle_scanned_barcode)
        self.barcode_entry.focus_set()

        tk.Label(product_panel, text="Search Product", font=self.font_base, bg="#ffffff").grid(
            row=2, column=0, sticky="w", pady=(0, 4)
        )
        search_box_row = tk.Frame(product_panel, bg="#ffffff")
        search_box_row.grid(row=2, column=1, sticky="ew", pady=(0, 4))
        search_box_row.grid_columnconfigure(0, weight=1)
        self.search_entry = tk.Entry(search_box_row, font=self.font_base)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.search_entry.bind("<Return>", self.handle_search_submit)
        tk.Button(search_box_row, text="Search", font=self.font_base, command=self.search_products).grid(
            row=0, column=1, sticky="e"
        )

        quantity_row = tk.Frame(product_panel, bg="#ffffff")
        quantity_row.grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 6))
        tk.Label(quantity_row, text="Quantity", font=self.font_base, bg="#ffffff").pack(side=tk.LEFT, padx=(0, 6))
        self.quantity_entry = tk.Entry(quantity_row, width=6, font=self.font_base)
        self.quantity_entry.insert(0, "1")
        self.quantity_entry.pack(side=tk.LEFT)
        self.quantity_entry.bind("<Return>", self.handle_quantity_submit)
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
        self.results_listbox.bind("<Double-Button-1>", self.handle_results_activate)
        self.results_listbox.bind("<Return>", self.handle_results_activate)
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
            cart_action_row, text="Clear Cart", font=self.font_base, command=self.clear_cart
        ).pack(side=tk.LEFT, padx=(10, 0))

        manual_row = tk.Frame(cart_panel, bg="#ffffff")
        manual_row.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        manual_row.grid_columnconfigure(1, weight=1)
        tk.Label(manual_row, text="Manual Item", font=self.font_small, bg="#ffffff").grid(row=0, column=0, padx=(0, 6))
        self.manual_name_entry = tk.Entry(manual_row, font=self.font_small)
        self.manual_name_entry.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        self.manual_price_entry = tk.Entry(manual_row, width=8, font=self.font_small)
        self.manual_price_entry.grid(row=0, column=2, padx=(0, 6))
        self.manual_price_entry.insert(0, "0")
        self.manual_qty_entry = tk.Entry(manual_row, width=6, font=self.font_small)
        self.manual_qty_entry.grid(row=0, column=3, padx=(0, 6))
        self.manual_qty_entry.insert(0, "1")
        tk.Button(manual_row, text="Quick Add", font=self.font_small, command=self.add_manual_item).grid(row=0, column=4)
        self.manual_name_entry.bind("<Return>", lambda event: self._focus_widget(self.manual_price_entry))
        self.manual_price_entry.bind("<Return>", lambda event: self._focus_widget(self.manual_qty_entry))
        self.manual_qty_entry.bind("<Return>", self.add_manual_item)

        tk.Label(cart_panel, textvariable=self.total_var, font=self.font_big, bg="#ffffff").grid(
            row=3, column=0, sticky="w", pady=(0, 6)
        )

        discount_row = tk.Frame(cart_panel, bg="#ffffff")
        discount_row.grid(row=4, column=0, sticky="w", pady=(0, 6))
        tk.Label(discount_row, text="Discount %", font=self.font_base, bg="#ffffff").pack(side=tk.LEFT, padx=(0, 8))
        self.discount_entry = tk.Entry(discount_row, width=8, font=self.font_base)
        self.discount_entry.pack(side=tk.LEFT)
        self.discount_entry.insert(0, "0")
        self.discount_entry.bind("<KeyRelease>", lambda _event: self.refresh_cart())
        self.discount_entry.bind("<FocusOut>", lambda _event: self.refresh_cart())

        payment_row = tk.Frame(cart_panel, bg="#ffffff")
        payment_row.grid(row=5, column=0, sticky="w", pady=(2, 6))
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
        self.qr_holder.grid(row=6, column=0, sticky="ew", pady=(4,6))
        self.qr_label = tk.Label(self.qr_holder, bg="#ffffff")
        self.qr_label.pack()
        self.qr_hint = tk.Label(self.qr_holder, font=self.font_small, bg="#ffffff")
        self.qr_hint.pack()

        self.set_payment_mode("Cash")

        tk.Button(cart_panel, text="Complete Sale", font=self.font_heading, command=self.complete_sale).grid(
            row=7, column=0, sticky="ew", pady=(4, 6)
        )
        tk.Button(
            cart_panel, text="Receive In PhonePe", font=self.font_base, command=self.open_phonepe_collection
        ).grid(row=8, column=0, sticky="ew", pady=(0, 6))
        tk.Label(cart_panel, textvariable=self.status_var, font=self.font_base, bg="#ffffff", anchor="w").grid(
            row=9, column=0, sticky="ew", pady=(2, 0)
        )

        self.refresh_cart()
        self.refresh_receipts_box()
        self.refresh_device_status(update_status=False)

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

        return self._resolve_runtime_asset_path(raw_path)

    def _resolve_logo_image_path(self):
        raw_path = str(APP_LOGO_IMAGE or "").strip()
        if not raw_path:
            return None

        return self._resolve_runtime_asset_path(raw_path)

    def _resolve_runtime_asset_path(self, raw_path):
        image_path = Path(raw_path).expanduser()
        if image_path.is_absolute():
            return image_path

        bundled_path = BUNDLED_BASE_DIR / image_path
        if bundled_path.exists():
            return bundled_path

        return BASE_DIR / image_path

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

    def _build_device_status_cards(self):
        definitions = [
            ("scanner", "Scanner", None),
            ("printer", "Printer", None),
            ("wifi_route", "Wi-Fi Printer", self.connect_wifi_printer),
            ("bluetooth_route", "Bluetooth Printer", self.connect_bluetooth_printer),
            ("wifi_radio", "Wi-Fi Radio", self.enable_wifi_radio),
            ("bluetooth_radio", "Bluetooth Radio", self.enable_bluetooth_radio),
        ]

        for index, (key, title, action_command) in enumerate(definitions):
            row = 0
            column = index
            self.device_status_grid.grid_columnconfigure(column, weight=1)

            card = tk.Frame(self.device_status_grid, bg="#f8fafc", bd=1, relief=tk.GROOVE)
            card.grid(row=row, column=column, sticky="nsew", padx=3, pady=3)

            top_row = tk.Frame(card, bg="#f8fafc")
            top_row.pack(fill=tk.X, padx=6, pady=(4, 1))
            tk.Label(top_row, text=title, font=self.font_tiny, bg="#f8fafc", fg="#4b5563").pack(side=tk.LEFT)
            state_label = tk.Label(top_row, text="Checking...", font=("Arial", 9, "bold"), bg="#f8fafc", fg="#1f2937")
            state_label.pack(side=tk.RIGHT)
            message_label = tk.Label(
                card,
                text="",
                font=self.font_tiny,
                bg="#f8fafc",
                fg="#1f2937",
                anchor="w",
                justify=tk.LEFT,
                wraplength=130,
            )
            message_label.pack(anchor="w", fill=tk.X, padx=6, pady=(0, 1))

            footer_row = tk.Frame(card, bg="#f8fafc")
            footer_row.pack(fill=tk.X, padx=6, pady=(0, 4))
            detail_label = tk.Label(
                footer_row,
                text="",
                font=self.font_tiny,
                bg="#f8fafc",
                fg="#5b6472",
                anchor="w",
                justify=tk.LEFT,
                wraplength=88,
            )
            detail_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

            action_button = None
            if action_command is not None:
                action_button = tk.Button(
                    footer_row,
                    text="Connect",
                    font=self.font_tiny,
                    command=action_command,
                    padx=6,
                    pady=0,
                )
                action_button.pack(side=tk.RIGHT, padx=(4, 0))

            self.device_cards[key] = {
                "frame": card,
                "state": state_label,
                "message": message_label,
                "detail": detail_label,
                "action": action_button,
            }

    def _device_state_color(self, state_text):
        normalized = str(state_text or "").strip().lower()
        if normalized in {"connected", "ready", "on"}:
            return "#0a7b24"
        if normalized in {"listening", "configured", "unknown"}:
            return "#9a6700"
        return "#b42318"

    def _set_device_card(self, key, state, message, detail=""):
        widgets = self.device_cards.get(key)
        if not widgets:
            return
        widgets["state"].config(text=state, fg=self._device_state_color(state))
        widgets["message"].config(text=self._short_status_text(message, 28))
        widgets["detail"].config(text=self._short_status_text(detail, 18))

    def _set_device_action(self, key, text, enabled=True):
        widgets = self.device_cards.get(key) or {}
        action_button = widgets.get("action")
        if action_button is None:
            return
        action_button.config(text=text, state=(tk.NORMAL if enabled else tk.DISABLED))

    def _short_status_text(self, text, limit):
        clean_text = " ".join(str(text or "").split())
        if len(clean_text) <= limit:
            return clean_text
        return clean_text[: max(limit - 3, 0)] + "..."

    def _record_scanner_activity(self, barcode):
        clean_barcode = str(barcode or "").strip()
        if not clean_barcode:
            return
        self._last_scan_at = datetime.now()
        self._last_scan_value = clean_barcode
        self.refresh_device_status(update_status=False)

    def refresh_device_status(self, update_status=True):
        self.device_snapshot = get_device_status_snapshot(
            last_scan_at=self._last_scan_at,
            last_scan_value=self._last_scan_value,
        )
        self.printer_info = dict(self.device_snapshot.get("printer") or {})

        scanner = self.device_snapshot.get("scanner") or {}
        scanner_detail = str(scanner.get("detail") or "").strip()
        last_scan_value = str(scanner.get("last_scan_value") or "").strip()
        if last_scan_value:
            scanner_detail = f"{scanner_detail} | Last code: {last_scan_value}"
        self._set_device_card(
            "scanner",
            scanner.get("state", "Listening"),
            scanner.get("message", "Scanner listener is enabled."),
            scanner_detail,
        )

        active_printer_state = "Ready" if self.printer_info.get("success") else "Offline"
        active_printer_detail = f"Mode: {str(self.printer_info.get('mode') or 'auto').upper()}"
        self._set_device_card(
            "printer",
            active_printer_state,
            self.printer_info.get("message", "Printer status unavailable."),
            active_printer_detail,
        )

        printer_routes = self.device_snapshot.get("printer_routes") or {}
        wifi_route = printer_routes.get("wifi") or {}
        wifi_state = "Connected" if wifi_route.get("connected") else ("Configured" if wifi_route.get("configured") else "Offline")
        self._set_device_card(
            "wifi_route",
            wifi_state,
            wifi_route.get("message", "Wi-Fi printer status unavailable."),
            ", ".join(wifi_route.get("candidates", [])[:2]),
        )

        bluetooth_route = printer_routes.get("bluetooth") or {}
        bluetooth_state = (
            "Connected"
            if bluetooth_route.get("connected")
            else ("Configured" if bluetooth_route.get("configured") else "Offline")
        )
        self._set_device_card(
            "bluetooth_route",
            bluetooth_state,
            bluetooth_route.get("message", "Bluetooth printer status unavailable."),
            ", ".join(bluetooth_route.get("candidates", [])[:2]),
        )

        wifi_radio = self.device_snapshot.get("wifi_radio") or {}
        self._set_device_card(
            "wifi_radio",
            wifi_radio.get("state", "Unknown"),
            wifi_radio.get("message", "Wi-Fi radio status unavailable."),
        )

        bluetooth_radio = self.device_snapshot.get("bluetooth_radio") or {}
        self._set_device_card(
            "bluetooth_radio",
            bluetooth_radio.get("state", "Unknown"),
            bluetooth_radio.get("message", "Bluetooth radio status unavailable."),
        )
        self._set_device_action("wifi_route", "Change" if wifi_route.get("configured") else "Connect")
        self._set_device_action("bluetooth_route", "Change" if bluetooth_route.get("configured") else "Connect")
        self._set_device_action("wifi_radio", "On" if wifi_radio.get("connected") else "Turn On", not wifi_radio.get("connected"))
        self._set_device_action(
            "bluetooth_radio",
            "On" if bluetooth_radio.get("connected") else "Turn On",
            not bluetooth_radio.get("connected"),
        )

        self.system_status_var.set(self._build_system_status_text())
        if self.service_links_visible:
            self._rebuild_service_links_panel()
        if update_status:
            self.status_var.set("Device status refreshed.")

    def _build_system_status_text(self):
        sqlite_ready = bool(self.sqlite_web_info.get("success"))
        scanner_state = str((self.device_snapshot.get("scanner") or {}).get("state") or "Listening")
        wifi_ready = bool(((self.device_snapshot.get("printer_routes") or {}).get("wifi") or {}).get("connected"))
        bluetooth_ready = bool(((self.device_snapshot.get("printer_routes") or {}).get("bluetooth") or {}).get("connected"))
        printer_ready = bool(self.printer_info.get("success"))
        sqlite_label = "live" if sqlite_ready and self.sqlite_web_info.get("url") else "offline"
        printer_label = "ready" if printer_ready else "offline"
        wifi_label = "connected" if wifi_ready else "offline"
        bluetooth_label = "connected" if bluetooth_ready else "offline"
        return (
            f"System status | Database browser: {sqlite_label} | "
            f"Scanner: {scanner_state.lower()} | Printer: {printer_label} | "
            f"Wi-Fi printer: {wifi_label} | Bluetooth printer: {bluetooth_label}"
        )

    def _service_link_rows(self):
        rows = []

        sqlite_url = str(self.sqlite_web_info.get("url") or "").strip()
        if sqlite_url:
            rows.append(("Database Browser", sqlite_url, True))
        else:
            rows.append(
                (
                    "Database Browser",
                    str(self.sqlite_web_info.get("message") or "sqlite-web is not available on this device."),
                    False,
                )
            )

        rows.append(("Database File", str(DB_PATH), False))
        return rows

    def _rebuild_service_links_panel(self):
        for child in self.service_links_body.winfo_children():
            child.destroy()

        printer_action_row = tk.Frame(self.service_links_body, bg="#f8fafc")
        printer_action_row.pack(fill=tk.X, pady=(0, 6))
        tk.Button(
            printer_action_row,
            text="Open Admin Panel",
            font=self.font_small,
            command=self.open_admin_panel,
        ).pack(side=tk.LEFT)

        for label_text, value_text, is_url in self._service_link_rows():
            row = tk.Frame(self.service_links_body, bg="#f8fafc")
            row.pack(fill=tk.X, pady=3)
            tk.Label(
                row,
                text=label_text,
                width=17,
                anchor="w",
                font=self.font_small,
                bg="#f8fafc",
                fg="#243b53",
            ).pack(side=tk.LEFT)

            value_entry = tk.Entry(row, font=self.font_small, relief=tk.FLAT, bd=1)
            value_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=4)
            value_entry.insert(0, value_text)
            value_entry.config(state="readonly", readonlybackground="#ffffff")

            tk.Button(
                row,
                text="Copy",
                font=self.font_small,
                command=lambda text=value_text: self.copy_to_clipboard(text),
            ).pack(side=tk.RIGHT, padx=(4, 0))

            if is_url:
                tk.Button(
                    row,
                    text="Open",
                    font=self.font_small,
                    command=lambda url=value_text: self.open_service_link(url),
                ).pack(side=tk.RIGHT)

    def _current_network_target(self):
        return str(get_printer_setting("network_address", PRINTER_NETWORK_ADDR) or "").strip()

    def _current_bluetooth_address(self):
        return str(get_printer_setting("bluetooth_address", PRINTER_BLUETOOTH_ADDRESS) or "").strip()

    def _current_bluetooth_name(self):
        return str(get_printer_setting("bluetooth_name", PRINTER_BLUETOOTH_NAME) or "").strip()

    def _current_bluetooth_channel(self):
        return str(get_printer_setting("bluetooth_channel", PRINTER_BLUETOOTH_CHANNEL) or "1").strip() or "1"

    def connect_wifi_printer(self):
        target = simpledialog.askstring(
            "Wi-Fi Printer",
            "Enter Wi-Fi printer IP or host[:port]:",
            parent=self.root,
            initialvalue=self._current_network_target(),
        )
        if target is None:
            self.status_var.set("Wi-Fi printer setup cancelled.")
            return

        target = str(target).strip()
        update_printer_settings(network_address=target)
        self.refresh_device_status(update_status=False)
        wifi_route = ((self.device_snapshot.get("printer_routes") or {}).get("wifi") or {})
        if target:
            self.status_var.set(wifi_route.get("message", f"Saved Wi-Fi printer target {target}."))
        else:
            self.status_var.set("Wi-Fi printer target cleared.")

    def connect_bluetooth_printer(self):
        address = simpledialog.askstring(
            "Bluetooth Printer",
            "Enter Bluetooth printer address:",
            parent=self.root,
            initialvalue=self._current_bluetooth_address(),
        )
        if address is None:
            self.status_var.set("Bluetooth printer setup cancelled.")
            return

        address = str(address).strip()
        if not address:
            messagebox.showerror("Bluetooth Printer", "Bluetooth address is required.", parent=self.root)
            return

        name = simpledialog.askstring(
            "Bluetooth Printer",
            "Enter Bluetooth printer name (optional):",
            parent=self.root,
            initialvalue=self._current_bluetooth_name(),
        )
        if name is None:
            self.status_var.set("Bluetooth printer setup cancelled.")
            return

        channel_text = simpledialog.askstring(
            "Bluetooth Printer",
            "Enter Bluetooth RFCOMM channel:",
            parent=self.root,
            initialvalue=self._current_bluetooth_channel(),
        )
        if channel_text is None:
            self.status_var.set("Bluetooth printer setup cancelled.")
            return

        try:
            channel = int(str(channel_text).strip() or "1")
            if channel <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Bluetooth Printer", "Bluetooth channel must be a positive whole number.", parent=self.root)
            return

        update_printer_settings(
            bluetooth_address=address,
            bluetooth_name=str(name).strip(),
            bluetooth_channel=str(channel),
        )
        connect_result = connect_bluetooth_device(address)
        self.refresh_device_status(update_status=False)
        bluetooth_route = ((self.device_snapshot.get("printer_routes") or {}).get("bluetooth") or {})
        self.status_var.set(connect_result.get("message") or bluetooth_route.get("message", "Bluetooth printer updated."))

    def enable_wifi_radio(self):
        result = set_wifi_radio_enabled(True)
        self.refresh_device_status(update_status=False)
        self.status_var.set(result.get("message", "Wi-Fi radio updated."))

    def enable_bluetooth_radio(self):
        result = set_bluetooth_radio_enabled(True)
        self.refresh_device_status(update_status=False)
        self.status_var.set(result.get("message", "Bluetooth radio updated."))

    def toggle_service_links(self, _event=None):
        if self.service_links_visible:
            self.service_links_visible = False
            self.service_links_panel.pack_forget()
            self.service_toggle_button.config(text="...")
            self.status_var.set("Database panel hidden.")
            return

        if not self.service_links_unlocked:
            passcode = simpledialog.askstring(
                "Passcode Required",
                "Enter passcode to open the database panel:",
                parent=self.root,
                show="*",
            )
            if passcode is None:
                self.status_var.set("Database panel locked.")
                return
            if str(passcode).strip() != self.SERVICE_PANEL_PASSCODE:
                messagebox.showerror("Access Denied", "Incorrect passcode.")
                self.status_var.set("Database panel locked.")
                return
            self.service_links_unlocked = True

        self.service_links_visible = True
        self._rebuild_service_links_panel()
        self.service_links_panel.pack(fill=tk.X, pady=(0, 8), before=self.receipts_card)
        self.service_toggle_button.config(text="x")
        self.status_var.set("Database panel unlocked.")

    def _prompt_service_passcode(self):
        passcode = simpledialog.askstring(
            "Passcode Required",
            "Enter passcode to open the hidden database panel:",
            parent=self.root,
            show="*",
        )
        if passcode is None:
            self.status_var.set("Database panel locked.")
            return False
        if str(passcode).strip() != self.SERVICE_PANEL_PASSCODE:
            messagebox.showerror("Access Denied", "Incorrect passcode.")
            self.status_var.set("Database panel locked.")
            return False
        self.service_links_unlocked = True
        return True

    def open_protected_system(self):
        if not self.service_links_unlocked and not self._prompt_service_passcode():
            return

        self.service_links_visible = True
        self._rebuild_service_links_panel()
        self.service_links_panel.pack(fill=tk.X, pady=(0, 8), before=self.receipts_card)
        self.service_toggle_button.config(text="x")
        self.open_admin_panel()
        self.refresh_system_state()

    def copy_to_clipboard(self, value):
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.status_var.set("Copied system details to clipboard.")

    def open_service_link(self, url):
        try:
            webbrowser.open_new_tab(url)
            self.status_var.set(f"Opened: {url}")
        except Exception as exc:
            messagebox.showerror("Open Link Failed", str(exc))

    def refresh_system_state(self, _event=None):
        self._scanner_buffer = ""
        self._scanner_last_char_at = 0.0
        self.refresh_device_status(update_status=False)
        self.refresh_cart()
        self.refresh_receipts_box()
        self.search_products()
        self._rebuild_service_links_panel()
        self.root.update_idletasks()
        self.system_status_var.set(self._build_system_status_text())
        self.status_var.set("System refreshed.")
        self.barcode_entry.focus_set()
        return "break"

    def refresh_printer_status(self, update_status=True):
        self.refresh_device_status(update_status=False)
        if update_status:
            self.status_var.set(self.printer_info.get("message", "Printer status updated."))

    def run_printer_test(self):
        self.refresh_printer_status(update_status=False)
        result = print_test_receipt()
        self.refresh_printer_status(update_status=False)
        if result.get("success"):
            self.status_var.set(result.get("message", "Printer test completed."))
            messagebox.showinfo("Printer Test", result.get("message", "Printer test completed."))
            return

        self.status_var.set(result.get("message", "Printer test failed."))
        messagebox.showwarning("Printer Test", result.get("message", "Printer test failed."))

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
            qr_result = build_upi_qr_image(total, size=200)
            if qr_result.get("success"):
                from PIL import ImageTk

                photo = ImageTk.PhotoImage(qr_result["image"])
                self.qr_label.config(image=photo)
                self.qr_label.image = photo
                self.qr_hint.config(text=f"Scan to pay | UPI ID: {qr_result.get('upi_id')}")
            else:
                self.qr_label.config(image="")
                self.qr_label.image = None
                self.qr_hint.config(text=qr_result.get("message", "QR unavailable."))
            self.qr_holder.grid()
        else:
            self.qr_label.config(image="")
            self.qr_label.image = None
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

    def _widget_accepts_free_text(self, widget):
        if widget is None:
            return False
        try:
            return widget.winfo_class() in {"Entry", "Text", "Spinbox", "TEntry", "TSpinbox"}
        except Exception:
            return False

    def _capture_usb_scanner_input(self, event):
        widget = event.widget
        if self._widget_accepts_free_text(widget):
            self._scanner_buffer = ""
            return None

        state = int(getattr(event, "state", 0) or 0)
        if state & 0x4 or state & 0x8:
            self._scanner_buffer = ""
            return None

        key = str(getattr(event, "keysym", "") or "")
        char = str(getattr(event, "char", "") or "")
        now = monotonic()

        if key in {"Return", "KP_Enter", "Tab"}:
            scan_value = self._scanner_buffer.strip()
            self._scanner_buffer = ""
            if len(scan_value) >= 4:
                self._record_scanner_activity(scan_value)
                self._add_by_barcode(scan_value)
                self.barcode_entry.focus_set()
                return "break"
            return None

        if len(char) != 1 or not char.isprintable() or char in "\r\n\t":
            if now - self._scanner_last_char_at > self._scanner_max_gap_seconds:
                self._scanner_buffer = ""
            return None

        if now - self._scanner_last_char_at > self._scanner_max_gap_seconds:
            self._scanner_buffer = char
        else:
            self._scanner_buffer += char
        self._scanner_last_char_at = now
        return None

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

        if self.search_results:
            self.results_listbox.selection_clear(0, tk.END)
            self.results_listbox.selection_set(0)
            self.results_listbox.activate(0)

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
        if self._add_product_to_cart(product_id, name, price, stock, qty):
            self.quantity_entry.delete(0, tk.END)
            self.quantity_entry.insert(0, "1")
            self.search_entry.focus_set()
            self.search_entry.selection_range(0, tk.END)

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
        self._record_scanner_activity(barcode)
        self._add_by_barcode(barcode)
        self.barcode_entry.focus_set()
        return "break"

    def add_manual_item(self, _event=None):
        name = self.manual_name_entry.get().strip()
        if not name:
            self.status_var.set("Enter a manual item name.")
            self.manual_name_entry.focus_set()
            return

        try:
            price = float(self.manual_price_entry.get().strip())
        except Exception:
            self.status_var.set("Manual item price must be a number.")
            self.manual_price_entry.focus_set()
            return

        try:
            qty = int(self.manual_qty_entry.get().strip())
        except Exception:
            self.status_var.set("Manual item quantity must be a whole number.")
            self.manual_qty_entry.focus_set()
            return

        if qty <= 0 or price < 0:
            self.status_var.set("Manual item quantity must be positive and price cannot be negative.")
            self.manual_name_entry.focus_set()
            return

        existing = next((item for item in self.cart if item.get("id", 0) == 0 and item.get("name") == name and item.get("price") == price), None)
        if existing:
            existing["qty"] += qty
            existing["total"] = round(existing["qty"] * existing["price"], 2)
        else:
            self.cart.append({"id": 0, "name": name, "qty": qty, "price": price, "total": round(price * qty, 2)})
        self.refresh_cart()
        self.manual_name_entry.delete(0, tk.END)
        self.manual_price_entry.delete(0, tk.END)
        self.manual_price_entry.insert(0, "0")
        self.manual_qty_entry.delete(0, tk.END)
        self.manual_qty_entry.insert(0, "1")
        self.manual_name_entry.focus_set()
        return "break"

    def _add_by_barcode(self, barcode):
        normalized_barcode = extract_scanned_code(barcode)
        if not normalized_barcode:
            return

        scanned_details = parse_scanned_payload(barcode)
        requested_qty = scanned_details.get("qty")
        if requested_qty is None:
            requested_qty = 1
        try:
            requested_qty = int(requested_qty)
        except (TypeError, ValueError):
            requested_qty = 1
        if requested_qty <= 0:
            requested_qty = 1

        product = find_product_by_scanned_barcode(normalized_barcode)
        if not product:
            self.status_var.set(f"Barcode not found: {normalized_barcode}")
            return

        product_id, _barcode, name, price, stock = product

        if self._add_product_to_cart(product_id, name, price, stock, requested_qty):
            if requested_qty > 1:
                self.status_var.set(f"Added by scan: {name} x{requested_qty}")
            elif scanned_details.get("barcode") and scanned_details.get("barcode") != str(barcode).strip():
                self.status_var.set(f"Added by scan: {name} ({normalized_barcode})")
            else:
                self.status_var.set(f"Added by barcode: {name}")

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

    def _focus_widget(self, widget):
        widget.focus_set()
        if hasattr(widget, "selection_range"):
            try:
                widget.selection_range(0, tk.END)
            except Exception:
                pass
        return "break"

    def handle_search_submit(self, _event=None):
        self.search_products()
        if not self.search_results:
            self.status_var.set("No matching product found.")
            return "break"

        if len(self.search_results) == 1:
            self.quantity_entry.focus_set()
            self.quantity_entry.selection_range(0, tk.END)
        else:
            self.results_listbox.focus_set()
        return "break"

    def handle_results_activate(self, _event=None):
        selected = self.results_listbox.curselection()
        if not selected and self.search_results:
            self.results_listbox.selection_set(0)
            self.results_listbox.activate(0)
        self.quantity_entry.focus_set()
        self.quantity_entry.selection_range(0, tk.END)
        return "break"

    def handle_quantity_submit(self, _event=None):
        self.add_to_cart()
        return "break"

    def open_admin_panel(self):
        existing_panel = getattr(self, "admin_panel", None)
        if existing_panel is not None:
            try:
                if existing_panel.window.winfo_exists():
                    existing_panel.window.deiconify()
                    existing_panel.window.lift()
                    existing_panel.window.focus_force()
                    self.status_var.set("Admin database panel focused.")
                    return
            except Exception:
                pass

        self.admin_panel = open_admin_panel(self.root, on_data_changed=self.refresh_system_state)
        self.status_var.set("Admin database panel opened.")

    def remove_selected_cart_item(self, _event=None):
        selected = self.cart_listbox.curselection()
        if not selected:
            self.status_var.set("Select an item in cart to remove.")
            return

        item_index = selected[0]
        removed_item = self.cart.pop(item_index)
        self.refresh_cart()
        self.status_var.set(f"Removed from cart: {removed_item['name']}")

    def clear_cart(self):
        if not self.cart:
            self.status_var.set("Cart is already empty.")
            return

        confirmed = messagebox.askyesno("Clear Cart", "Remove all items from the current cart?")
        if not confirmed:
            return

        self.cart = []
        self.discount_entry.delete(0, tk.END)
        self.discount_entry.insert(0, "0")
        self.refresh_cart()
        self.status_var.set("Cart cleared.")
        self.barcode_entry.focus_set()

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
        self.barcode_entry.focus_set()
