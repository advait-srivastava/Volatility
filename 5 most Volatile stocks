import requests
import pandas as pd
import numpy as np
from scipy.stats import skew, kurtosis
import time

# Session with cookie handling
session = requests.Session()

# NSE URLs
BASE_URL = "https://www.nseindia.com"
STOCK_URL = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050"  # Correct NSE API URL

# Headers for browser emulation
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE_URL
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

# Step 2: Fetch NSE stock data with JSON error handling & retries
def fetch_data(retries=3):
    for attempt in range(retries):
        try:
            print(f" Fetching data from NSE (Attempt {attempt + 1}/{retries})...")
            response = session.get(STOCK_URL, headers=HEADERS, timeout=10)

            # Debugging: Print response status
            print(f"Response Status Code: {response.status_code}")

            # Raise an error for bad responses (4xx, 5xx)
            response.raise_for_status()

            # Try to parse JSON
            data = response.json().get('data', [])

            if not data:
                print("Warning: Empty data received. NSE may have restricted access.")

            print(f"Fetched {len(data)} stock records.")
            return data

        except requests.exceptions.JSONDecodeError:
            print("JSON Decode Error: Response is not in JSON format. Possible NSE block.")
            print("Response (First 500 chars):", response.text[:500])

        except requests.exceptions.HTTPError as e:
            print(f" HTTP Error: {e}, Status Code: {response.status_code}")

        except requests.exceptions.RequestException as e:
            print(f" Request failed: {e}")

        # Wait before retrying
        print(" Retrying in 5 seconds...")
        time.sleep(5)

    print(" Failed to fetch data after multiple attempts.")
    return []  # Return empty list if all retries fail
# Step 3: Analyze Volatility
def analyze_volatility(stock_data):
    if not stock_data:
        print(" No stock data available for analysis.")
        return pd.DataFrame()

    df = pd.DataFrame(stock_data)

    # Ensure necessary columns exist
    if 'lastPrice' not in df.columns or 'previousClose' not in df.columns:
        print(" Error: Required price columns not found in the data.")
        return pd.DataFrame()

    # Convert to float
    df['lastPrice'] = pd.to_numeric(df['lastPrice'], errors='coerce')
    df['previousClose'] = pd.to_numeric(df['previousClose'], errors='coerce')

    # Drop rows with missing values
    df.dropna(subset=['lastPrice', 'previousClose'], inplace=True)

    # Calculate Daily Return Percentage
    df['Return (%)'] = ((df['lastPrice'] - df['previousClose']) / df['previousClose']) * 100

    # Calculate Standard Deviation (Volatility)
    df['Volatility'] = df['Return (%)'].rolling(window=5).std()

    # Compute Skewness & Excess Kurtosis
    df['Skewness'] = df['Return (%)'].rolling(window=5).apply(lambda x: skew(x, bias=False), raw=True)
    df['Kurtosis'] = df['Return (%)'].rolling(window=5).apply(lambda x: kurtosis(x, bias=False), raw=True)

    # Sort stocks by volatility (highest first)
    top_volatile_stocks = df.nlargest(5, 'Volatility')

    print("\n 5 Most Volatile Stocks:")
    print(top_volatile_stocks[['symbol', 'Return (%)', 'Volatility', 'Skewness', 'Kurtosis']])

    return top_volatile_stocks
# Step 4: Main Execution
if __name__ == "__main__":
    establish_session()  # Initialize session
    stock_data = fetch_data()  # Fetch stock data
    top_volatile = analyze_volatility(stock_data)  # Analyze volatility
