import tkinter as tk
from database import create_tables
from ui.billing_ui import BillingUI
from features.phone_bridge import start_phone_bridge

create_tables()
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
    BillingUI(root)

root.mainloop()
