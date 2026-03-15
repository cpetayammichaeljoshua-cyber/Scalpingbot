"""
AI-Powered Trading Signal System - Main Entry Point

Integrates all components:
- AI Trading Brain (GPT-5 integration for learning)
- AI Position Engine (Dynamic TP/SL/Position calculations)
- Trade Learning Database (Position tracking and outcome analysis)
- Production Signal Bot (Cornix-compatible Telegram signals)
- UT Bot + STC Indicator Strategy

Run with: python main.py
"""

import os
import sys
import asyncio
import logging
import signal as sig
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import pandas as pd
import numpy as np

from ut_bot_strategy.config import Config, load_config
from ut_bot_strategy.data.binance_fetcher import BinanceDataFetcher
from ut_bot_strategy.engine.signal_engine import SignalEngine
from ut_bot_strategy.ai.ai_trading_brain import AITradingBrain
from ut_bot_strategy.trading.ai_position_engine import AIPositionEngine, TradeSetup
from ut_bot_strategy.data.trade_learning_db import TradeLearningDB
from ut_bot_strategy.telegram.production_signal_bot import ProductionSignalBot
from ut_bot_strategy.trading.leverage_calculator import LeverageCalculator
from ut_bot_strategy.trading.futures_executor import FuturesExecutor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('ut_bot_signals.log')
    ]
)
logger = logging.getLogger(__name__)


