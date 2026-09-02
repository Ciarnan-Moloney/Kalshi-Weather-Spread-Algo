import asyncio
import json
import websockets
import math


class KalshiMarketMaker:
    def __init__(self, ticker, target_spread=0.02, skew_aggressiveness=0.005):
        self.ticker = ticker

        # Strategy Parameters
        self.target_spread = target_spread  # 2 cents default
        # How much to shift price per 100 contracts
        self.skew_aggressiveness = skew_aggressiveness

        # State Tracking
        self.inventory_yes = 0  # Positive = Long Yes, Negative = Long No
        self.bids = {}  # Local order book state (Price -> Quantity)
        self.asks = {}

    async def connect_and_listen(self):
        """
        Connects to Kalshi's WebSocket to receive millisecond updates.
        Note: Requires API authentication headers in production.
        """
        ws_url = "wss://api.elections.kalshi.com/trade-api/ws/v2"

        print(f"Connecting to Kalshi WebSocket for {self.ticker}...")

        # In a real bot, you must pass your Kalshi API signature in the headers here
        async with websockets.connect(ws_url) as ws:

            # Subscribe to the order book delta channel
            sub_msg = {
                "id": 1,
                "cmd": "subscribe",
                "params": {
                    "channels": ["orderbook_delta"],
                    "market_ticker": self.ticker
                }
            }
            await ws.send(json.dumps(sub_msg))

            while True:
                response = await ws.recv()
                data = json.loads(response)

                # Route the message
                if data.get("type") == "orderbook_snapshot":
                    self._process_snapshot(data)
                    self.recalculate_and_quote()

                elif data.get("type") == "orderbook_delta":
                    self._process_delta(data)
                    self.recalculate_and_quote()

    def _process_snapshot(self, data):
        """Builds the initial state of the order book"""
        print("Received full book snapshot.")

        # 1. Clear previous local book state
        self.bids.clear()
        self.asks.clear()

        # 2. Parse the YES bids (Buyers wanting to buy YES)
        # The data looks like: [["0.4000", "500.00"], ["0.3900", "1200.00"]]
        for price_str, qty_str in data.get("yes_dollars_fp", []):
            price = float(price_str)
            qty = float(qty_str)
            self.bids[price] = qty

        # 3. Parse the NO bids (Buyers wanting to buy NO)
        # CRITICAL: In Kalshi, a bid for NO at $0.60 is exactly the same as an ASK for YES at $0.40.
        # To keep our bot's logic simple, we convert NO bids into YES asks.
        for price_str, qty_str in data.get("no_dollars_fp", []):
            no_price = float(price_str)
            yes_ask_price = round(1.0 - no_price, 2)
            qty = float(qty_str)
            self.asks[yes_ask_price] = qty

    def _process_delta(self, data):
        """Updates the local book with incremental changes (faster than snapshots)"""
        # Example: Someone bought 10 contracts at 0.42, update self.bids/asks instantly
        pass

    def recalculate_and_quote(self):
        """
        The Brain of the Bot. 
        Calculates Fair Price, applies Inventory Skew, and determines new quotes.
        """
        if not self.bids or not self.asks:
            return  # Book isn't built yet

        # 1. Find Best Bid and Ask from local state
        best_bid = max(self.bids.keys())
        best_ask = min(self.asks.keys())

        # 2. Calculate Fair Value (Mid Price)
        fair_price = (best_bid + best_ask) / 2.0

        # 3. Calculate Inventory Skew
        # If we have 200 Yes contracts, math = (200 / 100) * 0.005 = 0.01 (1 cent skew)
        skew_offset = (self.inventory_yes / 100.0) * self.skew_aggressiveness

        # If we are LONG Yes (positive inventory), skew is positive.
        # We SUBTRACT the skew from fair price to lower our quotes and encourage selling.
        skewed_fair_price = fair_price - skew_offset

        # 4. Set New Orders
        my_new_bid = skewed_fair_price - (self.target_spread / 2.0)
        my_new_ask = skewed_fair_price + (self.target_spread / 2.0)

        # Round to nearest penny (Kalshi requirement)
        my_new_bid = round(my_new_bid, 2)
        my_new_ask = round(my_new_ask, 2)

        print(f"\n--- Strategy Update ---")
        print(f"Inventory: {self.inventory_yes} YES")
        print(
            f"Market Mid: ${fair_price:.2f} | Skewed Target: ${skewed_fair_price:.2f}")
        print(
            f"ACTION: Submit Bid @ ${my_new_bid:.2f} | Submit Ask @ ${my_new_ask:.2f}")

        # 5. EXECUTION: Send the REST API calls to cancel old orders and place these new ones

# To run this script:
# bot = KalshiMarketMaker("SOME_TICKER")
# asyncio.run(bot.connect_and_listen())
