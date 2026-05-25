import ccxt
import pandas as pd
import pandas_ta as ta
import time
import datetime
import requests
import os
from dotenv import load_dotenv


# ==========================================
# Security and settings
# ==========================================
load_dotenv()

API_KEY = os.getenv("BITGET_API_KEY")
SECRET_KEY = os.getenv("BITGET_SECRET_KEY")
PASSPHRASE = os.getenv("BITGET_PASSPHRASE")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not API_KEY or not SECRET_KEY:
    print("Error: check your .env settings.")
    exit()


# ==========================================
# Champion strategy parameters
# ==========================================
SYMBOL = "BTC/USDT:USDT"
TIMEFRAME = "1h"
LEVERAGE = 5
USDT_USAGE = 0.98

# Indicators
SHORT_MA = 60
LONG_MA = 80
ADX_THRESHOLD = 25

# Fixed stop-loss / take-profit based on price move before leverage.
# 5x leverage example: price -3% ~= account -15%, price +26% ~= account +130%.
SL_PCT = 0.03
TP_PCT = 0.26


# ==========================================
# Bitget connection and Telegram
# ==========================================
bitget = ccxt.bitget(
    {
        "apiKey": API_KEY,
        "secret": SECRET_KEY,
        "password": PASSPHRASE,
        "options": {"defaultType": "future"},
        "enableRateLimit": True,
    }
)


def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": message}
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram send failed: {e}")


def initial_setup():
    try:
        bitget.set_margin_mode("isolated", SYMBOL)
        bitget.set_leverage(LEVERAGE, SYMBOL)
        bitget.set_position_mode(False, SYMBOL)
        print(f"Initial setup complete: isolated/{LEVERAGE}x/one-way")
    except Exception as e:
        print(f"Initial setup warning, possibly already configured: {e}")


# ==========================================
# Data fetch and indicator calculation
# ==========================================
def fetch_data():
    try:
        ohlcv = bitget.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=200)
        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")

        df["MA_Short"] = df["close"].rolling(window=SHORT_MA).mean()
        df["MA_Long"] = df["close"].rolling(window=LONG_MA).mean()
        df["ADX"] = df.ta.adx(length=14)["ADX_14"]

        return df
    except Exception as e:
        print(f"Data fetch failed: {e}")
        return None


def get_balance():
    try:
        bal = bitget.fetch_balance()
        return bal["USDT"]["free"]
    except Exception:
        return 0


def get_position():
    try:
        positions = bitget.fetch_positions([SYMBOL])
        for p in positions:
            if p["contracts"] > 0:
                return {
                    "side": p["side"],
                    "amount": float(p["contracts"]),
                    "entry_price": float(p["entryPrice"]),
                    "unrealized_pnl": float(p["unrealizedPnl"]),
                }
        return None
    except Exception:
        return None


# ==========================================
# Order execution
# ==========================================
def close_position(position, reason):
    try:
        side = "sell" if position["side"] == "long" else "buy"
        bitget.create_market_order(
            SYMBOL, side, position["amount"], params={"reduceOnly": True}
        )

        roi = "N/A"
        try:
            margin = (position["entry_price"] * position["amount"]) / LEVERAGE
            roi_val = (position["unrealized_pnl"] / margin) * 100
            roi = f"{roi_val:.2f}%"
        except Exception:
            pass

        msg = (
            f"[Closed] {reason}\n"
            f"PnL: {position['unrealized_pnl']:.2f} USDT\n"
            f"ROI: {roi}"
        )
        print(msg)
        send_telegram(msg)
    except Exception as e:
        err_msg = f"Close order failed: {e}"
        print(err_msg)
        send_telegram(err_msg)


def open_position(side, price):
    try:
        balance = get_balance()
        usdt_amount = balance * USDT_USAGE
        if usdt_amount < 5:
            print("Insufficient balance to enter position")
            return

        quantity = (usdt_amount * LEVERAGE) / price
        amount = float(bitget.amount_to_precision(SYMBOL, quantity))

        order_side = "buy" if side == "long" else "sell"
        bitget.create_market_order(SYMBOL, order_side, amount)

        msg = (
            f"[Entry success] {side.upper()} position\n"
            f"Entry: {price}\n"
            f"Amount: {amount} BTC"
        )
        print(msg)
        send_telegram(msg)
    except Exception as e:
        err_msg = f"Entry order failed: {e}"
        print(err_msg)
        send_telegram(err_msg)


# ==========================================
# Main loop
# ==========================================
def main():
    print("=== Champion strategy bot started (SMA 60/80 + ADX 25) ===")
    initial_setup()
    send_telegram(
        "Bot started. Strategy: SMA 60/80 + ADX>25. "
        "SL: 3% / TP: 26% price move at 5x leverage."
    )

    last_heartbeat = time.time()

    while True:
        try:
            df = fetch_data()
            if df is None:
                time.sleep(60)
                continue

            prev = df.iloc[-2]
            prev2 = df.iloc[-3]

            ticker = bitget.fetch_ticker(SYMBOL)
            current_price = ticker["last"]

            if time.time() - last_heartbeat > 14400:
                pos = get_position()
                pos_str = (
                    f"{pos['side'].upper()} ({pos['unrealized_pnl']:.2f} USDT)"
                    if pos
                    else "waiting"
                )
                send_telegram(
                    f"[Heartbeat]\nCurrent price: {current_price}\nPosition: {pos_str}"
                )
                last_heartbeat = time.time()

            position = get_position()

            if position:
                entry_price = position["entry_price"]

                if position["side"] == "long":
                    if current_price >= entry_price * (1 + TP_PCT):
                        close_position(position, "take profit reached")
                    elif current_price <= entry_price * (1 - SL_PCT):
                        close_position(position, "stop loss reached")
                    elif prev["MA_Short"] < prev["MA_Long"]:
                        close_position(position, "opposite signal, dead cross")

                elif position["side"] == "short":
                    if current_price <= entry_price * (1 - TP_PCT):
                        close_position(position, "take profit reached")
                    elif current_price >= entry_price * (1 + SL_PCT):
                        close_position(position, "stop loss reached")
                    elif prev["MA_Short"] > prev["MA_Long"]:
                        close_position(position, "opposite signal, golden cross")

                print(
                    f"\r[{datetime.datetime.now().strftime('%H:%M:%S')}] "
                    f"Position open | PnL: {position['unrealized_pnl']:.2f}",
                    end="",
                )

            else:
                trend_ok = prev["ADX"] >= ADX_THRESHOLD
                gold_cross = (
                    prev2["MA_Short"] <= prev2["MA_Long"]
                    and prev["MA_Short"] > prev["MA_Long"]
                )
                dead_cross = (
                    prev2["MA_Short"] >= prev2["MA_Long"]
                    and prev["MA_Short"] < prev["MA_Long"]
                )

                if trend_ok:
                    if gold_cross:
                        open_position("long", current_price)
                        time.sleep(5)
                    elif dead_cross:
                        open_position("short", current_price)
                        time.sleep(5)

                print(
                    f"\r[{datetime.datetime.now().strftime('%H:%M:%S')}] "
                    f"Waiting | ADX:{prev['ADX']:.1f} | "
                    f"MA:{prev['MA_Short']:.1f}/{prev['MA_Long']:.1f}",
                    end="",
                )

            time.sleep(60)

        except Exception as e:
            err = f"Main loop error: {e}"
            print(err)
            time.sleep(60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBot stopped.")
    except Exception as e:
        send_telegram(f"Fatal bot error:\n{e}")
