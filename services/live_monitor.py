"""
Live Monitor Service

Consumes real-time WebSocket price feeds and calculates live Z-Scores for arbitrage monitoring.
Detects entry/exit signals and emits events via EventBus.

HYBRID APPROACH:
- Pre-loads 60 minutes of historical 1-minute candles to establish baseline spread statistics
- Calculates real-time Z-Scores by comparing live tick spreads against historical baseline
- Updates historical baseline once per minute to keep it moving forward slowly
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, List, Optional
from collections import deque
from datetime import datetime
import signal
import time

import pandas as pd
import ccxt.async_support as ccxt

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from core.ws_manager import WebSocketManager
from core.event_bus import EventBus
from utils.metrics import calculate_z_score
from utils.logger import get_logger


class LiveMonitor:
    """
    Real-time arbitrage monitoring service with hybrid Z-Score calculation.
    
    Consumes WebSocket price feeds, calculates spreads and Z-Scores against
    historical baseline, and emits trading signals when thresholds are crossed.
    """
    
    def __init__(self, config_path: str = 'config/config.yaml'):
        """
        Initialize Live Monitor.
        
        Args:
            config_path: Path to configuration file
        """
        self.logger = get_logger(__name__)
        
        # Components
        self.ws_manager = WebSocketManager(config_path)
        self.event_bus = EventBus.instance()
        self.config = self.ws_manager.config
        
        # Initialize CCXT exchanges for historical data
        self.bingx = ccxt.bingx({
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        self.bybit = ccxt.bybit({
            'enableRateLimit': True,
            'options': {'defaultType': 'linear'}
        })
        
        # Spread history storage (symbol -> deque of historical spreads from 1m candles)
        # This forms the BASELINE for Z-Score calculation
        self.spread_history: Dict[str, deque] = {}
        self.history_length = 60  # 60 minutes of historical baseline
        
        # Track last history update time for each symbol
        self.last_history_update: Dict[str, float] = {}
        self.history_update_interval = 60  # Update once per minute (seconds)
        
        # Price cache for pairing
        self.price_cache: Dict[str, Dict[str, dict]] = {
            'bingx': {},
            'bybit': {}
        }
        
        # Signal state tracking
        self.in_position: Dict[str, bool] = {}
        
        # Control
        self.running = False
        self.monitor_task: Optional[asyncio.Task] = None
        
        self.logger.info("LiveMonitor initialized with hybrid Z-Score approach")
    
    async def _preload_history(self, symbol: str) -> None:
        """
        Pre-load historical 1-minute candles for baseline spread calculation.
        
        Fetches the last 60 candles (1m timeframe) from both exchanges,
        calculates historical spreads, and populates spread_history.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
        """
        try:
            self.logger.info(f"Pre-loading 60 minutes of history for {symbol}...")
            
            # Fetch 1-minute candles from both exchanges
            # Format: [[timestamp, open, high, low, close, volume], ...]
            bingx_candles = await self.bingx.fetch_ohlcv(
                symbol=symbol,
                timeframe='1m',
                limit=60
            )
            
            bybit_candles = await self.bybit.fetch_ohlcv(
                symbol=symbol,
                timeframe='1m',
                limit=60
            )
            
            # Ensure we have data from both exchanges
            if not bingx_candles or not bybit_candles:
                self.logger.warning(
                    f"Failed to fetch candles for {symbol}. "
                    f"BingX: {len(bingx_candles) if bingx_candles else 0}, "
                    f"Bybit: {len(bybit_candles) if bybit_candles else 0}"
                )
                # Fallback: start with empty deque
                self.spread_history[symbol] = deque(maxlen=self.history_length)
                self.last_history_update[symbol] = time.time()
                return
            
            # Convert to DataFrames for easier processing
            df_bingx = pd.DataFrame(
                bingx_candles,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df_bybit = pd.DataFrame(
                bybit_candles,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            
            # Align by timestamp (use inner join to ensure matching timestamps)
            df_bingx['time'] = pd.to_datetime(df_bingx['timestamp'], unit='ms')
            df_bybit['time'] = pd.to_datetime(df_bybit['timestamp'], unit='ms')
            
            df_merged = pd.merge(
                df_bingx[['time', 'close']],
                df_bybit[['time', 'close']],
                on='time',
                suffixes=('_bingx', '_bybit')
            )
            
            # Calculate historical spreads: Close_BingX - Close_Bybit
            df_merged['spread'] = df_merged['close_bingx'] - df_merged['close_bybit']
            
            # Populate spread_history
            historical_spreads = df_merged['spread'].tolist()
            self.spread_history[symbol] = deque(
                historical_spreads,
                maxlen=self.history_length
            )
            
            # Set initial update time
            self.last_history_update[symbol] = time.time()
            
            self.logger.info(
                f"✅ Pre-loaded 60 minutes of history for {symbol}. "
                f"Got {len(self.spread_history[symbol])} spread values. "
                f"Initial Z-Score parameters set."
            )
            
        except Exception as e:
            self.logger.error(f"Error pre-loading history for {symbol}: {e}")
            # Fallback: start with empty deque and build gradually
            self.spread_history[symbol] = deque(maxlen=self.history_length)
            self.last_history_update[symbol] = time.time()
            self.logger.warning(
                f"Starting with empty history for {symbol}. "
                f"Will build baseline slowly."
            )
    
    async def _process_price_updates(self) -> None:
        """
        Continuously process price updates from WebSocket queue.
        """
        queue = self.ws_manager.get_queue()
        
        while self.running:
            try:
                # Get price update with timeout
                data = await asyncio.wait_for(queue.get(), timeout=1.0)
                
                # Update price cache
                exchange = data['exchange']
                symbol = data['symbol']
                self.price_cache[exchange][symbol] = data
                
                # Emit price update event
                self.event_bus.emit_price_update(data)
                
                # Check if we have prices from both exchanges
                await self._check_arbitrage_opportunity(symbol)
            
            except asyncio.TimeoutError:
                # No message received, continue
                continue
            
            except Exception as e:
                self.logger.error(f"Error processing price update: {e}")
                self.event_bus.emit_error('LiveMonitor', str(e))
    
    async def _check_arbitrage_opportunity(self, symbol: str) -> None:
        """
        Check for arbitrage opportunity when we have prices from both exchanges.
        
        HYBRID CALCULATION:
        - Step A: Calculate current_spread from live ticks (Ask - Bid)
        - Step A: Calculate Z-Score using historical baseline (spread_history)
        - Step B: Once per minute, update the historical baseline
        
        Args:
            symbol: Trading pair symbol
        """
        # Check if we have prices from both exchanges
        bingx_price = self.price_cache['bingx'].get(symbol)
        bybit_price = self.price_cache['bybit'].get(symbol)
        
        if not bingx_price or not bybit_price:
            return
        
        # === STEP A: LIVE CALCULATION ===
        
        # Calculate current executable spread (buy on one, sell on other)
        # Spread = ask_A - bid_B (cost to execute arbitrage)
        spread_a_to_b = bingx_price['ask'] - bybit_price['bid']
        spread_b_to_a = bybit_price['ask'] - bingx_price['bid']
        
        # Use the more favorable spread
        current_spread = min(abs(spread_a_to_b), abs(spread_b_to_a))
        if spread_a_to_b < 0:
            current_spread = -current_spread  # Negative spread means BingX cheaper
        
        # Initialize position tracking if needed
        if symbol not in self.in_position:
            self.in_position[symbol] = False
        
        # Check if we have historical baseline
        if symbol not in self.spread_history or len(self.spread_history[symbol]) < 10:
            # Not enough history yet, skip Z-Score calculation
            return
        
        # Calculate Z-Score from historical baseline
        try:
            # Get mean and std from historical baseline
            spreads = list(self.spread_history[symbol])
            mean = sum(spreads) / len(spreads)
            
            # Calculate standard deviation
            variance = sum((x - mean) ** 2 for x in spreads) / len(spreads)
            std_dev = variance ** 0.5
            
            # Handle zero standard deviation
            if std_dev == 0:
                self.logger.debug(f"{symbol}: Zero std deviation, setting Z-Score to 0")
                z_score = 0.0
            else:
                # Calculate Z-Score: (current_spread - baseline_mean) / baseline_std
                z_score = (current_spread - mean) / std_dev
            
            # Emit spread update
            self.event_bus.emit_spread_update(symbol, current_spread, z_score)
            
            # Check for entry/exit signals
            await self._check_signals(symbol, z_score, current_spread)
            
        except ZeroDivisionError:
            self.logger.warning(f"{symbol}: ZeroDivisionError in Z-Score calculation")
            z_score = 0.0
        except Exception as e:
            self.logger.error(f"{symbol}: Error calculating Z-Score: {e}")
            return
        
        # === STEP B: HISTORY MAINTENANCE ===
        
        # Update historical baseline once per minute
        current_time = time.time()
        time_since_update = current_time - self.last_history_update.get(symbol, 0)
        
        if time_since_update >= self.history_update_interval:
            # Add current spread to history (this updates the baseline slowly)
            self.spread_history[symbol].append(current_spread)
            self.last_history_update[symbol] = current_time
            
            self.logger.debug(
                f"{symbol}: Updated historical baseline "
                f"(size={len(self.spread_history[symbol])})"
            )
    
    async def _check_signals(self, symbol: str, z_score: float, spread: float) -> None:
        """
        Check if entry or exit signal conditions are met.
        
        Args:
            symbol: Trading pair symbol
            z_score: Current Z-Score
            spread: Current spread value
        """
        z_entry = self.config['trading']['z_score_entry']
        z_exit = self.config['trading']['z_score_exit']
        min_spread_pct = self.config['trading']['min_spread_pct']
        
        # Calculate spread percentage (approximate, using BingX price as base)
        bingx_price = self.price_cache['bingx'].get(symbol, {}).get('last', 1)
        spread_pct = abs(spread) / bingx_price if bingx_price > 0 else 0
        
        # Entry signal: |Z-Score| > threshold AND spread > min required
        if not self.in_position[symbol]:
            if abs(z_score) > z_entry and spread_pct > min_spread_pct:
                self.in_position[symbol] = True
                self.event_bus.emit_signal_triggered(symbol, 'ENTRY', z_score)
                self.logger.info(
                    f"🔔 ENTRY SIGNAL: {symbol} | Z-Score={z_score:.2f} | "
                    f"Spread={spread_pct*100:.3f}%"
                )
        
        # Exit signal: |Z-Score| < exit threshold
        else:
            if abs(z_score) < z_exit:
                self.in_position[symbol] = False
                self.event_bus.emit_signal_triggered(symbol, 'EXIT', z_score)
                self.logger.info(
                    f"🔔 EXIT SIGNAL: {symbol} | Z-Score={z_score:.2f}"
                )
    
    async def start(self, symbols: List[str]) -> None:
        """
        Start live monitoring for given symbols.
        
        Pre-loads historical data before starting WebSocket monitoring.
        
        Args:
            symbols: List of trading pair symbols to monitor
        """
        self.running = True
        self.logger.info(f"Starting LiveMonitor for {len(symbols)} symbols")
        
        # Pre-load historical data for all symbols
        for symbol in symbols:
            await self._preload_history(symbol)
        
        # Start WebSocket manager
        await self.ws_manager.start(symbols)
        
        # Start price processing task
        self.monitor_task = asyncio.create_task(self._process_price_updates())
        
        self.logger.info("LiveMonitor started with hybrid Z-Score calculation")
    
    async def stop(self) -> None:
        """
        Stop live monitoring and cleanup resources.
        """
        self.logger.info("Stopping LiveMonitor...")
        self.running = False
        
        # Stop WebSocket manager
        await self.ws_manager.stop()
        
        # Cancel monitor task
        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        # Close CCXT exchanges
        await self.bingx.close()
        await self.bybit.close()
        
        # Clear buffers
        self.spread_history.clear()
        self.price_cache = {'bingx': {}, 'bybit': {}}
        self.last_history_update.clear()
        
        self.logger.info("LiveMonitor stopped")
    
    def get_current_stats(self, symbol: str) -> Optional[Dict]:
        """
        Get current statistics for a symbol.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Dictionary with current stats or None
        """
        if symbol not in self.spread_history:
            return None
        
        if len(self.spread_history[symbol]) < 10:
            return None
        
        # Get current prices
        bingx_price = self.price_cache['bingx'].get(symbol)
        bybit_price = self.price_cache['bybit'].get(symbol)
        
        if not bingx_price or not bybit_price:
            return None
        
        # Calculate current spread
        spread_a_to_b = bingx_price['ask'] - bybit_price['bid']
        spread_b_to_a = bybit_price['ask'] - bingx_price['bid']
        current_spread = min(abs(spread_a_to_b), abs(spread_b_to_a))
        if spread_a_to_b < 0:
            current_spread = -current_spread
        
        # Calculate Z-Score from historical baseline
        spreads = list(self.spread_history[symbol])
        mean = sum(spreads) / len(spreads)
        variance = sum((x - mean) ** 2 for x in spreads) / len(spreads)
        std_dev = variance ** 0.5
        
        if std_dev == 0:
            z_score = 0.0
        else:
            z_score = (current_spread - mean) / std_dev
        
        return {
            'symbol': symbol,
            'spread': current_spread,
            'z_score': z_score,
            'in_position': self.in_position.get(symbol, False),
            'history_length': len(self.spread_history[symbol]),
            'baseline_mean': mean,
            'baseline_std': std_dev
        }


async def main():
    """CLI interface for testing LiveMonitor."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Live Arbitrage Monitor (Hybrid Z-Score)')
    parser.add_argument(
        'symbols',
        nargs='*',
        default=['BTC/USDT'],
        help='Symbols to monitor (default: BTC/USDT)'
    )
    parser.add_argument(
        '--config',
        default='config/config.yaml',
        help='Path to config file'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=5,
        help='Stats display interval in seconds (default: 5)'
    )
    
    args = parser.parse_args()
    
    # Create monitor
    monitor = LiveMonitor(config_path=args.config)
    
    # Setup graceful shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler(sig, frame):
        print("\n\nReceived shutdown signal...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start monitoring (includes pre-loading history)
    await monitor.start(args.symbols)
    
    print(f"\n{'='*70}")
    print(f"Live Arbitrage Monitor (Hybrid Z-Score) - {', '.join(args.symbols)}")
    print(f"{'='*70}\n")
    print("Pre-loaded historical baseline. Monitoring live ticks...\n")
    
    # Stats display loop
    try:
        while not shutdown_event.is_set():
            await asyncio.sleep(args.interval)
            
            print(f"\n{datetime.now().strftime('%H:%M:%S')} - Current Stats:")
            print(f"{'-'*70}")
            
            for symbol in args.symbols:
                stats = monitor.get_current_stats(symbol)
                
                if stats:
                    position_indicator = "📈 IN POSITION" if stats['in_position'] else "⏸️  WAITING"
                    
                    print(
                        f"{symbol:12} | "
                        f"Spread: {stats['spread']:8.2f} | "
                        f"Z-Score: {stats['z_score']:6.2f} | "
                        f"Baseline μ={stats['baseline_mean']:.2f} σ={stats['baseline_std']:.2f} | "
                        f"{position_indicator}"
                    )
                else:
                    history_len = len(monitor.spread_history.get(symbol, deque()))
                    print(f"{symbol:12} | Building baseline... ({history_len}/60 samples)")
            
            print(f"{'-'*70}")
    
    except Exception as e:
        print(f"\nError: {e}")
    
    finally:
        print("\nShutting down...")
        await monitor.stop()
        print("Stopped.")


if __name__ == '__main__':
    asyncio.run(main())
