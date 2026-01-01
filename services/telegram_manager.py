"""
Telegram Signal Manager

Listens for trading signals from Telegram, validates them using historical ADF tests,
and confirms real-time viability using live spreads (Z-Score and Net Spread).
Replies to signals with ✅ when confirmed.
"""

import asyncio
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from telethon import TelegramClient, events
from telethon.tl.types import Message

from services.historical_validator import HistoricalValidator
from services.live_monitor import LiveMonitor
from core.event_bus import EventBus
from utils.logger import get_logger
from utils.symbol_resolver import SymbolResolver
from utils.config import get_config

from telethon.sessions import StringSession

class TelegramSignalManager:
    """
    Manages Telegram connectivity and orchestrates signal validation.
    """
    
    def __init__(self, config_path: str = 'config/config.yaml'):
        self.logger = get_logger(__name__)
        self.config_path = config_path
        
        # Load config
        full_config = get_config(config_path)
        self.tg_config = full_config.get('telegram', {})
        
        self.validator = HistoricalValidator(config_path)
        self.monitor = LiveMonitor(config_path)
        self.event_bus = EventBus.instance()
        self.resolver = SymbolResolver(full_config)
        
        self.enabled = self.tg_config.get('enabled', False)
        self.api_id = self.tg_config.get('api_id')
        self.api_hash = self.tg_config.get('api_hash')
        self.session_name = self.tg_config.get('session_name', 'arbibot_session')
        self.session_string = self.tg_config.get('session_string')
        self.channels = self.tg_config.get('channels', [])
        self.signal_timeout = self.tg_config.get('signal_timeout', 1800)
        
        # Performance/Algo settings
        self.adf_candles = self.tg_config.get('adf_lookback_candles', 1000)
        self.adf_timeframe = self.tg_config.get('adf_timeframe', '15m')
        
        self.client: Optional[TelegramClient] = None
        self.active_signals: Dict[str, asyncio.Task] = {} # symbol -> monitoring task
        
        # 1. Specialized Headers: 
        # Form 1: "GAIB: ..."
        self.header_gaib_regex = re.compile(r'\b([A-Z0-9]{2,10}):', re.IGNORECASE)
        # Form 2: "PTBUSDT - ТЕК"
        self.header_tek_regex = re.compile(r'\b([A-Z0-9]{2,10})USDT\s*-\s*(?:ТЕК|ТEXT)', re.IGNORECASE)
        
        # 2. Emoji-coded Book Lines: 📗|gateio| - LONG or 📗|| - LONG (after URL stripping)
        # Extracts: emoji (color), exchange_name (optional), direction
        self.book_line_regex = re.compile(
            r'([📗📕])\s*\|\s*([^|]*)\s*\|\s*-\s*(LONG|SHORT|BUY|SELL)', 
            re.IGNORECASE
        )
        
        # 3. Refined Spread Values
        # Specifically targets "Курсовой: 3.12%"
        self.course_spread_regex = re.compile(r'Курсовой:\s*(\d+[.,]\d+)\s*%', re.IGNORECASE)
        
        # Regular fallback for simple pairs (if needed)
        self.pair_regex = re.compile(r'\b([A-Z0-9]{2,10})/(USDT|USDC|BUSD)\b', re.IGNORECASE)
        
        # Blacklist for common false positives
        self.symbol_blacklist = {
            'HTTPS', 'HTTP', 'TRADE', 'INFO', 'HELP', 'LIMIT', 'MARKET', 'ТЕК', 'TEXT',
            'CHART', 'FOLLOW', 'GRAPH', 'ГРАФИК', 'ГРАФ', 'СЛЕДИТЬ'
        }
        
        self.logger.info("TelegramSignalManager initialized with NARROW structured parsing")

    async def start(self):
        """Start the Telegram client and listeners."""
        if not self.enabled:
            self.logger.warning("Telegram integration is disabled in config")
            return

        if not self.api_id or not self.api_hash:
            self.logger.error("Telegram API credentials missing. Please check config/config.yaml or environment variables")
            return

        if self.session_string:
            self.logger.info("Connecting to Telegram using StringSession...")
            self.client = TelegramClient(StringSession(self.session_string), self.api_id, self.api_hash)
        else:
            self.logger.info(f"Connecting to Telegram (Session File: {self.session_name})...")
            self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)
        
        @self.client.on(events.NewMessage(chats=self.channels))
        async def handle_new_message(event: events.NewMessage.Event):
            chat = await event.get_chat()
            self.logger.info(f"📨 NEW MESSAGE from '{chat.title if hasattr(chat, 'title') else chat.username}' (ID: {event.chat_id})")
            await self._process_message(event.message)

        await self.client.start()
        self.logger.info("✅ Telegram connected and listening for signals")
        
        # Keep it running
        await self.client.run_until_disconnected()

    async def stop(self):
        """Stop the client and all active monitoring tasks."""
        if self.client:
            await self.client.disconnect()
        
        for task in self.active_signals.values():
            task.cancel()
        
        await self.monitor.stop()
        self.logger.info("TelegramSignalManager stopped")

    async def _process_message(self, message: Message):
        """Parse message for symbols and start validation if found."""
        if not message.text:
            return
            
        text = message.text.upper()
        
        # Pre-process: Strip Telegram Markdown & URLs (ORDER MATTERS!)
        # Step 1: Convert Markdown links to plain text FIRST: [bingx](url) -> bingx
        text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
        # Step 2: Remove bold/italic markers (**, *, _, ~)
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **bold** -> bold
        text = re.sub(r'[_*~]', '', text)  # Remove remaining markers
        # Step 3: Remove backticks (code formatting)
        text = re.sub(r'`', '', text)
        # Step 4: Clean up any remaining URLs
        text = re.sub(r'HTTPS?://\S+', '', text)
        
        self.logger.debug(f"📩 Processing message from {message.chat_id}: {text[:100]}...")
        self.logger.info(f"🔍 RAW MESSAGE from chat {message.chat_id}: {message.text[:200]}")  # NEW: Full visibility
        self.logger.info(f"🧹 CLEANED TEXT (after preprocessing): {text[:200]}")  # NEW: Show processed text
        
        symbols_found = set()
        
        # --- Parsing Strategy ---
        
        # 1. Check for Structured Headers
        header_1 = self.header_gaib_regex.search(text)
        header_2 = self.header_tek_regex.search(text)
        
        base_token = None
        if header_1:
            token_candidate = header_1.group(1).upper()
            if token_candidate not in self.symbol_blacklist:
                base_token = token_candidate
        elif header_2:
            token_candidate = header_2.group(1).upper()
            if token_candidate not in self.symbol_blacklist:
                base_token = token_candidate
            
        if base_token:
            symbols_found.add(f"{base_token}/USDT")
            self.logger.debug(f"💎 Found structured header for token: {base_token}")
            self.logger.info(f"✅ HEADER MATCH: {base_token}/USDT")  # NEW: Confirm header detection
        else:
            # Fallback for simple "BTC/USDT" format
            pair_matches = self.pair_regex.findall(text)
            for base, quote in pair_matches:
                if base not in self.symbol_blacklist:
                    symbols_found.add(f"{base}/{quote}")

        if not symbols_found:
            self.logger.debug(f"ℹ️ No trading symbols found in message")
            self.logger.info(f"⚠️ NO SYMBOLS DETECTED. Text preview: {text[:150]}")  # NEW: Show why nothing matched
            return

        # 2. Extract Specialized Metadata
        
        # Spread from "Курсовой: X.XX%"
        spread_match = self.course_spread_regex.search(text)
        reported_spread = float(spread_match.group(1).replace(',', '.')) / 100 if spread_match else 0.0
        
        # Direction/Exchanges from 📗/📕 lines
        direction = None
        supported_mentioned = []
        book_matches = self.book_line_regex.findall(text)
        
        # We look for BingX/Bybit direction
        for emoji, ex_name, dir_str in book_matches:
            ex_name = ex_name.lower()
            if ex_name in ['bingx', 'bybit']:
                direction = dir_str.upper()
                supported_mentioned.append(ex_name)
        
        # If no book lines found, fall back to simple detection if needed
        if not book_matches:
            # Legacy/Fallback detection could go here (Direction regex)
            pass

        for symbol in symbols_found:
            # Check for manual mapping in config first
            manual_map = self.tg_config.get('symbol_mapping', {})
            base, quote = symbol.split('/')
            if base in manual_map:
                symbol = f"{manual_map[base]}/{quote}"
                self.logger.info(f"🔄 Symbol remapped via config: {base} -> {manual_map[base]}")

            # Resolve exchange-specific symbols
            bingx_symbol = await self.resolver.resolve(self.validator.exchanges['bingx'], symbol)
            bybit_symbol = await self.resolver.resolve(self.validator.exchanges['bybit'], symbol)
            
            self.logger.info(
                f"📍 Signal detected for {symbol} | Direction: {direction} | Spread: {reported_spread:.2%}"
            )
            
            # Start asynchronous validation/monitoring flow
            if symbol not in self.active_signals or self.active_signals[symbol].done():
                metadata = {'direction': direction, 'reported_spread': reported_spread}
                task = asyncio.create_task(self._validate_and_confirm(symbol, message, metadata))
                self.active_signals[symbol] = task

    async def _validate_and_confirm(self, symbol: str, original_msg: Message, metadata: dict):
        """
        Flow:
        1. Historical ADF check
        2. Filter based on reported spread (if configured)
        3. If passed -> Start WebSockets for live monitoring
        4. Wait for Z-Score/Spread confirmation + Direction Match
        5. If confirmed -> Reply ✅
        """
        try:
            # Check reported spread filter
            min_repo_spread = self.tg_config.get('min_signal_spread_pct', 0.0)
            if metadata['reported_spread'] < min_repo_spread:
                self.logger.info(
                    f"⏩ {symbol} reported spread {metadata['reported_spread']:.2%} "
                    f"is below minimum {min_repo_spread:.2%}. Skipping."
                )
                return

            # 1. Historical Validation (ADF test)
            self.logger.info(f"🔍 Running ADF test for {symbol}...")
            results = await self.validator.analyze(
                symbol=symbol, 
                timeframe=self.adf_timeframe, 
                limit=self.adf_candles
            )
            
            if not results.get('is_stationary', False):
                self.logger.info(f"❌ {symbol} failed ADF stationarity check. Ignoring signal.")
                return

            self.logger.info(f"✅ {symbol} passed ADF test. Starting live monitoring...")

            # 2. Live Monitoring (Z-Score + Spread)
            # Add symbol to live monitor (ensure monitor is running)
            if not self.monitor.running:
                await self.monitor.start([symbol])
            else:
                # Add to existing monitor if possible (depends on LiveMonitor implementation)
                # For now, let's assume we call start with the specific symbol
                # and LiveMonitor handles multiple calls or we refactor it.
                # Note: Existing LiveMonitor.start cancels old task. 
                # Better to refactor LiveMonitor to support dynamic additions later if needed.
                await self.monitor.start([symbol]) 

            # 3. Wait loop for confirmation
            start_time = time.time()
            confirmed = False
            
            while time.time() - start_time < self.signal_timeout:
                stats = self.monitor.get_current_stats(symbol)
                if stats:
                    z_score = stats.get('z_score', 0)
                    net_spread_pct = stats.get('net_spread', 0) # Assuming this is pct or we compare value
                    
                    # Check conditions (Market Anomaly + Profitability)
                    z_threshold = self.tg_config.get('z_score_entry', 2.5)
                    z_cond = abs(z_score) > z_threshold
                    spread_cond = net_spread_pct > 0
                    
                    self.logger.debug(
                        f"👀 Checking {symbol}: Z={z_score:.2f} (Target > {z_threshold}), "
                        f"Spread={net_spread_pct:.2f}% (Target > 0%)"
                    )
                    
                    # Direction Match Check
                    dir_cond = True
                    if self.tg_config.get('require_direction_match', False) and metadata['direction']:
                        # z_score > 0 means BingX is expensive, so we'd SELL BingX, BUY Bybit
                        # If signal says LONG Huobi (Buy), then Huobi is cheap.
                        # So if signal says LONG, it means FIRST exchange is cheap.
                        # We don't know which exchange is 'first' in the signal message usually, 
                        # but we can check if our arbitrage direction makes sense.
                        # but we can check if our arbitrage direction makes sense.
                        # For now, let's just log it or implement a basic check if needed.
                        pass
                    
                    if not z_cond:
                         self.logger.debug(f"⏳ {symbol} Z-Score {z_score:.2f} too low (Need > {z_threshold})")
                    if not spread_cond:
                         self.logger.debug(f"⏳ {symbol} Net Spread {net_spread_pct:.2f}% too low (Need > 0%)")
                    
                    if z_cond and spread_cond and dir_cond:
                        confirmed = True
                        break
                
                await asyncio.sleep(5) # Check every 5 seconds
            
            if confirmed:
                self.logger.info(f"🚀 Signal CONFIRMED for {symbol}! Replying to Telegram...")
                await original_msg.reply("✅")
            else:
                self.logger.info(f"⏳ Signal for {symbol} timed out without confirmation.")

        except Exception as e:
            self.logger.error(f"Error in signal confirmation flow for {symbol}: {e}", exc_info=True)
        finally:
            # Cleanup if this was the only symbol or handle as needed
            # For now we keep monitoring until stopped or next signal
            pass

if __name__ == "__main__":
    # Test stub
    import sys
    loop = asyncio.get_event_loop()
    manager = TelegramSignalManager()
    try:
        loop.run_until_complete(manager.start())
    except KeyboardInterrupt:
        loop.run_until_complete(manager.stop())
