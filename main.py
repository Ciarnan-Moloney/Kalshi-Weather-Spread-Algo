import time
import datetime
import uuid
import re
import requests
import base64
import traceback
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization

import weather_api

# ==========================================
# 1. BOT CONFIGURATION & RISK LIMITS
# ==========================================
KALSHI_KEY_ID = "59502368-e6d9-4b89-9840-f877731e4329"
PRIVATE_KEY_PATH = "MCMOL.key"

ACTIVE_MARKETS = ["Chicago", "Miami", "Phoenix", "LAX", "Vegas", "Austin"]

MIN_EDGE_REQUIRED = 0.05
MAX_PAIRS_PER_TRADE = 5
ACCOUNT_BANKROLL = 500.00

KALSHI_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

# ==========================================
# 2. HELPER FUNCTIONS & AUTHENTICATION
# ==========================================


def calculate_fee(price, contracts):
    return 0.07 * price * (1 - price) * contracts


def extract_bracket_midpoint(title):
    """Safely extracts the temperature midpoint by stripping out the trailing date."""
    if "on " in title:
        title_clean = title.split("on ")[0]
    else:
        title_clean = title

    numbers = [int(n) for n in re.findall(r'\d+', title_clean)]

    if not numbers:
        return None

    if len(numbers) >= 2:
        return (numbers[0] + numbers[1]) / 2.0

    if "<" in title_clean or "below" in title_clean.lower():
        return numbers[0] - 1.0
    if ">" in title_clean or "above" in title_clean.lower() or "+" in title_clean:
        return numbers[0] + 1.0

    return numbers[0]


def get_auth_headers(method, path):
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
        print(f"❌ Error: Could not find private key at '{PRIVATE_KEY_PATH}'.")
        return None

# ==========================================
# 3. GUARDED PAIR SPREAD EXECUTION
# ==========================================


