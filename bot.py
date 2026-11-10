import time
import requests
import pandas as pd
import numpy as np

# --- Configuration ---
API_KEY = "31f97a183bcc4ff4925c924c6f3afcd0"
SYMBOL = "XAU/USD"
INTERVAL = "5min"
TELEGRAM_BOT_TOKEN = "9287421494:AAGy-IJ-ers3ddb-kZvPT1kEwZu3eeTsOM8"
TELEGRAM_CHAT_ID = "5189965664"

# --- Risk Parameters (Fixed Pips for XAU/USD) ---
PIP_SIZE = 0.10 
SL_PIPS = 35
TP1_PIPS = 40
TP2_PIPS = 75

def fetch_market_data():
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval={INTERVAL}&outputsize=100&apikey={API_KEY}"
    response = requests.get(url).json()
    if "values" in response:
        df = pd.DataFrame(response['values'])
        df = df.iloc[::-1].reset_index(drop=True)
        df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)
        return df
    print("Error fetching market data:", response)
    return None

def calculate_indicators(df, atr_period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(atr_period).mean()
    
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    
    sma_20 = df['close'].rolling(20).mean()
    df['upper_channel'] = sma_20 + (df['atr'] * 1.5)
    df['lower_channel'] = sma_20 - (df['atr'] * 1.5)
    
    df['candle_range'] = df['high'] - df['low']
    df['range_ma'] = df['candle_range'].rolling(20).mean()
    
    return df

def check_breakout_signals(df):
    latest = df.iloc[-1]
    activity_spike = latest['candle_range'] > (latest['range_ma'] * 1.5)
    
    bullish_trigger = (latest['close'] > latest['upper_channel']) and (latest['ema_9'] > latest['ema_20']) and activity_spike
    bearish_trigger = (latest['close'] < latest['lower_channel']) and (latest['ema_9'] < latest['ema_20']) and activity_spike
                      
    if bullish_trigger:
        return "BUY", latest['close'], latest['atr']
    elif bearish_trigger:
        return "SELL", latest['close'], latest['atr']
    return None, 0, 0

def calculate_risk_parameters(signal_type, entry_price):
    if signal_type == "BUY":
        stop_loss = entry_price - (SL_PIPS * PIP_SIZE)
        tp1 = entry_price + (TP1_PIPS * PIP_SIZE)
        tp2 = entry_price + (TP2_PIPS * PIP_SIZE)
    else:
        stop_loss = entry_price + (SL_PIPS * PIP_SIZE)
        tp1 = entry_price - (TP1_PIPS * PIP_SIZE)
        tp2 = entry_price - (TP2_PIPS * PIP_SIZE)
        
    return round(stop_loss, 2), round(tp1, 2), round(tp2, 2)

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def run_bot():
    print("🚀 ATR Volatility Scalper Bot active for XAU/USD (Fixed Pips Mode)...")
    
    # Send startup notification to Telegram
    startup_msg = (
        f"🟢 *Scalper Bot Started Successfully* 🟢\n\n"
        f"• **Asset:** {SYMBOL}\n"
        f"• **Timeframe:** {INTERVAL}\n"
        f"• **Strategy:** ATR Channels + EMA + Range Expansion\n"
        f"• **Risk Setup:** SL {SL_PIPS} pips | TP1 {TP1_PIPS} pips | TP2 {TP2_PIPS} pips\n\n"
        f"_Scanning for live breakout setups..._"
    )
    send_telegram_alert(startup_msg)
    
    last_candle_time = None
    while True:
        df = fetch_market_data()
        if df is not None:
            current_candle_time = df.iloc[-1]['datetime']
            if current_candle_time != last_candle_time:
                last_candle_time = current_candle_time
                df = calculate_indicators(df)
                sig, price, atr = check_breakout_signals(df)
                if sig:
                    sl, tp1, tp2 = calculate_risk_parameters(sig, price)
                    msg = (
                        f"🚨 *XAU/USD Intraday Scalp Alert* 🚨\n\n"
                        f"• **Action:** `{sig}`\n"
                        f"• **Entry Price:** `{price}`\n"
                        f"• **Stop Loss:** `{sl}` ({SL_PIPS} pips)\n"
                        f"• **TP1:** `{tp1}` ({TP1_PIPS} pips)\n"
                        f"• **TP2:** `{tp2}` ({TP2_PIPS} pips)\n"
                        f"• **ATR Volatility:** `{round(atr, 2)}`"
                    )
                    send_telegram_alert(msg)
                    print(f"Signal sent: {sig} at {price}")
                else:
                    print(f"[{current_candle_time}] Scanning XAU/USD... No breakout setup.")
        time.sleep(60)

if __name__ == "__main__":
    run_bot()
