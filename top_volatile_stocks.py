"""NIFTY 50 volatility screener.

Ranks index constituents by their own realised volatility, computed along the
*time* axis from a daily price history per symbol. The NSE endpoint is still
used, but only for what it can actually provide: today's constituent list and
snapshot quote. Volatility, skewness and kurtosis come from the price history.
"""

import argparse
import time

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from scipy.stats import kurtosis, skew

TRADING_DAYS = 252

# Session with cookie handling
session = requests.Session()

# NSE URLs
BASE_URL = "https://www.nseindia.com"
STOCK_URL = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050"

# Headers for browser emulation
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE_URL,
}

# Used when NSE is unreachable (geo-block, datacentre IP, endpoint change).
# The screener is about the price history, so it should not die with the scraper.
NIFTY50_FALLBACK = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BEL", "BHARTIARTL",
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO",
    "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK", "INFY",
    "ITC", "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
    "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]

# NSE symbols whose Yahoo ticker differs, e.g. after a demerger or rename.
# Without this the symbol silently disappears from the ranking.
YAHOO_OVERRIDES = {
    "TATAMOTORS": "TMPV",  # passenger-vehicle entity post-demerger
}


# Step 1: Establish session for cookies
def establish_session():
    try:
        print("Establishing session...")
        session.get(BASE_URL, headers=HEADERS, timeout=10)
        time.sleep(2)  # Wait to prevent being blocked
        print("Session established successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Session initiation failed: {e}")


# Step 2: Fetch the NIFTY 50 constituent snapshot, with JSON error handling & retries
def fetch_snapshot(retries=3):
    """Return NSE's snapshot rows: one row per constituent, one point in time."""
    response = None
    for attempt in range(retries):
        try:
            print(f"Fetching constituent list from NSE (attempt {attempt + 1}/{retries})...")
            response = session.get(STOCK_URL, headers=HEADERS, timeout=10)
            print(f"Response Status Code: {response.status_code}")
            response.raise_for_status()

            data = response.json().get("data", [])
            if not data:
                print("Warning: Empty data received. NSE may have restricted access.")

            print(f"Fetched {len(data)} constituent records.")
            return data

        except requests.exceptions.JSONDecodeError:
            print("JSON Decode Error: Response is not in JSON format. Possible NSE block.")
            print("Response (First 500 chars):", response.text[:500])

        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error: {e}, Status Code: {response.status_code}")

        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")

        print("Retrying in 5 seconds...")
        time.sleep(5)

    print("Failed to fetch data after multiple attempts.")
    return []


def constituents(snapshot):
    """Symbols from the snapshot, minus the index row itself; fallback if empty."""
    symbols = [
        row["symbol"]
        for row in snapshot
        if row.get("symbol") and row["symbol"].upper() not in {"NIFTY 50", "NIFTY50"}
    ]
    if not symbols:
        print(f"Falling back to a static NIFTY 50 list ({len(NIFTY50_FALLBACK)} symbols).")
        return NIFTY50_FALLBACK
    return symbols


# Step 3: Fetch a daily price history per symbol
def fetch_history(symbols, period="1y"):
    """Adjusted daily closes, indexed by date, one column per NSE symbol.

    This is the piece the NSE snapshot cannot supply: an actual time axis.
    """
    tickers = {f"{YAHOO_OVERRIDES.get(s, s)}.NS": s for s in symbols}
    print(f"Downloading {period} of daily history for {len(tickers)} symbols...")
    raw = yf.download(
        list(tickers),
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="column",
    )
    if raw.empty:
        print("No price history returned.")
        return pd.DataFrame()

    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(raw.columns, pd.MultiIndex):
        close.columns = list(tickers)

    close = close.rename(columns=tickers).sort_index()
    print(f"Got {len(close)} trading days, {close.notna().any().sum()} symbols with data.")
    return close


# Step 4: Analyse volatility along the time axis
def analyze_volatility(close, window=21, min_obs=60):
    """Per-symbol realised volatility, skewness and excess kurtosis over time.

    `window` is a number of *trading days for one symbol*, so the rolling
    standard deviation is a volatility. Third and fourth moments are estimated
    over the full sample, which needs far more than a handful of observations
    to mean anything.
    """
    if close.empty:
        print("No price history available for analysis.")
        return pd.DataFrame()

    # Log returns down each column: rows are dates, columns are stocks.
    returns = np.log(close / close.shift(1))

    rolling_vol = returns.rolling(window=window, min_periods=window).std(ddof=1)
    ann = np.sqrt(TRADING_DAYS) * 100  # decimal daily sigma -> annualised %

    rows, dropped = [], []
    for symbol in returns.columns:
        r = returns[symbol].dropna()
        if len(r) < min_obs:
            dropped.append(f"{symbol}({len(r)})")
            continue
        rows.append(
            {
                "symbol": symbol,
                "Obs": len(r),
                f"Vol {window}d (%)": rolling_vol[symbol].dropna().iloc[-1] * ann,
                "Vol full (%)": r.std(ddof=1) * ann,
                "Skewness": skew(r, bias=False),
                "Kurtosis": kurtosis(r, bias=False),
                "Return 1d (%)": (np.expm1(r.iloc[-1])) * 100,
            }
        )

    if dropped:
        print(f"Skipped {len(dropped)} symbols with fewer than {min_obs} returns: {', '.join(dropped)}")
    return pd.DataFrame(rows)


def report(df, window=21, top=5):
    if df.empty:
        print("Nothing to rank.")
        return df

    vol_col = f"Vol {window}d (%)"
    ranked = df.nlargest(top, vol_col)

    print(f"\n{top} Most Volatile Stocks (annualised, trailing {window} trading days):")
    print(
        ranked[
            ["symbol", vol_col, "Vol full (%)", "Skewness", "Kurtosis", "Obs", "Return 1d (%)"]
        ].to_string(index=False, float_format=lambda v: f"{v:8.2f}")
    )
    return ranked


# Step 5: Main Execution
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default="1y", help="history length passed to yfinance (default 1y)")
    parser.add_argument("--window", type=int, default=21, help="trading days in the volatility window (default 21)")
    parser.add_argument("--min-obs", type=int, default=60, help="minimum return observations to rank a symbol")
    parser.add_argument("--top", type=int, default=5, help="how many names to print")
    parser.add_argument("--no-nse", action="store_true", help="skip NSE and use the static constituent list")
    args = parser.parse_args()

    if args.no_nse:
        symbols = NIFTY50_FALLBACK
    else:
        establish_session()
        symbols = constituents(fetch_snapshot())

    close = fetch_history(symbols, period=args.period)
    stats = analyze_volatility(close, window=args.window, min_obs=args.min_obs)
    return report(stats, window=args.window, top=args.top)


if __name__ == "__main__":
    main()
