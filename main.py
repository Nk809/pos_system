import tkinter as tk
from database import create_tables
from ui.billing_ui import BillingUI

# sqlite-web support is optional; the feature module encapsulates the
# startup logic and prints a user-friendly message.
from features.sqlite_web import start_sqlite_web


def main():
    create_tables()

    # optionally start the sqlite-web browser in the background.  failing to
    # start it is non‑fatal (e.g. package not installed), so we simply print
    # any error message and continue.
    web = start_sqlite_web()
    if web.get("success"):
        print(f"SQLite browser running at {web['url']}")
    else:
        # message key may be absent in weird cases
        print(f"SQLite browser not available: {web.get('message', 'unknown error')}")

    root = tk.Tk()
    root.title("Matchless Gift ISKCON BURLA")
    print("Offline mode enabled: desktop scanner and local printer routes only.")
    BillingUI(root, sqlite_web=web)

    root.mainloop()


if __name__ == "__main__":
    main()
