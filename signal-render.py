import os
import requests
import pandas as pd
import time
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TOKEN or not CHAT_ID:
    print("خطا: توکن یا چت آیدی تنظیم نشده!")
    exit(1)


SENT_SIGNALS = set()

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
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
        print(f"چک کردن داده‌ها در {datetime.now().strftime('%H:%M:%S')}...")
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

        new_sig = 0
        for _, row in data.iterrows():
            sig = row["Signal_Action"]
            if sig in ["BUY", "SELL"]:
                key = f"{row['timestamp']}_{sig}_{row['close']:.2f}"
                if key not in SENT_SIGNALS:
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
تیک‌پروفیت: <b>{take:,.2f}</b>
RSI: <b>{row['RSI']:.1f}</b> | حجم: <b>{row['volume']:,.0f}</b>
                    """.strip()
                    send_telegram_message(msg)
                    SENT_SIGNALS.add(key)
                    new_sig += 1
                    time.sleep(1)

        if new_sig > 0:
            print(f"{new_sig} سیگنال جدید ارسال شد.")
        else:
            print("هیچ سیگنال جدیدی یافت نشد.")
    except Exception as e:
        print(f"خطا در اجرای چک: {e}")


print("ربات 24/7 شروع شد...")
while True:
    run_check()
    print("30 دقیقه صبر برای اجرای بعدی...")
    time.sleep(1800) 
