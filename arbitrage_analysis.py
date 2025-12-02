import ccxt
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from statsmodels.tsa.stattools import adfuller
from datetime import datetime

def fetch_data(exchange_id, symbol, timeframe, limit):
    """
    Fetches historical OHLCV data for a given exchange and symbol.
    Ensures 'swap' (perpetual futures) market is used.
    """
    print(f"Fetching data from {exchange_id}...")
    try:
        exchange_class = getattr(ccxt, exchange_id)
        
        # Configure options for perpetual futures
        options = {}
        if exchange_id == 'bybit':
            options = {'defaultType': 'linear'}
        elif exchange_id == 'bingx':
            options = {'defaultType': 'swap'}
            
        exchange = exchange_class({
            'enableRateLimit': True,
            'options': options
        })

        # Fetch OHLCV data with pagination
        all_ohlcv = []
        duration_ms = exchange.parse_timeframe(timeframe) * 1000
        now = exchange.milliseconds()
        since = now - (limit * duration_ms)
        
        print(f"Fetching {limit} candles starting from {datetime.fromtimestamp(since/1000)}...")
        
        while len(all_ohlcv) < limit:
            fetch_limit = min(limit - len(all_ohlcv), 1000) # Max 1000 per request usually
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=fetch_limit)
                if not ohlcv:
                    break
                
                all_ohlcv.extend(ohlcv)
                
                # Update 'since' for next batch
                last_timestamp = ohlcv[-1][0]
                since = last_timestamp + duration_ms
                
                # If we reached current time, stop
                if since > now:
                    break
                    
            except Exception as e:
                print(f"Error fetching chunk: {e}")
                break
        
        # Convert to DataFrame
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Remove duplicates if any
        df = df.drop_duplicates(subset='timestamp')
        
        print(f"Fetched {len(df)} candles from {exchange_id}.")
        return df[['timestamp', 'close']]
        
    except Exception as e:
        print(f"Error fetching data from {exchange_id}: {e}")
        return None

def analyze():
    symbol = 'BTC/USDT'
    timeframe = '5m'
    limit = 4000 # Increased to cover ~14 days at 5m intervals
    ESTIMATED_FEE = 0.002 # 0.2%

    # 1. Fetch Data
    bingx_df = fetch_data('bingx', symbol, timeframe, limit)
    bybit_df = fetch_data('bybit', symbol, timeframe, limit)

    if bingx_df is None or bybit_df is None:
        print("Failed to fetch data. Exiting.")
        return

    # 2. Data Processing (Inner Join)
    # Rename columns to distinguish exchanges
    bingx_df = bingx_df.rename(columns={'close': 'bingx_close'})
    bybit_df = bybit_df.rename(columns={'close': 'bybit_close'})

    # Merge on timestamp
    df = pd.merge(bingx_df, bybit_df, on='timestamp', how='inner')
    df = df.set_index('timestamp')
    
    print(f"Data aligned. {len(df)} overlapping periods found.")

    # 3. Analysis
    # Calculate Spread
    df['spread'] = df['bingx_close'] - df['bybit_close']
    
    # Calculate Spread Percentage (using BingX price as base)
    df['spread_pct'] = df['spread'].abs() / df['bingx_close']

    # ADF Test for Stationarity
    adf_result = adfuller(df['spread'])
    print(f"\nADF Statistic: {adf_result[0]}")
    print(f"P-Value: {adf_result[1]}")
    if adf_result[1] < 0.05:
        print("Result: The spread is likely stationary (good for mean reversion).")
    else:
        print("Result: The spread is likely non-stationary (trending).")

    # Z-Score Calculation
    window = 20
    df['spread_mean'] = df['spread'].rolling(window=window).mean()
    df['spread_std'] = df['spread'].rolling(window=window).std()
    df['z_score'] = (df['spread'] - df['spread_mean']) / df['spread_std']

    # Calculate average standard deviation to explain Z-Score
    avg_std = df['spread_std'].mean()
    print(f"\n--- Z-Score Context ---")
    print(f"Average Spread Standard Deviation (1 Sigma): {avg_std:.2f} USDT")
    print(f"Z-Score of 2 corresponds to roughly: {avg_std * 2:.2f} USDT difference (plus mean)")
    
    # 4. Profitability Analysis
    # Signal A: Statistical (Z > 2)
    stat_signals = df[df['z_score'].abs() > 2]
    count_z = len(stat_signals)
    
    # Signal B: Profitable (Z > 2 AND Spread % > Fee)
    profitable_signals = df[(df['z_score'].abs() > 2) & (df['spread_pct'] > ESTIMATED_FEE)]
    count_profitable = len(profitable_signals)
    
    max_spread_pct = df['spread_pct'].max()
    
    verdict = "SAFE TO TRADE" if count_profitable > 0 else "UNPROFITABLE PAIR"
    
    report_text = (
        f"ANALYSIS REPORT:\n"
        f"- Estimated Fee Threshold: {ESTIMATED_FEE*100:.2f}%\n"
        f"- Max Spread Found: {max_spread_pct*100:.4f}%\n"
        f"- Statistical Signals (Z>2): {count_z}\n"
        f"- PROFITABLE Signals (Z>2 & Spread > Fee): {count_profitable}\n"
        f"- VERDICT: {verdict}"
    )
    print(f"\n{report_text}")

    # 5. Visualization
    sns.set_theme(style="darkgrid")
    fig, axes = plt.subplots(3, 1, figsize=(12, 12), sharex=True) # Increased height for text

    # Plot 1: Prices (Adjusted for visibility)
    axes[0].plot(df.index, df['bingx_close'], label='BingX', color='blue', linewidth=2, alpha=0.6)
    axes[0].plot(df.index, df['bybit_close'], label='Bybit', color='orange', linewidth=1, linestyle='--', alpha=0.9)
    axes[0].set_title(f'{symbol} Price History (Perpetual Futures)')
    axes[0].set_ylabel('Price (USDT)')
    axes[0].legend()

    # Plot 2: Spread
    axes[1].plot(df.index, df['spread'], label='Spread (BingX - Bybit)', color='purple', linewidth=1)
    axes[1].set_title('Price Spread (USDT)')
    axes[1].set_ylabel('Spread (USDT)')
    axes[1].legend()

    # Plot 3: Z-Score
    axes[2].plot(df.index, df['z_score'], label='Z-Score (20 period)', color='green', linewidth=1)
    axes[2].axhline(2, color='red', linestyle='--', alpha=0.6, label='Entry Threshold (+/- 2)')
    axes[2].axhline(-2, color='red', linestyle='--', alpha=0.6)
    axes[2].axhline(0, color='black', linestyle='-', alpha=0.4, label='Mean')
    
    # Highlight entry zones
    axes[2].fill_between(df.index, 2, df['z_score'], where=(df['z_score'] > 2), color='red', alpha=0.3)
    axes[2].fill_between(df.index, -2, df['z_score'], where=(df['z_score'] < -2), color='red', alpha=0.3)
    
    axes[2].set_title('Z-Score of Spread')
    axes[2].set_ylabel('Z-Score')
    axes[2].legend(loc='upper left')
    
    # Add Text Report
    plt.figtext(0.1, 0.02, report_text, fontsize=10, bbox={"facecolor":"white", "alpha":0.8, "pad":5})
    
    # Adjust layout to make room for text
    plt.subplots_adjust(bottom=0.15)

    plt.show()
    
    # Save plot
    plt.savefig('arbitrage_analysis_plot.png')
    print("Plot saved as 'arbitrage_analysis_plot.png'")

if __name__ == "__main__":
    analyze()
