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
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval={INTERVAL}&outputsize=100&apikey={API_KEY}"
    response = requests.get(url).json()
    if "values" not in response:
        print("Error fetching data:", response)
        return None
    
    df = pd.DataFrame(response["values"])
    df = df.iloc[::-1].reset_index(drop=True)
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)
    return df

def calculate_indicators(df):
    # ATR 14
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    df['atr'] = df['tr'].rolling(window=14).mean()
    
    # EMAs for Trend Filtering
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # RSI 14
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
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
    tp1 = trade["tp1"]
    tp2 = trade["tp2"]
    sl = trade["sl"]
    direction = trade["direction"]

    hit = False
    result = ""

    # Check TP1 milestone
    if not trade.get("tp1_hit", False):
        if (direction == "BUY" and high >= tp1) or (direction == "SELL" and low <= tp1):
            trade["tp1_hit"] = True
            send_telegram(f"🎯 *TP1 Hit for {SYMBOL}!* First target locked. Moving SL to break-even. Let's push for TP2! 🚀")

    # Check final exit (TP2 or SL)
    if direction == "BUY":
        if high >= tp2:
            hit = True
            result = "TP2 HIT 🎯🎯 (Full Win)"
        elif low <= sl:
            hit = True
            result = "SL HIT 🛑"
    elif direction == "SELL":
        if low <= tp2:
            hit = True
            result = "TP2 HIT 🎯🎯 (Full Win)"
        elif high >= sl:
            hit = True
            result = "SL HIT 🛑"

    if hit:
        if "TP2" in result:
            status_text = "🎉 *Boom! Full target TP2 reached!* Absolute clinic on this gold breakout. Let's keep this momentum rolling! 🚀💰"
        else:
            status_text = "😔 *Ah, rough break — Stop Loss hit.* Gold market chop got the better of this one. Dusting it off and staying sharp for the next clean setup! 🛡️📉"

        msg = (
            f"📊 *Trade Closed - {SYMBOL}*\n"
            f"{status_text}\n\n"
            f"Result: *{result}*\n"
            f"Direction: {direction}\n"
            f"Entry: `{entry_price:.2f}`\n"
            f"Exit Time: {time_str}"
        )
        send_telegram(msg)
        
        trade["result"] = result
        trade["exit_time"] = time_str
        state["history"].append(trade)
        state["active_trade"] = None

    return state

def evaluate_strategy(df, state):
    if state["active_trade"] is not None:
        return

    row = df.iloc[-2]  # Last completed candle
    close = row["close"]
    ema20 = row["ema20"]
    ema50 = row["ema50"]
    atr = row["atr"]
    rsi = row["rsi"]
    
    upper_channel = ema20 + (1.8 * atr)
    lower_channel = ema20 - (1.8 * atr)

    # BUY Setup: Price breaks upper band + uptrend filter + RSI filter
    if close > upper_channel and close > ema50 and rsi < 68 and row["close"] > row["open"]:
        entry = close
        sl = entry - (3.5 * atr)  # Wide SL to prevent wick-outs
        tp1 = entry + (4.0 * atr) # TP1 partial target
        tp2 = entry + (7.5 * atr) # TP2 runner target
        
        state["active_trade"] = {
            "direction": "BUY",
            "entry_price": entry,
            "tp1": tp1,
            "tp2": tp2,
            "sl": sl,
            "time": row["datetime"],
            "tp1_hit": False
        }
        
        msg = (
            f"🚀 *New BUY Signal - {SYMBOL}*\n\n"
            f"• Entry: `{entry:.2f}`\n"
            f"• Stop Loss: `{sl:.2f}` (3.5 ATR)\n"
            f"• TP1: `{tp1:.2f}` (4.0 ATR)\n"
            f"• TP2: `{tp2:.2f}` (7.5 ATR)\n"
            f"• Trend Filter: Bullish (EMA50)"
        )
        send_telegram(msg)

    # SELL Setup: Price breaks lower band + downtrend filter + RSI filter
    elif close < lower_channel and close < ema50 and rsi > 32 and row["close"] < row["open"]:
        entry = close
        sl = entry + (3.5 * atr)
        tp1 = entry - (4.0 * atr)
        tp2 = entry - (7.5 * atr)
        
        state["active_trade"] = {
            "direction": "SELL",
            "entry_price": entry,
            "tp1": tp1,
            "tp2": tp2,
            "sl": sl,
            "time": row["datetime"],
            "tp1_hit": False
        }
        
        msg = (
            f"📉 *New SELL Signal - {SYMBOL}*\n\n"
            f"• Entry: `{entry:.2f}`\n"
            f"• Stop Loss: `{sl:.2f}` (3.5 ATR)\n"
            f"• TP1: `{tp1:.2f}` (4.0 ATR)\n"
            f"• TP2: `{tp2:.2f}` (7.5 ATR)\n"
            f"• Trend Filter: Bearish (EMA50)"
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
