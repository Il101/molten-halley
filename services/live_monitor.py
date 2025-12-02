"""
Live Monitor Service

Consumes real-time WebSocket price feeds and calculates live Z-Scores for arbitrage monitoring.
Detects entry/exit signals and emits events via EventBus.
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, List, Optional
from collections import deque
from datetime import datetime
import signal

import pandas as pd

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from core.ws_manager import WebSocketManager
from core.event_bus import EventBus
from utils.metrics import calculate_z_score
from utils.logger import get_logger


class LiveMonitor:
    """
    Real-time arbitrage monitoring service.
    
    Consumes WebSocket price feeds, calculates spreads and Z-Scores,
    and emits trading signals when thresholds are crossed.
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
        
        # Spread history storage (symbol -> deque of spreads)
        z_window = self.config['validation']['z_score_window']
        self.spread_history: Dict[str, deque] = {}
        self.max_history_length = z_window * 2  # Store 2x window for better stats
        
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
        
        self.logger.info("LiveMonitor initialized")
    
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
        
        Args:
            symbol: Trading pair symbol
        """
        # Check if we have prices from both exchanges
        bingx_price = self.price_cache['bingx'].get(symbol)
        bybit_price = self.price_cache['bybit'].get(symbol)
        
        if not bingx_price or not bybit_price:
            return
        
        # Calculate executable spread (buy on one, sell on other)
        # Spread = ask_A - bid_B (cost to execute arbitrage)
        spread_a_to_b = bingx_price['ask'] - bybit_price['bid']
        spread_b_to_a = bybit_price['ask'] - bingx_price['bid']
        
        # Use the more favorable spread
        spread = min(abs(spread_a_to_b), abs(spread_b_to_a))
        if spread_a_to_b < 0:
            spread = -spread  # Negative spread means BingX cheaper
        
        # Initialize spread history for this symbol if needed
        if symbol not in self.spread_history:
            self.spread_history[symbol] = deque(maxlen=self.max_history_length)
            self.in_position[symbol] = False
        
        # Store spread
        self.spread_history[symbol].append(spread)
        
        # Calculate Z-Score if we have enough history
        if len(self.spread_history[symbol]) >= self.config['validation']['z_score_window']:
            spread_series = pd.Series(list(self.spread_history[symbol]))
            z_score_series = calculate_z_score(
                spread_series,
                window=self.config['validation']['z_score_window']
            )
            
            # Get current Z-Score (last value)
            current_z_score = z_score_series.iloc[-1]
            
            if pd.notna(current_z_score):
                # Emit spread update
                self.event_bus.emit_spread_update(symbol, spread, current_z_score)
                
                # Check for entry/exit signals
                await self._check_signals(symbol, current_z_score, spread)
                
                self.logger.debug(
                    f"{symbol}: Spread={spread:.2f}, Z-Score={current_z_score:.2f}"
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
        
        Args:
            symbols: List of trading pair symbols to monitor
        """
        self.running = True
        self.logger.info(f"Starting LiveMonitor for {len(symbols)} symbols")
        
        # Start WebSocket manager
        await self.ws_manager.start(symbols)
        
        # Start price processing task
        self.monitor_task = asyncio.create_task(self._process_price_updates())
        
        self.logger.info("LiveMonitor started")
    
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
        
        # Clear buffers
        self.spread_history.clear()
        self.price_cache = {'bingx': {}, 'bybit': {}}
        
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
        
        if len(self.spread_history[symbol]) < self.config['validation']['z_score_window']:
            return None
        
        spread_series = pd.Series(list(self.spread_history[symbol]))
        z_score_series = calculate_z_score(
            spread_series,
            window=self.config['validation']['z_score_window']
        )
        
        current_z_score = z_score_series.iloc[-1]
        current_spread = spread_series.iloc[-1]
        
        return {
            'symbol': symbol,
            'spread': current_spread,
            'z_score': current_z_score,
            'in_position': self.in_position.get(symbol, False),
            'history_length': len(self.spread_history[symbol])
        }


async def main():
    """CLI interface for testing LiveMonitor."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Live Arbitrage Monitor')
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
    
    # Start monitoring
    await monitor.start(args.symbols)
    
    print(f"\n{'='*70}")
    print(f"Live Arbitrage Monitor - {', '.join(args.symbols)}")
    print(f"{'='*70}\n")
    print("Waiting for data...\n")
    
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
                        f"{position_indicator}"
                    )
                else:
                    print(f"{symbol:12} | Collecting data... ({monitor.spread_history.get(symbol, deque()).__len__()} samples)")
            
            print(f"{'-'*70}")
    
    except Exception as e:
        print(f"\nError: {e}")
    
    finally:
        print("\nShutting down...")
        await monitor.stop()
        print("Stopped.")


if __name__ == '__main__':
    asyncio.run(main())
