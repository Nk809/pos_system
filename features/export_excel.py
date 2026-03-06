from datetime import datetime
from pathlib import Path

import pandas as pd
from database import connect


def export_sales(output_dir=None):
    conn = connect()
    try:
        sales_df = pd.read_sql_query(
            """
            SELECT id, date, total, COALESCE(payment_mode, 'Cash') AS payment_mode
            FROM sales
            ORDER BY date, id
            """,
            conn,
        )

        sale_items_df = pd.read_sql_query(
            """
            SELECT
                si.id,
                si.sale_id,
                s.date AS sale_date,
                si.product_id,
                COALESCE(p.name, '') AS product_name,
                COALESCE(p.barcode, '') AS barcode,
                si.quantity,
                si.price,
                ROUND(si.quantity * si.price, 2) AS line_total
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            LEFT JOIN products p ON p.id = si.product_id
            ORDER BY si.sale_id, si.id
            """,
            conn,
        )

        daily_df = pd.read_sql_query(
            """
            SELECT
                date,
                COUNT(*) AS bills,
                ROUND(SUM(total), 2) AS total_sales,
                ROUND(SUM(CASE WHEN payment_mode = 'Online' THEN total ELSE 0 END), 2) AS online_sales,
                ROUND(SUM(CASE WHEN payment_mode = 'Cash' OR payment_mode IS NULL THEN total ELSE 0 END), 2) AS cash_sales
            FROM sales
            GROUP BY date
            ORDER BY date
            """,
            conn,
        )

        product_summary_df = pd.read_sql_query(
            """
            SELECT
                si.product_id,
                CASE
                    WHEN p.name IS NULL OR TRIM(p.name) = '' THEN 'Unknown Product'
                    ELSE p.name
                END AS product_name,
                COALESCE(p.barcode, '') AS barcode,
                SUM(si.quantity) AS total_qty_sold,
                ROUND(SUM(si.quantity * si.price), 2) AS total_amount,
                ROUND(AVG(si.price), 2) AS avg_unit_price,
                COUNT(DISTINCT si.sale_id) AS bills_count,
                MIN(s.date) AS first_sale_date,
                MAX(s.date) AS last_sale_date
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            LEFT JOIN products p ON p.id = si.product_id
            GROUP BY si.product_id, p.name, p.barcode
            ORDER BY total_qty_sold DESC, product_name
            """,
            conn,
        )

        product_count_df = pd.read_sql_query(
            """
            SELECT
                CASE
                    WHEN p.name IS NULL OR TRIM(p.name) = '' THEN 'Unknown Product'
                    ELSE p.name
                END AS product_name,
                SUM(si.quantity) AS number_of_products_sold
            FROM sale_items si
            LEFT JOIN products p ON p.id = si.product_id
            GROUP BY p.name
            ORDER BY number_of_products_sold DESC, product_name
            """,
            conn,
        )
    finally:
        conn.close()

    target_dir = Path(output_dir) if output_dir else Path.cwd()
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"sales_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    output_path = target_dir / filename

    with pd.ExcelWriter(output_path) as writer:
        product_count_df.to_excel(writer, sheet_name="ProductSold", index=False)
        sales_df.to_excel(writer, sheet_name="Sales", index=False)
        sale_items_df.to_excel(writer, sheet_name="SaleItems", index=False)
        daily_df.to_excel(writer, sheet_name="DailySummary", index=False)
        product_summary_df.to_excel(writer, sheet_name="ProductSummary", index=False)

    return str(output_path)
