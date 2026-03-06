import matplotlib.pyplot as plt
from database import connect


def show_sales_graph():
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT date, ROUND(SUM(total), 2) AS daily_total
            FROM sales
            GROUP BY date
            ORDER BY date
            """
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        raise ValueError("No sales data available to plot.")

    dates = [r[0] for r in rows]
    totals = [float(r[1]) for r in rows]

    plt.figure(figsize=(9, 4.5))
    plt.plot(dates, totals, marker="o", linewidth=2, color="#0a7cff")
    plt.title("Daily Sales Trend")
    plt.xlabel("Date")
    plt.ylabel("Total Sales")
    plt.grid(alpha=0.25, linestyle="--")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()

    plt.show()
