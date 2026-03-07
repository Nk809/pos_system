import tkinter as tk
from database import create_tables
from ui.billing_ui import BillingUI
from features.phone_bridge import start_phone_bridge

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

    # start phone bridge if configured
    bridge = start_phone_bridge()

    root = tk.Tk()
    root.title("Matchless Gift ISKCON BURLA")

    if not bridge["success"]:
        print(bridge["message"])
        BillingUI(root)
    else:
        if bridge.get("message"):
            print(bridge["message"])
        print(f"Phone bridge ready at: {bridge['url']}")
        # also mention alternate http URL if running https
        if bridge.get("url", "").startswith("https://"):
            alt = "http://" + bridge["url"][8:]
            print(f"(Try HTTP if your device cannot reach HTTPS: {alt})")
        BillingUI(root)

    root.mainloop()


if __name__ == "__main__":
    main()
