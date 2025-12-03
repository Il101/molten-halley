"""
Pair Selector Widget

Allows users to dynamically add/remove trading pairs from monitoring.
Integrates with WebSocketManager's subscribe/unsubscribe methods.
"""

import json
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox,
    QPushButton, QListWidget, QListWidgetItem, QLabel,
    QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal

from utils.logger import get_logger


class PairSelector(QWidget):
    """
    Widget for selecting and managing trading pairs.
    
    Features:
    - Load pairs from whitelist.json
    - Add pairs to monitoring (calls ws_manager.subscribe)
    - Remove pairs from monitoring (calls ws_manager.unsubscribe)
    - Display active pairs list
    
    Signals:
        pair_added: Emitted when a pair is added (str: symbol)
        pair_removed: Emitted when a pair is removed (str: symbol)
    """
    
    pair_added = pyqtSignal(str)
    pair_removed = pyqtSignal(str)
    
    def __init__(self, whitelist_path: str = 'config/whitelist.json'):
        """
        Initialize pair selector.
        
        Args:
            whitelist_path: Path to whitelist JSON file
        """
        super().__init__()
        
        self.logger = get_logger(__name__)
        self.whitelist_path = Path(whitelist_path)
        self.available_pairs: List[str] = []
        self.active_pairs: List[str] = []
        
        self._setup_ui()
        self._load_whitelist()
    
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Title
        title = QLabel("Pair Management")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(title)
        
        # Available pairs section
        available_group = QGroupBox("Available Pairs")
        available_layout = QVBoxLayout(available_group)
        
        # Pair selector
        selector_layout = QHBoxLayout()
        self.pair_combo = QComboBox()
        self.pair_combo.setMinimumWidth(150)
        selector_layout.addWidget(self.pair_combo)
        
        self.add_button = QPushButton("➕ Add Pair")
        self.add_button.clicked.connect(self._on_add_pair)
        self.add_button.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                font-weight: bold;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
            QPushButton:disabled {
                background-color: #7f8c8d;
            }
        """)
        selector_layout.addWidget(self.add_button)
        
        available_layout.addLayout(selector_layout)
        layout.addWidget(available_group)
        
        # Active pairs section
        active_group = QGroupBox("Active Pairs")
        active_layout = QVBoxLayout(active_group)
        
        self.active_list = QListWidget()
        self.active_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        active_layout.addWidget(self.active_list)
        
        # Remove button
        self.remove_button = QPushButton("🗑️ Remove Selected")
        self.remove_button.clicked.connect(self._on_remove_pair)
        self.remove_button.setEnabled(False)
        self.remove_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:disabled {
                background-color: #7f8c8d;
            }
        """)
        active_layout.addWidget(self.remove_button)
        
        layout.addWidget(active_group)
        
        # Connect signals
        self.active_list.itemSelectionChanged.connect(self._on_selection_changed)
        
        # Stretch
        layout.addStretch()
    
    def _load_whitelist(self):
        """Load available pairs from whitelist.json."""
        try:
            if not self.whitelist_path.exists():
                self.logger.warning(f"Whitelist not found: {self.whitelist_path}")
                self.pair_combo.addItem("No pairs available")
                self.add_button.setEnabled(False)
                return
            
            with open(self.whitelist_path, 'r') as f:
                data = json.load(f)
            
            pairs = data.get('pairs', [])
            self.available_pairs = [
                p['symbol'] for p in pairs 
                if p.get('enabled', True)
            ]
            
            if self.available_pairs:
                self.pair_combo.addItems(self.available_pairs)
                self.add_button.setEnabled(True)
                self.logger.info(f"Loaded {len(self.available_pairs)} pairs from whitelist")
            else:
                self.pair_combo.addItem("No enabled pairs")
                self.add_button.setEnabled(False)
                
        except Exception as e:
            self.logger.error(f"Error loading whitelist: {e}")
            self.pair_combo.addItem("Error loading pairs")
            self.add_button.setEnabled(False)
    
    def refresh_whitelist(self):
        """Reload whitelist from file."""
        self.pair_combo.clear()
        self.available_pairs.clear()
        self._load_whitelist()
        self.logger.info("Whitelist refreshed")
    
    def _on_add_pair(self):
        """Handle add pair button click."""
        selected_pair = self.pair_combo.currentText()
        
        if not selected_pair or selected_pair in ["No pairs available", "No enabled pairs", "Error loading pairs"]:
            return
        
        if selected_pair in self.active_pairs:
            QMessageBox.information(
                self,
                "Already Active",
                f"{selected_pair} is already being monitored."
            )
            return
        
        # Add to active list
        self.active_pairs.append(selected_pair)
        self.active_list.addItem(selected_pair)
        
        # Emit signal
        self.pair_added.emit(selected_pair)
        self.logger.info(f"Added pair: {selected_pair}")
    
    def _on_remove_pair(self):
        """Handle remove pair button click."""
        selected_items = self.active_list.selectedItems()
        
        if not selected_items:
            return
        
        item = selected_items[0]
        symbol = item.text()
        
        # Confirm removal
        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Remove {symbol} from monitoring?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove from list
            row = self.active_list.row(item)
            self.active_list.takeItem(row)
            self.active_pairs.remove(symbol)
            
            # Emit signal
            self.pair_removed.emit(symbol)
            self.logger.info(f"Removed pair: {symbol}")
    
    def _on_selection_changed(self):
        """Handle list selection change."""
        has_selection = len(self.active_list.selectedItems()) > 0
        self.remove_button.setEnabled(has_selection)
    
    def add_active_pair(self, symbol: str):
        """
        Programmatically add a pair to active list.
        
        Args:
            symbol: Trading pair symbol
        """
        if symbol not in self.active_pairs:
            self.active_pairs.append(symbol)
            self.active_list.addItem(symbol)
            self.logger.debug(f"Programmatically added: {symbol}")
    
    def get_active_pairs(self) -> List[str]:
        """
        Get list of currently active pairs.
        
        Returns:
            List of active pair symbols
        """
        return self.active_pairs.copy()
