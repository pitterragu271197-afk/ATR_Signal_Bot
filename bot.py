import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime

# Environment Variables from GitHub Secrets
API_KEY = "31f97a183bcc4ff4925c924c6f3afcd0"
TELEGRAM_BOT_TOKEN = "9287421494:AAGy-IJ-ers3ddb-kZvPT1kEwZu3eeTsOM8"
TELEGRAM_CHAT_ID = "5189965664"

SYMBOL = "XAU/USD"
INTERVAL = "5min"
STATE_FILE = "trade_state.json"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"active_trade": None, "history": []}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)

def fetch_data():
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval={INTERVAL}&outputsize=50&apikey={API_KEY}"
    response = requests.get(url).json()
    if "values" not in response:
        print("Error fetching data:", response)
        return None
    
    df = pd.DataFrame(response["values"])
    df = df.iloc[::-1].reset_index(drop=True) # Oldest to newest
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)
    return df

def calculate_indicators(df):
    # 14-period ATR
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    df['atr'] = df['tr'].rolling(window=14).mean()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    return df

def check_trade_status(df, state):
    trade = state["active_trade"]
    if not trade:
        return state

    latest_candle = df.iloc[-1]
    high = latest_candle["high"]
    low = latest_candle["low"]
    time_str = latest_candle["datetime"]

    entry_price = trade["entry_price"]
    tp = trade["tp"]
    sl = trade["sl"]
    direction = trade["direction"]

    hit = False
    result = ""

    if direction == "BUY":
        if high >= tp:
            hit = True
            result = "TP HIT 🎯"
        elif low <= sl:
            hit = True
            result = "SL HIT 🛑"
    elif direction == "SELL":
        if low <= tp:
            hit = True
            result = "TP HIT 🎯"
        elif high >= sl:
            hit = True
            result = "SL HIT 🛑"

    if hit:
        if "TP" in result:
            status_text = "🎉 *Boom! Take Profit reached smoothly!* Another clean setup locked in the green. Let's keep this momentum rolling! 🚀💰"
        else:
            status_text = "😔 *Ah, rough break — Stop Loss hit.* Market chop got the better of this one. Dusting it off and staying sharp for the next clean setup! 🛡️📉"

        msg = (
            f"📊 *Trade Update - {SYMBOL}*\n"
            f"{status_text}\n\n"
            f"Result: *{result}*\n"
            f"Direction: {direction}\n"
            f"Entry: `{entry_price}`\n"
            f"Exit Time: {time_str}"
        )
        send_telegram(msg)
        
        # Log to history
        trade["result"] = result
        trade["exit_time"] = time_str
        state["history"].append(trade)
        state["active_trade"] = None

    return state

def evaluate_strategy(df, state):
    if state["active_trade"] is not None:
        return # Don't open a new trade if one is active

    row = df.iloc[-2] # Completed candle
    prev_row = df.iloc[-3]

    close = row["close"]
    ema = row["ema20"]
    atr = row["atr"]
    upper_channel = ema + (1.5 * atr)
    lower_channel = ema - (1.5 * atr)

    # Simple ATR Channel Breakout logic
    if close > upper_channel and row["close"] > row["open"]:
        entry = close
        sl = entry - (1.5 * atr)
        tp = entry + (2.5 * atr)
        
        state["active_trade"] = {
            "direction": "BUY",
            "entry_price": entry,
            "tp": tp,
            "sl": sl,
            "time": row["datetime"]
        }
        
        msg = (
            f"🚀 *New BUY Signal - {SYMBOL}*\n"
            f"Entry: `{entry}`\n"
            f"TP: `{tp:.2f}` | SL: `{sl:.2f}`"
        )
        send_telegram(msg)

    elif close < lower_channel and row["close"] < row["open"]:
        entry = close
        sl = entry + (1.5 * atr)
        tp = entry - (2.5 * atr)
        
        state["active_trade"] = {
            "direction": "SELL",
            "entry_price": entry,
            "tp": tp,
            "sl": sl,
            "time": row["datetime"]
        }
        
        msg = (
            f"📉 *New SELL Signal - {SYMBOL}*\n"
            f"Entry: `{entry}`\n"
            f"TP: `{tp:.2f}` | SL: `{sl:.2f}`"
        )
        send_telegram(msg)

def main():
    state = load_state()
    df = fetch_data()
    if df is not None:
        df = calculate_indicators(df)
        state = check_trade_status(df, state)
        evaluate_strategy(df, state)
        save_state(state)

if __name__ == "__main__":
    main()
