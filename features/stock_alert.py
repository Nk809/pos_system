from database import connect

def low_stock():

    conn=connect()
    cur=conn.cursor()

    cur.execute(
    "SELECT name,stock FROM products WHERE stock < 5"
    )

    items=cur.fetchall()

    conn.close()

    return items