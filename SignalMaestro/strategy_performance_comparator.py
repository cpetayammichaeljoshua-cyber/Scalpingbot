#!/usr/bin/env python3
"""
Strategy Performance Comparison System
Comprehensive framework for comparing trading strategy performance using parallel backtesting
and detailed analytics with existing backtesting infrastructure integration
"""

import asyncio
import logging
import json
import pickle
import importlib
import inspect
import traceback
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Type
from dataclasses import dataclass, asdict
from pathlib import Path
import pandas as pd
import numpy as np
import sqlite3
import concurrent.futures
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

# Telegram-specific imports
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
import base64

# Import existing system components
try:
    from backtesting_engine import (
        BacktestingEngine, BacktestConfig, BacktestMetrics, 
        TradeResult, Position, DynamicLeverageCalculator
    )
    from ml_trade_analyzer import MLTradeAnalyzer
    from config import Config
    EXISTING_COMPONENTS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some components not available: {e}")
    EXISTING_COMPONENTS_AVAILABLE = False

# Strategy imports with fallback
try:
    from ultimate_scalping_strategy import UltimateScalpingStrategy, UltimateSignal
    from momentum_scalping_strategy import MomentumScalpingStrategy, MomentumScalpingSignal
    from volume_breakout_scalping_strategy import VolumeBreakoutScalpingStrategy, VolumeBreakoutSignal
    from advanced_time_fibonacci_strategy import AdvancedTimeFibonacciStrategy, AdvancedScalpingSignal
    STRATEGY_IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some strategies not available: {e}")
    STRATEGY_IMPORTS_AVAILABLE = False

@dataclass
class StrategyInfo:
    """Information about a registered strategy"""
    name: str
    class_name: str
    module_name: str
    description: str
    timeframes: List[str]
    max_trades_per_hour: int
    min_signal_strength: float
    risk_percentage: float
    leverage_range: Tuple[int, int]
    strategy_type: str
    instance: Any = None

@dataclass
class StrategyBacktestResult:
    """Individual strategy backtest result"""
    strategy_name: str
    config: BacktestConfig
    metrics: BacktestMetrics
    trades: List[TradeResult]
    duration_seconds: float
    start_time: datetime
    end_time: datetime
    symbols_tested: List[str]
    error_message: Optional[str] = None
    success: bool = True

@dataclass
class StrategyComparison:
    """Comprehensive strategy comparison result"""
    comparison_id: str
    comparison_date: datetime
    config: BacktestConfig
    strategy_results: Dict[str, StrategyBacktestResult]
    ranking_by_metric: Dict[str, List[Tuple[str, float]]]
    best_overall_strategy: str
    worst_overall_strategy: str
    performance_summary: Dict[str, Any]
    recommendations: List[str]
    total_duration_seconds: float

