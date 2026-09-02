import datetime
import requests
import base64
import tkinter as tk
from tkinter import ttk
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization

# ==========================================
# CONFIGURATION
# ==========================================
KALSHI_KEY_ID = "59502368-e6d9-4b89-9840-f877731e4329"
PRIVATE_KEY_PATH = "MCMOL.key"
REFRESH_RATE_MS = 10000  # 10 seconds in milliseconds


def get_auth_headers(method, path):
    """Generates the RSA cryptographic signature required by Kalshi V2."""
    timestamp = str(int(datetime.datetime.now().timestamp() * 1000))
    try:
        with open(PRIVATE_KEY_PATH, "rb") as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(), password=None)

        msg_string = timestamp + method + path
        signature = private_key.sign(
            msg_string.encode('utf-8'),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        return {
            "KALSHI-ACCESS-KEY": KALSHI_KEY_ID,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode('utf-8'),
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json"
        }
    except FileNotFoundError:
        return None


def fetch_portfolio_data():
    """Pulls live balance and open positions from Kalshi."""
    bal_path = "/trade-api/v2/portfolio/balance"
    pos_path = "/trade-api/v2/portfolio/positions"

    bal_headers = get_auth_headers("GET", bal_path)
    pos_headers = get_auth_headers("GET", pos_path)

    if not bal_headers or not pos_headers:
        return None, "Error: Private key file (MCMOL.key) not found."

    try:
        bal_resp = requests.get(
            f"https://external-api.kalshi.com{bal_path}", headers=bal_headers, timeout=10)
        bal_resp.raise_for_status()
        balance_cents = bal_resp.json().get('balance', 0)

        pos_resp = requests.get(
            f"https://external-api.kalshi.com{pos_path}", headers=pos_headers, timeout=10)
        pos_resp.raise_for_status()

        # ⚠️ FIXED: Kalshi V2 uses 'market_positions', not 'positions'
        positions = pos_resp.json().get('market_positions', [])

        return balance_cents / 100.0, positions

    except requests.exceptions.RequestException as e:
        error_msg = e.response.text if hasattr(
            e, 'response') and e.response is not None else str(e)
        return None, f"Server Rejection: {error_msg}"
    except Exception as e:
        return None, f"Local Processing Error: {str(e)}"

# ==========================================
# GUI APPLICATION (TKINTER)
# ==========================================


def update_dashboard():
    """Fetches new data and updates the GUI elements without freezing the window."""
    balance, positions = fetch_portfolio_data()
    current_time = datetime.datetime.now().strftime("%I:%M:%S %p")

    lbl_last_update.config(text=f"Last Update: {current_time}")

    if balance is None:
        # positions holds the error string here
        lbl_error.config(text=str(positions))
        lbl_balance.config(text="💰 Balance: $--.--")
    else:
        lbl_error.config(text="")
        lbl_balance.config(text=f"💰 Available Liquid Balance: ${balance:,.2f}")

        # Clear existing rows in the table
        for row in tree.get_children():
            tree.delete(row)

        # ⚠️ FIXED: V2 uses 'position_fp' as a fixed-point string, not an integer
        active_positions = [p for p in positions if float(
            p.get('position_fp', 0)) != 0]
        total_invested = 0

        if not active_positions:
            tree.insert("", "end", values=(
                "No active positions", "-", "-", "-"))
        else:
            for p in active_positions:
                ticker = p.get('ticker', 'UNKNOWN')

                # Convert the V2 fixed-point string to an integer count
                count = int(float(p.get('position_fp', 0)))

                # ⚠️ FIXED: V2 returns financials as pre-formatted dollar strings
                pos_cost = float(p.get('market_exposure_dollars', 0))
                realized_pnl = float(p.get('realized_pnl_dollars', 0))

                total_invested += pos_cost
                tree.insert("", "end", values=(ticker, count,
                            f"${pos_cost:,.2f}", f"${realized_pnl:,.2f}"))

        lbl_total.config(
            text=f"TOTAL CAPITAL DEPLOYED: ${total_invested:,.2f}")

    # Schedule the next update
    root.after(REFRESH_RATE_MS, update_dashboard)


# Initialize main window
root = tk.Tk()
root.title("Kalshi Live Portfolio")
root.geometry("650x400")
root.configure(padx=20, pady=20)

# Header Elements
lbl_title = tk.Label(
    root, text="📈 Kalshi Live Portfolio Dashboard", font=("Arial", 18, "bold"))
lbl_title.pack(anchor="w")

lbl_last_update = tk.Label(
    root, text="Last Update: --:--:--", font=("Arial", 12), fg="gray")
lbl_last_update.pack(anchor="w", pady=(0, 10))

lbl_balance = tk.Label(root, text="💰 Available Liquid Balance: $--.--",
                       font=("Arial", 14, "bold"), fg="#2E7D32")
lbl_balance.pack(anchor="w", pady=(0, 5))

lbl_error = tk.Label(root, text="", font=("Arial", 10), fg="red")
lbl_error.pack(anchor="w")

# Data Table (Treeview)
columns = ("ticker", "contracts", "cost", "pnl")
tree = ttk.Treeview(root, columns=columns, show="headings", height=8)

tree.heading("ticker", text="MARKET TICKER")
tree.column("ticker", width=250, anchor="w")

tree.heading("contracts", text="CONTRACTS")
tree.column("contracts", width=100, anchor="center")

tree.heading("cost", text="POS COST")
tree.column("cost", width=100, anchor="e")

tree.heading("pnl", text="REALIZED P&L")
tree.column("pnl", width=120, anchor="e")

tree.pack(fill="x", pady=10)

# Footer Element
lbl_total = tk.Label(
    root, text="TOTAL CAPITAL DEPLOYED: $--.--", font=("Arial", 12, "bold"))
lbl_total.pack(anchor="e")

# Start the auto-update loop
root.after(0, update_dashboard)

# Run the application
root.mainloop()
