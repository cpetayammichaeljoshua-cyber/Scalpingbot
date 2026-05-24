#!/usr/bin/env python3
"""
Trading Metrics Manager - Comprehensive Performance Tracking System
Provides real-time calculation and display of all trading performance metrics
"""

import asyncio
import logging
import sqlite3
import aiosqlite
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import math

@dataclass
class TradingMetrics:
    """Complete trading performance metrics"""
    # Basic Performance
    win_rate_percentage: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # PnL Metrics
    current_realized_pnl: float = 0.0
    current_unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    daily_pnl: float = 0.0
    
    # Streak Metrics
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    best_winning_streak: int = 0
    worst_losing_streak: int = 0
    current_streak_type: str = "none"  # "win", "loss", "none"
    
    # Trade Rate Metrics
    trades_per_hour: float = 0.0
    trades_completed_today: int = 0
    
    # Average Performance
    avg_profit_per_win: float = 0.0
    avg_loss_per_losing_trade: float = 0.0
    
    # Risk Metrics
    sharpe_ratio: float = 0.0
    maximum_drawdown: float = 0.0
    maximum_drawdown_percentage: float = 0.0
    
    # Time-based Analysis
    success_rate_by_time: Dict[str, float] = None
    performance_by_trading_pair: Dict[str, Dict[str, Any]] = None
    
    # Comparison Metrics
    daily_comparison: Dict[str, float] = None
    weekly_comparison: Dict[str, float] = None
    
    # Additional Context
    last_updated: datetime = None
    active_trades: int = 0
    portfolio_balance: float = 0.0
    
    def __post_init__(self):
        if self.success_rate_by_time is None:
            self.success_rate_by_time = {}
        if self.performance_by_trading_pair is None:
            self.performance_by_trading_pair = {}
        if self.daily_comparison is None:
            self.daily_comparison = {}
        if self.weekly_comparison is None:
            self.weekly_comparison = {}
        if self.last_updated is None:
            self.last_updated = datetime.now()

