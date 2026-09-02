import requests
from datetime import datetime
import meteostat as ms


URL = "https://external-api.kalshi.com/trade-api/v2/markets"


def get_live_weather_prices():
    # Define the specific city series you want to track
    # NY = New York, CH = Chicago, AU = Austin, MIA = Miami
    targets = {
        "New York": "KXHIGHNY",
        "Chicago": "KXHIGHCH",
        "Austin": "KXHIGHAU",
        "Miami": "KXHIGHMIA",
        "Las Vegas": "KXHIGHLV"
    }

    print("Fetching live weather markets...\n")

    for city_name, series_ticker in targets.items():
        params = {
            "series_ticker": series_ticker,
            "status": "open",
            "limit": 100
        }

        try:
            response = requests.get(URL, params=params)

            # If the API fails (e.g. 404 or 500), skip to next city
            if response.status_code != 200:
                print(
                    f"Skipping {city_name}: API returned {response.status_code}")
                continue

            data = response.json()
            markets = data.get("markets", [])

            if not markets:
                print(f"No open markets for {city_name} ({series_ticker})")
                continue

            print(f"=== {city_name} Daily Highs ===")

            # Sort by the 'floor_price' so the temperatures appear in order (e.g. >90, >91, >92)
            # We use float() here to prevent the 'str' error if the API sends strings
            markets.sort(key=lambda x: float(x.get("floor_price", 0) or 0))

            for m in markets:
                # 1. SAFELY extract the bid price
                # We prioritize 'yes_bid' (integer cents) because it's always a number.
                # If that's missing, we try 'yes_bid_dollars' but force it to be a float.
                raw_cents = m.get("yes_bid", 0)

                if raw_cents > 0:
                    price = raw_cents / 100.0
                else:
                    # Fallback: convert string price (e.g. "0.05") to float
                    price = float(m.get("yes_bid_dollars", 0.0))

                # Only print markets that actually have a bid (active trading)
                if price > 0:
                    print(
                        f"  {m['ticker']:<15} | {m['title']:<20} | Bid: ${price:.2f}")

            print("-" * 50)

        except Exception as e:
            # This will now print the REAL error, not just 'Network Error'
            print(f"CRASH on {city_name}: {e}")


if __name__ == "__main__":
    get_live_weather_prices()
