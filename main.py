import tkinter as tk
from database import create_tables
from ui.billing_ui import BillingUI
from features.phone_bridge import start_phone_bridge

create_tables()
# start bridge; prefer https but fall back to http if necessary
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
