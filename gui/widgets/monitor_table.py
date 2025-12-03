"""
Monitor Table Widget

Real-time table displaying arbitrage opportunities with color-coded Z-Scores.
"""

from typing import Dict, Optional
from collections import defaultdict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QColor, QBrush

from core.event_bus import EventBus
from utils.logger import get_logger


class MonitorTable(QWidget):
    """
    Real-time monitoring table for arbitrage opportunities.
    
    Features:
    - 7 columns: Symbol, BingX Price, Bybit Price, Spread $, Spread %, Z-Score, Status
    - Color-coded backgrounds based on Z-Score
    - O(1) row lookups via symbol->row_index mapping
    - EventBus integration for real-time updates
    """
    
    # Column indices
    COL_SYMBOL = 0
    COL_BINGX_PRICE = 1
    COL_BYBIT_PRICE = 2
    COL_SPREAD_USD = 3
    COL_SPREAD_PCT = 4
    COL_ZSCORE = 5
    COL_STATUS = 6
    
    def __init__(self):
        """Initialize monitor table."""
        super().__init__()
        
        self.logger = get_logger(__name__)
        self.symbol_to_row: Dict[str, int] = {}
        self.row_to_symbol: Dict[int, str] = {}
        
        # Track latest prices per exchange per symbol
        self.latest_prices: Dict[str, Dict[str, float]] = defaultdict(dict)
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Title
        title = QLabel("Real-Time Arbitrage Monitor")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(title)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Symbol", "BingX Price", "Bybit Price", 
            "Spread $", "Spread %", "Z-Score", "Status"
        ])
        
        # Table styling
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        
        # Column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Symbol
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # BingX
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Bybit
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Spread $
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Spread %
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Z-Score
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Status
        
        layout.addWidget(self.table)
    
    def _connect_signals(self):
        """Connect to EventBus signals."""
        bus = EventBus.instance()
        bus.price_updated.connect(self._on_price_updated)
        bus.spread_updated.connect(self._on_spread_updated)
    
    @pyqtSlot(dict)
    def _on_price_updated(self, data: dict):
        """
        Handle price update from EventBus.
        
        Args:
            data: Price data dictionary with exchange, symbol, bid, ask, etc.
        """
        try:
            exchange = data.get('exchange', '')
            symbol = data.get('symbol', '')
            
            if not exchange or not symbol:
                return
            
            # Calculate mid price
            bid = data.get('bid', 0.0)
            ask = data.get('ask', 0.0)
            mid_price = (bid + ask) / 2.0 if bid and ask else 0.0
            
            # Store latest price
            self.latest_prices[symbol][exchange] = mid_price
            
            # Update table if row exists
            if symbol in self.symbol_to_row:
                row = self.symbol_to_row[symbol]
                
                if exchange == 'bingx' and mid_price > 0:
                    self._update_cell(row, self.COL_BINGX_PRICE, f"${mid_price:,.2f}")
                elif exchange == 'bybit' and mid_price > 0:
                    self._update_cell(row, self.COL_BYBIT_PRICE, f"${mid_price:,.2f}")
                    
        except Exception as e:
            self.logger.error(f"Error handling price update: {e}")
    
    
    @pyqtSlot(str, float, float)
    def _on_spread_updated(self, symbol: str, spread: float, zscore: float):
        """
        Handle spread update from EventBus.
        
        Args:
            symbol: Trading pair symbol
            spread: Spread value in USD
            zscore: Z-Score value
        """
        try:
            # Get or create row
            if symbol not in self.symbol_to_row:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.symbol_to_row[symbol] = row
                self.row_to_symbol[row] = symbol
                
                # Set symbol (non-editable)
                symbol_item = QTableWidgetItem(symbol)
                symbol_item.setFlags(symbol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                symbol_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, self.COL_SYMBOL, symbol_item)
            
            row = self.symbol_to_row[symbol]
            
            # Calculate spread percentage using actual prices if available
            bingx_price = self.latest_prices.get(symbol, {}).get('bingx', 0.0)
            bybit_price = self.latest_prices.get(symbol, {}).get('bybit', 0.0)
            
            if bingx_price > 0 and bybit_price > 0:
                mid_price = (bingx_price + bybit_price) / 2.0
                spread_pct = (spread / mid_price) * 100.0
            else:
                # Fallback estimate
                spread_pct = (spread / 50000.0) * 100.0
            
            # Update cells
            self._update_cell(row, self.COL_SPREAD_USD, f"${spread:,.2f}")
            self._update_cell(row, self.COL_SPREAD_PCT, f"{spread_pct:.3f}%")
            self._update_cell(row, self.COL_ZSCORE, f"{zscore:.2f}")
            
            # Determine status and color
            status, bg_color = self._get_status_and_color(zscore)
            self._update_cell(row, self.COL_STATUS, status)
            
            # Apply row background color
            self._set_row_background(row, bg_color)
            
        except Exception as e:
            self.logger.error(f"Error updating table for {symbol}: {e}")
    
    def _update_cell(self, row: int, col: int, text: str):
        """
        Update a table cell with text.
        
        Args:
            row: Row index
            col: Column index
            text: Text to display
        """
        item = self.table.item(row, col)
        if item is None:
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, col, item)
        else:
            item.setText(text)
    
    def _get_status_and_color(self, zscore: float) -> tuple:
        """
        Determine status text and background color based on Z-Score.
        
        Args:
            zscore: Z-Score value
            
        Returns:
            Tuple of (status_text, QColor)
        """
        if zscore > 2.0:
            # Entry signal: LONG BingX / SHORT Bybit
            return "🔴 SIGNAL", QColor(220, 53, 69, 100)  # Red with transparency
        elif zscore < -2.0:
            # Entry signal: opposite direction
            return "🟢 SIGNAL", QColor(40, 167, 69, 100)  # Green with transparency
        elif -0.5 <= zscore <= 0.5:
            # Exit zone
            return "🟡 EXIT", QColor(255, 193, 7, 100)  # Yellow with transparency
        else:
            # Normal
            return "⚪ NORMAL", QColor(108, 117, 125, 50)  # Gray with transparency
    
    def _set_row_background(self, row: int, color: QColor):
        """
        Set background color for entire row.
        
        Args:
            row: Row index
            color: Background color
        """
        brush = QBrush(color)
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                item.setBackground(brush)
    
    def add_symbol(self, symbol: str):
        """
        Add a symbol to the table with LOADING status.
        
        Args:
            symbol: Trading pair symbol
        """
        if symbol in self.symbol_to_row:
            self.logger.debug(f"Symbol {symbol} already in table")
            return
        
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.symbol_to_row[symbol] = row
        self.row_to_symbol[row] = symbol
        
        # Set symbol
        symbol_item = QTableWidgetItem(symbol)
        symbol_item.setFlags(symbol_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        symbol_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, self.COL_SYMBOL, symbol_item)
        
        # Set loading status
        self._update_cell(row, self.COL_STATUS, "⏳ LOADING")
        
        self.logger.info(f"Added symbol to table: {symbol}")
    
    def remove_symbol(self, symbol: str):
        """
        Remove a symbol from the table.
        
        Args:
            symbol: Trading pair symbol
        """
        if symbol not in self.symbol_to_row:
            self.logger.debug(f"Symbol {symbol} not in table")
            return
        
        row = self.symbol_to_row[symbol]
        self.table.removeRow(row)
        
        # Update mappings
        del self.symbol_to_row[symbol]
        del self.row_to_symbol[row]
        
        # Rebuild mappings for rows after deleted row
        new_symbol_to_row = {}
        new_row_to_symbol = {}
        for r in range(self.table.rowCount()):
            item = self.table.item(r, self.COL_SYMBOL)
            if item:
                sym = item.text()
                new_symbol_to_row[sym] = r
                new_row_to_symbol[r] = sym
        
        self.symbol_to_row = new_symbol_to_row
        self.row_to_symbol = new_row_to_symbol
        
        self.logger.info(f"Removed symbol from table: {symbol}")
    
    def clear_table(self):
        """Clear all rows from the table."""
        self.table.setRowCount(0)
        self.symbol_to_row.clear()
        self.row_to_symbol.clear()
        self.logger.info("Table cleared")
