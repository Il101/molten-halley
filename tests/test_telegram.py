import unittest
import asyncio
from unittest.mock import MagicMock, patch
from services.telegram_manager import TelegramSignalManager

class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)

class TestTelegramParsing(unittest.TestCase):
    def setUp(self):
        # We don't want to actually connect to TG during unit tests
        with patch('telethon.TelegramClient'), patch('services.historical_validator.HistoricalValidator'):
            self.manager = TelegramSignalManager()
            # Mock resolver to be async
            self.manager.resolver.resolve = AsyncMock()
            self.manager.validator.analyze = AsyncMock()

    def test_structured_parsing(self):
        text_gaib = """
GAIB: gateio-bingx 3.12% курс. спред

📗|gateio| - LONG
📕|bingx| - SHORT

💰Спред:
Курсовой: 3.12%
"""
        text_ptb = """
PTBUSDT - ТЕК

📗|bingx| - LONG
📕|bybit| - SHORT

💰Спред:
Курсовой: 1.14%
"""
        # Test GAIB
        symbols = set()
        header_match = self.manager.header_gaib_regex.search(text_gaib.upper())
        self.assertTrue(header_match)
        symbols.add(f"{header_match.group(1)}/USDT")
        
        spread_match = self.manager.course_spread_regex.search(text_gaib.upper())
        self.assertEqual(float(spread_match.group(1).replace(',', '.')), 3.12)
        
        book_matches = self.manager.book_line_regex.findall(text_gaib.upper())
        # Find bingx direction
        bingx_dir = next(d for e, ex, d in book_matches if ex.lower() == 'bingx')
        self.assertEqual(bingx_dir, 'SHORT')
        
        # Test PTB
        header_tek = self.manager.header_tek_regex.search(text_ptb.upper())
        self.assertTrue(header_tek)
        self.assertEqual(header_tek.group(1), "PTB")
        
        spread_ptb = self.manager.course_spread_regex.search(text_ptb.upper())
        self.assertEqual(float(spread_ptb.group(1).replace(',', '.')), 1.14)

    def test_link_stripping_and_blacklist(self):
        # Even if it looks like a structured header, it should be ignored if it's HTTPS
        text_with_link = "Check our chart: https://tradingview.com/chart/BTCUSDT - and join HTTPS: channel"
        
        msg = MagicMock()
        msg.text = text_with_link
        
        # Capture the symbols found by mocking _validate_and_confirm
        self.manager._validate_and_confirm = AsyncMock()
        
        asyncio.run(self.manager._process_message(msg))
        
        # Should NOT have called _validate_and_confirm for HTTPS
        self.assertFalse(self.manager._validate_and_confirm.called, "Should not detect HTTPS/USDT from link")

    @patch('services.historical_validator.HistoricalValidator.analyze')
    @patch('services.live_monitor.LiveMonitor.get_current_stats')
    @patch('services.live_monitor.LiveMonitor.start')
    @patch('asyncio.sleep', new_callable=AsyncMock)
    def test_validation_logic(self, mock_sleep, mock_ws_start, mock_get_stats, mock_analyze):
        # Mock historical validation passing
        mock_analyze.return_value = {'is_stationary': True}
        
        # Mock live monitoring stats
        mock_get_stats.return_value = {
            'z_score': 3.0,
            'net_spread': 0.005 # Positive
        }
        
        # Setup a mock message
        mock_msg = MagicMock()
        mock_msg.text = "BTC/USDT Signal"
        mock_msg.reply = AsyncMock()
        
        # Ensure config has thresholds
        self.manager.validator.config = {
            'trading': {'z_score_entry': 2.0}
        }
        self.manager.signal_timeout = 10 # Shorten for test

        # Run the internal validation method
        async def run_test():
            metadata = {
                'reported_spread': 0.02,
                'direction': 'LONG'
            }
            await self.manager._validate_and_confirm("BTC/USDT", mock_msg, metadata)
            # Verify it replied
            mock_msg.reply.assert_called_with("✅")

        asyncio.run(run_test())

    def test_exchange_filter(self):
        # Case 1: Mentions BingX (Supported)
        msg_bingx = MagicMock()
        msg_bingx.text = "BTC/USDT on BingX"
        
        # Case 2: Mentions Bybit (Supported)
        msg_bybit = MagicMock()
        msg_bybit.text = "BTC/USDT Bybit signal"
        
        # Case 3: Mentions OKX (Unsupported)
        msg_okx = MagicMock()
        msg_okx.text = "BTC/USDT on OKX-Binance"
        
        # We need to mock _validate_and_confirm to see if it's called
        self.manager._validate_and_confirm = AsyncMock()
        
        # Test Case 1: Should proceed (structured header)
        msg_bingx.text = "GAIB: something"
        asyncio.run(self.manager._process_message(msg_bingx))
        self.assertTrue(self.manager._validate_and_confirm.called)
        self.manager._validate_and_confirm.reset_mock()
        
        # Test Case 2: Should skip (blacklist)
        msg_okx.text = "HTTPS/USDT link"
        asyncio.run(self.manager._process_message(msg_okx))
        self.assertFalse(self.manager._validate_and_confirm.called)

if __name__ == '__main__':
    unittest.main()