class TradingMetricsManager:
    """Comprehensive trading metrics management system"""
    
    def __init__(self, db_path: str = "SignalMaestro/advanced_ml_trading.db"):
        self.logger = logging.getLogger(__name__)
        self.db_path = db_path
        
        # Current metrics state
        self.current_metrics = TradingMetrics()
        
        # Historical data caches
        self.trade_history_cache = deque(maxlen=1000)
        self.pnl_history = deque(maxlen=500)
        self.drawdown_history = deque(maxlen=200)
        
        # Performance tracking
        self.metrics_calculation_times = deque(maxlen=100)
        self.last_full_calculation = None
        
        # Configuration
        self.update_interval_minutes = 5
        self.console_log_interval_minutes = 30
        self.last_console_log = datetime.now() - timedelta(hours=1)  # Force first log
        
        self.logger.info("📊 Trading Metrics Manager initialized")
    
    async def initialize_database(self):
        """Initialize metrics database tables"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Historical metrics snapshots table
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS metrics_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        metrics_data TEXT NOT NULL,
                        calculation_time_ms REAL,
                        snapshot_type TEXT DEFAULT 'regular',
                        trigger_event TEXT
                    )
                ''')
                
                # Daily performance summary table
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS daily_performance (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date DATE UNIQUE,
                        total_trades INTEGER DEFAULT 0,
                        winning_trades INTEGER DEFAULT 0,
                        losing_trades INTEGER DEFAULT 0,
                        win_rate REAL DEFAULT 0.0,
                        daily_pnl REAL DEFAULT 0.0,
                        best_winning_streak INTEGER DEFAULT 0,
                        worst_losing_streak INTEGER DEFAULT 0,
                        trades_per_hour REAL DEFAULT 0.0,
                        avg_profit_per_win REAL DEFAULT 0.0,
                        avg_loss_per_trade REAL DEFAULT 0.0,
                        max_drawdown REAL DEFAULT 0.0,
                        sharpe_ratio REAL DEFAULT 0.0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Trading pair performance table
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS pair_performance (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        date DATE NOT NULL,
                        total_trades INTEGER DEFAULT 0,
                        winning_trades INTEGER DEFAULT 0,
                        win_rate REAL DEFAULT 0.0,
                        total_pnl REAL DEFAULT 0.0,
                        avg_profit REAL DEFAULT 0.0,
                        max_drawdown REAL DEFAULT 0.0,
                        trades_per_hour REAL DEFAULT 0.0,
                        last_trade_time DATETIME,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(symbol, date)
                    )
                ''')
                
                # Time-based performance analysis table
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS time_performance (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        hour_of_day INTEGER NOT NULL,
                        day_of_week INTEGER NOT NULL,
                        total_trades INTEGER DEFAULT 0,
                        winning_trades INTEGER DEFAULT 0,
                        win_rate REAL DEFAULT 0.0,
                        avg_pnl REAL DEFAULT 0.0,
                        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(hour_of_day, day_of_week)
                    )
                ''')
                
                # Create indexes for better performance
                await db.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics_snapshots (timestamp)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_daily_performance_date ON daily_performance (date)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_pair_performance_symbol_date ON pair_performance (symbol, date)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_time_performance_hour_day ON time_performance (hour_of_day, day_of_week)")
                
                await db.commit()
                
            self.logger.info("📊 Metrics database tables initialized successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Error initializing metrics database: {e}")
            raise
    
    async def calculate_comprehensive_metrics(self, force_refresh: bool = False) -> TradingMetrics:
        """Calculate all trading metrics comprehensively"""
        start_time = datetime.now()
        
        try:
            # Skip calculation if recent update exists (unless forced)
            if not force_refresh and self.last_full_calculation:
                time_since_last = datetime.now() - self.last_full_calculation
                if time_since_last.total_seconds() < self.update_interval_minutes * 60:
                    return self.current_metrics
            
            self.logger.debug("🔄 Calculating comprehensive trading metrics...")
            
            # Get trade data from database
            trades_data = await self._fetch_trades_data()
            if not trades_data:
                self.logger.warning("⚠️ No trade data available for metrics calculation")
                return self.current_metrics
            
            # Calculate all metrics
            metrics = TradingMetrics()
            
            # Basic performance metrics
            await self._calculate_basic_performance(metrics, trades_data)
            
            # PnL metrics
            await self._calculate_pnl_metrics(metrics, trades_data)
            
            # Streak metrics
            await self._calculate_streak_metrics(metrics, trades_data)
            
            # Trade rate metrics
            await self._calculate_trade_rate_metrics(metrics, trades_data)
            
            # Average performance metrics
            await self._calculate_average_performance(metrics, trades_data)
            
            # Risk metrics
            await self._calculate_risk_metrics(metrics, trades_data)
            
            # Time-based analysis
            await self._calculate_time_based_metrics(metrics, trades_data)
            
            # Trading pair performance
            await self._calculate_pair_performance(metrics, trades_data)
            
            # Comparison metrics
            await self._calculate_comparison_metrics(metrics, trades_data)
            
            # Update state
            metrics.last_updated = datetime.now()
            self.current_metrics = metrics
            self.last_full_calculation = datetime.now()
            
            # Record calculation time
            calculation_time = (datetime.now() - start_time).total_seconds() * 1000
            self.metrics_calculation_times.append(calculation_time)
            
            # Save snapshot to database
            await self._save_metrics_snapshot(metrics, calculation_time)
            
            # Log to console if interval has passed
            await self._maybe_log_to_console(metrics)
            
            self.logger.debug(f"✅ Metrics calculation completed in {calculation_time:.2f}ms")
            return metrics
            
        except Exception as e:
            self.logger.error(f"❌ Error calculating comprehensive metrics: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return self.current_metrics
    
    async def _fetch_trades_data(self) -> List[Dict[str, Any]]:
        """Fetch all relevant trade data from multiple tables"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                # Fetch from ml_trades table (preferred) and trades table
                trades = []
                
                # Try ml_trades first (more detailed)
                try:
                    async with db.execute('''
                        SELECT * FROM ml_trades 
                        ORDER BY entry_time DESC
                    ''') as cursor:
                        rows = await cursor.fetchall()
                        for row in rows:
                            trade_dict = dict(row)
                            trade_dict['source'] = 'ml_trades'
                            trades.append(trade_dict)
                except sqlite3.OperationalError:
                    self.logger.debug("ml_trades table not found, trying trades table")
                
                # Fallback to trades table if ml_trades is empty
                if not trades:
                    try:
                        async with db.execute('''
                            SELECT *, created_at as entry_time, pnl as profit_loss 
                            FROM trades 
                            ORDER BY created_at DESC
                        ''') as cursor:
                            rows = await cursor.fetchall()
                            for row in rows:
                                trade_dict = dict(row)
                                trade_dict['source'] = 'trades'
                                trades.append(trade_dict)
                    except sqlite3.OperationalError:
                        self.logger.warning("trades table not found")
                
                self.logger.debug(f"Fetched {len(trades)} trades for metrics calculation")
                return trades
                
        except Exception as e:
            self.logger.error(f"Error fetching trades data: {e}")
            return []
    
    async def _calculate_basic_performance(self, metrics: TradingMetrics, trades_data: List[Dict]):
        """Calculate basic performance metrics"""
        metrics.total_trades = len(trades_data)
        
        if not trades_data:
            return
        
        # Count wins and losses
        winning_trades = 0
        losing_trades = 0
        
        for trade in trades_data:
            pnl = trade.get('profit_loss', trade.get('pnl', 0))
            if pnl is None:
                continue
                
            if pnl > 0:
                winning_trades += 1
            elif pnl < 0:
                losing_trades += 1
        
        metrics.winning_trades = winning_trades
        metrics.losing_trades = losing_trades
        metrics.win_rate_percentage = (winning_trades / metrics.total_trades * 100) if metrics.total_trades > 0 else 0
    
    async def _calculate_pnl_metrics(self, metrics: TradingMetrics, trades_data: List[Dict]):
        """Calculate PnL-related metrics"""
        total_pnl = 0
        daily_pnl = 0
        today = datetime.now().date()
        
        for trade in trades_data:
            pnl = trade.get('profit_loss', trade.get('pnl', 0))
            if pnl is None:
                continue
                
            total_pnl += pnl
            
            # Calculate daily PnL
            entry_time = trade.get('entry_time', trade.get('created_at'))
            if entry_time:
                if isinstance(entry_time, str):
                    try:
                        trade_date = datetime.fromisoformat(entry_time.replace('Z', '+00:00')).date()
                    except:
                        trade_date = datetime.strptime(entry_time[:10], '%Y-%m-%d').date()
                else:
                    trade_date = entry_time.date() if hasattr(entry_time, 'date') else today
                
                if trade_date == today:
                    daily_pnl += pnl
        
        metrics.current_realized_pnl = total_pnl
        metrics.total_pnl = total_pnl
        metrics.daily_pnl = daily_pnl
        
        # Note: Unrealized PnL would need to be calculated from open positions
        # This would require integration with the trading system's position tracking
        metrics.current_unrealized_pnl = 0.0  # Placeholder
    
    async def _calculate_streak_metrics(self, metrics: TradingMetrics, trades_data: List[Dict]):
        """Calculate winning/losing streak metrics"""
        if not trades_data:
            return
        
        # Sort trades by time (oldest first for streak calculation)
        sorted_trades = sorted(trades_data, key=lambda x: x.get('entry_time', x.get('created_at', '')))
        
        current_streak = 0
        current_streak_type = "none"
        best_win_streak = 0
        worst_loss_streak = 0
        temp_win_streak = 0
        temp_loss_streak = 0
        
        for trade in sorted_trades:
            pnl = trade.get('profit_loss', trade.get('pnl', 0))
            if pnl is None:
                continue
            
            if pnl > 0:  # Winning trade
                temp_win_streak += 1
                temp_loss_streak = 0
                if current_streak_type == "win":
                    current_streak += 1
                else:
                    current_streak = 1
                    current_streak_type = "win"
                best_win_streak = max(best_win_streak, temp_win_streak)
                
            elif pnl < 0:  # Losing trade
                temp_loss_streak += 1
                temp_win_streak = 0
                if current_streak_type == "loss":
                    current_streak += 1
                else:
                    current_streak = 1
                    current_streak_type = "loss"
                worst_loss_streak = max(worst_loss_streak, temp_loss_streak)
        
        metrics.consecutive_wins = current_streak if current_streak_type == "win" else 0
        metrics.consecutive_losses = current_streak if current_streak_type == "loss" else 0
        metrics.best_winning_streak = best_win_streak
        metrics.worst_losing_streak = worst_loss_streak
        metrics.current_streak_type = current_streak_type
    
    async def _calculate_trade_rate_metrics(self, metrics: TradingMetrics, trades_data: List[Dict]):
        """Calculate trade rate metrics"""
        today = datetime.now().date()
        today_trades = 0
        
        # Calculate trades today
        for trade in trades_data:
            entry_time = trade.get('entry_time', trade.get('created_at'))
            if entry_time:
                if isinstance(entry_time, str):
                    try:
                        trade_date = datetime.fromisoformat(entry_time.replace('Z', '+00:00')).date()
                    except:
                        trade_date = datetime.strptime(entry_time[:10], '%Y-%m-%d').date()
                else:
                    trade_date = entry_time.date() if hasattr(entry_time, 'date') else today
                
                if trade_date == today:
                    today_trades += 1
        
        metrics.trades_completed_today = today_trades
        
        # Calculate trades per hour (last 24 hours)
        if trades_data:
            recent_trades = []
            cutoff_time = datetime.now() - timedelta(hours=24)
            
            for trade in trades_data:
                entry_time_str = trade.get('entry_time', trade.get('created_at'))
                if entry_time_str:
                    try:
                        if isinstance(entry_time_str, str):
                            entry_time = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
                        else:
                            entry_time = entry_time_str
                        
                        if entry_time >= cutoff_time:
                            recent_trades.append(trade)
                    except:
                        continue
            
            metrics.trades_per_hour = len(recent_trades) / 24 if recent_trades else 0
    
    async def _calculate_average_performance(self, metrics: TradingMetrics, trades_data: List[Dict]):
        """Calculate average performance metrics"""
        if not trades_data:
            return
        
        winning_profits = []
        losing_profits = []
        
        for trade in trades_data:
            pnl = trade.get('profit_loss', trade.get('pnl', 0))
            if pnl is None:
                continue
                
            if pnl > 0:
                winning_profits.append(pnl)
            elif pnl < 0:
                losing_profits.append(pnl)
        
        metrics.avg_profit_per_win = sum(winning_profits) / len(winning_profits) if winning_profits else 0
        metrics.avg_loss_per_losing_trade = sum(losing_profits) / len(losing_profits) if losing_profits else 0
    
    async def _calculate_risk_metrics(self, metrics: TradingMetrics, trades_data: List[Dict]):
        """Calculate risk-adjusted metrics"""
        if not trades_data:
            return
        
        # Calculate Sharpe ratio
        returns = []
        running_balance = 10000  # Assume starting balance
        
        for trade in trades_data:
            pnl = trade.get('profit_loss', trade.get('pnl', 0))
            if pnl is None:
                continue
            
            return_pct = pnl / running_balance if running_balance > 0 else 0
            returns.append(return_pct)
            running_balance += pnl
        
        if returns:
            returns_array = np.array(returns)
            avg_return = np.mean(returns_array)
            std_return = np.std(returns_array)
            metrics.sharpe_ratio = (avg_return / std_return) if std_return > 0 else 0
        
        # Calculate maximum drawdown
        balance_history = [10000]  # Starting balance
        peak_balance = 10000
        max_drawdown = 0
        max_drawdown_pct = 0
        
        for trade in trades_data:
            pnl = trade.get('profit_loss', trade.get('pnl', 0))
            if pnl is None:
                continue
            
            balance = balance_history[-1] + pnl
            balance_history.append(balance)
            
            if balance > peak_balance:
                peak_balance = balance
            else:
                drawdown = peak_balance - balance
                drawdown_pct = (drawdown / peak_balance) * 100 if peak_balance > 0 else 0
                
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                if drawdown_pct > max_drawdown_pct:
                    max_drawdown_pct = drawdown_pct
        
        metrics.maximum_drawdown = max_drawdown
        metrics.maximum_drawdown_percentage = max_drawdown_pct
    
    async def _calculate_time_based_metrics(self, metrics: TradingMetrics, trades_data: List[Dict]):
        """Calculate time-based success rates"""
        hourly_stats = defaultdict(lambda: {'wins': 0, 'total': 0})
        
        for trade in trades_data:
            entry_time_str = trade.get('entry_time', trade.get('created_at'))
            pnl = trade.get('profit_loss', trade.get('pnl', 0))
            
            if not entry_time_str or pnl is None:
                continue
            
            try:
                if isinstance(entry_time_str, str):
                    entry_time = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00'))
                else:
                    entry_time = entry_time_str
                
                hour = entry_time.hour
                hourly_stats[hour]['total'] += 1
                
                if pnl > 0:
                    hourly_stats[hour]['wins'] += 1
                    
            except:
                continue
        
        # Convert to success rates
        success_rates = {}
        for hour, stats in hourly_stats.items():
            if stats['total'] > 0:
                success_rate = (stats['wins'] / stats['total']) * 100
                success_rates[f"{hour:02d}:00-{hour:02d}:59"] = round(success_rate, 2)
        
        metrics.success_rate_by_time = success_rates
    
    async def _calculate_pair_performance(self, metrics: TradingMetrics, trades_data: List[Dict]):
        """Calculate performance by trading pair"""
        pair_stats = defaultdict(lambda: {
            'total_trades': 0,
            'winning_trades': 0,
            'total_pnl': 0,
            'win_rate': 0,
            'avg_profit': 0,
            'best_trade': 0,
            'worst_trade': 0
        })
        
        for trade in trades_data:
            symbol = trade.get('symbol', 'UNKNOWN')
            pnl = trade.get('profit_loss', trade.get('pnl', 0))
            
            if pnl is None:
                continue
            
            stats = pair_stats[symbol]
            stats['total_trades'] += 1
            stats['total_pnl'] += pnl
            
            if pnl > 0:
                stats['winning_trades'] += 1
            
            stats['best_trade'] = max(stats['best_trade'], pnl)
            stats['worst_trade'] = min(stats['worst_trade'], pnl)
        
        # Calculate derived metrics
        for symbol, stats in pair_stats.items():
            if stats['total_trades'] > 0:
                stats['win_rate'] = (stats['winning_trades'] / stats['total_trades']) * 100
                stats['avg_profit'] = stats['total_pnl'] / stats['total_trades']
        
        metrics.performance_by_trading_pair = dict(pair_stats)
    
    async def _calculate_comparison_metrics(self, metrics: TradingMetrics, trades_data: List[Dict]):
        """Calculate comparison metrics vs previous periods"""
        # Get previous day and week data
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)
        
        today_pnl = 0
        yesterday_pnl = 0
        today_trades = 0
        yesterday_trades = 0
        week_pnl = 0
        week_trades = 0
        
        for trade in trades_data:
            entry_time_str = trade.get('entry_time', trade.get('created_at'))
            pnl = trade.get('profit_loss', trade.get('pnl', 0))
            
            if not entry_time_str or pnl is None:
                continue
            
            try:
                if isinstance(entry_time_str, str):
                    trade_date = datetime.fromisoformat(entry_time_str.replace('Z', '+00:00')).date()
                else:
                    trade_date = entry_time_str.date() if hasattr(entry_time_str, 'date') else today
                
                if trade_date == today:
                    today_pnl += pnl
                    today_trades += 1
                elif trade_date == yesterday:
                    yesterday_pnl += pnl
                    yesterday_trades += 1
                
                if trade_date >= week_ago:
                    week_pnl += pnl
                    week_trades += 1
                    
            except:
                continue
        
        # Daily comparison
        daily_pnl_change = ((today_pnl - yesterday_pnl) / abs(yesterday_pnl) * 100) if yesterday_pnl != 0 else 0
        daily_trades_change = ((today_trades - yesterday_trades) / yesterday_trades * 100) if yesterday_trades > 0 else 0
        
        metrics.daily_comparison = {
            'pnl_change_percentage': round(daily_pnl_change, 2),
            'trades_change_percentage': round(daily_trades_change, 2),
            'today_pnl': round(today_pnl, 2),
            'yesterday_pnl': round(yesterday_pnl, 2),
            'today_trades': today_trades,
            'yesterday_trades': yesterday_trades
        }
        
        # Weekly comparison (simplified)
        avg_weekly_pnl = week_pnl / 7 if week_trades > 0 else 0
        weekly_performance = 'improving' if today_pnl > avg_weekly_pnl else 'declining'
        
        metrics.weekly_comparison = {
            'avg_daily_pnl_this_week': round(avg_weekly_pnl, 2),
            'total_week_pnl': round(week_pnl, 2),
            'total_week_trades': week_trades,
            'performance_trend': weekly_performance
        }
    
    async def _save_metrics_snapshot(self, metrics: TradingMetrics, calculation_time_ms: float):
        """Save metrics snapshot to database"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO metrics_snapshots (metrics_data, calculation_time_ms, snapshot_type)
                    VALUES (?, ?, ?)
                ''', (json.dumps(asdict(metrics), default=str), calculation_time_ms, 'regular'))
                await db.commit()
                
        except Exception as e:
            self.logger.error(f"Error saving metrics snapshot: {e}")
    
    async def _maybe_log_to_console(self, metrics: TradingMetrics):
        """Log metrics to console if enough time has passed"""
        time_since_last_log = datetime.now() - self.last_console_log
        
        if time_since_last_log.total_seconds() >= self.console_log_interval_minutes * 60:
            await self.log_metrics_to_console(metrics)
            self.last_console_log = datetime.now()
    
    async def log_metrics_to_console(self, metrics: TradingMetrics = None):
        """Log comprehensive metrics to console with nice formatting"""
        if metrics is None:
            metrics = await self.calculate_comprehensive_metrics()
        
        # Create formatted console output
        console_output = self._format_metrics_for_console(metrics)
        
        # Log to console
        for line in console_output.split('\n'):
            if line.strip():
                self.logger.info(line)
    
    def _format_metrics_for_console(self, metrics: TradingMetrics) -> str:
        """Format metrics for beautiful console display"""
        
        def format_pnl(value: float) -> str:
            return f"${value:+,.2f}" if value != 0 else "$0.00"
        
        def format_percentage(value: float) -> str:
            return f"{value:+.2f}%" if value != 0 else "0.00%"
        
        def get_trend_emoji(value: float) -> str:
            if value > 5: return "🚀"
            elif value > 0: return "📈"
            elif value < -5: return "📉"
            else: return "➡️"
        
        def get_performance_emoji(win_rate: float) -> str:
            if win_rate >= 80: return "🏆"
            elif win_rate >= 70: return "🥇"
            elif win_rate >= 60: return "🥈"
            elif win_rate >= 50: return "🥉"
            else: return "⚠️"
        
        output_lines = [
            "",
            "╔════════════════════════════════════════════════════════════════════════════════════════╗",
            "║                                🤖 TRADING BOT PERFORMANCE METRICS 🤖                   ║",
            "╠════════════════════════════════════════════════════════════════════════════════════════╣",
            "",
            f"║ 📊 OVERALL PERFORMANCE                                                                 ║",
            f"║   • Win Rate: {get_performance_emoji(metrics.win_rate_percentage)} {metrics.win_rate_percentage:.2f}% ({metrics.winning_trades}/{metrics.total_trades} trades)",
            f"║   • Total PnL: {format_pnl(metrics.total_pnl)} | Daily PnL: {format_pnl(metrics.daily_pnl)}",
            f"║   • Realized PnL: {format_pnl(metrics.current_realized_pnl)} | Unrealized: {format_pnl(metrics.current_unrealized_pnl)}",
            "",
            f"║ 🔥 STREAK PERFORMANCE                                                                  ║",
            f"║   • Current Streak: {'🟢' if metrics.current_streak_type == 'win' else '🔴' if metrics.current_streak_type == 'loss' else '⚪'} {metrics.consecutive_wins if metrics.current_streak_type == 'win' else metrics.consecutive_losses if metrics.current_streak_type == 'loss' else 0} ({metrics.current_streak_type})",
            f"║   • Best Win Streak: 🏆 {metrics.best_winning_streak} | Worst Loss Streak: 💥 {metrics.worst_losing_streak}",
            "",
            f"║ ⚡ TRADING ACTIVITY                                                                    ║",
            f"║   • Trades Today: 📈 {metrics.trades_completed_today} | Rate: {metrics.trades_per_hour:.2f}/hour",
            f"║   • Avg Win: {format_pnl(metrics.avg_profit_per_win)} | Avg Loss: {format_pnl(metrics.avg_loss_per_losing_trade)}",
            "",
            f"║ 📊 RISK METRICS                                                                        ║",
            f"║   • Sharpe Ratio: {'🎯' if metrics.sharpe_ratio > 1 else '⚠️' if metrics.sharpe_ratio < 0 else '📊'} {metrics.sharpe_ratio:.3f}",
            f"║   • Max Drawdown: 📉 {format_pnl(metrics.maximum_drawdown)} ({metrics.maximum_drawdown_percentage:.2f}%)",
        ]
        
        # Add comparison metrics if available
        if metrics.daily_comparison:
            daily = metrics.daily_comparison
            pnl_trend = get_trend_emoji(daily['pnl_change_percentage'])
            trades_trend = get_trend_emoji(daily['trades_change_percentage'])
            
            output_lines.extend([
                "",
                f"║ 📅 DAILY COMPARISON (vs Yesterday)                                                    ║",
                f"║   • PnL Change: {pnl_trend} {format_percentage(daily['pnl_change_percentage'])} ({format_pnl(daily['today_pnl'])} vs {format_pnl(daily['yesterday_pnl'])})",
                f"║   • Trades: {trades_trend} {format_percentage(daily['trades_change_percentage'])} ({daily['today_trades']} vs {daily['yesterday_trades']})",
            ])
        
        # Add top performing pairs
        if metrics.performance_by_trading_pair:
            top_pairs = sorted(
                metrics.performance_by_trading_pair.items(), 
                key=lambda x: x[1]['total_pnl'], 
                reverse=True
            )[:3]
            
            if top_pairs:
                output_lines.extend([
                    "",
                    f"║ 🏆 TOP PERFORMING PAIRS                                                                ║"
                ])
                
                for i, (pair, stats) in enumerate(top_pairs, 1):
                    emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
                    output_lines.append(
                        f"║   {emoji} {pair}: {format_pnl(stats['total_pnl'])} | {stats['win_rate']:.1f}% WR ({stats['total_trades']} trades)"
                    )
        
        # Add best time periods
        if metrics.success_rate_by_time:
            best_times = sorted(
                metrics.success_rate_by_time.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:3]
            
            if best_times:
                output_lines.extend([
                    "",
                    f"║ ⏰ BEST TRADING HOURS                                                                  ║"
                ])
                
                for time_period, win_rate in best_times:
                    emoji = "🎯" if win_rate > 80 else "📈" if win_rate > 60 else "📊"
                    output_lines.append(
                        f"║   {emoji} {time_period}: {win_rate:.1f}% win rate"
                    )
        
        output_lines.extend([
            "",
            f"║ 🕐 Last Updated: {metrics.last_updated.strftime('%Y-%m-%d %H:%M:%S')}",
            "╚════════════════════════════════════════════════════════════════════════════════════════╝",
            ""
        ])
        
        return '\n'.join(output_lines)
    
    async def get_metrics_for_telegram(self) -> str:
        """Get formatted metrics for Telegram display"""
        metrics = await self.calculate_comprehensive_metrics()
        
        def format_pnl(value: float) -> str:
            return f"${value:+,.2f}" if value != 0 else "$0.00"
        
        def get_emoji(value: float, threshold: float = 0) -> str:
            if value > threshold: return "📈"
            elif value < -threshold: return "📉"
            else: return "➡️"
        
        # Create compact Telegram format
        telegram_format = f"""🤖 **TRADING PERFORMANCE** 🤖

