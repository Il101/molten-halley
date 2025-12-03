"""
Execution Engine

Manages arbitrage trade execution with rollback protection.
Works with both Paper and Real exchange clients via dependency injection.
"""

import asyncio
from typing import Dict, Optional
from datetime import datetime

from core.interfaces.exchange import BaseExchange
from core.event_bus import EventBus
from utils.logger import get_logger


class ExecutionEngine:
    """
    Core trading logic for arbitrage execution.
    
    Features:
    - Exchange-agnostic via BaseExchange interface
    - Atomic-like execution with rollback on failure
    - Event-driven signal handling
    - Position tracking and P&L calculation
    """
    
    def __init__(
        self,
        client_a: BaseExchange,
        client_b: BaseExchange,
        position_size_usdt: float = 100.0,
        max_positions: int = 5
    ):
        """
        Initialize Execution Engine.
        
        Args:
            client_a: First exchange client (BaseExchange)
            client_b: Second exchange client (BaseExchange)
            position_size_usdt: Fixed position size in USDT
            max_positions: Maximum concurrent positions
        """
        self.client_a = client_a
        self.client_b = client_b
        self.position_size_usdt = position_size_usdt
        self.max_positions = max_positions
        
        self.logger = get_logger(__name__)
        self.event_bus = EventBus.instance()
        
        # State tracking
        self.is_busy = False
        self.active_trades: Dict[str, Dict] = {}  # symbol -> trade metadata
        
        # Subscribe to trading signals
        self.event_bus.signal_triggered.connect(self._handle_signal)
        
        self.logger.info(
            f"ExecutionEngine initialized: "
            f"{client_a.get_exchange_name()} <-> {client_b.get_exchange_name()}, "
            f"Position Size: ${position_size_usdt}"
        )
    
    def _handle_signal(self, symbol: str, signal_type: str, z_score: float) -> None:
        """
        Handle trading signal from EventBus.
        
        Args:
            symbol: Trading pair
            signal_type: 'ENTRY' or 'EXIT'
            z_score: Z-Score at signal trigger
        """
        # Run async handler in event loop
        asyncio.create_task(self._process_signal(symbol, signal_type, z_score))
    
    async def _process_signal(
        self,
        symbol: str,
        signal_type: str,
        z_score: float
    ) -> None:
        """
        Process trading signal asynchronously.
        
        Args:
            symbol: Trading pair
            signal_type: 'ENTRY' or 'EXIT'
            z_score: Z-Score value
        """
        try:
            if signal_type == 'ENTRY':
                await self.execute_arb_entry(symbol, z_score)
            elif signal_type == 'EXIT':
                await self.execute_arb_exit(symbol)
        except Exception as e:
            self.logger.error(f"Error processing {signal_type} signal for {symbol}: {e}")
            self.event_bus.emit_error('ExecutionEngine', str(e))
    
    async def execute_arb_entry(self, symbol: str, z_score: float) -> bool:
        """
        Execute arbitrage entry with rollback protection.
        
        Strategy:
        - If Z-Score > 0: Buy on A (cheaper), Sell on B (expensive)
        - If Z-Score < 0: Sell on A (expensive), Buy on B (cheaper)
        
        Args:
            symbol: Trading pair
            z_score: Z-Score value (determines direction)
        
        Returns:
            True if successful, False otherwise
        """
        # Check if already busy
        if self.is_busy:
            self.logger.warning(f"⏸️  Execution busy, skipping {symbol}")
            return False
        
        # Check if already have position
        if symbol in self.active_trades:
            self.logger.warning(f"⏸️  Already have position in {symbol}")
            return False
        
        # Check position limit
        if len(self.active_trades) >= self.max_positions:
            self.logger.warning(f"⏸️  Max positions reached ({self.max_positions})")
            return False
        
        self.is_busy = True
        
        try:
            # Check balances
            balance_a = await self.client_a.get_balance()
            balance_b = await self.client_b.get_balance()
            
            free_a = balance_a.get('USDT', {}).get('free', 0)
            free_b = balance_b.get('USDT', {}).get('free', 0)
            
            if free_a < self.position_size_usdt or free_b < self.position_size_usdt:
                self.logger.error(
                    f"❌ Insufficient balance: A=${free_a:.2f}, B=${free_b:.2f}"
                )
                return False
            
            # Get current prices
            ticker_a = await self.client_a.fetch_ticker(symbol)
            ticker_b = await self.client_b.fetch_ticker(symbol)
            
            # Calculate position size in base currency
            # Use mid price for sizing
            avg_price = (ticker_a['last'] + ticker_b['last']) / 2
            amount = self.position_size_usdt / avg_price
            
            # Determine trade direction based on Z-Score
            if z_score > 0:
                # A is cheaper, B is expensive
                side_a = 'buy'
                side_b = 'sell'
                entry_spread = ticker_b['bid'] - ticker_a['ask']
            else:
                # A is expensive, B is cheaper
                side_a = 'sell'
                side_b = 'buy'
                entry_spread = ticker_a['bid'] - ticker_b['ask']
            
            self.logger.info(
                f"🚀 Opening arbitrage: {symbol}, Z-Score={z_score:.2f}, "
                f"Spread=${entry_spread:.2f}, Size={amount:.6f}"
            )
            
            # ATOMIC EXECUTION WITH ROLLBACK
            order_a = None
            order_b = None
            
            try:
                # First leg
                order_a = await self.client_a.create_order(
                    symbol=symbol,
                    side=side_a,
                    amount=amount
                )
                
                self.logger.info(
                    f"✅ Leg A complete: {side_a.upper()} on "
                    f"{self.client_a.get_exchange_name()}"
                )
                
                # Second leg
                try:
                    order_b = await self.client_b.create_order(
                        symbol=symbol,
                        side=side_b,
                        amount=amount
                    )
                    
                    self.logger.info(
                        f"✅ Leg B complete: {side_b.upper()} on "
                        f"{self.client_b.get_exchange_name()}"
                    )
                
                except Exception as e:
                    # CRITICAL: Second leg failed, rollback first leg
                    self.logger.error(
                        f"🚨 Second leg failed: {e}. Rolling back first leg..."
                    )
                    
                    try:
                        await self.client_a.close_position(symbol)
                        self.logger.warning("⚠️  Rollback successful")
                    except Exception as rollback_error:
                        self.logger.error(
                            f"💀 ROLLBACK FAILED: {rollback_error}. "
                            f"MANUAL INTERVENTION REQUIRED!"
                        )
                    
                    raise Exception(f"Arbitrage entry failed - rolled back: {e}")
            
            except Exception as e:
                self.logger.error(f"❌ Entry failed: {e}")
                return False
            
            # Store trade metadata
            # Store trade metadata
            trade_data = {
                'symbol': symbol,
                'entry_time': datetime.now().isoformat(),
                'entry_z_score': z_score,
                'entry_spread': entry_spread,
                'order_a_id': order_a['id'],
                'order_b_id': order_b['id'],
                'side_a': side_a,
                'side_b': side_b,
                'amount': amount,
                'entry_price_a': order_a.get('average', 0),
                'entry_price_b': order_b.get('average', 0)
            }
            self.active_trades[symbol] = trade_data
            
            # Emit signal for GUI
            self.event_bus.emit_trade_opened(trade_data)
            
            self.logger.info(
                f"✅ Arbitrage opened: {symbol} "
                f"({self.client_a.get_exchange_name()} {side_a.upper()} / "
                f"{self.client_b.get_exchange_name()} {side_b.upper()})"
            )
            
            return True
        
        except Exception as e:
            self.logger.error(f"❌ Arbitrage entry error: {e}")
            return False
        
        finally:
            self.is_busy = False
    
    async def execute_arb_exit(self, symbol: str) -> bool:
        """
        Execute arbitrage exit.
        
        Args:
            symbol: Trading pair
        
        Returns:
            True if successful, False otherwise
        """
        if symbol not in self.active_trades:
            self.logger.warning(f"⏸️  No active trade for {symbol}")
            return False
        
        self.is_busy = True
        
        try:
            trade = self.active_trades[symbol]
            
            self.logger.info(f"🔄 Closing arbitrage: {symbol}")
            
            # Close both positions
            close_a = await self.client_a.close_position(symbol)
            close_b = await self.client_b.close_position(symbol)
            
            # Calculate total P&L
            pnl_a = close_a.get('pnl', 0)
            pnl_b = close_b.get('pnl', 0)
            total_pnl = pnl_a + pnl_b
            
            # Calculate holding time
            entry_time = datetime.fromisoformat(trade['entry_time'])
            holding_time = (datetime.now() - entry_time).total_seconds()
            
            self.logger.info(
                f"✅ Arbitrage closed: {symbol}, "
                f"P&L=${total_pnl:.2f}, "
                f"Holding Time={holding_time:.0f}s"
            )
            
            # Emit signal for GUI
            self.event_bus.emit_trade_closed({
                'symbol': symbol,
                'pnl': total_pnl,
                'holding_time': holding_time,
                'exit_time': datetime.now().isoformat()
            })
            
            # Remove from active trades
            del self.active_trades[symbol]
            
            return True
        
        except Exception as e:
            self.logger.error(f"❌ Arbitrage exit error: {e}")
            return False
        
        finally:
            self.is_busy = False
    
    async def get_active_positions(self) -> Dict[str, Dict]:
        """
        Get all active arbitrage positions.
        
        Returns:
            Dictionary of symbol -> trade metadata
        """
        return self.active_trades.copy()
    
    async def emergency_close_all(self) -> None:
        """
        Emergency close all positions.
        
        Use this for risk management or shutdown.
        """
        self.logger.warning("🚨 EMERGENCY CLOSE ALL POSITIONS")
        
        for symbol in list(self.active_trades.keys()):
            try:
                await self.execute_arb_exit(symbol)
            except Exception as e:
                self.logger.error(f"Failed to close {symbol}: {e}")
