import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from core.ws_manager import WebSocketManager

async def test_selective_exchanges():
    print("Testing selective exchange selection...")
    
    # Mock symbols and exchanges
    symbols = ['BTC/USDT']
    target_exchanges = ['phemex', 'gateio']
    
    # Initialize WebSocketManager
    manager = WebSocketManager()
    
    # Patch connect_exchange to avoid actual connections
    with patch.object(manager, 'connect_exchange', return_value=asyncio.Future()) as mock_connect:
        mock_connect.return_value.set_result(None)
        
        # Start manager with specific exchanges
        await manager.start(symbols, exchanges=target_exchanges)
        
        # Verify calls
        called_exchanges = [call.args[0] for call in mock_connect.call_args_list]
        print(f"Exchanges called: {called_exchanges}")
        
        assert set(called_exchanges) == set(target_exchanges), f"Expected {target_exchanges}, but got {called_exchanges}"
        print("✅ SUCCESS: Only requested exchanges were connected.")

async def test_all_exchanges_by_default():
    print("\nTesting default behavior (all exchanges)...")
    
    symbols = ['BTC/USDT']
    all_supported = ['bingx', 'bybit', 'bitget', 'gateio', 'htx', 'phemex', 'mexc']
    
    manager = WebSocketManager()
    
    with patch.object(manager, 'connect_exchange', return_value=asyncio.Future()) as mock_connect:
        mock_connect.return_value.set_result(None)
        
        # Start manager without specified exchanges
        await manager.start(symbols)
        
        # Verify calls
        called_exchanges = [call.args[0] for call in mock_connect.call_args_list]
        print(f"Exchanges called: {len(called_exchanges)} exchanges")
        
        assert len(called_exchanges) == len(all_supported), f"Expected {len(all_supported)} exchanges, but got {len(called_exchanges)}"
        print("✅ SUCCESS: All exchanges were connected by default.")

if __name__ == "__main__":
    asyncio.run(test_selective_exchanges())
    asyncio.run(test_all_exchanges_by_default())