📊 **Overall Stats**
• Win Rate: {metrics.win_rate_percentage:.1f}% ({metrics.winning_trades}/{metrics.total_trades})
• Total PnL: {format_pnl(metrics.total_pnl)}
• Today PnL: {format_pnl(metrics.daily_pnl)}

🔥 **Streaks**
• Current: {'🟢' if metrics.current_streak_type == 'win' else '🔴' if metrics.current_streak_type == 'loss' else '⚪'} {metrics.consecutive_wins if metrics.current_streak_type == 'win' else metrics.consecutive_losses if metrics.current_streak_type == 'loss' else 0}
• Best Win: 🏆 {metrics.best_winning_streak}
• Worst Loss: 💥 {metrics.worst_losing_streak}

⚡ **Activity**
• Today: {metrics.trades_completed_today} trades
• Rate: {metrics.trades_per_hour:.1f}/hour
• Avg Win: {format_pnl(metrics.avg_profit_per_win)}
• Avg Loss: {format_pnl(metrics.avg_loss_per_losing_trade)}

📊 **Risk**
• Sharpe: {metrics.sharpe_ratio:.3f}
• Max DD: {format_pnl(metrics.maximum_drawdown)} ({metrics.maximum_drawdown_percentage:.1f}%)"""

        # Add daily comparison if available
        if metrics.daily_comparison:
            daily = metrics.daily_comparison
            pnl_emoji = get_emoji(daily['pnl_change_percentage'], 1)
            
            telegram_format += f"""

