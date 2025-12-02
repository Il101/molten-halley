"""
Market Scanner Service

Scans multiple trading pairs across exchanges to identify profitable arbitrage opportunities.
Generates whitelist of validated pairs for live trading.
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import warnings

import ccxt
import pandas as pd
import yaml

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from utils.logger import get_logger
from services.historical_validator import HistoricalValidator

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore")


class MarketScanner:
    """
    Scans cryptocurrency markets to identify arbitrage opportunities.
    
    Performs comprehensive analysis including:
    - Symbol discovery across exchanges
    - Volume and liquidity filtering
    - Statistical validation using HistoricalValidator
    - Whitelist generation for profitable pairs
    """
    
    def __init__(self, config_path: str = 'config/config.yaml'):
        """
        Initialize the Market Scanner.
        
        Args:
            config_path: Path to configuration YAML file
        """
        self.logger = get_logger(__name__)
        self.config = self._load_config(config_path)
        self.exchanges = self._setup_exchanges()
        self.validator = HistoricalValidator(config_path)
        
        self.logger.info("MarketScanner initialized successfully")
    
    def _load_config(self, config_path: str) -> dict:
        """
        Load configuration from YAML file.
        
        Args:
            config_path: Path to config file
            
        Returns:
            Configuration dictionary
        """
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                self.logger.warning(f"Config file not found: {config_path}, using defaults")
                return self._get_default_config()
            
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            self.logger.info(f"Configuration loaded from {config_path}")
            return config
            
        except Exception as e:
            self.logger.error(f"Error loading config: {e}, using defaults")
            return self._get_default_config()
    
    def _get_default_config(self) -> dict:
        """Return default configuration if config file is missing."""
        return {
            'validation': {
                'min_24h_volume': 10000,
                'min_depth_usdt': 5000,
                'timeframe': '1h',
                'candles_limit': 500
            },
            'scanner': {
                'exclude_patterns': ['1000*'],
                'auto_update_whitelist': True
            },
            'trading': {
                'min_spread_pct': 0.003
            },
            'exchanges': {
                'bingx': {'enabled': True, 'default_type': 'swap'},
                'bybit': {'enabled': True, 'default_type': 'linear'}
            }
        }
    
    def _setup_exchanges(self) -> Dict[str, ccxt.Exchange]:
        """
        Initialize CCXT exchange instances.
        
        Returns:
            Dictionary of exchange instances
        """
        exchanges = {}
        
        try:
            # BingX setup
            if self.config['exchanges']['bingx']['enabled']:
                exchanges['bingx'] = ccxt.bingx({
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': self.config['exchanges']['bingx']['default_type']
                    }
                })
                self.logger.debug("BingX exchange initialized")
            
            # Bybit setup
            if self.config['exchanges']['bybit']['enabled']:
                exchanges['bybit'] = ccxt.bybit({
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': self.config['exchanges']['bybit']['default_type']
                    }
                })
                self.logger.debug("Bybit exchange initialized")
            
            return exchanges
            
        except Exception as e:
            self.logger.error(f"Error setting up exchanges: {e}")
            raise
    
    def get_common_symbols(self) -> List[str]:
        """
        Find common trading symbols across both exchanges.
        
        Applies filters from configuration to exclude unwanted symbols.
        
        Returns:
            List of common symbol strings
        """
        self.logger.info("Fetching markets from exchanges...")
        
        try:
            bingx = self.exchanges['bingx']
            bybit = self.exchanges['bybit']
            
            # Load markets
            bingx_markets = bingx.load_markets()
            bybit_markets = bybit.load_markets()
            
            # Get symbol sets
            bingx_symbols = set(bingx_markets.keys())
            bybit_symbols = set(bybit_markets.keys())
            
            # Find intersection
            common_symbols = list(bingx_symbols.intersection(bybit_symbols))
            
            self.logger.info(f"Found {len(common_symbols)} common symbols")
            
            # Apply filters
            exclude_patterns = self.config['scanner'].get('exclude_patterns', [])
            filtered_symbols = []
            
            for symbol in common_symbols:
                # Check exclude patterns
                excluded = False
                for pattern in exclude_patterns:
                    if pattern.endswith('*'):
                        # Prefix match
                        if symbol.startswith(pattern[:-1]):
                            excluded = True
                            break
                    elif pattern.startswith('*'):
                        # Suffix match
                        if symbol.endswith(pattern[1:]):
                            excluded = True
                            break
                    else:
                        # Exact match
                        if symbol == pattern:
                            excluded = True
                            break
                
                if not excluded:
                    filtered_symbols.append(symbol)
            
            self.logger.info(
                f"Filtered to {len(filtered_symbols)} symbols "
                f"(excluded {len(common_symbols) - len(filtered_symbols)})"
            )
            
            return filtered_symbols
            
        except Exception as e:
            self.logger.error(f"Error fetching common symbols: {e}")
            return []
    
    def _get_depth_usdt(self, exchange: ccxt.Exchange, symbol: str) -> float:
        """
        Calculate order book depth in USDT within 2% of mid price.
        
        Args:
            exchange: CCXT exchange instance
            symbol: Trading pair symbol
            
        Returns:
            Total depth in USDT
        """
        try:
            orderbook = exchange.fetch_order_book(symbol, limit=20)
            
            if not orderbook['bids'] or not orderbook['asks']:
                return 0.0
            
            mid_price = (orderbook['bids'][0][0] + orderbook['asks'][0][0]) / 2
            lower_bound = mid_price * 0.98
            upper_bound = mid_price * 1.02
            
            depth_usdt = 0.0
            
            # Sum bids within range
            for price, amount in orderbook['bids']:
                if price >= lower_bound:
                    depth_usdt += price * amount
                else:
                    break
            
            # Sum asks within range
            for price, amount in orderbook['asks']:
                if price <= upper_bound:
                    depth_usdt += price * amount
                else:
                    break
            
            return depth_usdt
            
        except Exception as e:
            self.logger.debug(f"Error fetching depth for {symbol}: {e}")
            return 0.0
    
    def analyze_pair(self, symbol: str) -> Optional[Dict]:
        """
        Perform comprehensive analysis on a single trading pair.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Dictionary with pair metrics, or None if analysis failed
        """
        try:
            bingx = self.exchanges['bingx']
            bybit = self.exchanges['bybit']
            
            # 1. Volume Check
            ticker_a = bingx.fetch_ticker(symbol)
            ticker_b = bybit.fetch_ticker(symbol)
            
            vol_a = ticker_a.get('quoteVolume') or (
                ticker_a.get('baseVolume', 0) * ticker_a.get('last', 0)
            )
            vol_b = ticker_b.get('quoteVolume') or (
                ticker_b.get('baseVolume', 0) * ticker_b.get('last', 0)
            )
            
            min_volume = self.config['validation']['min_24h_volume']
            
            if not vol_a or not vol_b or vol_a < min_volume or vol_b < min_volume:
                self.logger.debug(f"{symbol}: Insufficient volume")
                return None
            
            # 2. Depth Check
            depth_a = self._get_depth_usdt(bingx, symbol)
            depth_b = self._get_depth_usdt(bybit, symbol)
            min_depth = min(depth_a, depth_b)
            
            min_depth_required = self.config['validation']['min_depth_usdt']
            
            if min_depth < min_depth_required:
                self.logger.debug(f"{symbol}: Insufficient depth (${min_depth:.0f})")
                return None
            
            # 3. Historical Analysis using HistoricalValidator
            timeframe = self.config['validation'].get('timeframe', '1h')
            limit = self.config['validation'].get('candles_limit', 500)
            
            analysis = self.validator.analyze(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit
            )
            
            if 'error' in analysis:
                self.logger.debug(f"{symbol}: Analysis failed - {analysis['error']}")
                return None
            
            # 4. Get current prices
            price_a = ticker_a.get('last', 0)
            price_b = ticker_b.get('last', 0)
            price_ratio = price_a / price_b if price_b else 0
            
            # Compile results
            return {
                'symbol': symbol,
                'max_spread_pct': analysis['max_spread_pct'],
                'price_bingx': price_a,
                'price_bybit': price_b,
                'price_ratio': price_ratio,
                'depth_usdt': min_depth,
                'volume_24h': min(vol_a, vol_b),
                'z_score_signals': analysis['z_score_signals'],
                'adf_pvalue': analysis['adf_pvalue'],
                'is_stationary': analysis['is_stationary'],
                'is_profitable': analysis['is_profitable'],
                'data_points': analysis.get('data_points', 0)
            }
            
        except Exception as e:
            self.logger.debug(f"Error analyzing {symbol}: {e}")
            return None
    
    def scan(
        self,
        save_to_whitelist: bool = True,
        csv_path: str = 'arbitrage_candidates.csv'
    ) -> List[Dict]:
        """
        Scan all common symbols and identify profitable arbitrage opportunities.
        
        Args:
            save_to_whitelist: Whether to save results to config/whitelist.json
            csv_path: Path to save CSV results
            
        Returns:
            List of dictionaries with pair analysis results
        """
        self.logger.info("Starting market scan...")
        
        # Get symbols to scan
        symbols = self.get_common_symbols()
        
        if not symbols:
            self.logger.warning("No symbols found to scan")
            return []
        
        results = []
        total = len(symbols)
        
        print(f"\n{'='*60}")
        print(f"Scanning {total} pairs for arbitrage opportunities")
        print(f"{'='*60}\n")
        
        # Scan each symbol
        for i, symbol in enumerate(symbols):
            print(f"[{i+1}/{total}] Analyzing {symbol}...", end='\r')
            
            metrics = self.analyze_pair(symbol)
            
            if metrics:
                results.append(metrics)
                self.logger.debug(f"{symbol}: Analysis complete")
            
            # Rate limiting
            time.sleep(0.5)
        
        print(f"\n\nScan complete. Found {len(results)} valid pairs.\n")
        
        if not results:
            self.logger.warning("No results generated")
            return []
        
        # Convert to DataFrame for processing
        df_results = pd.DataFrame(results)
        
        # Filter by profitability and stationarity
        df_filtered = df_results[
            (df_results['is_profitable'] == True) &
            (df_results['is_stationary'] == True)
        ]
        
        self.logger.info(
            f"Profitable & stationary pairs: {len(df_filtered)}/{len(results)}"
        )
        
        # Sort by max spread descending
        df_sorted = df_filtered.sort_values(by='max_spread_pct', ascending=False)
        
        # Save to CSV
        csv_file = Path(csv_path)
        df_sorted.to_csv(csv_file, index=False)
        self.logger.info(f"Results saved to {csv_file}")
        
        print(f"Saved {len(df_sorted)} profitable pairs to {csv_path}")
        
        # Save to whitelist JSON
        if save_to_whitelist and self.config['scanner'].get('auto_update_whitelist', True):
            self._save_whitelist(df_sorted)
        
        # Print top results
        if not df_sorted.empty:
            print(f"\n{'='*60}")
            print("TOP 10 ARBITRAGE OPPORTUNITIES")
            print(f"{'='*60}\n")
            
            display_df = df_sorted.head(10).copy()
            display_df['max_spread_pct'] = display_df['max_spread_pct'].map('{:.2%}'.format)
            display_df['price_ratio'] = display_df['price_ratio'].map('{:.4f}'.format)
            display_df['depth_usdt'] = display_df['depth_usdt'].map('${:,.0f}'.format)
            display_df['volume_24h'] = display_df['volume_24h'].map('${:,.0f}'.format)
            display_df['adf_pvalue'] = display_df['adf_pvalue'].map('{:.4f}'.format)
            
            print(display_df[['symbol', 'max_spread_pct', 'z_score_signals', 'depth_usdt', 'volume_24h']].to_string(index=False))
            print()
        
        return df_sorted.to_dict('records')
    
    def _save_whitelist(self, df: pd.DataFrame) -> None:
        """
        Save scan results to whitelist JSON file.
        
        Args:
            df: DataFrame with filtered results
        """
        whitelist_path = Path('config/whitelist.json')
        
        try:
            # Prepare whitelist data
            pairs = df.to_dict('records')
            
            whitelist_data = {
                'last_updated': datetime.now().isoformat(),
                'pairs': pairs,
                'metadata': {
                    'total_pairs': len(pairs),
                    'scan_timestamp': datetime.now().isoformat(),
                    'filters_applied': {
                        'min_volume': self.config['validation']['min_24h_volume'],
                        'min_depth': self.config['validation']['min_depth_usdt'],
                        'min_spread': self.config['trading']['min_spread_pct'],
                        'require_stationary': True
                    }
                }
            }
            
            # Save to file
            with open(whitelist_path, 'w') as f:
                json.dump(whitelist_data, f, indent=2)
            
            self.logger.info(f"Whitelist saved to {whitelist_path}")
            print(f"Whitelist updated: {whitelist_path}")
            
        except Exception as e:
            self.logger.error(f"Error saving whitelist: {e}")


def main():
    """Command-line interface for market scanning."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Scan markets for arbitrage opportunities'
    )
    parser.add_argument(
        '--config',
        default='config/config.yaml',
        help='Path to config file (default: config/config.yaml)'
    )
    parser.add_argument(
        '--no-whitelist',
        action='store_true',
        help='Skip whitelist generation'
    )
    parser.add_argument(
        '--csv',
        default='arbitrage_candidates.csv',
        help='Path to save CSV results (default: arbitrage_candidates.csv)'
    )
    
    args = parser.parse_args()
    
    # Create scanner
    scanner = MarketScanner(config_path=args.config)
    
    # Run scan
    results = scanner.scan(
        save_to_whitelist=not args.no_whitelist,
        csv_path=args.csv
    )
    
    print(f"\n{'='*60}")
    print(f"Scan complete! Found {len(results)} profitable opportunities.")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
