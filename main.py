#!/usr/bin/env python3
"""
ArbiBot - Cryptocurrency Arbitrage Bot
Main entry point and orchestrator
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.logger import setup_logger

# Setup logger
logger = setup_logger('arbibot', level='INFO')


def main():
    """
    Main entry point for ArbiBot
    """
    parser = argparse.ArgumentParser(
        description='ArbiBot - Cryptocurrency Arbitrage Trading Bot'
    )
    
    parser.add_argument(
        'mode',
        choices=['gui', 'scan', 'analyze', 'live'],
        help='Operation mode'
    )
    
    parser.add_argument(
        '--pair',
        type=str,
        help='Trading pair (e.g., BTC/USDT) for analyze mode'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='config/config.yaml',
        help='Path to configuration file'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    # Update log level if debug
    if args.debug:
        logger.setLevel('DEBUG')
        logger.debug('Debug mode enabled')
    
    logger.info(f"Starting ArbiBot in '{args.mode}' mode")
    logger.info(f"Using config: {args.config}")
    
    try:
        if args.mode == 'gui':
            run_gui(args)
        elif args.mode == 'scan':
            run_scanner(args)
        elif args.mode == 'analyze':
            run_analysis(args)
        elif args.mode == 'live':
            run_live_monitor(args)
    except KeyboardInterrupt:
        logger.info("\nShutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


def run_gui(args):
    """
    Launch PyQt6 GUI application
    """
    logger.info("Launching GUI...")
    try:
        from PyQt6.QtWidgets import QApplication
        from gui.main_window import ArbiGUI
        
        app = QApplication(sys.argv)
        window = ArbiGUI(config_path=args.config)
        window.show()
        sys.exit(app.exec())
    except ImportError as e:
        logger.error(f"GUI dependencies not installed: {e}")
        logger.error("Install with: pip install PyQt6 pyqtgraph")
        sys.exit(1)


def run_scanner(args):
    """
    Run market scanner to find profitable pairs
    """
    logger.info("Running market scanner...")
    try:
        from services.market_scanner import MarketScanner
        
        scanner = MarketScanner(config_path=args.config)
        results = scanner.scan()
        
        logger.info(f"Scan complete. Found {len(results)} profitable pairs")
        logger.info("Results saved to config/whitelist.json")
    except ImportError as e:
        logger.error(f"Scanner module not ready: {e}")
        sys.exit(1)


def run_analysis(args):
    """
    Run historical analysis on a specific pair
    """
    if not args.pair:
        logger.error("--pair argument required for analyze mode")
        logger.error("Example: python main.py analyze --pair BTC/USDT")
        sys.exit(1)
    
    logger.info(f"Analyzing {args.pair}...")
    try:
        from services.historical_validator import HistoricalValidator
        
        validator = HistoricalValidator(config_path=args.config)
        results = validator.analyze(args.pair)
        
        # Display results
        logger.info("\n" + "="*50)
        logger.info(f"Analysis Results for {args.pair}")
        logger.info("="*50)
        logger.info(f"Stationary: {results.get('is_stationary', False)}")
        logger.info(f"ADF P-Value: {results.get('adf_pvalue', 'N/A'):.4f}")
        logger.info(f"Max Spread: {results.get('max_spread_pct', 0):.2%}")
        logger.info(f"Z-Score Signals: {results.get('z_score_signals', 0)}")
        logger.info(f"Profitable: {results.get('is_profitable', False)}")
        logger.info("="*50)
        
    except ImportError as e:
        logger.error(f"Analysis module not ready: {e}")
        sys.exit(1)


def run_live_monitor(args):
    """
    Run live WebSocket monitoring (headless)
    """
    logger.info("Starting live monitor...")
    logger.warning("Live monitor not yet implemented")
    logger.info("Coming soon: WebSocket real-time monitoring")


if __name__ == '__main__':
    main()
