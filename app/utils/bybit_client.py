from pybit.unified_trading import HTTP
from app.config import BYBIT_API_KEY, BYBIT_API_SECRET, TESTNET


class BybitClient:
    def __init__(self):
        self.session = HTTP(
            testnet=TESTNET,
            api_key=BYBIT_API_KEY,
            api_secret=BYBIT_API_SECRET,
        )

    def get_server_time(self):
        return self.session.get_server_time()

    def get_tickers(self):
        return self.session.get_tickers(category="linear")


if __name__ == "__main__":
    client = BybitClient()

    print("Server Time:")
    print(client.get_server_time())

    print("\nBTC Ticker:")
    tickers = client.get_tickers()

    for coin in tickers["result"]["list"]:
        if coin["symbol"] == "BTCUSDT":
            print(coin)
            break