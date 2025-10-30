import os
import requests
import pandas as pd
from datetime import datetime
import time

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SAVE_PATH = "/app/sent_signals"
os.makedirs(SAVE_PATH, exist_ok=True)

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            print("سیگنال ارسال شد.")
        else:
            print(f"خطا در ارسال: {response.status_code}")
    except Exception as e:
        print(f"خطا: {e}")

def run_check():
    try:
        url = "https://api.coinex.com/v1/market/kline"
        params = {"market": "BTCUSDT", "type": "30min", "limit": 1000}
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200 or response.json().get("code") != 0:
            print("خطا در دریافت داده")
            return

        data = pd.DataFrame(response.json()["data"], columns=["timestamp", "open", "close", "high", "low", "volume", "amount"])
        data["timestamp"] = pd.to_datetime(data["timestamp"], unit="s")
        data = data.astype({col: float for col in ["open", "close", "high", "low", "volume", "amount"]})

        data["MA55"] = data["close"].rolling(55).mean()
        data["MA200"] = data["close"].rolling(200).mean()
        delta = data["close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        data["RSI"] = 100 - (100 / (1 + rs))
        tr = pd.concat([data["high"]-data["low"], (data["high"]-data["close"].shift(1)).abs(), (data["low"]-data["close"].shift(1)).abs()], axis=1).max(axis=1)
        data["ATR"] = tr.rolling(14).mean()
        data["Volume_MA20"] = data["volume"].rolling(20).mean()
        data["Trend_Up"] = data["close"] > data["MA200"]
        data["Trend_Down"] = data["close"] < data["MA200"]

        def gen(row, prev_ma200):
            if row["MA55"] > row["MA200"] and row["RSI"] < 55 and row["volume"] > row["Volume_MA20"] and row["Trend_Up"]:
                return "BUY"
            elif row["MA55"] < row["MA200"] and row["RSI"] > 45 and row["volume"] > row["Volume_MA20"] and row["Trend_Down"] and row["MA55"] < prev_ma200:
                return "SELL"
            return "HOLD"

        data["Signal_Action"] = "HOLD"
        for i in range(1, len(data)):
            data.loc[data.index[i], "Signal_Action"] = gen(data.iloc[i], data.iloc[i-1]["MA200"])

        log_file = os.path.join(SAVE_PATH, "sent_signals.log")
        sent = set(open(log_file, "r", encoding="utf-8").read().splitlines()) if os.path.exists(log_file) else set()

        new_sig = []
        for _, row in data.iterrows():
            sig = row["Signal_Action"]
            if sig in ["BUY", "SELL"]:
                key = f"{row['timestamp']}_{sig}_{row['close']:.2f}"
                if key not in sent:
                    atr = row["ATR"]
                    price = row["close"]
                    stop = price - 5*atr if sig == "BUY" else price + 5*atr
                    take = price * 1.03 if sig == "BUY" else price * 0.97
                    direction = "خرید" if sig == "BUY" else "فروش"

                    msg = f"""
سیگنال جدید BTC/USDT
{direction} در قیمت: <b>{price:,.2f} USDT</b>
زمان: <code>{row['timestamp'].strftime('%Y-%m-%d %H:%M')}</code>
استاپ‌لاس: <b>{stop:,.2f}</b>
تیک‌پرافیت: <b>{take:,.2f}</b>
RSI: <b>{row['RSI']:.1f}</b> | حجم: <b>{row['volume']:,.0f}</b>
                    """.strip()
                    send_telegram_message(msg)
                    new_sig.append(key)
                    sent.add(key)
                    time.sleep(1)

        if new_sig:
            with open(log_file, "a", encoding="utf-8") as f:
                for s in new_sig: f.write(s + "\n")
            print(f"{len(new_sig)} سیگنال جدید ارسال شد.")
        else:
            print("هیچ سیگنال جدیدی یافت نشد.")
    except Exception as e:
        print(f"خطا در اجرای چک: {e}")

print("ربات شروع شد...")
run_check()
