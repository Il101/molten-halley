import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

# Mock dependencies
from unittest.mock import MagicMock
telethon = MagicMock()
sys.modules['telethon'] = telethon
sys.modules['telethon.sync'] = MagicMock()
sys.modules['telethon.sessions'] = MagicMock()
sys.modules['telethon.tl'] = MagicMock()
sys.modules['telethon.tl.types'] = MagicMock()
sys.modules['telethon.events'] = MagicMock()

sys.modules['services.historical_validator'] = MagicMock()
sys.modules['services.live_monitor'] = MagicMock()
sys.modules['utils.logger'] = MagicMock()
sys.modules['utils.symbol_resolver'] = MagicMock()

from services.telegram_manager import TelegramSignalManager

class TestTelegramParsing(unittest.TestCase):
    def setUp(self):
        # Mock Config
        mock_config = {
            'telegram': {
                'enabled': True,
                'min_signal_spread_pct': 0.005, # 0.5%
                'symbol_mapping': {}
            }
        }
        
        # Patch get_config
        import utils.config
        utils.config.get_config = MagicMock(return_value=mock_config)
        
        self.manager = TelegramSignalManager()
        self.manager.logger = MagicMock()
        
        # Mock awaited methods
        self.manager.resolver.resolve = AsyncMock(side_effect=lambda exchange, symbol: symbol)
        self.manager.validator.exchanges = {
            'bingx': MagicMock(),
            'bybit': MagicMock()
        }

    def test_river_signal_parsing(self):
        """
        Verify that the RIVER signal is parsed correctly (8.37% not -7.72%).
        And direction is correct (huobi=LONG, bybit=SHORT).
        """
        # Mock message content from user report
        sample_text = """
RIVER: huobi-bybit 8.37% курс. спред
📗|[huobi](https://futures.htx.com/futures/linear_swap/exchange#contract_code=RIVER-USDT)| - LONG
Текущая: **-1.11**%
Отклонение: -7.72%
📗|HUOBI| - LONG
ТЕКУЩАЯ: -1.11%
ОТКЛОНЕНИЕ: -7.72% 
Курсовой: 8.31%
📕|BYBIT| - SHORT
ТЕКУЩАЯ: -1.05%
        """
        
        mock_msg = MagicMock()
        mock_msg.text = sample_text
        
        self.manager._validate_and_confirm = AsyncMock()
        asyncio.run(self.manager._process_message(mock_msg))
        
        args, kwargs = self.manager._validate_and_confirm.call_args
        metadata = args[2]
        
        reported_spread = metadata['reported_spread']
        pair = metadata['pair']
        
        print(f"Extracted spread: {reported_spread:.2%}")
        print(f"Detected pair: {pair}")
        
        # Should be 8.31% (from the explicit 'Курсовой' line)
        self.assertAlmostEqual(reported_spread, 0.0831, places=4)
        
        # huobi-bybit order -> huobi (htx) is LONG, bybit is SHORT
        self.assertEqual(pair, ('htx', 'bybit'))

    def test_reversed_exchange_direction(self):
        """
        Verify that order determines direction: bybit-huobi -> bybit=LONG, htx=SHORT
        """
        sample_text = "RIVER: bybit-huobi Курсовой: 5.0%"
        mock_msg = MagicMock()
        mock_msg.text = sample_text
        
        self.manager._validate_and_confirm = AsyncMock()
        asyncio.run(self.manager._process_message(mock_msg))
        
        args, kwargs = self.manager._validate_and_confirm.call_args
        pair = args[2]['pair']
        
        print(f"Detected pair (reversed): {pair}")
        self.assertEqual(pair, ('bybit', 'htx'))

if __name__ == '__main__':
    unittest.main()