def print_banner():
    """Print startup banner"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║      AI-POWERED UT BOT + STC TRADING SIGNAL SYSTEM           ║
║                                                              ║
║  Features:                                                    ║
║  - GPT-5 AI Brain for Signal Analysis & Learning             ║
║  - Dynamic TP/SL with Multi-Target Allocations               ║
║  - Intelligent Leverage Optimization (2x-20x)                ║
║  - Cornix-Compatible Telegram Signals                        ║
║  - Trade Outcome Learning & Performance Tracking             ║
║                                                              ║
║  Strategy: UT Bot Alerts + Schaff Trend Cycle                ║
║  Pair: ETH/USDT | Timeframe: 5 minutes                       ║
║                                                              ║
║  Indicator Settings:                                          ║
║  - UT Bot: Key=2, ATR=6, Heikin Ashi=ON                      ║
║  - STC: Length=80, Fast=27, Slow=50                          ║
╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)


class AITradingOrchestrator:
    """
    AI-Powered Trading Orchestrator
    
    Integrates all AI components for intelligent trading:
    - Signal generation with UT Bot + STC strategy
    - AI-enhanced signal analysis and confidence scoring
    - Dynamic position sizing with multi-TP levels
    - Learning from trade outcomes
    - Production-ready Telegram notifications
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the AI Trading Orchestrator
        
        Args:
            config: Configuration object (loads from environment if not provided)
        """
        self.config = config or load_config()
        self.running = False
        self._shutdown_event = asyncio.Event()
        self._last_signal_time: Optional[datetime] = None
        self._signal_count = 0
        self._error_count = 0
        
        self.data_fetcher = BinanceDataFetcher(
            api_key=self.config.binance_api_key,
            api_secret=self.config.binance_api_secret,
            symbol=self.config.trading.symbol,
            interval=self.config.trading.timeframe
        )
        
        self.signal_engine = SignalEngine(
            ut_key_value=self.config.ut_bot.key_value,
            ut_atr_period=self.config.ut_bot.atr_period,
            ut_use_heikin_ashi=self.config.ut_bot.use_heikin_ashi,
            stc_length=self.config.stc.length,
            stc_fast_length=self.config.stc.fast_length,
            stc_slow_length=self.config.stc.slow_length,
            swing_lookback=self.config.trading.swing_lookback,
            risk_reward_ratio=self.config.trading.risk_reward_ratio,
            min_risk_percent=self.config.trading.min_risk_percent,
            max_risk_percent=self.config.trading.max_risk_percent
        )
        
        self.ai_brain = AITradingBrain()
        
        self.position_engine = AIPositionEngine(
            min_leverage=self.config.trading.leverage.min_leverage,
            max_leverage=self.config.trading.leverage.max_leverage,
            base_leverage=self.config.trading.leverage.base_leverage,
            default_risk_percent=self.config.trading.leverage.risk_per_trade_percent,
            max_position_percent=self.config.trading.leverage.max_position_percent
        )
        
        self.trade_db = TradeLearningDB()
        
        self.telegram_bot = ProductionSignalBot(
            bot_token=self.config.telegram_bot_token,
            chat_id=self.config.telegram_chat_id
        )
        
        self.leverage_calculator = LeverageCalculator(
            min_leverage=self.config.trading.leverage.min_leverage,
            max_leverage=self.config.trading.leverage.max_leverage,
            base_leverage=self.config.trading.leverage.base_leverage,
            risk_per_trade_percent=self.config.trading.leverage.risk_per_trade_percent,
            max_position_percent=self.config.trading.leverage.max_position_percent,
            volatility_low_threshold=self.config.trading.leverage.volatility_low_threshold,
            volatility_high_threshold=self.config.trading.leverage.volatility_high_threshold,
            signal_strength_multiplier=self.config.trading.leverage.signal_strength_multiplier
        )
        
        self.futures_executor = FuturesExecutor(
            api_key=self.config.binance_api_key,
            api_secret=self.config.binance_api_secret,
            symbol=self.config.trading.symbol
        )
        
        self.auto_trading_enabled = self.config.trading.leverage.enabled
        self._current_trade_id: Optional[int] = None
        
        logger.info("=" * 60)
        logger.info("AI Trading Orchestrator Initialized")
        logger.info("=" * 60)
        logger.info(f"Symbol: {self.config.trading.symbol}")
        logger.info(f"Timeframe: {self.config.trading.timeframe}")
        logger.info(f"UT Bot: Key={self.config.ut_bot.key_value}, ATR={self.config.ut_bot.atr_period}")
        logger.info(f"STC: Length={self.config.stc.length}, Fast={self.config.stc.fast_length}, Slow={self.config.stc.slow_length}")
        logger.info(f"Leverage Range: {self.config.trading.leverage.min_leverage}x - {self.config.trading.leverage.max_leverage}x")
        logger.info(f"AI Brain: {'Active' if self.ai_brain.ai_available else 'Fallback Mode'}")
        logger.info(f"Auto Trading: {'ENABLED' if self.auto_trading_enabled else 'DISABLED'}")
        logger.info("=" * 60)
    
    async def initialize(self) -> bool:
        """Initialize all async components"""
        try:
            await self.ai_brain.initialize()
            await self.trade_db.initialize()
            
            # Send welcome message to Telegram channel
            await self.telegram_bot.send_welcome_message()
            
            # Send comprehensive startup test message
            await self.telegram_bot.send_startup_test_message()
            
            logger.info("All components initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            return False
    
    def _can_send_signal(self) -> bool:
        """Check if we can send a new signal (respecting cooldown)"""
        if self._last_signal_time is None:
            return True
        
        cooldown = timedelta(minutes=self.config.bot.signal_cooldown_minutes)
        return datetime.now() - self._last_signal_time > cooldown
    
    def _calculate_true_atr(self, df, period: int = 14) -> float:
        """
        Calculate true Average True Range using Wilder's method
        
        Args:
            df: DataFrame with high, low, close columns
            period: ATR period (default 14)
            
        Returns:
            ATR value as float
        """
        try:
            high = df['high']
            low = df['low']
            close = df['close']
            
            high_low = high - low
            high_close = np.abs(high - close.shift(1))
            low_close = np.abs(low - close.shift(1))
            
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = true_range.rolling(window=period).mean().iloc[-1]
            
            if pd.isna(atr) or atr <= 0:
                atr = true_range.iloc[-period:].mean()
            
            return float(atr) if not pd.isna(atr) else float(high.iloc[-1] - low.iloc[-1])
            
        except Exception as e:
            logger.warning(f"Error calculating ATR: {e}")
            return float(df['high'].iloc[-1] - df['low'].iloc[-1])
    
    def _calculate_volatility_score(self, atr_percent: float) -> float:
        """
        Calculate normalized volatility score (0-1, where 1 is low volatility/safer)
        
        Args:
            atr_percent: ATR as percentage of price
            
        Returns:
            Volatility score between 0 and 1
        """
        min_atr_pct = 0.3
        max_atr_pct = 3.0
        
        clamped_atr = max(min_atr_pct, min(max_atr_pct, atr_percent))
        
        volatility_score = 1.0 - ((clamped_atr - min_atr_pct) / (max_atr_pct - min_atr_pct))
        
        return max(0.0, min(1.0, volatility_score))
    
    def _detect_market_structure(self, df, atr_percent: float) -> str:
        """
        Detect market structure from price action
        
        Args:
            df: DataFrame with OHLCV data
            atr_percent: ATR as percentage of price
            
        Returns:
            Market structure: 'trending', 'ranging', 'volatile', 'breakout', 'consolidation'
        """
        try:
            lookback = min(50, len(df) - 1)
            if lookback < 10:
                return 'ranging'
            
            close = df['close'].iloc[-lookback:]
            high = df['high'].iloc[-lookback:]
            low = df['low'].iloc[-lookback:]
            
            x = np.arange(len(close))
            slope = np.polyfit(x, close.values, 1)[0]
            price_range = close.max() - close.min()
            normalized_slope = slope / (price_range / len(close)) if price_range > 0 else 0
            
            recent_range = (high.iloc[-10:].max() - low.iloc[-10:].min()) / close.iloc[-1] * 100
            historical_range = (high.iloc[-30:-10].max() - low.iloc[-30:-10].min()) / close.iloc[-20] * 100 if len(close) >= 30 else recent_range
            
            if atr_percent > 2.0:
                return 'volatile'
            
            if recent_range > historical_range * 1.5:
                return 'breakout'
            
            if abs(normalized_slope) > 0.5:
                return 'trending'
            
            if atr_percent < 0.5 and recent_range < historical_range * 0.7:
                return 'consolidation'
            
            return 'ranging'
            
        except Exception as e:
            logger.warning(f"Error detecting market structure: {e}")
            return 'ranging'
    
    async def _enhance_signal_with_ai(
        self,
        signal: Dict[str, Any],
        df
    ) -> Dict[str, Any]:
        """
        Enhance signal with AI analysis and position calculations
        
        Args:
            signal: Raw signal from signal engine
            df: DataFrame with market data
            
        Returns:
            Enhanced signal with AI insights and trade setup
        """
        try:
            entry_price = signal.get('entry_price', 0)
            
            if 'atr' in df.columns and not df['atr'].isna().all():
                atr = float(df['atr'].iloc[-1])
                if pd.isna(atr) or atr <= 0:
                    atr = self._calculate_true_atr(df, period=14)
            else:
                atr = self._calculate_true_atr(df, period=14)
            
            atr_percent = (atr / entry_price) * 100 if entry_price > 0 else 1.0
            volatility_score = self._calculate_volatility_score(atr_percent)
            
            market_structure = self._detect_market_structure(df, atr_percent)
            
            signal['atr'] = atr
            signal['atr_percent'] = atr_percent
            signal['volatility_score'] = volatility_score
            signal['market_structure'] = market_structure
            
            ai_analysis = await self.ai_brain.analyze_signal({
                'symbol': signal.get('symbol', self.config.trading.symbol),
                'direction': signal.get('type', 'LONG'),
                'entry_price': entry_price,
                'stop_loss': signal.get('stop_loss', 0),
                'take_profit': signal.get('take_profit', 0),
                'indicators': {
                    'stc_value': signal.get('stc_value', 0),
                    'stc_valid': True,
                    'ut_bot_confirmed': True,
                    'atr': atr
                },
                'timeframe': signal.get('timeframe', '5m')
            })
            
            signal['ai_analysis'] = ai_analysis
            signal['ai_confidence'] = ai_analysis.get('confidence', 0.5)
            signal['ai_recommendation'] = ai_analysis.get('recommendation', 'EXECUTE')
            
            market_data = {
                'atr': atr,
                'atr_percent': atr_percent,
                'volatility_score': volatility_score,
                'market_structure': market_structure
            }
            
            account_balance = 1000.0
            if self.auto_trading_enabled:
                try:
                    balance = await self.futures_executor.get_account_balance()
                    account_balance = balance.get('free', 1000.0)
                except Exception:
                    pass
            
            enhanced_signal = {
                'direction': signal.get('type', 'LONG'),
                'entry_price': entry_price,
                'stop_loss': signal.get('stop_loss', 0),
                'take_profit': signal.get('take_profit', 0),
                'confidence': ai_analysis.get('confidence', 0.7),
                'signal_strength': signal.get('signal_strength', ai_analysis.get('confidence', 0.7)),
                'ai_adjustment': ai_analysis.get('confidence_adjustment', 0),
                'risk_reward_ratios': [1.0, 2.0, 3.0],
                'risk_percent': self.config.trading.leverage.risk_per_trade_percent
            }
            
            trade_setup: TradeSetup = self.position_engine.get_complete_trade_setup(
                signal=enhanced_signal,
                account_balance=account_balance,
                market_data=market_data
            )
            
            signal['trade_setup'] = {
                'entry_price': trade_setup.entry_price,
                'stop_loss': trade_setup.stop_loss,
                'tp1': trade_setup.tp1.price,
                'tp2': trade_setup.tp2.price,
                'tp3': trade_setup.tp3.price,
                'tp1_allocation': trade_setup.tp1.allocation_percent,
                'tp2_allocation': trade_setup.tp2.allocation_percent,
                'tp3_allocation': trade_setup.tp3.allocation_percent,
                'leverage': trade_setup.leverage,
                'position_size': trade_setup.position_size,
                'margin_required': trade_setup.margin_required,
                'risk_amount': trade_setup.risk_amount,
                'risk_reward': trade_setup.total_risk_reward,
                'confidence_score': trade_setup.confidence_score
            }
            
            logger.info(
                f"Signal enhanced with AI: confidence={ai_analysis.get('confidence', 0):.2f}, "
                f"recommendation={ai_analysis.get('recommendation', 'N/A')}, "
                f"leverage={trade_setup.leverage}x"
            )
            
            return signal
            
        except Exception as e:
            logger.error(f"Error enhancing signal with AI: {e}")
            return signal
    
    async def _record_trade_entry(self, signal: Dict[str, Any]) -> Optional[int]:
        """Record trade entry to database"""
        try:
            trade_setup = signal.get('trade_setup', {})
            ai_analysis = signal.get('ai_analysis', {})
            
            trade_data = {
                'symbol': signal.get('symbol', self.config.trading.symbol),
                'direction': signal.get('type', 'LONG'),
                'entry_price': trade_setup.get('entry_price', signal.get('entry_price', 0)),
                'stop_loss': trade_setup.get('stop_loss', signal.get('stop_loss', 0)),
                'take_profit_1': trade_setup.get('tp1', signal.get('take_profit', 0)),
                'take_profit_2': trade_setup.get('tp2', 0),
                'take_profit_3': trade_setup.get('tp3', 0),
                'leverage': trade_setup.get('leverage', 1),
                'position_size': trade_setup.get('position_size', 0),
                'margin_used': trade_setup.get('margin_required', 0),
                'signal_confidence': signal.get('ai_confidence', 0),
                'ai_confidence': ai_analysis.get('confidence', 0),
                'signal_strength': signal.get('signal_strength', 0),
                'ut_bot_signal': signal.get('type', ''),
                'stc_value': signal.get('stc_value', 0),
                'stc_color': signal.get('stc_color', ''),
                'atr_value': signal.get('atr', 0),
                'volatility_score': signal.get('volatility_score', 0),
                'entry_time': datetime.now().isoformat()
            }
            
            trade_id = await self.trade_db.record_trade_entry(trade_data)
            
            if ai_analysis:
                await self.trade_db.record_ai_learning(trade_id, {
                    'ai_analysis': ai_analysis,
                    'ai_recommendations': ai_analysis.get('suggested_adjustments', {}),
                    'learning_insights': ai_analysis.get('analysis', ''),
                    'parameter_adjustments': {}
                })
            
            logger.info(f"Trade entry recorded: ID={trade_id}")
            return trade_id
            
        except Exception as e:
            logger.error(f"Error recording trade entry: {e}")
            return None
    
    async def _send_telegram_signal(self, signal: Dict[str, Any]) -> bool:
        """Send signal via production Telegram bot"""
        try:
            trade_setup = signal.get('trade_setup', {})
            ai_analysis = signal.get('ai_analysis', {})
            
            signal_data = {
                'symbol': signal.get('symbol', self.config.trading.symbol),
                'direction': signal.get('type', 'LONG'),
                'entry_price': trade_setup.get('entry_price', signal.get('entry_price', 0)),
                'stop_loss': trade_setup.get('stop_loss', signal.get('stop_loss', 0)),
                'tp1': trade_setup.get('tp1', signal.get('take_profit', 0)),
                'tp2': trade_setup.get('tp2', 0),
                'tp3': trade_setup.get('tp3', 0)
            }
            
            setup_data = {
                'leverage': trade_setup.get('leverage', 10),
                'margin_type': 'CROSS',
                'position_size': trade_setup.get('position_size', 0),
                'tp1_allocation': trade_setup.get('tp1_allocation', 40),
                'tp2_allocation': trade_setup.get('tp2_allocation', 35),
                'tp3_allocation': trade_setup.get('tp3_allocation', 25)
            }
            
            ai_data = {
                'confidence': ai_analysis.get('confidence', 0),
                'signal_strength': int(ai_analysis.get('confidence', 0) * 100),
                'market_sentiment': ai_analysis.get('risk_assessment', {}).get('level', 'neutral'),
                'risk_level': ai_analysis.get('risk_assessment', {}).get('level', 'medium')
            }
            
            result = await self.telegram_bot.send_signal(signal_data, setup_data, ai_data)
            
            if result.get('success'):
                logger.info(f"Signal sent to Telegram: {result.get('signal_id')}")
                return True
            else:
                logger.error(f"Failed to send signal: {result.get('error')}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Telegram signal: {e}")
            return False
    
    async def fetch_and_process(self) -> tuple:
        """
        Fetch data and process for signals
        
        Returns:
            Tuple of (signal, dataframe) if valid signal found, (None, None) otherwise
        """
        try:
            df = self.data_fetcher.fetch_historical_data(
                limit=max(200, self.config.trading.min_candles_required + 50)
            )
            
            if df is None or len(df) < self.config.trading.min_candles_required:
                logger.warning(f"Insufficient data: {len(df) if df is not None else 0} candles")
                return None, None
            
            logger.debug(f"Fetched {len(df)} candles, latest: {df.index[-1]}")
            
            signal = self.signal_engine.generate_signal(df)
            
            if signal and self._can_send_signal():
                signal = await self._enhance_signal_with_ai(signal, df)
                
                ai_recommendation = signal.get('ai_recommendation', 'EXECUTE')
                ai_confidence = signal.get('ai_confidence', 0)
                
                if ai_recommendation == 'SKIP' and ai_confidence < 0.4:
                    logger.info(f"Signal skipped due to low AI confidence: {ai_confidence:.2f}")
                    return None, df
                
                logger.info(f"Valid {signal['type']} signal generated with AI confidence: {ai_confidence:.2f}")
                return signal, df
            elif signal:
                logger.info(f"Signal generated but in cooldown period")
            
            return None, df
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Error in fetch_and_process: {e}")
            return None, None
    
    async def process_signal(self, signal: Dict[str, Any], df=None) -> bool:
        """
        Process and send a trading signal
        
        Args:
            signal: Enhanced signal dictionary
            df: DataFrame for trade execution (optional)
            
        Returns:
            True if signal was processed successfully
        """
        try:
            self._current_trade_id = await self._record_trade_entry(signal)
            
            success = await self._send_telegram_signal(signal)
            
            if success:
                self._last_signal_time = datetime.now()
                self._signal_count += 1
                self._error_count = 0
                logger.info(f"Signal processed successfully. Total signals: {self._signal_count}")
            else:
                logger.error("Failed to send signal to Telegram")
            
            return success
            
        except Exception as e:
            logger.error(f"Error processing signal: {e}")
            return False
    
    async def run_cycle(self):
        """Run a single monitoring cycle"""
        signal, df = await self.fetch_and_process()
        
        if signal:
            await self.process_signal(signal, df)
    
    async def run(self):
        """
        Main monitoring loop
        
        Continuously monitors the market and sends signals
        """
        if not self.config.validate():
            logger.error("Invalid configuration. Cannot start bot.")
            return
        
        if not await self.initialize():
            logger.error("Failed to initialize components. Cannot start bot.")
            return
        
        self.running = True
        logger.info("=" * 60)
        logger.info("AI Trading Signal Bot Started")
        logger.info("=" * 60)
        
        try:
            while self.running and not self._shutdown_event.is_set():
                try:
                    await self.run_cycle()
                except Exception as e:
                    logger.error(f"Error in monitoring cycle: {e}")
                    self._error_count += 1
                
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.config.bot.check_interval_seconds
                    )
                except asyncio.TimeoutError:
                    pass
                
        except asyncio.CancelledError:
            logger.info("Bot cancelled")
        except Exception as e:
            logger.error(f"Fatal error in run loop: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self, reason: str = "Manual shutdown") -> None:
        """
        Gracefully shutdown the bot
        
        Args:
            reason: Shutdown reason for logging
        """
        logger.info(f"Shutting down: {reason}")
        self.running = False
        self._shutdown_event.set()
        
        try:
            await self.telegram_bot.close()
        except Exception as e:
            logger.warning(f"Error closing telegram bot: {e}")
        
        try:
            await self.futures_executor.close()
        except Exception as e:
            logger.warning(f"Error closing futures executor: {e}")
        
        try:
            await self.data_fetcher.close()
        except Exception as e:
            logger.warning(f"Error closing data fetcher: {e}")
        
        await asyncio.sleep(0.5)
        logger.info("Bot shutdown complete")
    
    def stop(self):
        """Signal the bot to stop"""
        self._shutdown_event.set()
        self.running = False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current bot status"""
        return {
            'running': self.running,
            'signal_count': self._signal_count,
            'error_count': self._error_count,
            'last_signal_time': self._last_signal_time,
            'ai_brain_active': self.ai_brain.ai_available,
            'rate_limit_status': self.telegram_bot.get_rate_limit_status(),
            'performance_stats': self.telegram_bot.get_performance_stats()
        }


def setup_signal_handlers(orchestrator: AITradingOrchestrator):
    """Setup system signal handlers for graceful shutdown"""
    def handle_shutdown(signum, frame):
        logger.info(f"Received signal {signum}")
        orchestrator.stop()
    
    sig.signal(sig.SIGINT, handle_shutdown)
    sig.signal(sig.SIGTERM, handle_shutdown)


async def run_bot():
    """Run the trading bot"""
    print_banner()
    
    logger.info("Loading configuration...")
    config = load_config()
    
    if not config.validate():
        logger.error("Configuration validation failed!")
        logger.error("Please ensure all required environment variables are set:")
        logger.error("  - BINANCE_API_KEY")
        logger.error("  - BINANCE_API_SECRET")
        logger.error("  - TELEGRAM_BOT_TOKEN")
        logger.error("  - TELEGRAM_CHAT_ID")
        sys.exit(1)
    
    logger.info("Configuration loaded successfully")
    
    orchestrator = AITradingOrchestrator(config)
    setup_signal_handlers(orchestrator)
    
    try:
        await orchestrator.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        if orchestrator.running:
            await orchestrator.shutdown("Application exit")


def main():
    """Main entry point"""
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
