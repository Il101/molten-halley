"""
Integration Test

Verifies that ExecutionEngine emits correct signals to EventBus.
"""

import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path

# Mock PyQt6 signals before importing EventBus
import sys
from unittest.mock import MagicMock

# Mock PyQt6 modules if not available in headless env
try:
    from PyQt6.QtCore import QObject, pyqtSignal
except ImportError:
    # Create dummy classes for headless testing
    class QObject:
        pass
    
    class pyqtSignal:
        def __init__(self, *args): pass
        def emit(self, *args): pass
        def connect(self, func): pass

from core.event_bus import EventBus
from services.execution import ExecutionEngine
from core.interfaces.exchange import BaseExchange

class MockExchange(BaseExchange):
    def __init__(self, name):
        self.name = name
    
    async def get_balance(self):
        return {'USDT': {'free': 1000.0, 'total': 1000.0}}
    
    async def fetch_ticker(self, symbol):
        return {'bid': 50000.0, 'ask': 50010.0, 'last': 50005.0}
    
    async def create_order(self, symbol, side, amount, price=None):
        return {'id': f'{self.name}_1', 'average': 50005.0}
    
    async def fetch_positions(self):
        return []
    
    async def close_position(self, symbol):
        return {'pnl': 10.0}
    
    def get_exchange_name(self):
        return self.name

class TestIntegration(unittest.TestCase):
    def setUp(self):
        # Reset EventBus singleton
        EventBus._instance = None
        self.event_bus = EventBus.instance()
        
        # Mock signals
        self.event_bus.trade_opened = MagicMock()
        self.event_bus.trade_closed = MagicMock()
        self.event_bus.signal_triggered = MagicMock()
        
        # Mock connect method
        self.event_bus.trade_opened.emit = MagicMock()
        self.event_bus.trade_closed.emit = MagicMock()
        self.event_bus.signal_triggered.connect = MagicMock()
        
        self.client_a = MockExchange('A')
        self.client_b = MockExchange('B')
        self.engine = ExecutionEngine(self.client_a, self.client_b)

    def test_trade_signals(self):
        async def run_test():
            # Test Entry
            print("Testing Trade Entry Signal...")
            await self.engine.execute_arb_entry('BTC/USDT', 2.5)
            
            # Verify trade_opened signal
            self.event_bus.trade_opened.emit.assert_called_once()
            args = self.event_bus.trade_opened.emit.call_args[0][0]
            self.assertEqual(args['symbol'], 'BTC/USDT')
            self.assertEqual(args['entry_z_score'], 2.5)
            print("✅ Trade Entry Signal Verified")
            
            # Test Exit
            print("\nTesting Trade Exit Signal...")
            await self.engine.execute_arb_exit('BTC/USDT')
            
            # Verify trade_closed signal
            self.event_bus.trade_closed.emit.assert_called_once()
            args = self.event_bus.trade_closed.emit.call_args[0][0]
            self.assertEqual(args['symbol'], 'BTC/USDT')
            self.assertIn('pnl', args)
            print("✅ Trade Exit Signal Verified")

        asyncio.run(run_test())

if __name__ == '__main__':
    unittest.main()