📅 **Daily Comparison**
• PnL: {pnl_emoji} {daily['pnl_change_percentage']:+.1f}%
• Trades: {daily['today_trades']} vs {daily['yesterday_trades']}"""
        
        telegram_format += f"\n\n🕐 Updated: {metrics.last_updated.strftime('%H:%M:%S')}"
        
        return telegram_format
    
    async def force_metrics_update(self, trigger_event: str = "manual"):
        """Force a complete metrics update"""
        self.logger.info(f"🔄 Forcing metrics update (trigger: {trigger_event})")
        
        start_time = datetime.now()
        metrics = await self.calculate_comprehensive_metrics(force_refresh=True)
        calculation_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # Save snapshot with trigger info
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO metrics_snapshots (metrics_data, calculation_time_ms, snapshot_type, trigger_event)
                    VALUES (?, ?, ?, ?)
                ''', (json.dumps(asdict(metrics), default=str), calculation_time, 'forced', trigger_event))
                await db.commit()
        except Exception as e:
            self.logger.error(f"Error saving forced metrics snapshot: {e}")
        
        await self.log_metrics_to_console(metrics)
        return metrics
    
    async def update_on_trade_execution(self, trade_data: Dict[str, Any]):
        """Update metrics when a new trade is executed"""
        try:
            self.logger.debug("📊 Updating metrics after trade execution")
            
            # Add to cache for quick access
            self.trade_history_cache.append(trade_data)
            
            # Force metrics recalculation
            await self.force_metrics_update("trade_execution")
            
        except Exception as e:
            self.logger.error(f"Error updating metrics on trade execution: {e}")
    
    async def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of current metrics for API/external use"""
        metrics = await self.calculate_comprehensive_metrics()
        
        return {
            'win_rate': metrics.win_rate_percentage,
            'total_trades': metrics.total_trades,
            'total_pnl': metrics.total_pnl,
            'daily_pnl': metrics.daily_pnl,
            'consecutive_wins': metrics.consecutive_wins,
            'consecutive_losses': metrics.consecutive_losses,
            'best_winning_streak': metrics.best_winning_streak,
            'worst_losing_streak': metrics.worst_losing_streak,
            'trades_per_hour': metrics.trades_per_hour,
            'trades_today': metrics.trades_completed_today,
            'avg_profit_per_win': metrics.avg_profit_per_win,
            'avg_loss_per_trade': metrics.avg_loss_per_losing_trade,
            'sharpe_ratio': metrics.sharpe_ratio,
            'max_drawdown': metrics.maximum_drawdown,
            'max_drawdown_pct': metrics.maximum_drawdown_percentage,
            'top_pairs': dict(list(sorted(
                metrics.performance_by_trading_pair.items(), 
                key=lambda x: x[1]['total_pnl'], 
                reverse=True
            )[:5])) if metrics.performance_by_trading_pair else {},
            'best_hours': dict(list(sorted(
                metrics.success_rate_by_time.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:5])) if metrics.success_rate_by_time else {},
            'last_updated': metrics.last_updated.isoformat()
        }

