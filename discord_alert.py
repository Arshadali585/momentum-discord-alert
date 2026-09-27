import requests
import os
import pandas as pd
import time

# =====================================================
# SETTINGS
# =====================================================

INTERVAL = "1h"
TOP_N = 10          # top gainers count

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK", "")

emaFastLen = 9
emaSlowLen = 21

bodyAvgLen = 20
bodyMult = 1.5

distPct = 3.0
closePosPct = 70.0

useVol = True
volLen = 20
volMult = 1.2

useConfirm = False
cooldown = 3

# =====================================================
# GET TOP GAINERS FROM BINANCE FUTURES
# =====================================================

def get_top_gainers():

    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()

    df = pd.DataFrame(data)

    df["priceChangePercent"] = df["priceChangePercent"].astype(float)

    # Only USDT perpetuals
    df = df[df["symbol"].str.endswith("USDT")]

    top = df.sort_values(
        "priceChangePercent", ascending=False
    ).head(TOP_N)

    return top["symbol"].tolist()


# =====================================================
# BINANCE FUTURES CANDLE DATA
# =====================================================

def get_data(symbol):

    url = "https://fapi.binance.com/fapi/v1/klines"

    params = {
        "symbol": symbol,
        "interval": INTERVAL,
        "limit": 100
    }

    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()

    data = r.json()

    df = pd.DataFrame(data, columns=[
        "time", "open", "high", "low", "close",
        "volume", "close_time", "quote_volume",
        "trades", "buy_base", "buy_quote", "ignore"
    ])

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    return df


# =====================================================
# CHECK SIGNAL — SAME LOGIC AS BEFORE
# =====================================================

def check_signal(df):

    i = len(df) - 2

    open_ = df["open"].iloc[i]
    high = df["high"].iloc[i]
    low = df["low"].iloc[i]
    close = df["close"].iloc[i]
    volume = df["volume"].iloc[i]

    body = abs(close - open_)
    bodies = abs(df["close"] - df["open"])
    avgBody = bodies.iloc[:i].tail(bodyAvgLen).mean()

    rng = high - low
    closePos = (close - low) / rng * 100 if rng > 0 else 50

    emaFast = df["close"].ewm(span=emaFastLen, adjust=False).mean().iloc[i]
    emaSlow = df["close"].ewm(span=emaSlowLen, adjust=False).mean().iloc[i]

    distUp = (close - emaFast) / emaFast * 100
    distDn = (emaFast - close) / emaFast * 100

    volAvg = df["volume"].iloc[:i].tail(volLen).mean()
    volOk = (not useVol or pd.isna(volAvg) or volume > volAvg * volMult)

    bigBody = body > avgBody * bodyMult

    rawLong = (
        close > open_ and bigBody
        and distUp >= distPct
        and closePos >= closePosPct
        and volOk
    )

    rawShort = (
        close < open_ and bigBody
        and distDn >= distPct
        and closePos <= (100 - closePosPct)
        and volOk
    )

    longCond = rawLong
    shortCond = rawShort

    if longCond:
        return "LONG", close
    if shortCond:
        return "SHORT", close
    return None, close


# =====================================================
# DISCORD
# =====================================================

def send_discord(symbol, signal, price):

    if signal == "LONG":
        title = "🚀 MOMENTUM LONG"
    else:
        title = "🔻 MOMENTUM SHORT"
