import shutil
import sqlite3
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from config import DB_PATH
from database import connect


def _default_dialog_dir():
    home_dir = Path.home().expanduser()
    if home_dir.is_dir():
        return str(home_dir)
    return str(Path(DB_PATH).resolve().parent)


class AdminPanelWindow:
    def __init__(self, parent, on_data_changed=None):
        self.parent = parent
        self.on_data_changed = on_data_changed
        self.window = tk.Toplevel(parent)
        self.window.title("Admin Database Panel")
        self.window.geometry("1180x760")
        self.window.minsize(980, 660)
        self.window.configure(bg="#f4f6f8")

        self.status_var = tk.StringVar(value="Admin panel ready.")
        self.sql_result_meta = tk.StringVar(value="Run a SELECT or update statement.")

        self.products_tree = None
        self.sales_tree = None
        self.receipts_tree = None
        self.sql_tree = None
        self.sql_text = None
        self.overview_cards = {}

        self.product_barcode_var = tk.StringVar()
        self.product_name_var = tk.StringVar()
        self.product_price_var = tk.StringVar(value="0")
        self.product_stock_var = tk.StringVar(value="0")

        header = tk.Frame(self.window, bg="#f4f6f8")
        header.pack(fill=tk.X, padx=12, pady=(10, 6))
        tk.Label(
            header,
            text="Protected Admin Database Panel",
            font=("Arial", 14, "bold"),
            bg="#f4f6f8",
            fg="#1f2937",
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Manage database data, import/export files, and run direct SQL maintenance inside the POS.",
            font=("Arial", 10),
            bg="#f4f6f8",
            fg="#4b5563",
        ).pack(anchor="w", pady=(2, 0))

        notebook = ttk.Notebook(self.window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        self.notebook = notebook

        self.overview_tab = tk.Frame(notebook, bg="#ffffff")
        self.products_tab = tk.Frame(notebook, bg="#ffffff")
        self.sales_tab = tk.Frame(notebook, bg="#ffffff")
        self.receipts_tab = tk.Frame(notebook, bg="#ffffff")
        self.sql_tab = tk.Frame(notebook, bg="#ffffff")

        notebook.add(self.overview_tab, text="Overview")
        notebook.add(self.products_tab, text="Products")
        notebook.add(self.sales_tab, text="Sales")
        notebook.add(self.receipts_tab, text="Receipts")
        notebook.add(self.sql_tab, text="SQL")

        self._build_overview_tab()
        self._build_products_tab()
        self._build_sales_tab()
        self._build_receipts_tab()
        self._build_sql_tab()

        footer = tk.Frame(self.window, bg="#f4f6f8")
        footer.pack(fill=tk.X, padx=12, pady=(0, 10))
        tk.Label(footer, textvariable=self.status_var, bg="#f4f6f8", fg="#374151", anchor="w").pack(fill=tk.X)

        self.refresh_all()

    def _load_pandas(self):
        try:
            import pandas as pd

            return pd
        except Exception as exc:
            messagebox.showerror(
                "Dependency Missing",
                f"Import/export needs pandas and Excel support in this Python environment.\n\nDetails: {exc}",
                parent=self.window,
            )
            return None

    def _build_overview_tab(self):
        action_row = tk.Frame(self.overview_tab, bg="#ffffff")
        action_row.pack(fill=tk.X, padx=12, pady=(12, 8))
        tk.Button(action_row, text="Refresh Overview", command=self._load_overview).pack(side=tk.LEFT)
        tk.Button(action_row, text="Download DB Copy", command=self.download_database_copy).pack(side=tk.LEFT, padx=(8, 0))

        cards_row = tk.Frame(self.overview_tab, bg="#ffffff")
        cards_row.pack(fill=tk.X, padx=12, pady=(0, 8))
        for index, key in enumerate(("products", "sales", "sale_items", "receipts")):
            cards_row.grid_columnconfigure(index, weight=1)
            card = tk.Frame(cards_row, bg="#f8fafc", bd=1, relief=tk.GROOVE)
            card.grid(row=0, column=index, sticky="nsew", padx=4, pady=4)
            tk.Label(card, text=key.replace("_", " ").title(), font=("Arial", 10), bg="#f8fafc", fg="#4b5563").pack(
                anchor="w", padx=10, pady=(10, 2)
            )
            value_label = tk.Label(card, text="0", font=("Arial", 18, "bold"), bg="#f8fafc", fg="#111827")
            value_label.pack(anchor="w", padx=10, pady=(0, 10))
            self.overview_cards[key] = value_label

        self.overview_summary_var = tk.StringVar(value="Loading database summary...")
        tk.Label(
            self.overview_tab,
            textvariable=self.overview_summary_var,
            font=("Arial", 11),
            bg="#ffffff",
            fg="#1f2937",
            justify=tk.LEFT,
            anchor="w",
        ).pack(fill=tk.X, padx=16, pady=(4, 10))

    def _build_products_tab(self):
        top = tk.Frame(self.products_tab, bg="#ffffff")
        top.pack(fill=tk.X, padx=12, pady=(12, 8))
        tk.Label(top, text="Products", font=("Arial", 12, "bold"), bg="#ffffff", fg="#111827").pack(anchor="w")
        tk.Label(
            top,
            text="Add products manually, delete selected rows, and import/export CSV or Excel files.",
            font=("Arial", 10),
            bg="#ffffff",
            fg="#4b5563",
        ).pack(anchor="w", pady=(2, 8))

        form = tk.Frame(self.products_tab, bg="#ffffff")
        form.pack(fill=tk.X, padx=12, pady=(0, 8))
        labels = (
            ("Barcode", self.product_barcode_var, 18),
            ("Name", self.product_name_var, 32),
            ("Price", self.product_price_var, 10),
            ("Stock", self.product_stock_var, 10),
        )
        for index, (label_text, variable, width) in enumerate(labels):
            tk.Label(form, text=label_text, bg="#ffffff", fg="#374151").grid(row=0, column=index * 2, sticky="w", padx=(0, 6))
            entry = tk.Entry(form, textvariable=variable, width=width)
            entry.grid(row=0, column=index * 2 + 1, sticky="w", padx=(0, 10))

        action_row = tk.Frame(self.products_tab, bg="#ffffff")
        action_row.pack(fill=tk.X, padx=12, pady=(0, 8))
        tk.Button(action_row, text="Add Product", command=self.add_product_record).pack(side=tk.LEFT)
        tk.Button(action_row, text="Delete Selected", command=self.delete_selected_product).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(action_row, text="Select All", command=lambda: self.select_all_rows(self.products_tree)).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(action_row, text="Import CSV/XLS", command=self.import_products_file).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(action_row, text="Export Table", command=lambda: self.export_tree(self.products_tree, "products")).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(action_row, text="Refresh", command=self.load_products).pack(side=tk.LEFT, padx=(8, 0))

        self.products_tree = self._build_tree_container(self.products_tab)

    def _build_sales_tab(self):
        top = tk.Frame(self.sales_tab, bg="#ffffff")
        top.pack(fill=tk.X, padx=12, pady=(12, 8))
        tk.Label(top, text="Sales", font=("Arial", 12, "bold"), bg="#ffffff", fg="#111827").pack(anchor="w")
        tk.Label(top, text="Review sales, delete selected sale records, or export reports.", font=("Arial", 10), bg="#ffffff", fg="#4b5563").pack(anchor="w", pady=(2, 8))

        action_row = tk.Frame(self.sales_tab, bg="#ffffff")
        action_row.pack(fill=tk.X, padx=12, pady=(0, 8))
        tk.Button(action_row, text="Delete Selected Sale", command=self.delete_selected_sale).pack(side=tk.LEFT)
        tk.Button(action_row, text="Select All", command=lambda: self.select_all_rows(self.sales_tree)).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(action_row, text="Export Table", command=lambda: self.export_tree(self.sales_tree, "sales")).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(action_row, text="Export Sales Report", command=self.export_sales_report).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(action_row, text="Refresh", command=self.load_sales).pack(side=tk.LEFT, padx=(8, 0))

        self.sales_tree = self._build_tree_container(self.sales_tab)

    def _build_receipts_tab(self):
        top = tk.Frame(self.receipts_tab, bg="#ffffff")
        top.pack(fill=tk.X, padx=12, pady=(12, 8))
        tk.Label(top, text="Recent Receipts", font=("Arial", 12, "bold"), bg="#ffffff", fg="#111827").pack(anchor="w")
        tk.Label(top, text="Delete old receipt log rows or export them.", font=("Arial", 10), bg="#ffffff", fg="#4b5563").pack(anchor="w", pady=(2, 8))

        action_row = tk.Frame(self.receipts_tab, bg="#ffffff")
        action_row.pack(fill=tk.X, padx=12, pady=(0, 8))
        tk.Button(action_row, text="Delete Selected", command=self.delete_selected_receipt).pack(side=tk.LEFT)
        tk.Button(action_row, text="Select All", command=lambda: self.select_all_rows(self.receipts_tree)).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(action_row, text="Export Table", command=lambda: self.export_tree(self.receipts_tree, "receipts")).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(action_row, text="Refresh", command=self.load_receipts).pack(side=tk.LEFT, padx=(8, 0))

        self.receipts_tree = self._build_tree_container(self.receipts_tab)

    def _build_sql_tab(self):
        top = tk.Frame(self.sql_tab, bg="#ffffff")
        top.pack(fill=tk.X, padx=12, pady=(12, 8))
        tk.Label(top, text="SQL Console", font=("Arial", 12, "bold"), bg="#ffffff", fg="#111827").pack(anchor="w")
        tk.Label(
            top,
            text="Use SELECT for browsing or INSERT/UPDATE/DELETE for direct maintenance.",
            font=("Arial", 10),
            bg="#ffffff",
            fg="#4b5563",
        ).pack(anchor="w", pady=(2, 8))

        self.sql_text = tk.Text(self.sql_tab, height=8, font=("Courier", 10), wrap="word")
        self.sql_text.pack(fill=tk.X, padx=12, pady=(0, 8))
        self.sql_text.insert(
            "1.0",
            "SELECT id, barcode, name, price, stock\nFROM products\nORDER BY id DESC\nLIMIT 50;",
        )

        action_row = tk.Frame(self.sql_tab, bg="#ffffff")
        action_row.pack(fill=tk.X, padx=12, pady=(0, 8))
        tk.Button(action_row, text="Run SQL", command=self.run_sql).pack(side=tk.LEFT)
        tk.Button(action_row, text="Refresh All Tabs", command=self.refresh_all).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(action_row, textvariable=self.sql_result_meta, font=("Arial", 10), bg="#ffffff", fg="#4b5563").pack(side=tk.LEFT, padx=(12, 0))

        self.sql_tree = self._build_tree_container(self.sql_tab)

    def _build_tree_container(self, parent):
        holder = tk.Frame(parent, bg="#ffffff")
        holder.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        tree = ttk.Treeview(holder, show="headings", selectmode="extended")
        tree.grid(row=0, column=0, sticky="nsew")
        holder.grid_columnconfigure(0, weight=1)
        holder.grid_rowconfigure(0, weight=1)
        y_scroll = ttk.Scrollbar(holder, orient=tk.VERTICAL, command=tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(holder, orient=tk.HORIZONTAL, command=tree.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        return tree

    def _query_rows(self, sql, params=()):
        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            columns = [description[0] for description in cur.description or []]
            rows = cur.fetchall()
            return columns, rows
        finally:
            conn.close()

    def _populate_tree(self, tree, columns, rows):
        tree.delete(*tree.get_children())
        tree["columns"] = list(columns)

        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=150, minwidth=90, anchor="w", stretch=True)

        for row in rows:
            if isinstance(row, sqlite3.Row):
                values = [row[column] for column in columns]
            else:
                values = list(row)
            tree.insert("", tk.END, values=values)

    def _load_named_table(self, tree, sql, empty_message):
        try:
            columns, rows = self._query_rows(sql)
        except Exception as exc:
            self.status_var.set(f"Load failed: {exc}")
            messagebox.showerror("Database Error", str(exc), parent=self.window)
            return

        if not rows:
            columns = columns or ["message"]
            rows = [(empty_message,)]

        self._populate_tree(tree, columns, rows)
        self.status_var.set(f"Loaded {len(rows)} row(s).")

    def _load_overview(self):
        conn = connect()
        try:
            cur = conn.cursor()
            counts = {}
            for table_name in ("products", "sales", "sale_items", "recent_receipts"):
                cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                counts[table_name] = int((cur.fetchone() or [0])[0] or 0)

            cur.execute(
                """
                SELECT
                    COALESCE(SUM(total), 0),
                    COALESCE(SUM(CASE WHEN payment_mode = 'Online' THEN total ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN payment_mode = 'Cash' OR payment_mode IS NULL THEN total ELSE 0 END), 0)
                FROM sales
                """
            )
            totals = cur.fetchone() or (0, 0, 0)
        finally:
            conn.close()

        self.overview_cards["products"].config(text=str(counts["products"]))
        self.overview_cards["sales"].config(text=str(counts["sales"]))
        self.overview_cards["sale_items"].config(text=str(counts["sale_items"]))
        self.overview_cards["receipts"].config(text=str(counts["recent_receipts"]))
        self.overview_summary_var.set(
            "Sales total: "
            f"{float(totals[0] or 0):.2f} | Online: {float(totals[1] or 0):.2f} | Cash: {float(totals[2] or 0):.2f}"
        )

    def _selected_tree_id(self, tree):
        selection = tree.selection()
        if not selection:
            return None
        values = tree.item(selection[0], "values")
        if not values:
            return None
        return values[0]

    def _selected_tree_ids(self, tree):
        selected_ids = []
        for item_id in tree.selection():
            values = tree.item(item_id, "values")
            if not values:
                continue
            try:
                selected_ids.append(int(values[0]))
            except (TypeError, ValueError):
                continue
        return selected_ids

    def select_all_rows(self, tree):
        item_ids = tree.get_children()
        if not item_ids:
            self.status_var.set("No rows available to select.")
            return

        tree.selection_set(item_ids)
        tree.focus(item_ids[0])
        tree.see(item_ids[0])
        self.status_var.set(f"Selected {len(item_ids)} row(s).")

    def add_product_record(self):
        barcode = self.product_barcode_var.get().strip()
        name = self.product_name_var.get().strip()
        if not name:
            messagebox.showwarning("Missing Name", "Product name is required.", parent=self.window)
            return

        try:
            price = float(self.product_price_var.get().strip())
            stock = int(self.product_stock_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Data", "Price must be numeric and stock must be a whole number.", parent=self.window)
            return

        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO products(barcode, name, price, stock) VALUES(?,?,?,?)",
                (barcode or None, name, price, stock),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            messagebox.showerror("Duplicate Barcode", "This barcode already exists in products.", parent=self.window)
            return
        finally:
            conn.close()

        self.product_barcode_var.set("")
        self.product_name_var.set("")
        self.product_price_var.set("0")
        self.product_stock_var.set("0")
        self.load_products()
        self._notify_data_changed("Product added.")

    def delete_selected_product(self):
        product_ids = self._selected_tree_ids(self.products_tree)
        if not product_ids:
            self.status_var.set("Select one or more product rows first.")
            return

        confirmed = messagebox.askyesno(
            "Delete Product",
            f"Delete {len(product_ids)} selected product record(s)?",
            parent=self.window,
        )
        if not confirmed:
            return

        conn = connect()
        try:
            cur = conn.cursor()
            cur.executemany("DELETE FROM products WHERE id = ?", [(product_id,) for product_id in product_ids])
            conn.commit()
        finally:
            conn.close()

        self.load_products()
        self._load_overview()
        self._notify_data_changed(f"Deleted {len(product_ids)} product(s).")

    def delete_selected_sale(self):
        sale_ids = self._selected_tree_ids(self.sales_tree)
        if not sale_ids:
            self.status_var.set("Select one or more sale rows first.")
            return

        confirmed = messagebox.askyesno(
            "Delete Sale",
            f"Delete {len(sale_ids)} selected sale record(s), linked sale items, and receipt entries?",
            parent=self.window,
        )
        if not confirmed:
            return

        conn = connect()
        try:
            cur = conn.cursor()
            cur.executemany("DELETE FROM recent_receipts WHERE sale_id = ?", [(sale_id,) for sale_id in sale_ids])
            cur.executemany("DELETE FROM sale_items WHERE sale_id = ?", [(sale_id,) for sale_id in sale_ids])
            cur.executemany("DELETE FROM sales WHERE id = ?", [(sale_id,) for sale_id in sale_ids])
            conn.commit()
        finally:
            conn.close()

        self.load_sales()
        self.load_receipts()
        self._load_overview()
        self._notify_data_changed(f"Deleted {len(sale_ids)} sale(s).")

    def delete_selected_receipt(self):
        receipt_ids = self._selected_tree_ids(self.receipts_tree)
        if not receipt_ids:
            self.status_var.set("Select one or more receipt rows first.")
            return

        confirmed = messagebox.askyesno(
            "Delete Receipt",
            f"Delete {len(receipt_ids)} selected receipt log row(s)?",
            parent=self.window,
        )
        if not confirmed:
            return

        conn = connect()
        try:
            cur = conn.cursor()
            cur.executemany("DELETE FROM recent_receipts WHERE id = ?", [(receipt_id,) for receipt_id in receipt_ids])
            conn.commit()
        finally:
            conn.close()

        self.load_receipts()
        self._load_overview()
        self._notify_data_changed(f"Deleted {len(receipt_ids)} receipt row(s).")

    def import_products_file(self):
        pd = self._load_pandas()
        if pd is None:
            return

        path = filedialog.askopenfilename(
            parent=self.window,
            title="Import Product File",
            initialdir=_default_dialog_dir(),
            filetypes=[
                ("CSV Files", "*.csv"),
                ("Excel Files", "*.xlsx *.xls"),
                ("All Supported", "*.csv *.xlsx *.xls"),
            ],
        )
        if not path:
            return

        file_path = Path(path)
        try:
            if file_path.suffix.lower() == ".csv":
                data_frame = pd.read_csv(file_path)
            else:
                data_frame = pd.read_excel(file_path)
        except Exception as exc:
            messagebox.showerror("Import Failed", str(exc), parent=self.window)
            return

        normalized_map = {str(column).strip().lower(): column for column in data_frame.columns}
        required = ("name", "price", "stock")
        missing = [column for column in required if column not in normalized_map]
        if missing:
            messagebox.showerror(
                "Import Failed",
                f"Missing required columns: {', '.join(missing)}. Use columns: barcode, name, price, stock.",
                parent=self.window,
            )
            return

        barcode_column = normalized_map.get("barcode")
        name_column = normalized_map["name"]
        price_column = normalized_map["price"]
        stock_column = normalized_map["stock"]

        imported = 0
        updated = 0
        conn = connect()
        try:
            cur = conn.cursor()
            for _, row in data_frame.fillna("").iterrows():
                name = str(row[name_column]).strip()
                if not name:
                    continue
                barcode = str(row[barcode_column]).strip() if barcode_column else ""
                try:
                    price = float(row[price_column])
                    stock = int(float(row[stock_column]))
                except Exception:
                    continue

                if barcode:
                    cur.execute("SELECT id FROM products WHERE barcode = ?", (barcode,))
                    existing = cur.fetchone()
                    if existing:
                        cur.execute(
                            "UPDATE products SET name = ?, price = ?, stock = ? WHERE barcode = ?",
                            (name, price, stock, barcode),
                        )
                        updated += 1
                    else:
                        cur.execute(
                            "INSERT INTO products(barcode, name, price, stock) VALUES(?,?,?,?)",
                            (barcode, name, price, stock),
                        )
                        imported += 1
                else:
                    cur.execute(
                        "INSERT INTO products(barcode, name, price, stock) VALUES(?,?,?,?)",
                        (None, name, price, stock),
                    )
                    imported += 1
            conn.commit()
        except Exception as exc:
            conn.rollback()
            messagebox.showerror("Import Failed", str(exc), parent=self.window)
            return
        finally:
            conn.close()

        self.load_products()
        self._load_overview()
        self._notify_data_changed(f"Imported {imported} product(s), updated {updated}.")

    def export_tree(self, tree, default_name):
        pd = self._load_pandas()
        if pd is None:
            return

        rows = [tree.item(item_id, "values") for item_id in tree.get_children()]
        columns = list(tree["columns"])
        if not columns:
            self.status_var.set("Nothing to export.")
            return

        save_path = filedialog.asksaveasfilename(
            parent=self.window,
            title="Export Data",
            initialdir=_default_dialog_dir(),
            initialfile=f"{default_name}.csv",
            defaultextension=".csv",
            filetypes=[
                ("CSV Files", "*.csv"),
                ("Excel Files", "*.xlsx"),
            ],
        )
        if not save_path:
            return

        data_frame = pd.DataFrame(rows, columns=columns)
        try:
            if str(save_path).lower().endswith(".xlsx"):
                data_frame.to_excel(save_path, index=False)
            else:
                data_frame.to_csv(save_path, index=False)
        except Exception as exc:
            messagebox.showerror("Export Failed", str(exc), parent=self.window)
            return

        self.status_var.set(f"Exported data to {save_path}")

    def export_sales_report(self):
        try:
            from features.export_excel import export_sales
        except Exception as exc:
            messagebox.showerror(
                "Dependency Missing",
                f"Sales export needs pandas and Excel support in this Python environment.\n\nDetails: {exc}",
                parent=self.window,
            )
            return

        output_dir = filedialog.askdirectory(
            parent=self.window,
            title="Select Folder For Sales Report",
            initialdir=_default_dialog_dir(),
        )
        if not output_dir:
            return
        try:
            output_path = export_sales(output_dir=output_dir)
        except Exception as exc:
            messagebox.showerror("Export Failed", str(exc), parent=self.window)
            return
        self.status_var.set(f"Sales report saved: {output_path}")

    def download_database_copy(self):
        save_path = filedialog.asksaveasfilename(
            parent=self.window,
            title="Save Database Copy",
            initialdir=_default_dialog_dir(),
            initialfile="pos_backup.db",
            defaultextension=".db",
            filetypes=[("SQLite Database", "*.db"), ("All Files", "*.*")],
        )
        if not save_path:
            return

        try:
            shutil.copy2(DB_PATH, save_path)
        except Exception as exc:
            messagebox.showerror("Copy Failed", str(exc), parent=self.window)
            return
        self.status_var.set(f"Database copied to {save_path}")

    def run_sql(self):
        sql = self.sql_text.get("1.0", tk.END).strip()
        if not sql:
            self.sql_result_meta.set("Enter a SQL statement first.")
            return

        conn = connect()
        try:
            cur = conn.cursor()
            leading = sql.lstrip().split(None, 1)[0].lower() if sql.split() else ""
            if leading in {"select", "pragma", "with", "explain"}:
                cur.execute(sql)
                columns = [description[0] for description in cur.description or []]
                rows = cur.fetchall()
                if not rows:
                    columns = columns or ["message"]
                    rows = [("Query returned no rows.",)]
                self._populate_tree(self.sql_tree, columns, rows)
                self.sql_result_meta.set(f"Query returned {len(rows)} row(s).")
            else:
                cur.executescript(sql)
                conn.commit()
                self._populate_tree(self.sql_tree, ["message"], [("Statement executed successfully.",)])
                self.sql_result_meta.set("Update committed to the local database.")
                self.refresh_all()
                self._notify_data_changed("SQL update committed.")
        except Exception as exc:
            conn.rollback()
            self.sql_result_meta.set(f"SQL error: {exc}")
            messagebox.showerror("SQL Error", str(exc), parent=self.window)
        finally:
            conn.close()

    def load_products(self):
        self._load_named_table(
            self.products_tree,
            """
            SELECT id, barcode, name, price, stock
            FROM products
            ORDER BY name COLLATE NOCASE, id DESC
            LIMIT 500
            """,
            empty_message="No products found.",
        )

    def load_sales(self):
        self._load_named_table(
            self.sales_tree,
            """
            SELECT id, date, total, payment_mode
            FROM sales
            ORDER BY id DESC
            LIMIT 500
            """,
            empty_message="No sales found.",
        )

    def load_receipts(self):
        self._load_named_table(
            self.receipts_tree,
            """
            SELECT id, created_at, sale_id, line_text
            FROM recent_receipts
            ORDER BY id DESC
            LIMIT 500
            """,
            empty_message="No receipts found.",
        )

    def _notify_data_changed(self, status_text):
        self.status_var.set(status_text)
        if callable(self.on_data_changed):
            self.on_data_changed()

    def refresh_all(self):
        self._load_overview()
        self.load_products()
        self.load_sales()
        self.load_receipts()


def open_admin_panel(parent, on_data_changed=None):
    return AdminPanelWindow(parent, on_data_changed=on_data_changed)
