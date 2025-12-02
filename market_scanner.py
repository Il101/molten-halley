import ccxt
import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import adfuller
import time
import warnings

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore")

def get_common_symbols():
    """
    Fetches markets from BingX and Bybit and finds common linear futures symbols.
    """
    print("Fetching markets...")
    try:
        bingx = ccxt.bingx({'options': {'defaultType': 'swap'}})
        bybit = ccxt.bybit({'options': {'defaultType': 'linear'}})
        
        bingx_markets = bingx.load_markets()
        bybit_markets = bybit.load_markets()
        
        bingx_symbols = set(bingx_markets.keys())
        bybit_symbols = set(bybit_markets.keys())
        
        common_symbols = list(bingx_symbols.intersection(bybit_symbols))
        
        # Filter out "1000" symbols
        filtered_symbols = [s for s in common_symbols if not s.startswith('1000')]
        
        print(f"Found {len(common_symbols)} common symbols.")
        print(f"Filtered down to {len(filtered_symbols)} symbols (excluding '1000' prefix).")
        
        return filtered_symbols, bingx, bybit
        
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return [], None, None

def get_depth_usdt(exchange, symbol):
    """
    Calculates the depth in USDT within 2% of the mid price.
    """
    try:
        orderbook = exchange.fetch_order_book(symbol, limit=20)
        if not orderbook['bids'] or not orderbook['asks']:
            return 0
            
        mid_price = (orderbook['bids'][0][0] + orderbook['asks'][0][0]) / 2
        lower_bound = mid_price * 0.98
        upper_bound = mid_price * 1.02
        
        depth_usdt = 0
        
        # Sum bids
        for price, amount in orderbook['bids']:
            if price >= lower_bound:
                depth_usdt += price * amount
            else:
                break
                
        # Sum asks
        for price, amount in orderbook['asks']:
            if price <= upper_bound:
                depth_usdt += price * amount
            else:
                break
                
        return depth_usdt
        
    except Exception as e:
        return 0

def analyze_pair(exchange_a, exchange_b, symbol):
    """
    Analyzes a single pair for arbitrage opportunities.
    """
    try:
        # 1. Volume Check (24h)
        ticker_a = exchange_a.fetch_ticker(symbol)
        ticker_b = exchange_b.fetch_ticker(symbol)
        
        vol_a = ticker_a.get('quoteVolume') or (ticker_a.get('baseVolume') * ticker_a.get('last'))
        vol_b = ticker_b.get('quoteVolume') or (ticker_b.get('baseVolume') * ticker_b.get('last'))
        
        if not vol_a or not vol_b:
            return None
            
        # Minimal Volume Filter (> $10k)
        if vol_a < 10000 or vol_b < 10000:
            return None

        # 2. Fetch Candles
        limit = 500
        timeframe = '1h'
        
        ohlcv_a = exchange_a.fetch_ohlcv(symbol, timeframe, limit=limit)
        ohlcv_b = exchange_b.fetch_ohlcv(symbol, timeframe, limit=limit)
        
        if not ohlcv_a or not ohlcv_b:
            return None
            
        df_a = pd.DataFrame(ohlcv_a, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_b = pd.DataFrame(ohlcv_b, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df_a['timestamp'] = pd.to_datetime(df_a['timestamp'], unit='ms')
        df_b['timestamp'] = pd.to_datetime(df_b['timestamp'], unit='ms')
        
        # Merge
        df = pd.merge(df_a[['timestamp', 'close']], df_b[['timestamp', 'close']], on='timestamp', how='inner', suffixes=('_bingx', '_bybit'))
        
        if len(df) < 50:
            return None
            
        # 3. Analysis
        df['spread'] = df['close_bingx'] - df['close_bybit']
        df['spread_pct'] = df['spread'].abs() / df['close_bingx']
        
        # Z-Score
        window = 20
        df['spread_mean'] = df['spread'].rolling(window=window).mean()
        df['spread_std'] = df['spread'].rolling(window=window).std()
        df['z_score'] = (df['spread'] - df['spread_mean']) / df['spread_std']
        
        # ADF Test
        try:
            adf_result = adfuller(df['spread'])
            adf_pvalue = adf_result[1]
        except:
            adf_pvalue = 1.0 # Fail safe
        
        # Metrics
        z_score_signals = len(df[df['z_score'].abs() > 2])
        max_spread_pct = df['spread_pct'].max()
        
        # Current Prices
        price_a = df['close_bingx'].iloc[-1]
        price_b = df['close_bybit'].iloc[-1]
        price_ratio = price_a / price_b if price_b else 0
        
        # 4. Depth Check
        depth_a = get_depth_usdt(exchange_a, symbol)
        depth_b = get_depth_usdt(exchange_b, symbol)
        min_depth = min(depth_a, depth_b)
        
        return {
            'Symbol': symbol,
            'Max_Spread_Pct': max_spread_pct,
            'Price_BingX': price_a,
            'Price_Bybit': price_b,
            'Price_Ratio': price_ratio,
            'Depth_USDT': min_depth,
            'Z_Score_Signals': z_score_signals,
            'ADF_Pvalue': adf_pvalue
        }
        
    except Exception as e:
        # print(f"Error analyzing {symbol}: {e}")
        return None

def main():
    symbols, bingx, bybit = get_common_symbols()
    
    if not symbols:
        print("No symbols found. Exiting.")
        return
        
    results = []
    
    print(f"Starting scan of {len(symbols)} pairs...")
    print("Filters: 24h Vol > $10k. Showing ALL spreads.")
    
    for i, symbol in enumerate(symbols):
        print(f"[{i+1}/{len(symbols)}] Analyzing {symbol}...", end='\r')
        
        metrics = analyze_pair(bingx, bybit, symbol)
        if metrics:
            results.append(metrics)
            
        time.sleep(0.5) # Rate limiting
        
    print("\nScan complete. Processing results...")
    
    if not results:
        print("No results generated.")
        return
        
    df_results = pd.DataFrame(results)
    
    # Sort by Max Spread descending
    sorted_df = df_results.sort_values(by='Max_Spread_Pct', ascending=False)
    
    # Save
    sorted_df.to_csv('arbitrage_candidates.csv', index=False)
    print("Full report saved to 'arbitrage_candidates.csv'")
    
    # Print Top 10
    print("\n--- Top 10 Anomalies (Max Spread) ---")
    if not sorted_df.empty:
        # Format for display
        display_df = sorted_df.copy()
        display_df['Max_Spread_Pct'] = display_df['Max_Spread_Pct'].map('{:.2%}'.format)
        display_df['Price_Ratio'] = display_df['Price_Ratio'].map('{:.2f}'.format)
        display_df['Depth_USDT'] = display_df['Depth_USDT'].map('${:,.0f}'.format)
        display_df['ADF_Pvalue'] = display_df['ADF_Pvalue'].map('{:.4f}'.format)
        
        print(display_df.head(10).to_string(index=False))
    else:
        print("No pairs found.")

if __name__ == "__main__":
    main()
