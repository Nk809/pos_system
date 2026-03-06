import tkinter as tk
from tkinter import messagebox


def reports_window():
    win = tk.Toplevel()
    win.title("Reports")
    win.geometry("320x150")

    def show_graph_safe():
        try:
            from features.graphs import show_sales_graph
            show_sales_graph()
        except Exception as exc:
            messagebox.showerror("Reports Error", f"Sales graph unavailable: {exc}")

    def export_excel_safe():
        try:
            from features.export_excel import export_sales
            output_path = export_sales()
            messagebox.showinfo("Reports", f"Sales exported to:\n{output_path}")
        except Exception as exc:
            messagebox.showerror("Reports Error", f"Excel export unavailable: {exc}")

    tk.Label(win, text="Reports", font=("Arial", 12, "bold")).pack(pady=(12, 8))
    tk.Button(win, text="Sales Graph", command=show_graph_safe, width=20).pack(pady=4)
    tk.Button(win, text="Export Excel", command=export_excel_safe, width=20).pack(pady=4)
