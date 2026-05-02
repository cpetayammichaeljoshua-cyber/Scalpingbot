"""
Configuration management for the trading bot
Handles environment variables and default settings
"""

import os
import json
from typing import Dict, Any, List
from datetime import timedelta

class Config:
    """Configuration class for managing bot settings"""

    def __init__(self):
        # Telegram Configuration
        self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        self.TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

        # Binance Configuration
        self.BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
        self.BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

        # Use mainnet by default for live trading
        self.BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

        # Session Secret
        self.SESSION_SECRET = os.getenv(
            "SESSION_SECRET",
            "snfpdA4kx+l9/+w0qMi3DzmND+CqQx/XUG0f4irkipuqmxNH++NpQ738XBdURGSuM574qS0iQsabmf6vmiwa2g=="
        )

        # Trading Configuration - Optimized for $10 Capital Base
        self.DEFAULT_RISK_PERCENTAGE = float(os.getenv("DEFAULT_RISK_PERCENTAGE", "5.0"))
        self.CAPITAL_BASE = float(os.getenv("CAPITAL_BASE", "10.0"))
        # Position size limits optimized for small capital ($10 base)
        # Max position: 80% of capital ($8.00) to prevent over-exposure
        self.MAX_POSITION_SIZE = float(os.getenv("MAX_POSITION_SIZE", "8.0"))
        # Min position: $0.10 for micro-trading with small capital
        self.MIN_POSITION_SIZE = float(os.getenv("MIN_POSITION_SIZE", "0.10"))
        self.STOP_LOSS_PERCENTAGE = float(os.getenv("STOP_LOSS_PERCENTAGE", "3.0"))
        self.TAKE_PROFIT_PERCENTAGE = float(os.getenv("TAKE_PROFIT_PERCENTAGE", "6.0"))

        # Cornix Configuration
        self.CORNIX_WEBHOOK_URL = os.getenv("CORNIX_WEBHOOK_URL", "https://dashboard.cornix.io/tradingview/")
        self.CORNIX_BOT_UUID = os.getenv("CORNIX_BOT_UUID", "")

        # Database Configuration
        self.DATABASE_PATH = os.getenv("DATABASE_PATH", "trading_bot.db")

        # Server Configuration
        self.WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
        self.WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "5000"))

        # Logging Configuration
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FILE = os.getenv("LOG_FILE", "trading_bot.log")

        # Trading Pairs Configuration
        self.SUPPORTED_PAIRS = [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT",
            "LINKUSDT", "LTCUSDT", "BCHUSDT", "XLMUSDT", "EOSUSDT",
            "TRXUSDT", "XRPUSDT", "SOLUSDT", "AVAXUSDT", "MATICUSDT",
        ]

        # BTCUSDT Perpetual Futures — Primary Symbol Configuration
        self.BTCUSDT_SYMBOL = "BTCUSDT"
        self.BTCUSDT_TIMEFRAME = "15m"
        self.BTCUSDT_STRATEGY = "mirofish_swarm"

        # API Rate Limits
        self.BINANCE_REQUEST_TIMEOUT = int(os.getenv("BINANCE_REQUEST_TIMEOUT", "30"))
        self.MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
        self.RETRY_DELAY = float(os.getenv("RETRY_DELAY", "1.0"))

        # Signal Processing
        self.SIGNAL_VALIDATION_ENABLED = os.getenv("SIGNAL_VALIDATION_ENABLED", "true").lower() == "true"
        self.AUTO_TRADE_ENABLED = os.getenv("AUTO_TRADE_ENABLED", "false").lower() == "true"

        # Security Settings
        self.AUTHORIZED_USERS = self._parse_authorized_users()
        self.ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "")
        self.ADMIN_USER_NAME = os.getenv("ADMIN_USER_NAME", "Trading Bot Admin")

        # Webhook Security
        self.WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

        # Dynamic Leverage Configuration
        self.ENABLE_DYNAMIC_LEVERAGE = os.getenv("ENABLE_DYNAMIC_LEVERAGE", "true").lower() == "true"
        self.MIN_LEVERAGE = int(os.getenv("MIN_LEVERAGE", "2"))
        self.MAX_LEVERAGE = int(os.getenv("MAX_LEVERAGE", "10"))
        self.DEFAULT_LEVERAGE = int(os.getenv("DEFAULT_LEVERAGE", "5"))
        self.CONSERVATIVE_MAX_LEVERAGE = int(os.getenv("CONSERVATIVE_MAX_LEVERAGE", "6"))
        self.AGGRESSIVE_MAX_LEVERAGE = int(os.getenv("AGGRESSIVE_MAX_LEVERAGE", "10"))

        # Futures Trading Configuration
        self.ENABLE_FUTURES_TRADING = os.getenv("ENABLE_FUTURES_TRADING", "true").lower() == "true"
        self.FUTURES_DEFAULT_TYPE = os.getenv("FUTURES_DEFAULT_TYPE", "future")  # 'future' for USDM futures
        self.MAX_PORTFOLIO_LEVERAGE = float(os.getenv("MAX_PORTFOLIO_LEVERAGE", "5.0"))
        
        # Volatility-based Leverage Thresholds
        self.VOLATILITY_THRESHOLD_VERY_LOW = float(os.getenv("VOLATILITY_THRESHOLD_VERY_LOW", "0.5"))
        self.VOLATILITY_THRESHOLD_LOW = float(os.getenv("VOLATILITY_THRESHOLD_LOW", "1.0"))
        self.VOLATILITY_THRESHOLD_MEDIUM = float(os.getenv("VOLATILITY_THRESHOLD_MEDIUM", "2.0"))
        self.VOLATILITY_THRESHOLD_HIGH = float(os.getenv("VOLATILITY_THRESHOLD_HIGH", "3.5"))
        self.VOLATILITY_THRESHOLD_VERY_HIGH = float(os.getenv("VOLATILITY_THRESHOLD_VERY_HIGH", "5.0"))
        
        # Risk Management for Leverage
        self.LEVERAGE_CHANGE_COOLDOWN = int(os.getenv("LEVERAGE_CHANGE_COOLDOWN", "300"))  # 5 minutes
        self.EMERGENCY_VOLATILITY_THRESHOLD = float(os.getenv("EMERGENCY_VOLATILITY_THRESHOLD", "8.0"))
        self.VOLATILITY_LOOKBACK_PERIODS = int(os.getenv("VOLATILITY_LOOKBACK_PERIODS", "100"))

        # OpenAI Configuration
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        self.OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "2048"))
        self.OPENAI_ENABLED = os.getenv("OPENAI_ENABLED", "true").lower() == "true"

        # Centralized Trading Bot Settings (from scattered configs)
        self._load_centralized_settings()
        self._load_external_config()

    def _parse_authorized_users(self) -> list:
        """Parse authorized user IDs from environment variable"""
        users_str = os.getenv("AUTHORIZED_USERS", "")
        if not users_str:
            return []

        try:
            return [int(user_id.strip()) for user_id in users_str.split(",") if user_id.strip()]
        except ValueError:
            return []

    def get_trading_config(self) -> Dict[str, Any]:
        """Get trading configuration as dictionary"""
        return {
            "default_risk_percentage": self.DEFAULT_RISK_PERCENTAGE,
            "capital_base": self.CAPITAL_BASE,
            "max_position_size": self.MAX_POSITION_SIZE,
            "min_position_size": self.MIN_POSITION_SIZE,
            "stop_loss_percentage": self.STOP_LOSS_PERCENTAGE,
            "take_profit_percentage": self.TAKE_PROFIT_PERCENTAGE,
            "supported_pairs": self.SUPPORTED_PAIRS,
            "signal_validation_enabled": self.SIGNAL_VALIDATION_ENABLED,
            "auto_trade_enabled": self.AUTO_TRADE_ENABLED
        }

    def get_leverage_config(self) -> Dict[str, Any]:
        """Get leverage configuration as dictionary"""
        return {
            "enable_dynamic_leverage": self.ENABLE_DYNAMIC_LEVERAGE,
            "min_leverage": self.MIN_LEVERAGE,
            "max_leverage": self.MAX_LEVERAGE,
            "default_leverage": self.DEFAULT_LEVERAGE,
            "conservative_max_leverage": self.CONSERVATIVE_MAX_LEVERAGE,
            "aggressive_max_leverage": self.AGGRESSIVE_MAX_LEVERAGE,
            "enable_futures_trading": self.ENABLE_FUTURES_TRADING,
            "futures_default_type": self.FUTURES_DEFAULT_TYPE,
            "max_portfolio_leverage": self.MAX_PORTFOLIO_LEVERAGE,
            "volatility_thresholds": {
                "very_low": self.VOLATILITY_THRESHOLD_VERY_LOW,
                "low": self.VOLATILITY_THRESHOLD_LOW,
                "medium": self.VOLATILITY_THRESHOLD_MEDIUM,
                "high": self.VOLATILITY_THRESHOLD_HIGH,
                "very_high": self.VOLATILITY_THRESHOLD_VERY_HIGH
            },
            "risk_management": {
                "leverage_change_cooldown": self.LEVERAGE_CHANGE_COOLDOWN,
                "emergency_volatility_threshold": self.EMERGENCY_VOLATILITY_THRESHOLD,
                "volatility_lookback_periods": self.VOLATILITY_LOOKBACK_PERIODS
            }
        }

    def is_authorized_user(self, user_id: int) -> bool:
        """Check if user is authorized to use the bot"""
        if not self.AUTHORIZED_USERS:
            return True  # Allow all users if no restrictions set
        return user_id in self.AUTHORIZED_USERS

    def is_admin_user(self, user_id: int) -> bool:
        """Check if user is an admin"""
        if not self.ADMIN_USER_ID:
            return False
        return str(user_id) == self.ADMIN_USER_ID

    def validate_config(self) -> bool:
        """Validate that all required configuration is present"""
        required_fields = [
            "TELEGRAM_BOT_TOKEN",
            "BINANCE_API_KEY", 
            "BINANCE_API_SECRET"
        ]

        for field in required_fields:
            value = getattr(self, field, None)
            if not value or value == "":
                raise ValueError(f"Required configuration field '{field}' is missing or empty")

        return True

    def _load_centralized_settings(self):
        """Load all centralized trading bot settings from various components"""
        
        # Scalping Bot Settings
        self.TIMEFRAMES = ['1m', '3m', '5m', '15m', '1h', '4h']
        self.TRADING_SYMBOLS = [
            # Top Market Cap
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'SOLUSDT', 'DOGEUSDT',
            # Layer 1 & Major Altcoins
            'AVAXUSDT', 'DOTUSDT', 'MATICUSDT', 'LINKUSDT', 'LTCUSDT', 'BCHUSDT', 'ETCUSDT',
            'ATOMUSDT', 'ALGOUSDT', 'XLMUSDT', 'VETUSDT', 'TRXUSDT', 'EOSUSDT', 'THETAUSDT',
            # DeFi Tokens
            'UNIUSDT', 'AAVEUSDT', 'COMPUSDT', 'MKRUSDT', 'YFIUSDT', 'SUSHIUSDT', 'CAKEUSDT',
            'CRVUSDT', '1INCHUSDT', 'SNXUSDT', 'ALPHAUSDT', 'RAMPUSDT',
            # Additional pairs for maximum coverage
            'NEARUSDT', 'FTMUSDT', 'ONEUSDT', 'ZILUSDT', 'RVNUSDT', 'WAVESUSDT'
        ]
        
        # Signal Processing Settings
        self.MIN_SIGNAL_STRENGTH = float(os.getenv("MIN_SIGNAL_STRENGTH", "75"))
        self.MAX_SIGNALS_PER_HOUR = int(os.getenv("MAX_SIGNALS_PER_HOUR", "6"))
        self.MIN_SIGNAL_INTERVAL = int(os.getenv("MIN_SIGNAL_INTERVAL", "180"))  # seconds
        self.RISK_REWARD_RATIO = float(os.getenv("RISK_REWARD_RATIO", "3.0"))
        self.CAPITAL_ALLOCATION = float(os.getenv("CAPITAL_ALLOCATION", "0.025"))  # 2.5% per trade
        self.MAX_CONCURRENT_TRADES = int(os.getenv("MAX_CONCURRENT_TRADES", "15"))
        
        # Advanced Leverage Configuration (consolidating from trading_bot_config.json)
        self.ADVANCED_LEVERAGE_CONFIG = {
            'min_leverage': int(os.getenv("ADVANCED_MIN_LEVERAGE", "25")),
            'max_leverage': int(os.getenv("ADVANCED_MAX_LEVERAGE", "125")),
            'base_leverage': int(os.getenv("ADVANCED_BASE_LEVERAGE", "50")),
            'leverage_multiplier': float(os.getenv("LEVERAGE_MULTIPLIER", "1.0")),
            'dynamic_leverage_enabled': os.getenv("DYNAMIC_LEVERAGE_ENABLED", "true").lower() == "true",
            'leverage_volatility_adjustment': os.getenv("LEVERAGE_VOLATILITY_ADJUSTMENT", "true").lower() == "true",
            'volatility_threshold_low': float(os.getenv("VOLATILITY_THRESHOLD_LOW_LEVERAGE", "0.01")),
            'volatility_threshold_high': float(os.getenv("VOLATILITY_THRESHOLD_HIGH_LEVERAGE", "0.04")),
            'volume_threshold_low': float(os.getenv("VOLUME_THRESHOLD_LOW", "0.8")),
            'volume_threshold_high': float(os.getenv("VOLUME_THRESHOLD_HIGH", "1.5"))
        }
        
        # Stop Loss and Take Profit Configuration
        self.STOP_LOSS_CONFIG = {
            'sl1_percent': float(os.getenv("SL1_PERCENT", "1.2")),
            'sl2_percent': float(os.getenv("SL2_PERCENT", "2.5")),
            'sl3_percent': float(os.getenv("SL3_PERCENT", "4.0")),
            'tp1_percent': float(os.getenv("TP1_PERCENT", "1.5")),
            'tp2_percent': float(os.getenv("TP2_PERCENT", "3.0")),
            'tp3_percent': float(os.getenv("TP3_PERCENT", "4.5")),
            'move_sl_to_entry_after_tp1': os.getenv("MOVE_SL_TO_ENTRY_AFTER_TP1", "true").lower() == "true",
            'move_sl_to_tp1_after_tp2': os.getenv("MOVE_SL_TO_TP1_AFTER_TP2", "true").lower() == "true",
            'close_after_tp3': os.getenv("CLOSE_AFTER_TP3", "true").lower() == "true"
        }
        
        # ML Configuration (from ml_trade_analyzer and advanced_ml_trading)
        self.ML_CONFIG = {
            'model_dir': os.getenv("ML_MODEL_DIR", "SignalMaestro/ml_models"),
            'db_path': os.getenv("ML_DB_PATH", "SignalMaestro/trade_learning.db"),
            'min_trades_for_learning': int(os.getenv("MIN_TRADES_FOR_LEARNING", "10")),
            'feature_importance_threshold': float(os.getenv("FEATURE_IMPORTANCE_THRESHOLD", "0.01")),
            'retrain_threshold': int(os.getenv("RETRAIN_THRESHOLD", "3")),
            'learning_multiplier': float(os.getenv("LEARNING_MULTIPLIER", "1.5")),
            'accuracy_target': float(os.getenv("ACCURACY_TARGET", "95.0")),
            'min_confidence_for_signal': float(os.getenv("MIN_CONFIDENCE_FOR_SIGNAL", "68.0")),
            'ml_confidence_threshold': float(os.getenv("ML_CONFIDENCE_THRESHOLD", "68.0"))
        }
        
        # Telegram Channel Settings
        self.TARGET_CHANNEL = os.getenv("TARGET_CHANNEL", "@SignalTactics")
        self.CHANNEL_INVITE_LINK = os.getenv("CHANNEL_INVITE_LINK", "https://t.me/+PTfQ9RWEukBlNTNl")
        
        # Performance Metrics Configuration
        self.PERFORMANCE_METRICS = {
            'track_winrate': os.getenv("TRACK_WINRATE", "true").lower() == "true",
            'track_pnl': os.getenv("TRACK_PNL", "true").lower() == "true",
            'track_consecutive_wins': os.getenv("TRACK_CONSECUTIVE_WINS", "true").lower() == "true",
            'track_consecutive_losses': os.getenv("TRACK_CONSECUTIVE_LOSSES", "true").lower() == "true",
            'track_trades_per_hour': os.getenv("TRACK_TRADES_PER_HOUR", "true").lower() == "true",
            'track_max_drawdown': os.getenv("TRACK_MAX_DRAWDOWN", "true").lower() == "true",
            'track_sharpe_ratio': os.getenv("TRACK_SHARPE_RATIO", "true").lower() == "true",
            'real_time_display': os.getenv("REAL_TIME_DISPLAY", "true").lower() == "true"
        }
        
        # Parallel Processing Configuration
        self.PARALLEL_PROCESSING = {
            'enabled': os.getenv("PARALLEL_PROCESSING_ENABLED", "true").lower() == "true",
            'max_workers': int(os.getenv("MAX_WORKERS", "16")),
            'max_async_tasks': int(os.getenv("MAX_ASYNC_TASKS", "50")),
            'signal_processing_parallel': os.getenv("SIGNAL_PROCESSING_PARALLEL", "true").lower() == "true",
            'market_data_parallel': os.getenv("MARKET_DATA_PARALLEL", "true").lower() == "true",
            'indicator_calculation_parallel': os.getenv("INDICATOR_CALCULATION_PARALLEL", "true").lower() == "true",
            'strategy_execution_parallel': os.getenv("STRATEGY_EXECUTION_PARALLEL", "true").lower() == "true"
        }
        
        # Advanced Price Action Configuration
        self.PRICE_ACTION_CONFIG = {
            'threshold': float(os.getenv("ADVANCED_PRICE_ACTION_THRESHOLD", "0.75")),
            'liquidity_zone_sensitivity': float(os.getenv("LIQUIDITY_ZONE_SENSITIVITY", "0.8")),
            'order_flow_confirmation': os.getenv("ORDER_FLOW_CONFIRMATION", "true").lower() == "true",
            'preferred_sessions': [
                "London Session",
                "NY-London Overlap", 
                "Asian Session"
            ],
            'session_risk_multiplier': float(os.getenv("SESSION_RISK_MULTIPLIER", "1.1"))
        }
        
        # AI Orchestrator Configuration
        self.AI_CONFIG = {
            'decision_thresholds': {
                'buy_threshold': float(os.getenv("AI_BUY_THRESHOLD", "0.75")),
                'sell_threshold': float(os.getenv("AI_SELL_THRESHOLD", "0.75")),
                'confidence_threshold': float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.68"))
            },
            'model_weights': {
                'technical_analysis': float(os.getenv("AI_TA_WEIGHT", "0.4")),
                'sentiment_analysis': float(os.getenv("AI_SENTIMENT_WEIGHT", "0.2")),
                'market_structure': float(os.getenv("AI_MARKET_STRUCTURE_WEIGHT", "0.25")),
                'ml_prediction': float(os.getenv("AI_ML_PREDICTION_WEIGHT", "0.15"))
            },
            'risk_parameters': {
                'max_portfolio_risk': float(os.getenv("AI_MAX_PORTFOLIO_RISK", "10.0")),
                'correlation_threshold': float(os.getenv("AI_CORRELATION_THRESHOLD", "0.8")),
                'volatility_adjustment': os.getenv("AI_VOLATILITY_ADJUSTMENT", "true").lower() == "true"
            }
        }

    def _load_external_config(self):
        """Load configuration from external JSON files if they exist"""
        config_files = [
            'trading_bot_config.json',
            'enhanced_optimized_bot_config.json',
            'continuous_operation_config.json'
        ]
        
        for config_file in config_files:
            try:
                if os.path.exists(config_file):
                    with open(config_file, 'r') as f:
                        external_config = json.load(f)
                        self._merge_external_config(external_config)
            except Exception as e:
                # Log warning but don't fail - external config is optional
                pass
    
    def _merge_external_config(self, external_config: Dict[str, Any]):
        """Merge external configuration with existing settings"""
        if 'trading_config' in external_config:
            trading_config = external_config['trading_config']
            # Override with external config values if present
            if 'capital_base' in trading_config:
                self.CAPITAL_BASE = trading_config['capital_base']
            if 'risk_percentage' in trading_config:
                self.DEFAULT_RISK_PERCENTAGE = trading_config['risk_percentage']
            if 'max_concurrent_trades' in trading_config:
                self.MAX_CONCURRENT_TRADES = trading_config['max_concurrent_trades']
            if 'max_leverage' in trading_config:
                self.ADVANCED_LEVERAGE_CONFIG['max_leverage'] = trading_config['max_leverage']
        
        # Merge other sections as needed
        if 'performance_metrics' in external_config:
            self.PERFORMANCE_METRICS.update(external_config['performance_metrics'])
        
        if 'parallel_processing' in external_config:
            self.PARALLEL_PROCESSING.update(external_config['parallel_processing'])
    
    def get_openai_config(self) -> Dict[str, Any]:
        """Get OpenAI configuration"""
        return {
            'api_key': self.OPENAI_API_KEY,
            'model': self.OPENAI_MODEL,
            'max_tokens': self.OPENAI_MAX_TOKENS,
            'enabled': self.OPENAI_ENABLED
        }
    
    def get_trading_signals_config(self) -> Dict[str, Any]:
        """Get trading signals configuration"""
        return {
            'timeframes': self.TIMEFRAMES,
            'symbols': self.TRADING_SYMBOLS,
            'min_signal_strength': self.MIN_SIGNAL_STRENGTH,
            'max_signals_per_hour': self.MAX_SIGNALS_PER_HOUR,
            'min_signal_interval': self.MIN_SIGNAL_INTERVAL,
            'risk_reward_ratio': self.RISK_REWARD_RATIO,
            'capital_allocation': self.CAPITAL_ALLOCATION,
            'max_concurrent_trades': self.MAX_CONCURRENT_TRADES,
            'target_channel': self.TARGET_CHANNEL
        }
    
    def get_ml_config(self) -> Dict[str, Any]:
        """Get ML configuration"""
        return self.ML_CONFIG
    
    def get_advanced_leverage_config(self) -> Dict[str, Any]:
        """Get advanced leverage configuration"""
        return self.ADVANCED_LEVERAGE_CONFIG
    
    def get_stop_loss_config(self) -> Dict[str, Any]:
        """Get stop loss and take profit configuration"""
        return self.STOP_LOSS_CONFIG
    
    def get_ai_config(self) -> Dict[str, Any]:
        """Get AI orchestrator configuration"""
        return self.AI_CONFIG
    
    def get_performance_metrics_config(self) -> Dict[str, Any]:
        """Get performance metrics configuration"""
        return self.PERFORMANCE_METRICS
    
    def get_parallel_processing_config(self) -> Dict[str, Any]:
        """Get parallel processing configuration"""
        return self.PARALLEL_PROCESSING
    
    def get_price_action_config(self) -> Dict[str, Any]:
        """Get price action configuration"""
        return self.PRICE_ACTION_CONFIG
    
    def get_all_config(self) -> Dict[str, Any]:
        """Get complete configuration as dictionary"""
        return {
            'telegram': {
                'bot_token': self.TELEGRAM_BOT_TOKEN,
                'chat_id': self.TELEGRAM_CHAT_ID,
                'target_channel': self.TARGET_CHANNEL,
                'channel_invite_link': self.CHANNEL_INVITE_LINK
            },
            'binance': {
                'api_key': self.BINANCE_API_KEY,
                'api_secret': self.BINANCE_API_SECRET,
                'testnet': self.BINANCE_TESTNET,
                'request_timeout': self.BINANCE_REQUEST_TIMEOUT,
                'max_retries': self.MAX_RETRIES,
                'retry_delay': self.RETRY_DELAY
            },
            'openai': self.get_openai_config(),
            'trading': self.get_trading_config(),
            'trading_signals': self.get_trading_signals_config(),
            'leverage': self.get_leverage_config(),
            'advanced_leverage': self.get_advanced_leverage_config(),
            'stop_loss': self.get_stop_loss_config(),
            'ml': self.get_ml_config(),
            'ai': self.get_ai_config(),
            'performance_metrics': self.get_performance_metrics_config(),
            'parallel_processing': self.get_parallel_processing_config(),
            'price_action': self.get_price_action_config(),
            'cornix': {
                'webhook_url': self.CORNIX_WEBHOOK_URL,
                'bot_uuid': self.CORNIX_BOT_UUID
            },
            'database': {
                'path': self.DATABASE_PATH
            },
            'server': {
                'webhook_host': self.WEBHOOK_HOST,
                'webhook_port': self.WEBHOOK_PORT
            },
            'logging': {
                'level': self.LOG_LEVEL,
                'file': self.LOG_FILE
            },
            'security': {
                'authorized_users': self.AUTHORIZED_USERS,
                'admin_user_id': self.ADMIN_USER_ID,
                'admin_user_name': self.ADMIN_USER_NAME,
                'webhook_secret': self.WEBHOOK_SECRET,
                'session_secret': self.SESSION_SECRET
            }
        }
