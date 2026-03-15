"""
UT Bot + STC Trading Signal Bot

A comprehensive trading signal bot for ETH/USDT that combines:
- UT Bot Alerts (ATR-based trailing stop)
- STC (Schaff Trend Cycle) indicator

Strategy:
- LONG: UT Bot BUY signal + STC green + STC pointing up + STC < 75
- SHORT: UT Bot SELL signal + STC red + STC pointing down + STC > 25
- Stop loss at recent swing high/low
- Take profit at 1.5x risk (R:R = 1:1.5)
"""

from .config import Config, load_config
from .orchestrator import TradingOrchestrator
from .indicators import UTBotAlerts, STCIndicator
from .engine import SignalEngine
from .telegram import TelegramSignalBot
from .data import BinanceDataFetcher

__version__ = "1.0.0"
__author__ = "Trading Bot"

__all__ = [
    'Config',
    'load_config',
    'TradingOrchestrator',
    'UTBotAlerts',
    'STCIndicator',
    'SignalEngine',
    'TelegramSignalBot',
    'BinanceDataFetcher'
]
