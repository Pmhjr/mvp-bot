import requests
import pandas as pd
import os
from datetime import datetime
import time

# ----------------------------
# تنظیمات امن (برای Render + Public Repo)
# ----------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("توکن یا چت آیدی تنظیم نشده است! در Render اضافه کنید.")

SAVE_PATH = "/tmp"  # برای Render
os.makedirs(SAVE_PATH, exist_ok=True)


# ----------------------------
# تابع ارسال پیام به تلگرام
# ----------------------------
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
        print(f"خطا در ارتباط: {e}")


# ----------------------------
# دریافت داده
# ----------------------------
url = "https://api.coinex.com/v1/market/kline"
params = {"market": "BTCUSDT", "type": "30min", "limit": 1000}
response = requests.get(url, params=params)

if response.status_code != 200 or response.json().get("code") != 0:
    print("خطا در دریافت داده")
    exit()

data = pd.DataFrame(response.json()["data"], columns=["timestamp", "open", "close", "high", "low", "volume", "amount"])
data["timestamp"] = pd.to_datetime(data["timestamp"], unit="s")
data = data.astype({col: float for col in ["open", "close", "high", "low", "volume", "amount"]})

# ----------------------------
# اندیکاتورها
# ----------------------------
data["MA55"] = data["close"].rolling(55).mean()
data["MA200"] = data["close"].rolling(200).mean()
delta = data["close"].diff()
gain = delta.clip(lower=0).rolling(14).mean()
loss = (-delta.clip(upper=0)).rolling(14).mean()
data["RSI"] = 100 - (100 / (1 + (gain / loss)))
data["TR"] = pd.concat([
    data["high"] - data["low"],
    (data["high"] - data["close"].shift(1)).abs(),
    (data["low"] - data["close"].shift(1)).abs()
], axis=1).max(axis=1)
data["ATR"] = data["TR"].rolling(14).mean()
data["Volume_MA20"] = data["volume"].rolling(20).mean()
data["Trend_Up"] = data["close"] > data["MA200"]
data["Trend_Down"] = data["close"] < data["MA200"]


# ----------------------------
# تولید سیگنال دقیقاً مطابق استراتژی شما
# ----------------------------
def generate_signal(row, prev_ma200):
    # خرید
    if (row["MA55"] > row["MA200"] and
            row["RSI"] < 55 and
            row["volume"] > row["Volume_MA20"] and
            row["Trend_Up"]):
        return "BUY"

    # فروش: با شرط اضافی MA55 < MA200 قبلی
    elif (row["MA55"] < row["MA200"] and
          row["RSI"] > 45 and
          row["volume"] > row["Volume_MA20"] and
          row["Trend_Down"] and
          row["MA55"] < prev_ma200):  # شرط کلیدی شما
        return "SELL"

    return "HOLD"


# اعمال سیگنال با MA200 دوره قبلی
data["Signal_Action"] = "HOLD"
for i in range(1, len(data)):
    prev_ma200 = data.iloc[i - 1]["MA200"]
    data.loc[data.index[i], "Signal_Action"] = generate_signal(data.iloc[i], prev_ma200)

# ----------------------------
# لاگ سیگنال‌های ارسال‌شده (جلوگیری از تکرار)
# ----------------------------
signal_log_file = os.path.join(SAVE_PATH, "sent_signals.log")
sent_signals = set()
if os.path.exists(signal_log_file):
    with open(signal_log_file, "r", encoding="utf-8") as f:
        sent_signals = set(f.read().splitlines())

# ----------------------------
# ارسال فقط سیگنال‌های جدید
# ----------------------------
new_signals = []
for idx, row in data.iterrows():
    signal = row["Signal_Action"]
    if signal in ["BUY", "SELL"]:
        signal_key = f"{row['timestamp']}_{signal}_{row['close']:.2f}"
        if signal_key not in sent_signals:
            atr = row["ATR"]
            price = row["close"]
            stop_price = price - 5 * atr if signal == "BUY" else price + 5 * atr
            take_price = price * 1.03 if signal == "BUY" else price * 0.97
            direction = "خرید" if signal == "BUY" else "فروش"

            message = f"""
سیگنال جدید BTC/USDT

{direction} در قیمت: <b>{price:,.2f} USDT</b>
زمان: <code>{row['timestamp'].strftime('%Y-%m-%d %H:%M')}</code>

استاپ‌لاس: <b>{stop_price:,.2f}</b>
تیک‌پرافیت: <b>{take_price:,.2f}</b>

RSI: <b>{row['RSI']:.1f}</b> | حجم: <b>{row['volume']:,.0f}</b>
ATR: <b>{atr:.2f}</b>

MA55: {row['MA55']:.1f} | MA200: {row['MA200']:.1f}
            """.strip()

            send_telegram_message(message)
            new_signals.append(signal_key)
            sent_signals.add(signal_key)
            time.sleep(1)

# ذخیره لاگ
if new_signals:
    with open(signal_log_file, "a", encoding="utf-8") as f:
        for sig in new_signals:
            f.write(sig + "\n")
    print(f"{len(new_signals)} سیگنال جدید ارسال شد.")
else:
    print("هیچ سیگنال جدیدی یافت نشد.")

# ذخیره داده (اختیاری)
data.to_csv(os.path.join(SAVE_PATH, "data_with_signals.csv"), index=False)