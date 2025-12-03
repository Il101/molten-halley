"""
Active Trades Widget

Displays active arbitrage positions and real-time P&L.
"""

import time
from typing import Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QColor, QBrush

from core.event_bus import EventBus
from utils.logger import get_logger


class ActiveTradesWidget(QWidget):
    """
    Widget to display active arbitrage trades.
    
    Columns:
    - Symbol
    - Side (Long/Short)
    - Entry Price
    - Current Price
    - P&L (USDT)
    - Duration
    """
    
    # Column indices
    COL_SYMBOL = 0
    COL_SIDE = 1
    COL_ENTRY = 2
    COL_CURRENT = 3
    COL_PNL = 4
    COL_DURATION = 5
    
    def __init__(self):
        """Initialize widget."""
        super().__init__()
        
        self.logger = get_logger(__name__)
        self.event_bus = EventBus.instance()
        
        # Track active rows: symbol -> row_index
        self.active_rows: Dict[str, int] = {}
        # Track entry data for P&L calculation: symbol -> trade_data
        self.trade_data: Dict[str, Dict] = {}
        # Track latest prices: symbol -> {exchange: price}
        self.latest_prices: Dict[str, Dict[str, float]] = {}
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        """Setup user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header label
        header = QLabel("Active Positions")
        header.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        layout.addWidget(header)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Symbol", "Side", "Entry Price", "Current Price", "P&L (USDT)", "Duration"
        ])
        
        # Table styling
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        
        layout.addWidget(self.table)
    
    def _connect_signals(self):
        """Connect to EventBus signals."""
        self.event_bus.trade_opened.connect(self._on_trade_opened)
        self.event_bus.trade_closed.connect(self._on_trade_closed)
        self.event_bus.price_updated.connect(self._on_price_updated)
    
    @pyqtSlot(dict)
    def _on_trade_opened(self, data: dict):
        """
        Handle new trade opened.
        
        Args:
            data: Trade metadata
        """
        symbol = data['symbol']
        
        if symbol in self.active_rows:
            return  # Already exists
        
        # Add new row
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # Store row index and data
        self.active_rows[symbol] = row
        self.trade_data[symbol] = data
        self.trade_data[symbol]['start_time'] = time.time()
        
        # Set items
        self.table.setItem(row, self.COL_SYMBOL, QTableWidgetItem(symbol))
        
        # Side (e.g., "Long A / Short B")
        side_str = f"{data['side_a'].title()} A / {data['side_b'].title()} B"
        self.table.setItem(row, self.COL_SIDE, QTableWidgetItem(side_str))
        
        # Entry Price (Avg)
        entry_price = (data.get('entry_price_a', 0) + data.get('entry_price_b', 0)) / 2
        self.table.setItem(row, self.COL_ENTRY, QTableWidgetItem(f"${entry_price:.2f}"))
        
        self.table.setItem(row, self.COL_CURRENT, QTableWidgetItem("---"))
        self.table.setItem(row, self.COL_PNL, QTableWidgetItem("0.00"))
        self.table.setItem(row, self.COL_DURATION, QTableWidgetItem("0s"))
        
        self.logger.info(f"GUI: Added active trade row for {symbol}")
    
    @pyqtSlot(dict)
    def _on_trade_closed(self, data: dict):
        """
        Handle trade closed.
        
        Args:
            data: Trade close metadata
        """
        symbol = data['symbol']
        
        if symbol in self.active_rows:
            row = self.active_rows[symbol]
            self.table.removeRow(row)
            del self.active_rows[symbol]
            del self.trade_data[symbol]
            if symbol in self.latest_prices:
                del self.latest_prices[symbol]
            
            # Rebuild index map for remaining rows
            # This is inefficient for many rows but fine for < 10 positions
            self.active_rows = {}
            for r in range(self.table.rowCount()):
                sym_item = self.table.item(r, self.COL_SYMBOL)
                if sym_item:
                    self.active_rows[sym_item.text()] = r
            
            self.logger.info(f"GUI: Removed active trade row for {symbol}")
    
    @pyqtSlot(dict)
    def _on_price_updated(self, data: dict):
        """
        Update P&L and prices in real-time.
        
        Args:
            data: Price update data
        """
        symbol = data.get('symbol')
        
        if symbol not in self.active_rows:
            return
            
        row = self.active_rows[symbol]
        trade = self.trade_data[symbol]
        
        # Update Duration
        duration = int(time.time() - trade['start_time'])
        duration_str = f"{duration // 60}m {duration % 60}s"
        self.table.setItem(row, self.COL_DURATION, QTableWidgetItem(duration_str))
        
        # Update Current Price (Last)
        current_price = data.get('last', 0)
        exchange = data.get('exchange')
        
        # Update price cache
        if symbol not in self.latest_prices:
            self.latest_prices[symbol] = {}
        self.latest_prices[symbol][exchange] = current_price
        
        # Calculate average current price for display
        prices = self.latest_prices[symbol].values()
        if prices:
            avg_price = sum(prices) / len(prices)
            self.table.setItem(row, self.COL_CURRENT, QTableWidgetItem(f"${avg_price:.2f}"))
        
        # Calculate P&L
        self._update_pnl(row, symbol)
        
    def _update_pnl(self, row: int, symbol: str):
        """
        Calculate and update P&L for a row.
        
        Args:
            row: Table row index
            symbol: Trading pair symbol
        """
        if symbol not in self.trade_data or symbol not in self.latest_prices:
            return
            
        trade = self.trade_data[symbol]
        prices = self.latest_prices[symbol]
        
        # We need prices from both exchanges to calculate accurate P&L
        # If we only have one, we can estimate or wait
        # For now, let's calculate what we can
        
        pnl = 0.0
        amount = trade['amount']
        
        # Leg A
        if 'bingx' in prices:
            current_a = prices['bingx']
            entry_a = trade['entry_price_a']
            if trade['side_a'] == 'buy':
                pnl += (current_a - entry_a) * amount
            else:
                pnl += (entry_a - current_a) * amount
                
        # Leg B
        if 'bybit' in prices:
            current_b = prices['bybit']
            entry_b = trade['entry_price_b']
            if trade['side_b'] == 'buy':
                pnl += (current_b - entry_b) * amount
            else:
                pnl += (entry_b - current_b) * amount
        
        # Update P&L Cell
        item = QTableWidgetItem(f"${pnl:.2f}")
        
        # Color coding
        if pnl > 0:
            item.setForeground(QBrush(QColor("#00ff00")))  # Green
        elif pnl < 0:
            item.setForeground(QBrush(QColor("#ff0000")))  # Red
        else:
            item.setForeground(QBrush(QColor("#ffffff")))  # White
            
        self.table.setItem(row, self.COL_PNL, item)
