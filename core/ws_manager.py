"""
WebSocket Manager for Real-Time Price Feeds

Manages WebSocket connections to BingX and Bybit exchanges for live price streaming.
Handles connection lifecycle, message normalization, and auto-reconnection.
"""

import asyncio
import json
import gzip
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict
import sys

import aiohttp
from aiohttp import WSMsgType
import yaml

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from utils.logger import get_logger


class WebSocketManager:
    """
    Manages WebSocket connections to cryptocurrency exchanges.
    
    Features:
    - Multi-exchange support (BingX, Bybit)
    - Auto-reconnection with exponential backoff
    - Message normalization across exchanges
    - Heartbeat/ping-pong monitoring
    - Async queue-based data distribution
    """
    
    def __init__(self, config_path: str = 'config/config.yaml'):
        """
        Initialize WebSocket Manager.
        
        Args:
            config_path: Path to configuration YAML file
        """
        self.logger = get_logger(__name__)
        self.config = self._load_config(config_path)
        
        # Connection state
        self.connections: Dict[str, aiohttp.ClientWebSocketResponse] = {}
        self.connection_status: Dict[str, bool] = {
            'bingx': False,
            'bybit': False
        }
        
        # Data distribution
        self.message_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.config['websocket'].get('message_queue_size', 1000)
        )
        
        # Latest prices cache
        self.latest_prices: Dict[str, Dict[str, Dict]] = defaultdict(dict)
        
        # Task management
        self.tasks: List[asyncio.Task] = []
        self.running = False
        
        # Subscription tracking
        self.subscribed_symbols: Dict[str, List[str]] = {
            'bingx': [],
            'bybit': []
        }
        
        self.logger.info("WebSocketManager initialized")
    
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
        """Return default configuration."""
        return {
            'websocket': {
                'bingx': {
                    'url': 'wss://open-api-swap.bingx.com/swap-market'
                },
                'bybit': {
                    'url': 'wss://stream.bybit.com/v5/public/linear'
                },
                'reconnect_delay': 5,
                'max_reconnect_attempts': 10,
                'ping_interval': 30,
                'pong_timeout': 60,
                'message_queue_size': 1000
            }
        }
    
    async def connect_exchange(
        self,
        exchange_name: str,
        symbols: List[str]
    ) -> None:
        """
        Establish WebSocket connection to an exchange with auto-reconnect.
        
        Args:
            exchange_name: Exchange identifier ('bingx' or 'bybit')
            symbols: List of symbols to subscribe to
        """
        ws_config = self.config['websocket'][exchange_name]
        url = ws_config['url']
        
        reconnect_delay = self.config['websocket']['reconnect_delay']
        max_attempts = self.config['websocket']['max_reconnect_attempts']
        
        attempt = 0
        
        while self.running and attempt < max_attempts:
            try:
                self.logger.info(f"Connecting to {exchange_name} WebSocket (attempt {attempt + 1}/{max_attempts})")
                
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(url) as ws:
                        self.connections[exchange_name] = ws
                        self.connection_status[exchange_name] = True
                        self.logger.info(f"Connected to {exchange_name}")
                        
                        # Subscribe to symbols
                        await self._subscribe_symbols(exchange_name, ws, symbols)
                        
                        # Start heartbeat task
                        heartbeat_task = asyncio.create_task(
                            self._heartbeat(ws, exchange_name)
                        )
                        self.tasks.append(heartbeat_task)
                        
                        # Message processing loop
                        async for msg in ws:
                            # Handle TEXT messages (Bybit JSON, BingX Pong)
                            if msg.type == WSMsgType.TEXT:
                                # Check if it's a raw "Pong" from BingX
                                if msg.data == "Pong":
                                    self.logger.debug(f"Received Pong from {exchange_name}")
                                    continue
                                
                                # Otherwise parse as JSON
                                try:
                                    data = json.loads(msg.data)
                                    await self._handle_message(exchange_name, data)
                                except json.JSONDecodeError as e:
                                    self.logger.error(f"JSON decode error from {exchange_name}: {e}")
                                except Exception as e:
                                    self.logger.error(f"Error handling message from {exchange_name}: {e}")
                            
                            # Handle BINARY messages (BingX GZIP compressed)
                            elif msg.type == WSMsgType.BINARY:
                                try:
                                    # Decompress GZIP data
                                    decompressed = gzip.decompress(msg.data).decode('utf-8')
                                    
                                    # Check if it's a raw "Pong"
                                    if decompressed == "Pong":
                                        self.logger.debug(f"Received Pong from {exchange_name}")
                                        continue
                                    
                                    # Parse as JSON
                                    data = json.loads(decompressed)
                                    await self._handle_message(exchange_name, data)
                                except gzip.BadGzipFile as e:
                                    self.logger.error(f"GZIP decompression error from {exchange_name}: {e}")
                                except json.JSONDecodeError as e:
                                    self.logger.error(f"JSON decode error from {exchange_name} (after GZIP): {e}")
                                except Exception as e:
                                    self.logger.error(f"Error handling binary message from {exchange_name}: {e}")
                            
                            elif msg.type == WSMsgType.ERROR:
                                self.logger.error(f"WebSocket error from {exchange_name}: {ws.exception()}")
                                break
                            
                            elif msg.type == WSMsgType.CLOSED:
                                self.logger.warning(f"WebSocket closed by {exchange_name}")
                                break

                        
                        # Connection closed
                        heartbeat_task.cancel()
                        self.connection_status[exchange_name] = False
                        
            except aiohttp.ClientError as e:
                self.logger.error(f"Connection error to {exchange_name}: {e}")
                self.connection_status[exchange_name] = False
                
            except Exception as e:
                self.logger.error(f"Unexpected error with {exchange_name}: {e}")
                self.connection_status[exchange_name] = False
            
            # Reconnect logic
            if self.running:
                attempt += 1
                if attempt < max_attempts:
                    delay = reconnect_delay * (2 ** (attempt - 1))  # Exponential backoff
                    self.logger.info(f"Reconnecting to {exchange_name} in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(f"Max reconnection attempts reached for {exchange_name}")
                    break
    
    async def _subscribe_symbols(
        self,
        exchange_name: str,
        ws: aiohttp.ClientWebSocketResponse,
        symbols: List[str]
    ) -> None:
        """
        Subscribe to ticker streams for given symbols.
        
        Args:
            exchange_name: Exchange identifier
            ws: WebSocket connection
            symbols: List of symbols to subscribe
        """
        if exchange_name == 'bingx':
            # BingX subscription format
            for symbol in symbols:
                # Convert BTC/USDT to BTC-USDT for BingX
                bingx_symbol = symbol.replace('/', '-')
                subscribe_msg = {
                    "id": f"sub_{bingx_symbol}",
                    "reqType": "sub",
                    "dataType": f"{bingx_symbol}@ticker"
                }
                await ws.send_json(subscribe_msg)
                self.logger.debug(f"Subscribed to {bingx_symbol} on BingX")
            
            self.subscribed_symbols['bingx'] = symbols
        
        elif exchange_name == 'bybit':
            # Bybit subscription format
            bybit_symbols = [symbol.replace('/', '') for symbol in symbols]  # BTCUSDT
            subscribe_msg = {
                "op": "subscribe",
                "args": [f"tickers.{s}" for s in bybit_symbols]
            }
            await ws.send_json(subscribe_msg)
            self.logger.debug(f"Subscribed to {len(symbols)} symbols on Bybit")
            
            self.subscribed_symbols['bybit'] = symbols
    
    async def _handle_message(self, exchange_name: str, message: dict) -> None:
        """
        Parse and normalize incoming WebSocket messages.
        
        Args:
            exchange_name: Exchange identifier
            message: Raw message from exchange
        """
        try:
            normalized_data = None
            
            if exchange_name == 'bingx':
                # Debug: Log raw BingX payload
                self.logger.debug(f"Raw BingX payload: {message}")
                
                # BingX message format
                if 'dataType' in message and '@ticker' in message.get('dataType', ''):
                    data = message.get('data', {})
                    symbol_raw = message['dataType'].split('@')[0]
                    symbol = symbol_raw.replace('-', '/')  # Convert back to BTC/USDT
                    
                    # Log available keys in first message
                    if not hasattr(self, '_bingx_keys_logged'):
                        self.logger.info(f"BingX ticker keys: {list(data.keys())}")
                        self._bingx_keys_logged = True
                    
                    # Try to get bid/ask, fallback to last price if not available
                    bid = float(data.get('b', 0)) or float(data.get('bid1', 0)) or float(data.get('c', 0))
                    ask = float(data.get('a', 0)) or float(data.get('ask1', 0)) or float(data.get('c', 0))
                    last = float(data.get('c', 0))  # Close/last price
                    
                    # If still no bid/ask, use last price as fallback
                    if bid == 0:
                        bid = last
                    if ask == 0:
                        ask = last
                    
                    normalized_data = {
                        'exchange': 'bingx',
                        'symbol': symbol,
                        'bid': bid,
                        'ask': ask,
                        'last': last,
                        'timestamp': int(data.get('E', 0)),  # Event time
                        'local_timestamp': time.time()
                    }
            
            elif exchange_name == 'bybit':
                # Bybit message format
                if message.get('topic', '').startswith('tickers.'):
                    data = message.get('data', {})
                    symbol_raw = data.get('symbol', '')
                    
                    # Convert BTCUSDT to BTC/USDT
                    if symbol_raw.endswith('USDT'):
                        base = symbol_raw[:-4]
                        symbol = f"{base}/USDT"
                    else:
                        symbol = symbol_raw
                    
                    normalized_data = {
                        'exchange': 'bybit',
                        'symbol': symbol,
                        'bid': float(data.get('bid1Price', 0)),
                        'ask': float(data.get('ask1Price', 0)),
                        'last': float(data.get('lastPrice', 0)),
                        'timestamp': int(message.get('ts', 0)),
                        'local_timestamp': time.time()
                    }
            
            # Store and distribute normalized data
            if normalized_data and normalized_data['bid'] > 0 and normalized_data['ask'] > 0:
                # Update cache
                self.latest_prices[exchange_name][normalized_data['symbol']] = normalized_data
                
                # Put in queue (non-blocking)
                try:
                    self.message_queue.put_nowait(normalized_data)
                except asyncio.QueueFull:
                    self.logger.warning(f"Message queue full, dropping message for {normalized_data['symbol']}")
                
                self.logger.debug(
                    f"{exchange_name} {normalized_data['symbol']}: "
                    f"bid={normalized_data['bid']}, ask={normalized_data['ask']}"
                )
        
        except Exception as e:
            self.logger.error(f"Error normalizing message from {exchange_name}: {e}")
    
    async def _heartbeat(
        self,
        ws: aiohttp.ClientWebSocketResponse,
        exchange_name: str
    ) -> None:
        """
        Send periodic ping messages to keep connection alive.
        
        Args:
            ws: WebSocket connection
            exchange_name: Exchange identifier
        """
        ping_interval = self.config['websocket']['ping_interval']
        
        try:
            while not ws.closed:
                await asyncio.sleep(ping_interval)
                
                if exchange_name == 'bingx':
                    # BingX ping format: raw string "Ping"
                    await ws.send_str("Ping")
                    self.logger.debug(f"Sent Ping (raw string) to {exchange_name}")
                
                elif exchange_name == 'bybit':
                    # Bybit ping format: JSON
                    await ws.send_json({"op": "ping"})
                    self.logger.debug(f"Sent ping (JSON) to {exchange_name}")
        
        except asyncio.CancelledError:
            self.logger.debug(f"Heartbeat cancelled for {exchange_name}")
        except Exception as e:
            self.logger.error(f"Heartbeat error for {exchange_name}: {e}")
    
    async def subscribe(self, symbols: List[str]) -> None:
        """
        Subscribe to additional symbols on active connections.
        
        Args:
            symbols: List of symbols to subscribe to
        """
        for exchange_name, ws in self.connections.items():
            if not ws.closed:
                await self._subscribe_symbols(exchange_name, ws, symbols)
    
    async def unsubscribe(self, symbols: List[str]) -> None:
        """
        Unsubscribe from symbols.
        
        Args:
            symbols: List of symbols to unsubscribe from
        """
        for exchange_name, ws in self.connections.items():
            if not ws.closed:
                if exchange_name == 'bingx':
                    for symbol in symbols:
                        bingx_symbol = symbol.replace('/', '-')
                        unsub_msg = {
                            "id": f"unsub_{bingx_symbol}",
                            "reqType": "unsub",
                            "dataType": f"{bingx_symbol}@ticker"
                        }
                        await ws.send_json(unsub_msg)
                
                elif exchange_name == 'bybit':
                    bybit_symbols = [symbol.replace('/', '') for symbol in symbols]
                    unsub_msg = {
                        "op": "unsubscribe",
                        "args": [f"tickers.{s}" for s in bybit_symbols]
                    }
                    await ws.send_json(unsub_msg)
                
                self.logger.info(f"Unsubscribed from {len(symbols)} symbols on {exchange_name}")
    
    def get_queue(self) -> asyncio.Queue:
        """
        Get the message queue for consuming price updates.
        
        Returns:
            Async queue with normalized price data
        """
        return self.message_queue
    
    def get_latest_price(self, exchange: str, symbol: str) -> Optional[Dict]:
        """
        Get last known price for a symbol (synchronous access).
        
        Args:
            exchange: Exchange name
            symbol: Trading pair symbol
            
        Returns:
            Latest price data or None
        """
        return self.latest_prices.get(exchange, {}).get(symbol)
    
    def get_connection_status(self) -> Dict[str, bool]:
        """
        Get connection status for all exchanges.
        
        Returns:
            Dictionary of exchange: connected status
        """
        return self.connection_status.copy()
    
    async def start(self, symbols: List[str]) -> None:
        """
        Start WebSocket connections for all enabled exchanges.
        
        Args:
            symbols: List of symbols to monitor
        """
        self.running = True
        self.logger.info(f"Starting WebSocket Manager for {len(symbols)} symbols")
        
        # Start connection tasks for each exchange
        for exchange_name in ['bingx', 'bybit']:
            if self.config['websocket'].get(exchange_name, {}).get('enabled', True):
                task = asyncio.create_task(
                    self.connect_exchange(exchange_name, symbols)
                )
                self.tasks.append(task)
        
        self.logger.info("WebSocket Manager started")
    
    async def stop(self) -> None:
        """
        Gracefully stop all WebSocket connections.
        """
        self.logger.info("Stopping WebSocket Manager...")
        self.running = False
        
        # Close all WebSocket connections
        for exchange_name, ws in self.connections.items():
            if not ws.closed:
                await ws.close()
                self.logger.info(f"Closed connection to {exchange_name}")
        
        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Clear queue
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        self.logger.info("WebSocket Manager stopped")


async def main():
    """Test WebSocket Manager standalone."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test WebSocket Manager')
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
    
    args = parser.parse_args()
    
    # Create manager
    manager = WebSocketManager(config_path=args.config)
    
    # Start connections
    await manager.start(args.symbols)
    
    # Consume messages
    print(f"\n{'='*60}")
    print(f"WebSocket Manager - Monitoring {', '.join(args.symbols)}")
    print(f"{'='*60}\n")
    print("Press Ctrl+C to stop\n")
    
    try:
        queue = manager.get_queue()
        while True:
            try:
                # Get message with timeout
                data = await asyncio.wait_for(queue.get(), timeout=1.0)
                
                print(
                    f"[{data['exchange'].upper()}] {data['symbol']}: "
                    f"Bid={data['bid']:.2f}, Ask={data['ask']:.2f}, "
                    f"Spread={data['ask'] - data['bid']:.2f}"
                )
            
            except asyncio.TimeoutError:
                # Check connection status
                status = manager.get_connection_status()
                if not any(status.values()):
                    print("All connections lost!")
                    break
    
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    
    finally:
        await manager.stop()


if __name__ == '__main__':
    asyncio.run(main())
