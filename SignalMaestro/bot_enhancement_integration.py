#!/usr/bin/env python3
"""
Integration layer to add ML Agent system to existing perfect_scalping_bot.py
Add these imports and initialize in the PerfectScalpingBot class
"""

import json
import asyncio
from ml_agent_signal_analyzer import MultiAgentSignalAnalyzer, EnhancedSignal
from parallel_trade_processor import ParallelTradeProcessor, BatchProcessor, RateLimiter
from dynamic_entry_sl_tp_manager import DynamicSLTPManager, AdaptiveRiskManager

class BotEnhancementIntegration:
    """Integration module for ML and agent-based enhancements"""
    
    def __init__(self, config_path: str = "ml_agent_enhancement_config.json"):
        """Initialize all enhancement modules"""
        self.config = self._load_config(config_path)
        
        # Initialize components
        self.analyzer = MultiAgentSignalAnalyzer()
        self.processor = ParallelTradeProcessor(
            max_concurrent_tasks=self.config['parallel_processing']['max_concurrent_tasks'],
            max_workers=self.config['parallel_processing']['max_worker_threads']
        )
        self.batch_processor = BatchProcessor(
            batch_size=self.config['parallel_processing']['batch_size'],
            batch_timeout=self.config['parallel_processing']['batch_timeout_seconds']
        )
        self.rate_limiter = RateLimiter(
            max_operations_per_second=self.config['parallel_processing']['rate_limit_ops_per_second']
        )
        self.sl_tp_manager = DynamicSLTPManager(
            account_balance=self.config['dynamic_sl_tp']['account_balance'],
            risk_per_trade_pct=self.config['dynamic_sl_tp']['risk_per_trade_percent']
        )
        self.adaptive_risk = AdaptiveRiskManager(
            lookback_trades=self.config['dynamic_sl_tp']['lookback_trades']
        )
    
    @staticmethod
    def _load_config(config_path: str) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Config file {config_path} not found, using defaults")
            return {}
    
    async def enhance_signal_with_ml_and_agents(self, symbol: str, indicators: dict,
                                                current_price: float, atr: float) -> dict:
        """
        Enhanced signal analysis using ML and multi-agent system
        Call this instead of generate_scalping_signal
        """
        
        if not self.config.get('feature_flags', {}).get('use_ml_predictions', True):
            return None
        
        # Get enhanced signal from multi-agent analyzer
        enhanced_signal = await self.analyzer.analyze_signal_parallel(
            symbol, indicators, current_price, atr
        )
        
        if not enhanced_signal:
            return None
        
        # Filter by confidence
        min_confidence = self.config['signal_filtering']['min_confidence_score']
        if enhanced_signal.confidence_score < min_confidence:
            return None
        
        # Get dynamic SL/TP configuration
        position_config = self.sl_tp_manager.calculate_position_config(
            symbol=symbol,
            entry_price=current_price,
            direction=enhanced_signal.direction,
            atr=atr,
            volatility_pct=indicators.get('atr_percent', 1.0),
            rsi=indicators.get('rsi', 50),
            volume_ratio=indicators.get('volume_ratio', 1.0),
            ml_confidence=enhanced_signal.ml_prediction
        )
        
        if not position_config:
            return None
        
        # Build output signal with all enhancements
        signal = {
            'symbol': symbol,
            'direction': enhanced_signal.direction,
            'entry_price': enhanced_signal.entry_price,
            'confidence': enhanced_signal.confidence_score,
            'ml_probability': enhanced_signal.ml_prediction,
            'risk_score': enhanced_signal.risk_score,
            'agent_votes': enhanced_signal.agent_votes,
            'reasoning': enhanced_signal.reasoning,
            'stop_loss': position_config.stop_loss,
            'take_profit_1': position_config.take_profit_1,
            'take_profit_2': position_config.take_profit_2,
            'take_profit_3': position_config.take_profit_3,
            'position_size': position_config.position_size,
            'risk_per_trade': position_config.risk_per_trade,
            'risk_reward_ratio': position_config.risk_reward_ratio,
            'market_condition': position_config.market_condition.value,
            'timestamp': enhanced_signal.timestamp.isoformat(),
            'enhanced': True
        }
        
        return signal
    
    async def process_multiple_signals_parallel(self, signals_with_context: list) -> list:
        """
        Process multiple signals in parallel using the enhanced analyzer
        signals_with_context: list of (symbol, indicators, price, atr) tuples
        """
        tasks = [
            self.enhance_signal_with_ml_and_agents(symbol, indicators, price, atr)
            for symbol, indicators, price, atr in signals_with_context
        ]
        
        results = await self.processor.submit_batch([
            (s[0], 'analyze_signal', tasks[i]) 
            for i, s in enumerate(signals_with_context)
        ])
        
        return [r for r in results if r is not None]
    
    def record_trade_outcome(self, symbol: str, entry: float, exit: float,
                           direction: str, tp_level: int, pnl: float):
        """Record trade outcome for ML learning"""
        # Record in SL/TP manager
        self.sl_tp_manager.record_trade_result(entry, exit, direction, tp_level)
        
        # Record in adaptive risk manager
        risk_taken = abs(entry - exit)  # Simplified
        self.adaptive_risk.add_trade_result(pnl, risk_taken)
        
        # Let ML model learn from this trade
        # Build indicators dict from available data (simplistic)
        indicators = {
            'entry': entry,
            'exit': exit,
            'direction': direction
        }
        won = pnl > 0
        self.analyzer.record_trade_result(symbol, indicators, won)
    
    def get_enhancement_stats(self) -> dict:
        """Get statistics about enhancements"""
        return {
            'parallel_processor_stats': self.processor.get_statistics(),
            'sl_tp_manager_stats': self.sl_tp_manager.get_stats(),
            'active_agents': len(self.analyzer.agent_weights),
            'decision_history_size': sum(len(v) for v in self.analyzer.decision_history.values()),
            'ml_models_trained': len(self.analyzer.ml_model.model_data)
        }
    
    async def shutdown(self):
        """Gracefully shutdown all components"""
        await self.processor.shutdown()
    
    def print_enhancement_info(self):
        """Print information about active enhancements"""
        print("\n" + "="*60)
        print("ML AGENT ENHANCEMENT SYSTEM ACTIVE")
        print("="*60)
        print(f"✓ Multi-Agent Signal Analysis: ENABLED")
        print(f"✓ Parallel Signal Processing: ENABLED")
        print(f"✓ Dynamic SL/TP Configuration: ENABLED")
        print(f"✓ ML-Based Trade Prediction: ENABLED")
        print(f"✓ Adaptive Risk Management: ENABLED")
        print(f"\nActive Agents: {len(self.analyzer.agent_weights)}")
        print(f"Max Concurrent Tasks: {self.processor.max_concurrent_tasks}")
        print(f"Min Signal Confidence: {self.config['signal_filtering']['min_confidence_score']}%")
        print(f"Risk Per Trade: {self.config['dynamic_sl_tp']['risk_per_trade_percent']}%")
        print("="*60 + "\n")

# INTEGRATION GUIDE:
# ==================
# 
# 1. In PerfectScalpingBot.__init__(), add:
#    from bot_enhancement_integration import BotEnhancementIntegration
#    self.enhancement = BotEnhancementIntegration()
#    self.enhancement.print_enhancement_info()
#
# 2. Replace signal generation calls:
#    BEFORE: signal = self.generate_scalping_signal(symbol, indicators, df)
#    AFTER: signal = await self.enhancement.enhance_signal_with_ml_and_agents(
#               symbol, indicators, current_price, atr)
#
# 3. For parallel processing multiple signals:
#    signals = await self.enhancement.process_multiple_signals_parallel(signal_context_list)
#
# 4. Record trade outcomes for ML learning:
#    self.enhancement.record_trade_outcome(symbol, entry, exit, direction, tp_level, pnl)
#
# 5. On shutdown:
#    await self.enhancement.shutdown()
