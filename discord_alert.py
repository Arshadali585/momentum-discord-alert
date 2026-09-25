import requests
import os
import pandas as pd
import time

# =====================================================
# SAME SETTINGS AS YOUR TRADINGVIEW INDICATOR
# =====================================================

SYMBOL = "BTCUSDT"
INTERVAL = "1h"

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

atrLen = 14
slMult = 1.5
rr = 2.0

# =====================================================
# BINANCE FUTURES DATA
# =====================================================

def get_data():

    url = "https://fapi.binance.com/fapi/v1/klines"

    params = {
        "symbol": SYMBOL,
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
# CHECK SIGNAL — SAME LOGIC
# =====================================================

def check_signal(df):

    # Last CLOSED candle
    i = len(df) - 2

    open_ = df["open"].iloc[i]
    high = df["high"].iloc[i]
    low = df["low"].iloc[i]
    close = df["close"].iloc[i]
    volume = df["volume"].iloc[i]

    # Body
    body = abs(close - open_)

    # Same as ta.sma(body, 20)[1]
    bodies = abs(df["close"] - df["open"])

    avgBody = bodies.iloc[:i].tail(bodyAvgLen).mean()

    # Range
    rng = high - low

    closePos = (
        (close - low) / rng * 100
        if rng > 0 else 50
    )

    # EMA
    emaFast = (
        df["close"]
        .ewm(span=emaFastLen, adjust=False)
        .mean()
        .iloc[i]
    )

    emaSlow = (
        df["close"]
        .ewm(span=emaSlowLen, adjust=False)
        .mean()
        .iloc[i]
    )

    # Distance
    distUp = (
        (close - emaFast) / emaFast * 100
    )

    distDn = (
        (emaFast - close) / emaFast * 100
    )

    # Volume average — previous candles only
    volAvg = (
        df["volume"]
        .iloc[:i]
        .tail(volLen)
        .mean()
    )

    volOk = (
        not useVol
        or pd.isna(volAvg)
        or volume > volAvg * volMult
    )

    # Big body
    bigBody = body > avgBody * bodyMult

    # EXACT rawLong
    rawLong = (
        close > open_
        and bigBody
        and distUp >= distPct
        and closePos >= closePosPct
        and volOk
    )

    # EXACT rawShort
    rawShort = (
        close < open_
        and bigBody
        and distDn >= distPct
        and closePos <= (100 - closePosPct)
        and volOk
    )

    # Confirmation
    if useConfirm:

        previous = i - 1

        prev_open = df["open"].iloc[previous]
        prev_close = df["close"].iloc[previous]

        prev_high = df["high"].iloc[previous]
        prev_low = df["low"].iloc[previous]

        prev_rng = prev_high - prev_low

        prev_closePos = (
            (prev_close - prev_low) /
            prev_rng * 100
            if prev_rng > 0 else 50
        )

        prev_body = abs(
            prev_close - prev_open
        )

        prev_avgBody = (
            bodies.iloc[:previous]
            .tail(bodyAvgLen)
            .mean()
        )

        prev_emaFast = (
            df["close"]
            .ewm(span=emaFastLen, adjust=False)
            .mean()
            .iloc[previous]
        )

        prev_distUp = (
            (prev_close - prev_emaFast) /
            prev_emaFast * 100
        )

        prev_distDn = (
            (prev_emaFast - prev_close) /
            prev_emaFast * 100
        )

        prev_volAvg = (
            df["volume"]
            .iloc[:previous]
            .tail(volLen)
            .mean()
        )

        prev_volOk = (
            not useVol
            or pd.isna(prev_volAvg)
            or df["volume"].iloc[previous]
            > prev_volAvg * volMult
        )

        prev_bigBody = (
            prev_body >
            prev_avgBody * bodyMult
        )

        prev_rawLong = (
            prev_close > prev_open
            and prev_bigBody
            and prev_distUp >= distPct
            and prev_closePos >= closePosPct
            and prev_volOk
        )

        prev_rawShort = (
            prev_close < prev_open
            and prev_bigBody
            and prev_distDn >= distPct
            and prev_closePos <= (100 - closePosPct)
            and prev_volOk
        )

        longCond = (
            prev_rawLong
            and close > prev_close
            and close > open_
        )

        shortCond = (
            prev_rawShort
            and close < prev_close
            and close < open_
        )

    else:
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

def send_discord(signal, price):

    if signal == "LONG":
        title = "🚀 MOMENTUM LONG"
    else:
        title = "🔻 MOMENTUM SHORT"

    message = (
        f"**{title}**\n"
        f"Symbol: **{SYMBOL} Futures**\n"
        f"Timeframe: **1H**\n"
        f"Price: **{price}**"
    )

    requests.post(
        WEBHOOK_URL,
        json={"content": message},
        timeout=30
    )


# =====================================================
# RUN
# =====================================================

print("Your Momentum Breakout Discord Alert started...")

try:

    df = get_data()

    # Only CLOSED candle
    candle_time = df["time"].iloc[-2]

    signal, price = check_signal(df)

    if signal:

        print(f"{signal} SIGNAL | {price}")

        send_discord(
            signal,
            price
        )

    else:

        print(
            "No signal |",
            pd.to_datetime(
                candle_time,
                unit="ms"
            )
        )

except Exception as e:

    print("Error:", e)