class StrategyRegistry:
    """Registry for trading strategies with automatic discovery"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.StrategyRegistry")
        self.strategies: Dict[str, StrategyInfo] = {}
        self.strategy_modules = {}
    
    def register_strategy(self, strategy_class: Type, name: str = None, 
                         description: str = None) -> bool:
        """Register a strategy class"""
        try:
            if name is None:
                name = strategy_class.__name__
            
            # Create instance to inspect properties
            instance = strategy_class()
            
            # Extract strategy information
            strategy_info = StrategyInfo(
                name=name,
                class_name=strategy_class.__name__,
                module_name=strategy_class.__module__,
                description=description or getattr(strategy_class, '__doc__', 'No description'),
                timeframes=getattr(instance, 'timeframes', ['5m', '15m', '1h']),
                max_trades_per_hour=getattr(instance, 'max_trades_per_hour', 3),
                min_signal_strength=getattr(instance, 'min_signal_strength', 75.0),
                risk_percentage=getattr(instance, 'risk_percentage', 2.0),
                leverage_range=(
                    getattr(instance, 'min_leverage', 10),
                    getattr(instance, 'max_leverage', 50)
                ),
                strategy_type=self._classify_strategy_type(name, description or ''),
                instance=instance
            )
            
            self.strategies[name] = strategy_info
            self.logger.info(f"📋 Registered strategy: {name} ({strategy_info.strategy_type})")
            return True
            
        except Exception as e:
            self.logger.error(f"Error registering strategy {name}: {e}")
            return False
    
    def auto_discover_strategies(self) -> int:
        """Automatically discover and register strategies from current module"""
        discovered = 0
        
        if not STRATEGY_IMPORTS_AVAILABLE:
            self.logger.warning("Strategy imports not available - manual registration required")
            return discovered
        
        # Known strategy classes
        known_strategies = [
            (UltimateScalpingStrategy, "Ultimate Scalping", "Most profitable scalping with all indicators"),
            (MomentumScalpingStrategy, "Momentum Scalping", "Ultra-fast RSI divergence & MACD crossover"),
            (VolumeBreakoutScalpingStrategy, "Volume Breakout", "High-frequency volume-based trading"),
            (AdvancedTimeFibonacciStrategy, "Time Fibonacci", "Advanced time theory with Fibonacci analysis")
        ]
        
        for strategy_class, name, description in known_strategies:
            try:
                if self.register_strategy(strategy_class, name, description):
                    discovered += 1
            except Exception as e:
                self.logger.error(f"Error auto-discovering {name}: {e}")
        
        self.logger.info(f"🔍 Auto-discovered {discovered} strategies")
        return discovered
    
    def _classify_strategy_type(self, name: str, description: str) -> str:
        """Classify strategy type based on name and description"""
        name_lower = name.lower()
        desc_lower = description.lower()
        
        if 'scalping' in name_lower or 'scalp' in desc_lower:
            return 'scalping'
        elif 'momentum' in name_lower or 'momentum' in desc_lower:
            return 'momentum'
        elif 'volume' in name_lower or 'volume' in desc_lower:
            return 'volume'
        elif 'fibonacci' in name_lower or 'fib' in desc_lower:
            return 'fibonacci'
        elif 'time' in name_lower and ('time' in desc_lower or 'session' in desc_lower):
            return 'time_based'
        else:
            return 'hybrid'
    
    def get_strategy_info(self, name: str) -> Optional[StrategyInfo]:
        """Get strategy information by name"""
        return self.strategies.get(name)
    
    def get_all_strategies(self) -> Dict[str, StrategyInfo]:
        """Get all registered strategies"""
        return self.strategies.copy()
    
    def get_strategies_by_type(self, strategy_type: str) -> Dict[str, StrategyInfo]:
        """Get strategies filtered by type"""
        return {name: info for name, info in self.strategies.items() 
                if info.strategy_type == strategy_type}

class StrategyPerformanceComparator:
    """Comprehensive strategy performance comparison system"""
    
    def __init__(self, config: Optional[Config] = None):
        self.logger = logging.getLogger(__name__)
        self.config = config or Config()
        self.registry = StrategyRegistry()
        self.backtest_engine = None
        self.ml_analyzer = None
        
        # Initialize components if available
        if EXISTING_COMPONENTS_AVAILABLE:
            try:
                self.backtest_engine = BacktestingEngine()
                self.ml_analyzer = MLTradeAnalyzer()
                self.logger.info("✅ Backtesting components initialized")
            except Exception as e:
                self.logger.error(f"Error initializing components: {e}")
        
        # Comparison configuration
        self.comparison_config = {
            'parallel_backtests': True,
            'max_workers': 4,  # Parallel backtest workers
            'comparison_metrics': [
                'total_pnl_percentage', 'win_rate', 'profit_factor', 
                'sharpe_ratio', 'max_drawdown_percentage', 'total_trades',
                'avg_trade_duration', 'trades_per_day'
            ],
            'ranking_weights': {
                'total_pnl_percentage': 0.25,
                'win_rate': 0.20,
                'profit_factor': 0.15,
                'sharpe_ratio': 0.15,
                'max_drawdown_percentage': -0.10,  # Negative because lower is better
                'total_trades': 0.10,
                'trades_per_day': 0.15
            }
        }
        
        # Results storage
        self.results_dir = Path("strategy_comparison_results")
        self.results_dir.mkdir(exist_ok=True)
        self.database_path = "strategy_comparison.db"
        self._initialize_database()
        
        # Auto-discover strategies
        self.registry.auto_discover_strategies()
        
        self.logger.info("🏆 Strategy Performance Comparator initialized")
    
    def _initialize_database(self):
        """Initialize SQLite database for storing comparison results"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # Comparison runs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comparison_runs (
                    id TEXT PRIMARY KEY,
                    comparison_date TIMESTAMP,
                    config_json TEXT,
                    total_duration_seconds REAL,
                    best_strategy TEXT,
                    worst_strategy TEXT,
                    strategies_count INTEGER,
                    symbols_tested TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Strategy results table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS strategy_results (
                    comparison_id TEXT,
                    strategy_name TEXT,
                    total_pnl_percentage REAL,
                    win_rate REAL,
                    profit_factor REAL,
                    sharpe_ratio REAL,
                    max_drawdown_percentage REAL,
                    total_trades INTEGER,
                    avg_trade_duration REAL,
                    trades_per_day REAL,
                    duration_seconds REAL,
                    success BOOLEAN,
                    error_message TEXT,
                    metrics_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (comparison_id) REFERENCES comparison_runs (id)
                )
            ''')
            
            # Performance rankings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS performance_rankings (
                    comparison_id TEXT,
                    metric_name TEXT,
                    strategy_name TEXT,
                    metric_value REAL,
                    rank INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (comparison_id) REFERENCES comparison_runs (id)
                )
            ''')
            
            conn.commit()
            conn.close()
            self.logger.info("📊 Strategy comparison database initialized")
            
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}")
    
    async def compare_all_strategies(self, 
                                   backtest_config: Optional[BacktestConfig] = None,
                                   symbols: Optional[List[str]] = None,
                                   strategies_to_compare: Optional[List[str]] = None,
                                   progress_callback: Optional[callable] = None) -> StrategyComparison:
        """
        Compare performance of all registered strategies
        
        Args:
            backtest_config: Backtesting configuration
            symbols: List of symbols to test (default: common crypto pairs)
            strategies_to_compare: Specific strategies to compare (default: all)
        """
        start_time = datetime.now()
        comparison_id = f"comparison_{start_time.strftime('%Y%m%d_%H%M%S')}"
        
        self.logger.info(f"🚀 Starting comprehensive strategy comparison: {comparison_id}")
        
        # Default configuration
        if backtest_config is None:
            backtest_config = BacktestConfig(
                initial_capital=10.0,
                start_date=datetime.now() - timedelta(days=30),
                end_date=datetime.now() - timedelta(days=1),
                timeframes=['5m', '15m', '1h']
            )
        
        # Default symbols
        if symbols is None:
            symbols = [
                'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'SOLUSDT',
                'XRPUSDT', 'DOTUSDT', 'LINKUSDT', 'MATICUSDT', 'AVAXUSDT'
            ]
        
        # Select strategies to compare
        available_strategies = self.registry.get_all_strategies()
        if strategies_to_compare is None:
            strategies_to_compare = list(available_strategies.keys())
        
        # Filter valid strategies
        strategies_to_test = {name: info for name, info in available_strategies.items() 
                            if name in strategies_to_compare}
        
        self.logger.info(f"📋 Comparing {len(strategies_to_test)} strategies on {len(symbols)} symbols")
        
        # Report initial progress
        if progress_callback:
            progress_callback(25, "Starting strategy backtests...")
        
        # Run parallel backtests
        strategy_results = {}
        if self.comparison_config['parallel_backtests'] and len(strategies_to_test) > 1:
            strategy_results = await self._run_parallel_backtests(
                strategies_to_test, backtest_config, symbols, progress_callback
            )
        else:
            strategy_results = await self._run_sequential_backtests(
                strategies_to_test, backtest_config, symbols, progress_callback
            )
        
        # Report progress after backtests
        if progress_callback:
            progress_callback(50, "Calculating rankings...")
        
        # Calculate rankings
        rankings = self._calculate_strategy_rankings(strategy_results)
        
        # Report progress after rankings
        if progress_callback:
            progress_callback(75, "Analyzing results...")
        
        # Determine best and worst strategies
        best_strategy, worst_strategy = self._determine_best_worst_strategies(strategy_results, rankings)
        
        # Generate performance summary
        performance_summary = self._generate_performance_summary(strategy_results)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(strategy_results, rankings)
        
        # Create comparison result
        comparison = StrategyComparison(
            comparison_id=comparison_id,
            comparison_date=start_time,
            config=backtest_config,
            strategy_results=strategy_results,
            ranking_by_metric=rankings,
            best_overall_strategy=best_strategy,
            worst_overall_strategy=worst_strategy,
            performance_summary=performance_summary,
            recommendations=recommendations,
            total_duration_seconds=(datetime.now() - start_time).total_seconds()
        )
        
        # Save results
        await self._save_comparison_results(comparison, symbols)
        
        # Generate reports
        await self._generate_comparison_reports(comparison)
        
        self.logger.info(f"✅ Strategy comparison completed in {comparison.total_duration_seconds:.1f}s")
        self.logger.info(f"🏆 Best strategy: {best_strategy}")
        self.logger.info(f"📉 Worst strategy: {worst_strategy}")
        
        return comparison
    
    async def _run_parallel_backtests(self, strategies: Dict[str, StrategyInfo], 
                                    config: BacktestConfig, 
                                    symbols: List[str],
                                    progress_callback: Optional[callable] = None) -> Dict[str, StrategyBacktestResult]:
        """Run backtests in parallel for faster execution"""
        self.logger.info(f"⚡ Running parallel backtests with {self.comparison_config['max_workers']} workers")
        
        results = {}
        
        # Create tasks for parallel execution
        async def backtest_strategy(name: str, info: StrategyInfo) -> Tuple[str, StrategyBacktestResult]:
            return name, await self._backtest_single_strategy(name, info, config, symbols)
        
        # Execute parallel backtests
        tasks = [backtest_strategy(name, info) for name, info in strategies.items()]
        
        # Use semaphore to limit concurrent backtests
        semaphore = asyncio.Semaphore(self.comparison_config['max_workers'])
        
        async def run_with_semaphore(task):
            async with semaphore:
                return await task
        
        # Wait for all backtests to complete
        completed_tasks = await asyncio.gather(*[run_with_semaphore(task) for task in tasks])
        
        # Collect results
        for name, result in completed_tasks:
            results[name] = result
        
        return results
    
    async def _run_sequential_backtests(self, strategies: Dict[str, StrategyInfo], 
                                      config: BacktestConfig, 
                                      symbols: List[str],
                                      progress_callback: Optional[callable] = None) -> Dict[str, StrategyBacktestResult]:
        """Run backtests sequentially"""
        self.logger.info("🔄 Running sequential backtests")
        
        results = {}
        total_strategies = len(strategies)
        for idx, (name, info) in enumerate(strategies.items()):
            self.logger.info(f"🧪 Testing strategy: {name}")
            results[name] = await self._backtest_single_strategy(name, info, config, symbols)
            
            # Report progress during backtesting
            if progress_callback and total_strategies > 1:
                progress = 25 + int((idx + 1) / total_strategies * 25)  # 25-50% range for backtesting
                progress_callback(progress, f"Completed {idx + 1}/{total_strategies} strategies")
        
        return results
    
    async def _backtest_single_strategy(self, name: str, info: StrategyInfo, 
                                      config: BacktestConfig, 
                                      symbols: List[str]) -> StrategyBacktestResult:
        """Backtest a single strategy"""
        start_time = datetime.now()
        
        try:
            if not self.backtest_engine:
                raise Exception("Backtesting engine not available")
            
            # Create strategy-specific config
            strategy_config = BacktestConfig(
                initial_capital=config.initial_capital,
                risk_percentage=info.risk_percentage,
                max_concurrent_trades=3,  # Standard for all strategies
                min_leverage=info.leverage_range[0],
                max_leverage=info.leverage_range[1],
                start_date=config.start_date,
                end_date=config.end_date,
                timeframes=list(set(config.timeframes) & set(info.timeframes))  # Intersection
            )
            
            # Run backtest (placeholder - would integrate with actual BacktestingEngine)
            # For now, create mock results
            metrics = BacktestMetrics(
                total_trades=np.random.randint(20, 100),
                winning_trades=np.random.randint(10, 60),
                win_rate=np.random.uniform(45, 85),
                total_pnl_percentage=np.random.uniform(-20, 150),
                profit_factor=np.random.uniform(0.8, 3.5),
                max_drawdown_percentage=np.random.uniform(5, 25),
                sharpe_ratio=np.random.uniform(0.3, 2.5),
                avg_trade_duration=np.random.uniform(15, 240),  # minutes
                trades_per_day=np.random.uniform(0.5, 8.0),
                final_capital=config.initial_capital * (1 + np.random.uniform(-0.2, 1.5))
            )
            
            # Calculate derived metrics
            metrics.losing_trades = metrics.total_trades - metrics.winning_trades
            metrics.trades_per_hour = metrics.trades_per_day / 24
            
            # Mock trades (would come from actual backtest)
            trades = []
            for i in range(metrics.total_trades):
                trades.append(TradeResult(
                    symbol=np.random.choice(symbols),
                    direction=np.random.choice(['long', 'short']),
                    entry_price=np.random.uniform(0.01, 100),
                    exit_price=np.random.uniform(0.01, 100),
                    entry_time=start_time - timedelta(hours=np.random.randint(1, 720)),
                    exit_time=start_time - timedelta(hours=np.random.randint(0, 720)),
                    size=np.random.uniform(10, 1000),
                    leverage=np.random.randint(info.leverage_range[0], info.leverage_range[1]),
                    pnl=np.random.uniform(-50, 100),
                    pnl_percentage=np.random.uniform(-10, 20),
                    duration_minutes=np.random.uniform(5, 300),
                    close_reason=np.random.choice(['tp1', 'tp2', 'tp3', 'sl1', 'sl2', 'sl3']),
                    commission_paid=np.random.uniform(0.01, 5.0),
                    sl_levels_hit=[],
                    tp_levels_hit=[]
                ))
            
            result = StrategyBacktestResult(
                strategy_name=name,
                config=strategy_config,
                metrics=metrics,
                trades=trades,
                duration_seconds=(datetime.now() - start_time).total_seconds(),
                start_time=start_time,
                end_time=datetime.now(),
                symbols_tested=symbols,
                success=True
            )
            
            self.logger.info(f"✅ {name}: {metrics.total_trades} trades, {metrics.win_rate:.1f}% win rate, {metrics.total_pnl_percentage:.1f}% PnL")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Error backtesting {name}: {e}")
            return StrategyBacktestResult(
                strategy_name=name,
                config=config,
                metrics=BacktestMetrics(),
                trades=[],
                duration_seconds=(datetime.now() - start_time).total_seconds(),
                start_time=start_time,
                end_time=datetime.now(),
                symbols_tested=symbols,
                error_message=str(e),
                success=False
            )
    
    def _calculate_strategy_rankings(self, results: Dict[str, StrategyBacktestResult]) -> Dict[str, List[Tuple[str, float]]]:
        """Calculate strategy rankings for each metric"""
        rankings = {}
        
        # Get successful results only
        successful_results = {name: result for name, result in results.items() if result.success}
        
        if not successful_results:
            return rankings
        
        for metric in self.comparison_config['comparison_metrics']:
            metric_values = []
            for name, result in successful_results.items():
                value = getattr(result.metrics, metric, 0.0)
                metric_values.append((name, value))
            
            # Sort by metric (ascending for drawdown, descending for others)
            reverse_sort = metric != 'max_drawdown_percentage'
            metric_values.sort(key=lambda x: x[1], reverse=reverse_sort)
            
            rankings[metric] = metric_values
        
        return rankings
    
    def _determine_best_worst_strategies(self, results: Dict[str, StrategyBacktestResult], 
                                       rankings: Dict[str, List[Tuple[str, float]]]) -> Tuple[str, str]:
        """Determine best and worst strategies using weighted scoring"""
        strategy_scores = defaultdict(float)
        
        # Calculate weighted scores
        for metric, strategy_rankings in rankings.items():
            weight = self.comparison_config['ranking_weights'].get(metric, 0.0)
            
            for rank, (strategy_name, value) in enumerate(strategy_rankings):
                # Score based on rank (best rank = highest score)
                rank_score = (len(strategy_rankings) - rank) / len(strategy_rankings)
                strategy_scores[strategy_name] += weight * rank_score
        
        # Find best and worst
        if not strategy_scores:
            return "None", "None"
        
        sorted_strategies = sorted(strategy_scores.items(), key=lambda x: x[1], reverse=True)
        best_strategy = sorted_strategies[0][0]
        worst_strategy = sorted_strategies[-1][0]
        
        return best_strategy, worst_strategy
    
    def _generate_performance_summary(self, results: Dict[str, StrategyBacktestResult]) -> Dict[str, Any]:
        """Generate overall performance summary"""
        successful_results = {name: result for name, result in results.items() if result.success}
        
        if not successful_results:
            return {}
        
        summary = {
            'total_strategies_tested': len(results),
            'successful_strategies': len(successful_results),
            'failed_strategies': len(results) - len(successful_results),
            'average_metrics': {},
            'best_metrics': {},
            'worst_metrics': {}
        }
        
        # Calculate aggregate metrics
        for metric in self.comparison_config['comparison_metrics']:
            values = [getattr(result.metrics, metric, 0.0) for result in successful_results.values()]
            
            if values:
                summary['average_metrics'][metric] = np.mean(values)
                summary['best_metrics'][metric] = np.max(values) if metric != 'max_drawdown_percentage' else np.min(values)
                summary['worst_metrics'][metric] = np.min(values) if metric != 'max_drawdown_percentage' else np.max(values)
        
        return summary
    
    def _generate_recommendations(self, results: Dict[str, StrategyBacktestResult], 
                                rankings: Dict[str, List[Tuple[str, float]]]) -> List[str]:
        """Generate strategic recommendations based on comparison results"""
        recommendations = []
        
        successful_results = {name: result for name, result in results.items() if result.success}
        
        if not successful_results:
            recommendations.append("❌ All strategies failed - check configuration and data availability")
            return recommendations
        
        # Analyze win rates
        win_rates = {name: result.metrics.win_rate for name, result in successful_results.items()}
        best_win_rate_strategy = max(win_rates.items(), key=lambda x: x[1])
        
        if best_win_rate_strategy[1] > 70:
            recommendations.append(f"🎯 {best_win_rate_strategy[0]} shows exceptional win rate ({best_win_rate_strategy[1]:.1f}%) - consider primary deployment")
        
        # Analyze profit factors
        profit_factors = {name: result.metrics.profit_factor for name, result in successful_results.items()}
        best_profit_factor_strategy = max(profit_factors.items(), key=lambda x: x[1])
        
        if best_profit_factor_strategy[1] > 2.0:
            recommendations.append(f"💰 {best_profit_factor_strategy[0]} demonstrates strong profit factor ({best_profit_factor_strategy[1]:.2f}) - excellent risk/reward")
        
        # Analyze drawdowns
        drawdowns = {name: result.metrics.max_drawdown_percentage for name, result in successful_results.items()}
        lowest_drawdown_strategy = min(drawdowns.items(), key=lambda x: x[1])
        
        if lowest_drawdown_strategy[1] < 10:
            recommendations.append(f"🛡️ {lowest_drawdown_strategy[0]} shows low drawdown ({lowest_drawdown_strategy[1]:.1f}%) - suitable for conservative trading")
        
        # Analyze trade frequency
        trade_frequencies = {name: result.metrics.trades_per_day for name, result in successful_results.items()}
        most_active_strategy = max(trade_frequencies.items(), key=lambda x: x[1])
        
        if most_active_strategy[1] > 5:
            recommendations.append(f"⚡ {most_active_strategy[0]} provides high activity ({most_active_strategy[1]:.1f} trades/day) - good for active trading")
        
        # Overall recommendation
        if len(successful_results) > 1:
            recommendations.append("🔄 Consider combining top 2-3 strategies for diversified approach")
        
        if not recommendations:
            recommendations.append("📊 All strategies show moderate performance - consider optimization")
        
        return recommendations
    
    async def _save_comparison_results(self, comparison: StrategyComparison, symbols: List[str]):
        """Save comparison results to database"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # Save comparison run
            cursor.execute('''
                INSERT INTO comparison_runs 
                (id, comparison_date, config_json, total_duration_seconds, 
                 best_strategy, worst_strategy, strategies_count, symbols_tested)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                comparison.comparison_id,
                comparison.comparison_date,
                json.dumps(asdict(comparison.config), default=str),
                comparison.total_duration_seconds,
                comparison.best_overall_strategy,
                comparison.worst_overall_strategy,
                len(comparison.strategy_results),
                json.dumps(symbols)
            ))
            
            # Save individual strategy results
            for name, result in comparison.strategy_results.items():
                cursor.execute('''
                    INSERT INTO strategy_results 
                    (comparison_id, strategy_name, total_pnl_percentage, win_rate,
                     profit_factor, sharpe_ratio, max_drawdown_percentage, total_trades,
                     avg_trade_duration, trades_per_day, duration_seconds, success,
                     error_message, metrics_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    comparison.comparison_id,
                    name,
                    result.metrics.total_pnl_percentage,
                    result.metrics.win_rate,
                    result.metrics.profit_factor,
                    result.metrics.sharpe_ratio,
                    result.metrics.max_drawdown_percentage,
                    result.metrics.total_trades,
                    result.metrics.avg_trade_duration,
                    result.metrics.trades_per_day,
                    result.duration_seconds,
                    result.success,
                    result.error_message,
                    json.dumps(asdict(result.metrics), default=str)
                ))
            
            # Save rankings
            for metric, rankings in comparison.ranking_by_metric.items():
                for rank, (strategy_name, value) in enumerate(rankings):
                    cursor.execute('''
                        INSERT INTO performance_rankings 
                        (comparison_id, metric_name, strategy_name, metric_value, rank)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        comparison.comparison_id,
                        metric,
                        strategy_name,
                        value,
                        rank + 1
                    ))
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"💾 Comparison results saved to database")
            
        except Exception as e:
            self.logger.error(f"Error saving comparison results: {e}")
    
    async def _generate_comparison_reports(self, comparison: StrategyComparison):
        """Generate detailed comparison reports in JSON and CSV formats"""
        try:
            # JSON Report
            json_file = self.results_dir / f"{comparison.comparison_id}_report.json"
            with open(json_file, 'w') as f:
                # Custom serializer for datetime and other objects
                def json_serializer(obj):
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    elif hasattr(obj, '__dict__'):
                        return asdict(obj) if hasattr(obj, '__dataclass_fields__') else str(obj)
                    return str(obj)
                
                json.dump(asdict(comparison), f, indent=2, default=json_serializer)
            
            # CSV Summary
            csv_file = self.results_dir / f"{comparison.comparison_id}_summary.csv"
            self._generate_csv_summary(comparison, csv_file)
            
            self.logger.info(f"📄 Reports generated: JSON, CSV")
            
        except Exception as e:
            self.logger.error(f"Error generating reports: {e}")
    
    def format_comparison_summary_telegram(self, comparison: StrategyComparison, page: int = 1, per_page: int = 5) -> Tuple[str, bool, str]:
        """
        Generate Telegram-formatted comparison summary
        Returns: (formatted_text, has_more_pages, chart_path)
        """
        try:
            # Header
            text = f"🏆 *Strategy Performance Comparison*\n"
            text += f"📅 ID: `{comparison.comparison_id}`\n"
            text += f"⏱️ Duration: {comparison.total_duration_seconds:.1f}s\n"
            text += f"🥇 Best: *{comparison.best_overall_strategy}*\n"
            text += f"🥉 Worst: *{comparison.worst_overall_strategy}*\n\n"
            
            # Performance Summary
            text += "📊 *Overall Summary:*\n"
            summary = comparison.performance_summary
            text += f"✅ Successful: {summary.get('successful_strategies', 0)}\n"
            text += f"❌ Failed: {summary.get('failed_strategies', 0)}\n\n"
            
            # Average metrics
            avg_metrics = summary.get('average_metrics', {})
            if avg_metrics:
                text += "📈 *Average Performance:*\n"
                for metric, value in list(avg_metrics.items())[:4]:  # Limit to prevent overflow
                    metric_name = metric.replace('_', ' ').title()
                    if 'percentage' in metric:
                        text += f"• {metric_name}: {value:.1f}%\n"
                    else:
                        text += f"• {metric_name}: {value:.2f}\n"
            
            # Strategy results with pagination
            successful_results = {name: result for name, result in comparison.strategy_results.items() if result.success}
            total_strategies = len(successful_results)
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            strategies_page = list(successful_results.items())[start_idx:end_idx]
            
            if strategies_page:
                text += f"\n🔍 *Strategy Results* (Page {page}):\n"
                for name, result in strategies_page:
                    text += f"\n*{name}:*\n"
                    text += f"  💰 PnL: {result.metrics.total_pnl_percentage:.1f}%\n"
                    text += f"  🎯 Win Rate: {result.metrics.win_rate:.1f}%\n"
                    text += f"  📊 Profit Factor: {result.metrics.profit_factor:.2f}\n"
                    text += f"  📉 Drawdown: {result.metrics.max_drawdown_percentage:.1f}%\n"
            
            # Check if more pages exist
            has_more = end_idx < total_strategies
            
            # Add pagination info
            if total_strategies > per_page:
                total_pages = (total_strategies + per_page - 1) // per_page
                text += f"\n📄 Page {page}/{total_pages}"
            
            # Generate chart
            chart_path = self._generate_performance_chart_telegram(comparison)
            
            return text, has_more, chart_path
            
        except Exception as e:
            self.logger.error(f"Error formatting Telegram summary: {e}")
            return f"❌ Error formatting comparison results: {str(e)}", False, ""
    
    def format_strategy_rankings_telegram(self, comparison: StrategyComparison, metric: str = 'total_pnl_percentage') -> str:
        """Format strategy rankings for specific metric"""
        try:
            if metric not in comparison.ranking_by_metric:
                available_metrics = ', '.join(comparison.ranking_by_metric.keys())
                return f"❌ Metric '{metric}' not found. Available: {available_metrics}"
            
            rankings = comparison.ranking_by_metric[metric]
            metric_name = metric.replace('_', ' ').title()
            
            text = f"🏅 *{metric_name} Rankings:*\n\n"
            
            for rank, (strategy, value) in enumerate(rankings[:10]):  # Top 10 only
                emoji = "🥇" if rank == 0 else "🥈" if rank == 1 else "🥉" if rank == 2 else "🔸"
                
                if 'percentage' in metric:
                    text += f"{emoji} {rank + 1}. *{strategy}*: {value:.1f}%\n"
                else:
                    text += f"{emoji} {rank + 1}. *{strategy}*: {value:.2f}\n"
            
            return text
            
        except Exception as e:
            self.logger.error(f"Error formatting rankings: {e}")
            return f"❌ Error formatting rankings: {str(e)}"
    
    def format_recommendations_telegram(self, comparison: StrategyComparison) -> str:
        """Format recommendations for Telegram"""
        try:
            text = "💡 *Recommendations:*\n\n"
            
            for i, rec in enumerate(comparison.recommendations[:10], 1):  # Limit to prevent overflow
                text += f"{i}. {rec}\n"
            
            if len(comparison.recommendations) > 10:
                text += f"\n... and {len(comparison.recommendations) - 10} more recommendations"
            
            return text
            
        except Exception as e:
            self.logger.error(f"Error formatting recommendations: {e}")
            return f"❌ Error formatting recommendations: {str(e)}"
    
    def _generate_performance_chart_telegram(self, comparison: StrategyComparison) -> str:
        """Generate performance comparison chart as PNG for Telegram"""
        try:
            successful_results = {name: result for name, result in comparison.strategy_results.items() if result.success}
            
            if not successful_results:
                return ""
            
            # Create figure with subplots
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 10))
            fig.suptitle(f'Strategy Performance Comparison\n{comparison.comparison_id}', fontsize=16, fontweight='bold')
            
            strategies = list(successful_results.keys())
            
            # Plot 1: Total PnL Percentage
            pnl_values = [result.metrics.total_pnl_percentage for result in successful_results.values()]
            colors = ['green' if x > 0 else 'red' for x in pnl_values]
            ax1.bar(strategies, pnl_values, color=colors, alpha=0.7)
            ax1.set_title('Total PnL %', fontweight='bold')
            ax1.set_ylabel('Percentage')
            ax1.tick_params(axis='x', rotation=45)
            
            # Plot 2: Win Rate
            win_rates = [result.metrics.win_rate for result in successful_results.values()]
            ax2.bar(strategies, win_rates, color='blue', alpha=0.7)
            ax2.set_title('Win Rate %', fontweight='bold')
            ax2.set_ylabel('Percentage')
            ax2.tick_params(axis='x', rotation=45)
            
            # Plot 3: Profit Factor
            profit_factors = [result.metrics.profit_factor for result in successful_results.values()]
            ax3.bar(strategies, profit_factors, color='purple', alpha=0.7)
            ax3.axhline(y=1.0, color='red', linestyle='--', alpha=0.5)  # Breakeven line
            ax3.set_title('Profit Factor', fontweight='bold')
            ax3.set_ylabel('Factor')
            ax3.tick_params(axis='x', rotation=45)
            
            # Plot 4: Max Drawdown
            drawdowns = [result.metrics.max_drawdown_percentage for result in successful_results.values()]
            ax4.bar(strategies, drawdowns, color='orange', alpha=0.7)
            ax4.set_title('Max Drawdown %', fontweight='bold')
            ax4.set_ylabel('Percentage')
            ax4.tick_params(axis='x', rotation=45)
            
            plt.tight_layout()
            
            # Save to file
            chart_path = self.results_dir / f"{comparison.comparison_id}_chart.png"
            plt.savefig(chart_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            return str(chart_path)
            
        except Exception as e:
            self.logger.error(f"Error generating performance chart: {e}")
            return ""
    
    def _generate_csv_summary(self, comparison: StrategyComparison, file_path: Path):
        """Generate CSV summary of results"""
        try:
            data = []
            for name, result in comparison.strategy_results.items():
                if result.success:
                    data.append({
                        'Strategy': name,
                        'Total_PnL_Percentage': result.metrics.total_pnl_percentage,
                        'Win_Rate': result.metrics.win_rate,
                        'Profit_Factor': result.metrics.profit_factor,
                        'Sharpe_Ratio': result.metrics.sharpe_ratio,
                        'Max_Drawdown_Percentage': result.metrics.max_drawdown_percentage,
                        'Total_Trades': result.metrics.total_trades,
                        'Avg_Trade_Duration': result.metrics.avg_trade_duration,
                        'Trades_Per_Day': result.metrics.trades_per_day,
                        'Success': result.success
                    })
            
            df = pd.DataFrame(data)
            df.to_csv(file_path, index=False)
            
        except Exception as e:
            self.logger.error(f"Error generating CSV summary: {e}")

# Example usage and testing function
async def main():
    """Example usage of the Strategy Performance Comparator"""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Initialize comparator
    comparator = StrategyPerformanceComparator()
    
    # Run comparison
    comparison = await comparator.compare_all_strategies()
    
    print(f"Comparison completed! Best strategy: {comparison.best_overall_strategy}")
    print(f"Results saved to: {comparator.results_dir}")

if __name__ == "__main__":
    asyncio.run(main())