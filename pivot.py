
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import timedelta
import time

# =========================================================
# 1. SETTINGS
# =========================================================

INPUT_FILE = "stocks.csv"
OUTPUT_FILE = "stocks_with_correct_ema.csv"

EMA_PERIOD = 200

# =========================================================
# 2. EMA CALCULATION
# =========================================================

def calculate_ema(prices, period=200):

    prices = pd.Series(prices).dropna().astype(float)

    result = pd.Series(
        np.nan,
        index=prices.index,
        dtype=float
    )

    if len(prices) < period:
        return result

    alpha = 2 / (period + 1)

    # Initialize EMA with first 200-period SMA
    first_ema = prices.iloc[:period].mean()

    result.iloc[period - 1] = first_ema

    # Calculate remaining EMA values
    for i in range(period, len(prices)):

        previous_ema = result.iloc[i - 1]

        current_price = prices.iloc[i]

        result.iloc[i] = (
            current_price * alpha
            + previous_ema * (1 - alpha)
        )

    return result


# =========================================================
# 3. CONVERT NSE/BSE TICKER TO YAHOO FINANCE FORMAT
# =========================================================

def convert_ticker(ticker):

    ticker = str(ticker).strip().upper()

    if ticker.startswith("NSE:"):
        return ticker.replace("NSE:", "") + ".NS"

    elif ticker.startswith("BSE:"):
        return ticker.replace("BSE:", "") + ".BO"

    elif ticker.endswith(".NS") or ticker.endswith(".BO"):
        return ticker

    else:
        return ticker + ".NS"


# =========================================================
# 4. GET LAST COMPLETED WEEK
# =========================================================

def get_last_completed_friday():

    today = pd.Timestamp.now(
        tz="Asia/Kolkata"
    ).tz_localize(None).normalize()

    days_since_friday = (today.weekday() - 4) % 7

    return today - pd.Timedelta(days=days_since_friday)


# =========================================================
# 5. FETCH DATA AND CALCULATE BOTH EMA
# =========================================================

def calculate_stock_ema(original_ticker):

    yahoo_ticker = convert_ticker(original_ticker)

    try:

        # Fetch maximum available daily history
        data = yf.Ticker(yahoo_ticker).history(
            period="max",
            interval="1d",
            auto_adjust=False,
            actions=False
        )

        if data.empty:
            raise ValueError("No historical data available")

        # Remove timezone without changing exchange dates
        if data.index.tz is not None:
            data.index = data.index.tz_localize(None)

        # Use actual daily closing prices
        close = data["Close"].dropna().astype(float)

        if close.empty:
            raise ValueError("Closing prices unavailable")

        # -------------------------------------------------
        # A. DAILY 200 EMA
        # -------------------------------------------------

        daily_ema = calculate_ema(
            close,
            EMA_PERIOD
        )

        latest_daily_ema = daily_ema.iloc[-1]

        # -------------------------------------------------
        # B. WEEKLY CLOSING PRICE
        # -------------------------------------------------

        weekly_close = close.resample("W-FRI").last().dropna()

        # Exclude incomplete current week
        last_completed_week = get_last_completed_friday()

        weekly_close = weekly_close[
            weekly_close.index <= last_completed_week
        ]

        # -------------------------------------------------
        # C. WEEKLY 200 EMA
        # -------------------------------------------------

        weekly_ema = calculate_ema(
            weekly_close,
            EMA_PERIOD
        )

        latest_weekly_ema = (
            weekly_ema.iloc[-1]
            if len(weekly_ema) >= EMA_PERIOD
            else np.nan
        )

        return {
            "Yahoo Ticker": yahoo_ticker,
            "Daily 200 EMA": latest_daily_ema,
            "Weekly 200 EMA": latest_weekly_ema,
            "Daily Data Points": len(close),
            "Weekly Data Points": len(weekly_close),
            "Last Daily Date": close.index[-1],
            "Last Completed Week": (
                weekly_close.index[-1]
                if not weekly_close.empty
                else None
            ),
            "EMA Status": "OK"
        }

    except Exception as e:

        return {
            "Yahoo Ticker": yahoo_ticker,
            "Daily 200 EMA": np.nan,
            "Weekly 200 EMA": np.nan,
            "Daily Data Points": 0,
            "Weekly Data Points": 0,
            "Last Daily Date": None,
            "Last Completed Week": None,
            "EMA Status": str(e)
        }


# =========================================================
# 6. READ EXISTING STOCK FILE
# =========================================================

df = pd.read_csv(INPUT_FILE)

# Identify ticker column
if "Ticker" in df.columns:

    ticker_column = "Ticker"

elif "Symbol" in df.columns:

    ticker_column = "Symbol"

else:

    raise ValueError(
        "CSV must contain a Ticker or Symbol column"
    )


# =========================================================
# 7. CALCULATE EMA FOR ALL STOCKS
# =========================================================

results = []

unique_tickers = df[ticker_column].dropna().unique()

print("Total stocks:", len(unique_tickers))

for i, ticker in enumerate(unique_tickers, start=1):

    print(
        f"Processing {i}/{len(unique_tickers)}: {ticker}"
    )

    result = calculate_stock_ema(ticker)

    result["Original Ticker"] = ticker

    results.append(result)

    time.sleep(0.15)


# =========================================================
# 8. MERGE EMA VALUES WITH EXISTING DATA
# =========================================================

ema_df = pd.DataFrame(results)

df = df.merge(
    ema_df[
        [
            "Original Ticker",
            "Daily 200 EMA",
            "Weekly 200 EMA",
            "Daily Data Points",
            "Weekly Data Points",
            "Last Daily Date",
            "Last Completed Week",
            "EMA Status"
        ]
    ],
    left_on=ticker_column,
    right_on="Original Ticker",
    how="left"
)

df.drop(
    columns=["Original Ticker"],
    inplace=True
)


# =========================================================
# 9. ROUND VALUES
# =========================================================

df["Daily 200 EMA"] = df["Daily 200 EMA"].round(2)

df["Weekly 200 EMA"] = df["Weekly 200 EMA"].round(2)


# =========================================================
# 10. EXPORT FINAL FILE
# =========================================================

df.to_csv(
    OUTPUT_FILE,
    index=False
)

print("\n================================")
print("EMA CALCULATION COMPLETED")
print("================================")

print("Total Stocks:", len(df))

print(
    "Successful:",
    (df["EMA Status"] == "OK").sum()
)

print(
    "Failed:",
    (df["EMA Status"] != "OK").sum()
)

print("Output File:", OUTPUT_FILE)
