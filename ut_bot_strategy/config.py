"""
Configuration for UT Bot + STC Trading Strategy

All configurable parameters for the trading bot.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UTBotConfig:
    """UT Bot Alerts indicator configuration"""
    key_value: float = 2.0
    atr_period: int = 6
    use_heikin_ashi: bool = True
    ema_period: int = 1


@dataclass
class STCConfig:
    """STC indicator configuration (modified settings from video)"""
    length: int = 80
    fast_length: int = 27
    slow_length: int = 50
    aaa_factor: float = 0.5


@dataclass
class LeverageConfig:
    """Auto-leverage trading configuration"""
    enabled: bool = False
    min_leverage: int = 1
    max_leverage: int = 25
    base_leverage: int = 12
    risk_per_trade_percent: float = 2.0
    max_position_percent: float = 50.0
    use_isolated_margin: bool = False
    margin_type: str = "CROSS"
    auto_adjust_by_volatility: bool = True
    volatility_low_threshold: float = 1.0
    volatility_high_threshold: float = 3.0
    signal_strength_multiplier: bool = True
    auto_add_margin: bool = True


@dataclass
class TradingConfig:
    """Trading parameters configuration"""
    symbol: str = "ETHUSDT"
    timeframe: str = "5m"
    swing_lookback: int = 5
    risk_reward_ratio: float = 1.5
    min_risk_percent: float = 0.1
    max_risk_percent: float = 5.0
    min_candles_required: int = 100
    leverage: LeverageConfig = field(default_factory=LeverageConfig)


@dataclass
class BotConfig:
    """Main bot configuration"""
    check_interval_seconds: int = 30
    signal_cooldown_minutes: int = 5
    send_market_updates: bool = False
    market_update_interval_minutes: int = 60
    log_level: str = "INFO"
    enable_startup_notification: bool = True
    enable_shutdown_notification: bool = True


@dataclass
class Config:
    """Complete configuration container"""
    ut_bot: UTBotConfig = field(default_factory=UTBotConfig)
    stc: STCConfig = field(default_factory=STCConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    bot: BotConfig = field(default_factory=BotConfig)
    
    binance_api_key: str = field(default_factory=lambda: os.getenv('BINANCE_API_KEY', ''))
    binance_api_secret: str = field(default_factory=lambda: os.getenv('BINANCE_API_SECRET', ''))
    telegram_bot_token: str = field(default_factory=lambda: os.getenv('TELEGRAM_BOT_TOKEN', ''))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv('TELEGRAM_CHAT_ID', ''))
    
    def validate(self) -> bool:
        """Validate that all required configuration is present"""
        errors = []
        
        if not self.binance_api_key:
            errors.append("BINANCE_API_KEY not set")
        if not self.binance_api_secret:
            errors.append("BINANCE_API_SECRET not set")
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN not set")
        if not self.telegram_chat_id:
            errors.append("TELEGRAM_CHAT_ID not set")
        
        if errors:
            print("Configuration errors:")
            for error in errors:
                print(f"  - {error}")
            return False
        return True
    
    def to_dict(self) -> dict:
        """Convert configuration to dictionary"""
        return {
            'ut_bot': {
                'key_value': self.ut_bot.key_value,
                'atr_period': self.ut_bot.atr_period,
                'use_heikin_ashi': self.ut_bot.use_heikin_ashi,
                'ema_period': self.ut_bot.ema_period
            },
            'stc': {
                'length': self.stc.length,
                'fast_length': self.stc.fast_length,
                'slow_length': self.stc.slow_length,
                'aaa_factor': self.stc.aaa_factor
            },
            'trading': {
                'symbol': self.trading.symbol,
                'timeframe': self.trading.timeframe,
                'swing_lookback': self.trading.swing_lookback,
                'risk_reward_ratio': self.trading.risk_reward_ratio,
                'min_risk_percent': self.trading.min_risk_percent,
                'max_risk_percent': self.trading.max_risk_percent
            },
            'bot': {
                'check_interval_seconds': self.bot.check_interval_seconds,
                'signal_cooldown_minutes': self.bot.signal_cooldown_minutes,
                'send_market_updates': self.bot.send_market_updates,
                'log_level': self.bot.log_level
            }
        }


def load_config() -> Config:
    """Load configuration from environment and defaults"""
    return Config()
