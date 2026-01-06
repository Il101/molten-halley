# ArbiBot GUI - User Guide

## Overview

ArbiBot GUI provides real-time visualization of cryptocurrency arbitrage opportunities between BingX and Bybit exchanges.

## Features

- **Live Price Monitoring**: Real-time price updates from both exchanges
- **Z-Score Visualization**: Interactive chart showing Z-Score history
- **Signal Detection**: Automatic highlighting of entry/exit opportunities
- **Dark Theme**: Professional trading interface

## Installation

```bash
# Install GUI dependencies
pip install PyQt6 pyqtgraph qasync

# Or install all requirements
pip install -r requirements.txt
```

## Usage

### Launch GUI

```bash
python3 main.py gui
```

### Interface Components

#### 1. Price Table
- **Symbol**: Trading pair (e.g., BTC/USDT)
- **BingX Price**: Current price on BingX
- **Bybit Price**: Current price on Bybit
- **Spread %**: Percentage difference between exchanges
- **Z-Score**: Statistical measure of spread deviation
  - **Red background**: Z-Score > 2 (potential entry signal)
  - **Green background**: Z-Score < -2 (potential entry signal)
- **Status**: Current signal state
  - 🔔 SIGNAL: Entry opportunity detected
  - ⏸️ Waiting: No signal

#### 2. Z-Score Chart
- Shows historical Z-Score for selected symbol
- Click any row in the table to view its chart
- **Red dashed line**: +2 threshold (entry signal)
- **Green dashed line**: -2 threshold (entry signal)
- **White dotted line**: Mean (0)

### Menu Options

**File Menu**
- Exit (Ctrl+Q): Close application

**View Menu**
- Refresh (F5): Refresh data

**Help Menu**
- About: Application information

## Configuration

Edit `config/config.yaml` to customize:

```yaml
trading:
  z_score_entry: 2.5    # Entry threshold
  z_score_exit: 0.5     # Exit threshold
  min_spread_pct: 0.003 # Minimum spread

validation:
  z_score_window: 20    # Rolling window size
```

## Technical Details

### Architecture

```
┌─────────────────────────────────────┐
│         PyQt6 GUI (Main Thread)     │
│  ┌──────────────┐  ┌──────────────┐ │
│  │ Price Table  │  │  Z-Score     │ │
│  │              │  │  Chart       │ │
│  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────┘
           ↑
           │ EventBus (PyQt Signals)
           │
┌─────────────────────────────────────┐
│    Asyncio Event Loop (qasync)      │
│  ┌──────────────┐  ┌──────────────┐ │
│  │ WebSocket    │  │ Live         │ │
│  │ Manager      │  │ Monitor      │ │
│  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────┘
```

### Event Flow

1. **WebSocket Manager** receives price data from exchanges
2. **Live Monitor** calculates spreads and Z-Scores
3. **EventBus** emits signals (price_updated, spread_updated)
4. **Dashboard** receives signals and updates UI

### Threading Model

- **Main Thread**: PyQt6 GUI rendering
- **Asyncio Loop**: WebSocket connections (via qasync)
- **No blocking**: UI remains responsive during network operations

## Troubleshooting

### GUI doesn't start
```bash
# Check dependencies
pip install PyQt6 pyqtgraph qasync

# Check for errors
python3 main.py gui --debug
```

### No data appearing
- Check internet connection
- Verify exchanges are accessible
- Check logs in `logs/` directory

### High CPU usage
- Reduce number of monitored symbols
- Increase `z_score_window` in config
- Close other applications

## Keyboard Shortcuts

- **Ctrl+Q**: Quit application
- **F5**: Refresh data
- **Click row**: Select symbol for chart

## Next Steps

- Add more trading pairs to monitor
- Customize Z-Score thresholds
- Enable trading execution (coming soon)