# Global metrics manager instance
_global_metrics_manager = None

async def get_global_metrics_manager(db_path: str = "SignalMaestro/advanced_ml_trading.db") -> TradingMetricsManager:
    """Get the global metrics manager instance"""
    global _global_metrics_manager
    
    if _global_metrics_manager is None:
        _global_metrics_manager = TradingMetricsManager(db_path)
        await _global_metrics_manager.initialize_database()
    
    return _global_metrics_manager

async def log_trade_metrics_update(trade_data: Dict[str, Any]):
    """Convenience function to update metrics after a trade"""
    try:
        metrics_manager = await get_global_metrics_manager()
        await metrics_manager.update_on_trade_execution(trade_data)
    except Exception as e:
        logging.getLogger(__name__).error(f"Error updating trade metrics: {e}")

if __name__ == "__main__":
    # Test the metrics system
    async def test_metrics():
        logging.basicConfig(level=logging.INFO)
        
        manager = TradingMetricsManager()
        await manager.initialize_database()
        
        # Test metrics calculation
        metrics = await manager.calculate_comprehensive_metrics()
        await manager.log_metrics_to_console(metrics)
        
        # Test Telegram format
        telegram_output = await manager.get_metrics_for_telegram()
        print("\nTelegram Format:")
        print(telegram_output)
    
    asyncio.run(test_metrics())