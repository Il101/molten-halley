import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from core.event_bus import EventBus
from services.execution import ExecutionEngine
from utils.logger import setup_logger

async def test_execution():
    setup_logger('test_execution', level='INFO')
    bus = EventBus.instance()
    
    print("Initializing Multi-Exchange ExecutionEngine...")
    engine = ExecutionEngine(
        position_size_usdt=100.0,
        max_positions=5
    )
    
    # We need to mock fetch_ticker and get_balance for PaperExchange to work without WS
    # But PaperExchange is already designed to use ws_manager.
    # For a simple test, we can just check if the listener is hooked up.
    
    print("Emitting mock ENTRY signal for BTC/USDT (bingx <-> bybit)...")
    bus.emit_signal_triggered('BTC/USDT', 'ENTRY', 3.0, 'bingx', 'bybit')
    
    # Wait a bit for async task to process
    await asyncio.sleep(2)
    
    print("\nTest complete. Check logs for '🚀 Opening arbitrage' or balance errors.")

if __name__ == "__main__":
    asyncio.run(test_execution())