def evaluate_and_trade():
    print("\n📡 Scanning Kalshi and Aviation Feeds for real-time weather...")

    kalshi_prefixes = {
        "Chicago": "KXHIGHCHI",
        "Miami": "KXHIGHMIA",
        "Phoenix": "KXHIGHTPHX",
        "LAX": "KXHIGHLAX",
        "Vegas": "KXHIGHTLV",
        "Austin": "KXHIGHAUS"
    }

    date_code = datetime.datetime.now().strftime("%y%b%d").upper()

    for city in ACTIVE_MARKETS:
        print(f"\n--- Evaluating {city} ---")

        # 1. Pull predictive criteria from the low-latency aviation model
        try:
            model_result = weather_api.get_market_probability(city)
        except Exception as e:
            print(f"❌ Crash inside weather_api.py for {city}:")
            traceback.print_exc()
            continue

        if model_result is None:
            print(
                f"⚠️ Aviation feed returned None for {city}. Skipping station.")
            continue

        true_prob = model_result['probability']
        forecast_max = model_result['forecast_max']

        print(f"✈️ Live Airport Sensor High: {forecast_max}°F")
        print(f"🧠 Model True Probability: {true_prob * 100:.1f}%")

        # 2. Fetch specific Kalshi Event Ticker
        target_event_ticker = f"{kalshi_prefixes[city]}-{date_code}"

        try:
            url = f"{KALSHI_BASE_URL}/markets?event_ticker={target_event_ticker}"
            resp = requests.get(url)
            resp.raise_for_status()
            raw_markets = resp.json().get('markets', [])
            city_markets = [m for m in raw_markets if m.get('status') in [
                'active', 'open']]
        except Exception as e:
            print(
                f"❌ Error fetching Kalshi markets for {target_event_ticker}: {e}")
            continue

        if len(city_markets) < 2:
            print(
                f"❌ Insufficient active brackets found for ticker: {target_event_ticker}")
            continue

        # 3. Sort brackets using clean temperature midpoints
        markets_with_midpoints = []
        for m in city_markets:
            mid = extract_bracket_midpoint(m['title'])
            if mid is not None:
                distance = abs(mid - forecast_max)
                markets_with_midpoints.append((distance, m))

        if len(markets_with_midpoints) < 2:
            print(
                f"❌ Failure extracting numerical ranges from brackets for {city}.")
            continue

        # Sort strictly by closest distance to the live airport station temperature
        markets_with_midpoints.sort(key=lambda x: x[0])
        target_pair = [markets_with_midpoints[0]
                       [1], markets_with_midpoints[1][1]]

        print(
            f"🎯 Target Pair Locked: '{target_pair[0]['title']}' AND '{target_pair[1]['title']}'")

        # 4. Request orderbook depth for both legs
        leg_1_ticker = target_pair[0]['ticker']
        leg_2_ticker = target_pair[1]['ticker']

        try:
            ob_1_resp = requests.get(
                f"{KALSHI_BASE_URL}/markets/{leg_1_ticker}/orderbook")
            ob_2_resp = requests.get(
                f"{KALSHI_BASE_URL}/markets/{leg_2_ticker}/orderbook")

            ob_1_fp = ob_1_resp.json().get('orderbook_fp', {})
            ob_2_fp = ob_2_resp.json().get('orderbook_fp', {})

            def get_v2_yes_ask(ob):
                """Calculates the YES Ask from the NO Bids in the Kalshi V2 fixed-point orderbook."""
                no_bids = ob.get('no_dollars', [])
                if not no_bids:
                    return None, 0

                best_no_bid_price = float(no_bids[-1][0])
                best_no_bid_vol = float(no_bids[-1][1])

                yes_ask_cents = round((1.0 - best_no_bid_price) * 100.0, 2)
                return yes_ask_cents, int(best_no_bid_vol)

            leg_1_ask, leg_1_vol = get_v2_yes_ask(ob_1_fp)
            leg_2_ask, leg_2_vol = get_v2_yes_ask(ob_2_fp)

        except Exception as e:
            print(f"❌ Error getting orderbooks: {e}")
            continue

        if leg_1_ask is None or leg_2_ask is None:
            print(f"📉 Missing liquidity on one or both legs. Spread build halted.")
            continue

        # 5. Synthetic Pricing & Edge
        available_spread_volume = min(leg_1_vol, leg_2_vol)
        if available_spread_volume == 0:
            print(f"📉 Spread Volume bottlenecked at 0.")
            continue

        implied_prob_1 = leg_1_ask / 100.0
        implied_prob_2 = leg_2_ask / 100.0

        cost_1 = implied_prob_1 + calculate_fee(implied_prob_1, 1)
        cost_2 = implied_prob_2 + calculate_fee(implied_prob_2, 1)

        synthetic_cost = cost_1 + cost_2
        synthetic_prob = implied_prob_1 + implied_prob_2
        edge = true_prob - synthetic_cost

        print(
            f"📊 Leg 1: {leg_1_ask}¢ | Leg 2: {leg_2_ask}¢ | Available Vol: {available_spread_volume}")
        print(f"💵 Total Synthetic Cost w/ Fees: ${(synthetic_cost):.4f}")
        print(f"📈 Mathematical Edge: {edge * 100:.1f}%")

        # 6. Kelly Risk Allocation Management
        if edge >= MIN_EDGE_REQUIRED:
            kelly_fraction = edge / (1 - synthetic_prob)
            quarter_kelly = kelly_fraction / 4.0
            target_risk_dollars = ACCOUNT_BANKROLL * quarter_kelly
            calculated_contracts = int(target_risk_dollars / synthetic_cost)

            final_contract_count = int(
                min(calculated_contracts, MAX_PAIRS_PER_TRADE, available_spread_volume))

            if final_contract_count < 1:
                print(f"⚠️ Insufficient edge/unit scale to buy a contract pair.")
                continue

            print(
                f"🔥 EDGE DETECTED! Kelly risk allocation: ${target_risk_dollars:.2f}.")
            print(
                f"📝 SUBMITTING TRADES: Buying {final_contract_count} YES pairs at raw price of {(implied_prob_1+implied_prob_2)*100}¢.")

            # --- LIVE TRADING ROUTINE ---
            for ticker, ask_price in [(leg_1_ticker, leg_1_ask), (leg_2_ticker, leg_2_ask)]:
                try:
                    payload = {
                        "ticker": ticker,
                        "side": "bid",  # 'bid' means buy YES in Kalshi V2 event markets
                        "count": str(final_contract_count),
                        # Formats cleanly to 4 decimal places
                        "price": f"{ask_price / 100.0:.4f}",
                        "time_in_force": "good_till_canceled",
                        "self_trade_prevention_type": "taker_at_cross",
                        "client_order_id": str(uuid.uuid4())
                    }

                    path = "/trade-api/v2/portfolio/events/orders"
                    auth_headers = get_auth_headers("POST", path)

                    if auth_headers:
                        url = f"https://external-api.kalshi.com{path}"
                        resp = requests.post(
                            url, headers=auth_headers, json=payload)
                        resp.raise_for_status()
                        print(f"✅ Executed leg: {ticker} at {ask_price}¢")

                except Exception as e:
                    print(f"❌ Failed leg {ticker}: {e}")
                    if hasattr(e, 'response') and e.response is not None:
                        print(f"Server rejection: {e.response.text}")


# ==========================================
# 4. THE MASTER LOOP (24/7 Mode)
# ==========================================
if __name__ == "__main__":
    print("🚀 Starting Weather Spread Bot (Low-Latency Aviation Edition)...")

    try:
        with open(PRIVATE_KEY_PATH, "rb") as f:
            print(
                "✅ Private key detected. System initialized and reading FAA data feeds.")
    except FileNotFoundError:
        print(
            f"⚠️ Warning: Cannot find {PRIVATE_KEY_PATH}. Running on backup.")

    while True:
        evaluate_and_trade()
        print("\n💤 Bot is active 24/7. Sleeping for 5 minutes before next scan...\n")
        time.sleep(300)
