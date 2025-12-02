# ArbiBot - Cryptocurrency Arbitrage Bot

## Overview

ArbiBot is an automated arbitrage trading bot for cryptocurrency futures markets. It uses statistical arbitrage strategies (Z-Score mean reversion) to identify and execute profitable trades between BingX and Bybit exchanges.

## Features

- ✅ **Statistical Validation**: ADF test for spread stationarity
- ✅ **Z-Score Strategy**: Entry at Z > 2.5, exit at Z → 0
- ✅ **Real-time Monitoring**: WebSocket price feeds
- ✅ **Desktop GUI**: PyQt6 interface with live charts
- ✅ **Risk Management**: Position limits, stop-loss, time stops
- ✅ **Market Scanner**: Auto-discovery of profitable pairs

## Project Structure

```
molten-halley/
├── config/          # Configuration files
├── core/            # Core functionality (WS, exchange clients)
├── services/        # Business logic (validation, monitoring, execution)
├── utils/           # Utilities (metrics, logging)
├── gui/             # Desktop GUI
├── legacy/          # Old scripts (for reference)
└── main.py          # Entry point
```

## Installation

```bash
# Clone repository
git clone https://github.com/Il101/molten-halley.git
cd molten-halley

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

1. Copy example config:
```bash
cp config/exchanges.yaml.example config/exchanges.yaml
```

2. Add your API keys to `config/exchanges.yaml`

3. Adjust parameters in `config/config.yaml`

## Usage

### Run Market Scanner

Find profitable trading pairs:

```bash
python -m services.market_scanner
```

### Run Historical Analysis

Analyze a specific pair:

```bash
python -m services.historical_validator BTC/USDT
```

### Launch GUI (Coming Soon)

```bash
python main.py
```

## Strategy

### Statistical Arbitrage (Mean Reversion)

1. **Spread Calculation**: `Spread = Price_BingX - Price_Bybit`
2. **Stationarity Test**: ADF test ensures spread reverts to mean
3. **Z-Score Signal**:
   - Entry: |Z-Score| > 2.5 AND Spread% > fees
   - Exit: |Z-Score| < 0.5
   - Stop: |Z-Score| > 4.0 or time > 1 hour

### Risk Controls

- Maximum 5 concurrent positions
- Position size: $500 per trade
- Minimum spread: 0.3% (to cover 0.2% fees)
- Time stop: 1 hour maximum per position

## Development Status

- [x] Mathematical validation (Z-Score, ADF test)
- [x] Market scanner
- [x] Project structure refactoring
- [ ] WebSocket Manager
- [ ] Desktop GUI
- [ ] Live monitoring
- [ ] Execution engine
- [ ] Backtesting

## License

MIT

## Disclaimer

**Use at your own risk.** Cryptocurrency trading involves substantial risk of loss. This software is provided for educational purposes. Always test on testnet first.
