# Phase 2: WebSocket Real-Time Monitoring - Usage Guide

## Overview

Phase 2 adds real-time WebSocket monitoring capabilities to ArbiBot, enabling live price feeds from BingX and Bybit exchanges with automatic Z-Score calculation and signal detection.

## Components

### 1. WebSocketManager (`core/ws_manager.py`)

Manages WebSocket connections to exchanges with auto-reconnection and message normalization.

**Features:**
- Multi-exchange support (BingX, Bybit)
- Auto-reconnection with exponential backoff
- Message normalization across different exchange formats
- Heartbeat/ping-pong monitoring
- Async queue-based data distribution

**Standalone Usage:**
```bash
# Monitor BTC/USDT
python -m core.ws_manager BTC/USDT

# Monitor multiple symbols
python -m core.ws_manager BTC/USDT ETH/USDT SOL/USDT
```

**Programmatic Usage:**
```python
import asyncio
from core.ws_manager import WebSocketManager

async def main():
    manager = WebSocketManager(config_path='config/config.yaml')
    
    # Start connections
    await manager.start(['BTC/USDT', 'ETH/USDT'])
    
    # Consume messages
    queue = manager.get_queue()
    while True:
        data = await queue.get()
        print(f"{data['exchange']} {data['symbol']}: bid={data['bid']}, ask={data['ask']}")
    
    # Cleanup
    await manager.stop()

asyncio.run(main())
```

### 2. EventBus (`core/event_bus.py`)

Singleton event bus for inter-module communication using PyQt6 signals.

**Signals:**
- `price_updated` - Emitted on each price update
- `spread_updated` - Emitted when spread/Z-Score calculated
- `signal_triggered` - Emitted on entry/exit signals
- `connection_status` - Emitted on connection changes
- `error_occurred` - Emitted on errors

**Usage:**
```python
from core.event_bus import EventBus

# Get singleton instance
bus = EventBus.instance()

# Connect to signals
bus.price_updated.connect(lambda data: print(f"Price update: {data}"))
bus.signal_triggered.connect(lambda symbol, sig_type, z: print(f"{sig_type} signal for {symbol}"))

# Emit events
bus.emit_price_update({'exchange': 'bingx', 'symbol': 'BTC/USDT', ...})
bus.emit_signal_triggered('BTC/USDT', 'ENTRY', 2.8)
```

### 3. LiveMonitor (`services/live_monitor.py`)

Real-time arbitrage monitoring service that consumes WebSocket feeds and calculates Z-Scores.

**Features:**
- Real-time spread calculation between exchanges
- Rolling Z-Score calculation using `utils.metrics`
- Entry/exit signal detection based on thresholds
- EventBus integration for GUI updates
- CLI interface for testing

**Standalone Usage:**
```bash
# Monitor BTC/USDT with 5-second stats updates
python -m services.live_monitor BTC/USDT --interval 5

# Monitor multiple pairs
python -m services.live_monitor BTC/USDT ETH/USDT --interval 10

# Custom config
python -m services.live_monitor BTC/USDT --config config/config.yaml
```

**Output Example:**
```
============================================================
Live Arbitrage Monitor - BTC/USDT
============================================================

22:15:30 - Current Stats:
----------------------------------------------------------------------
BTC/USDT     | Spread:   -12.50 | Z-Score:  -2.35 | 📈 IN POSITION
----------------------------------------------------------------------

🔔 ENTRY SIGNAL: BTC/USDT | Z-Score=-2.35 | Spread=0.015%
```

**Programmatic Usage:**
```python
import asyncio
from services.live_monitor import LiveMonitor

async def main():
    monitor = LiveMonitor(config_path='config/config.yaml')
    
    # Start monitoring
    await monitor.start(['BTC/USDT', 'ETH/USDT'])
    
    # Let it run
    await asyncio.sleep(60)
    
    # Get current stats
    stats = monitor.get_current_stats('BTC/USDT')
    print(f"Z-Score: {stats['z_score']}, In Position: {stats['in_position']}")
    
    # Stop
    await monitor.stop()

asyncio.run(main())
```

## Configuration

All WebSocket settings are in `config/config.yaml`:

```yaml
websocket:
  bingx:
    url: 'wss://open-api-swap.bingx.com/swap-market'
    enabled: true
  
  bybit:
    url: 'wss://stream.bybit.com/v5/public/linear'
    enabled: true
  
  reconnect_delay: 5            # Seconds
  max_reconnect_attempts: 10
  ping_interval: 30             # Seconds
  pong_timeout: 60              # Seconds
  message_queue_size: 1000      # Max messages in queue
```

## Signal Detection Logic

### Entry Signal
Triggered when:
1. `|Z-Score| > z_score_entry` (default: 2.5)
2. `spread_pct > min_spread_pct` (default: 0.3%)
3. Not currently in position

### Exit Signal
Triggered when:
1. `|Z-Score| < z_score_exit` (default: 0.5)
2. Currently in position

## Message Flow

```
WebSocket Feeds (BingX, Bybit)
    ↓
WebSocketManager (normalize messages)
    ↓
AsyncIO Queue
    ↓
LiveMonitor (calculate spread & Z-Score)
    ↓
EventBus (emit signals)
    ↓
GUI / Trading Engine / Logger
```

## Error Handling

All components include comprehensive error handling:

- **Connection Errors**: Auto-reconnect with exponential backoff
- **Parse Errors**: Log and skip malformed messages
- **Queue Full**: Drop oldest messages with warning
- **Network Timeout**: Trigger reconnection

## Testing

### Test WebSocket Manager
```bash
python -m core.ws_manager BTC/USDT
```

Expected output: Real-time bid/ask prices from both exchanges

### Test Live Monitor
```bash
python -m services.live_monitor BTC/USDT --interval 5
```

Expected output: Z-Score calculations and signal detection

### Test Event Bus
```python
from core.event_bus import EventBus

bus = EventBus.instance()
bus.price_updated.connect(lambda data: print(f"Received: {data}"))
bus.emit_price_update({'test': 'data'})
```

## Integration with GUI

The EventBus is designed for PyQt6 GUI integration:

```python
from PyQt6.QtWidgets import QMainWindow
from core.event_bus import EventBus

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Connect to event bus
        bus = EventBus.instance()
        bus.price_updated.connect(self.on_price_update)
        bus.signal_triggered.connect(self.on_signal)
    
    def on_price_update(self, data):
        # Update GUI with new price
        self.update_price_display(data)
    
    def on_signal(self, symbol, signal_type, z_score):
        # Show notification
        self.show_alert(f"{signal_type} signal for {symbol}")
```

## Dependencies

New dependencies added in Phase 2:
- `aiohttp>=3.9.0` - WebSocket client
- `PyQt6>=6.6.0` - Event bus signals

Install with:
```bash
pip install -r requirements.txt
```

## Troubleshooting

### WebSocket Connection Fails
- Check internet connection
- Verify exchange URLs in config
- Check firewall settings

### No Z-Score Calculated
- Need minimum `z_score_window` data points (default: 20)
- Wait for data accumulation
- Check if both exchanges have prices for symbol

### High Memory Usage
- Reduce `message_queue_size` in config
- Reduce `max_history_length` in LiveMonitor
- Monitor fewer symbols simultaneously

## Next Steps

Phase 3 will add:
- GUI dashboard with real-time charts
- Position management
- Order execution
- Performance tracking
