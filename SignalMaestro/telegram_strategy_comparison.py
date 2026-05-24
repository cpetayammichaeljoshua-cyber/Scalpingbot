#!/usr/bin/env python3
"""
Telegram Strategy Comparison Service
Wrapper service for StrategyPerformanceComparator with Telegram bot integration
Handles async operations, message formatting, and bot-specific functionality
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import json
import aiohttp
import time
import random

from strategy_performance_comparator import (
    StrategyPerformanceComparator, StrategyComparison, 
    BacktestConfig, StrategyInfo
)
from config import Config
from api_resilience_layer import TelegramAPIWrapper, APICall

class TelegramStrategyComparison:
    """Telegram-specific wrapper for strategy performance comparison"""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.logger = logging.getLogger(__name__)
        self.comparator = StrategyPerformanceComparator(config)
        
        # Active comparisons tracking
        self.active_comparisons: Dict[str, Dict[str, Any]] = {}
        self.comparison_results: Dict[str, StrategyComparison] = {}
        
        # Configuration for Telegram limits
        self.max_message_length = 4096
        self.max_strategies_per_page = 5
        
        # Initialize Telegram API wrapper with resilience
        self.telegram_api = TelegramAPIWrapper()
        self.connection_retries = 0
        self.max_connection_retries = 5
        self.retry_backoff_base = 2.0
        
        self.logger.info("📱 Telegram Strategy Comparison Service initialized with resilience layer")
    
    async def get_available_strategies(self) -> Tuple[str, int]:
        """
        Get list of available strategies formatted for Telegram
        Returns: (formatted_text, total_count)
        """
        try:
            strategies = self.comparator.registry.get_all_strategies()
            
            if not strategies:
                return "❌ No strategies available. Please check system configuration.", 0
            
            text = "🎯 *Available Trading Strategies:*\n\n"
            
            # Group strategies by type
            strategy_types = {}
            for name, info in strategies.items():
                strategy_type = info.strategy_type
                if strategy_type not in strategy_types:
                    strategy_types[strategy_type] = []
                strategy_types[strategy_type].append((name, info))
            
            # Format by type
            type_emojis = {
                'scalping': '⚡',
                'momentum': '🚀',
                'volume': '📊',
                'fibonacci': '📐',
                'time_based': '⏰',
                'hybrid': '🔄'
            }
            
            for strategy_type, strategy_list in strategy_types.items():
                emoji = type_emojis.get(strategy_type, '🔸')
                text += f"{emoji} *{strategy_type.title()} Strategies:*\n"
                
                for name, info in strategy_list:
                    text += f"  • `{name}`\n"
                    text += f"    Risk: {info.risk_percentage}% | "
                    text += f"Leverage: {info.leverage_range[0]}-{info.leverage_range[1]}x\n"
                
                text += "\n"
            
            text += f"📈 Total: {len(strategies)} strategies available"
            
            return text, len(strategies)
            
        except Exception as e:
            self.logger.error(f"Error getting available strategies: {e}")
            return f"❌ Error retrieving strategies: {str(e)}", 0
    
    async def start_comparison(self, 
                             user_id: int,
                             symbols: Optional[List[str]] = None,
                             days: int = 30,
                             strategies: Optional[List[str]] = None,
                             initial_capital: float = 10.0) -> Tuple[str, str]:
        """
        Start a new strategy comparison
        Returns: (formatted_message, comparison_id)
        """
        try:
            # Validate input parameters
            if days < 1 or days > 365:
                return "❌ Days must be between 1 and 365", ""
            
            if initial_capital < 1.0 or initial_capital > 10000.0:
                return "❌ Initial capital must be between $1 and $10,000", ""
            
            # Create comparison ID
            comparison_id = f"tg_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Set default symbols if not provided
            if symbols is None:
                symbols = [
                    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'SOLUSDT',
                    'XRPUSDT', 'DOTUSDT', 'LINKUSDT', 'MATICUSDT', 'AVAXUSDT'
                ]
            
            # Validate symbols
            symbols = [s.upper() for s in symbols if s and len(s) >= 6]
            if len(symbols) == 0:
                return "❌ No valid trading pairs provided", ""
            
            # Create backtest configuration
            backtest_config = BacktestConfig(
                initial_capital=initial_capital,
                start_date=datetime.now() - timedelta(days=days),
                end_date=datetime.now() - timedelta(days=1),
                timeframes=['5m', '15m', '1h']
            )
            
            # Track active comparison
            self.active_comparisons[comparison_id] = {
                'user_id': user_id,
                'status': 'starting',
                'start_time': datetime.now(),
                'symbols': symbols,
                'strategies': strategies,
                'config': backtest_config,
                'progress': 0,
                'total_steps': len(strategies) if strategies else len(self.comparator.registry.get_all_strategies())
            }
            
            # Start comparison in background
            asyncio.create_task(self._run_comparison_background(comparison_id, backtest_config, symbols, strategies))
            
            # Format confirmation message
            strategy_count = len(strategies) if strategies else len(self.comparator.registry.get_all_strategies())
            text = f"🚀 *Strategy Comparison Started*\n\n"
            text += f"📋 ID: `{comparison_id}`\n"
            text += f"📊 Symbols: {len(symbols)} pairs\n"
            text += f"🎯 Strategies: {strategy_count}\n"
            text += f"📅 Period: {days} days\n"
            text += f"💰 Capital: ${initial_capital}\n\n"
            text += f"⏳ Estimated time: {strategy_count * 2} to {strategy_count * 5} seconds\n"
            text += f"📱 Use `/compare_status {comparison_id}` to check progress"
            
            return text, comparison_id
            
        except Exception as e:
            self.logger.error(f"Error starting comparison: {e}")
            return f"❌ Error starting comparison: {str(e)}", ""
    
    def _update_progress_callback(self, comparison_id: str):
        """Create progress callback function for the specific comparison"""
        def callback(progress: int, message: str = ""):
            try:
                if comparison_id in self.active_comparisons:
                    # Map progress from 0-100 to 10-95 range (leaving room for initialization and finalization)
                    mapped_progress = int(10 + (progress / 100.0) * 85)
                    self.active_comparisons[comparison_id]['progress'] = mapped_progress
                    self.active_comparisons[comparison_id]['current_step'] = message
                    self.logger.info(f"📊 Comparison {comparison_id}: {mapped_progress}% - {message}")
            except Exception as e:
                self.logger.error(f"Error updating progress for {comparison_id}: {e}")
        
        return callback
    
    async def send_telegram_message_with_retry(self, 
                                             chat_id: int, 
                                             message: str, 
                                             parse_mode: str = 'Markdown',
                                             max_retries: int = 3) -> bool:
        """Send Telegram message with retry logic and connection resilience"""
        for attempt in range(max_retries + 1):
            try:
                # Use the resilient API wrapper
                api_call = APICall(
                    service_name="telegram",
                    endpoint="sendMessage",
                    method="POST",
                    payload={
                        "chat_id": chat_id,
                        "text": message[:self.max_message_length],  # Truncate if too long
                        "parse_mode": parse_mode
                    },
                    timeout=30.0
                )
                
                response = await self.telegram_api.send_message(api_call)
                
                if response and response.get('ok', False):
                    self.connection_retries = 0  # Reset counter on success
                    return True
                else:
                    raise Exception(f"API returned error: {response.get('description', 'Unknown error')}")
                    
            except Exception as e:
                self.connection_retries += 1
                self.logger.warning(f"📱 Telegram send attempt {attempt + 1}/{max_retries + 1} failed: {e}")
                
                if attempt < max_retries:
                    # Exponential backoff with jitter
                    delay = (self.retry_backoff_base ** attempt) + random.uniform(0, 1)
                    self.logger.info(f"🔄 Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(f"❌ All Telegram send attempts failed for chat {chat_id}")
                    
        return False
    
    async def check_telegram_connection(self) -> bool:
        """Check if Telegram connection is healthy"""
        try:
            api_call = APICall(
                service_name="telegram",
                endpoint="getMe",
                method="GET",
                timeout=10.0
            )
            
            response = await self.telegram_api.get_me(api_call)
            return response and response.get('ok', False)
            
        except Exception as e:
            self.logger.error(f"🔍 Telegram connection check failed: {e}")
            return False
    
    async def _run_comparison_background(self, 
                                       comparison_id: str, 
                                       backtest_config: BacktestConfig,
                                       symbols: List[str],
                                       strategies: Optional[List[str]]):
        """Run comparison in background and update status"""
        try:
            self.active_comparisons[comparison_id]['status'] = 'running'
            self.logger.info(f"📊 Starting background comparison: {comparison_id}")
            
            # Update progress incrementally
            self.active_comparisons[comparison_id]['progress'] = 10
            await asyncio.sleep(0.1)  # Small delay for progress to register
            
            # Run the actual comparison
            comparison = await self.comparator.compare_all_strategies(
                backtest_config=backtest_config,
                symbols=symbols,
                strategies_to_compare=strategies,
                progress_callback=self._update_progress_callback(comparison_id)
            )
            
            # Final progress updates
            self.active_comparisons[comparison_id]['progress'] = 95
            await asyncio.sleep(0.1)
            
            # Store results
            self.comparison_results[comparison_id] = comparison
            self.active_comparisons[comparison_id]['status'] = 'completed'
            self.active_comparisons[comparison_id]['end_time'] = datetime.now()
            self.active_comparisons[comparison_id]['progress'] = 100
            
            self.logger.info(f"✅ Background comparison completed: {comparison_id}")
            
        except Exception as e:
            self.logger.error(f"Error in background comparison {comparison_id}: {e}")
            self.active_comparisons[comparison_id]['status'] = 'error'
            self.active_comparisons[comparison_id]['error'] = str(e)
            self.active_comparisons[comparison_id]['progress'] = 0
    
    async def get_comparison_status(self, comparison_id: str) -> str:
        """Get status of running comparison"""
        try:
            if comparison_id not in self.active_comparisons:
                return "❌ Comparison not found. Use `/compare_recent` to see available comparisons."
            
            comparison_info = self.active_comparisons[comparison_id]
            status = comparison_info['status']
            
            text = f"📊 *Comparison Status*\n\n"
            text += f"📋 ID: `{comparison_id}`\n"
            text += f"👤 User: {comparison_info['user_id']}\n"
            text += f"⏰ Started: {comparison_info['start_time'].strftime('%H:%M:%S')}\n"
            
            if status == 'starting':
                text += f"🔄 Status: *Initializing...*\n"
                text += f"📊 Progress: 0%"
            elif status == 'running':
                progress = comparison_info.get('progress', 0)
                text += f"🔄 Status: *Running...*\n"
                text += f"📊 Progress: {progress}%\n"
                elapsed = (datetime.now() - comparison_info['start_time']).total_seconds()
                text += f"⏱️ Elapsed: {elapsed:.1f}s"
            elif status == 'completed':
                end_time = comparison_info.get('end_time', datetime.now())
                duration = (end_time - comparison_info['start_time']).total_seconds()
                text += f"✅ Status: *Completed*\n"
                text += f"⏱️ Duration: {duration:.1f}s\n"
                text += f"📱 Use `/compare_result {comparison_id}` to view results"
            elif status == 'error':
                text += f"❌ Status: *Error*\n"
                text += f"💬 Error: {comparison_info.get('error', 'Unknown error')}"
            
            return text
            
        except Exception as e:
            self.logger.error(f"Error getting comparison status: {e}")
            return f"❌ Error getting status: {str(e)}"
    
    async def get_comparison_result(self, comparison_id: str, page: int = 1) -> Tuple[str, Optional[str], bool]:
        """
        Get comparison results formatted for Telegram
        Returns: (formatted_text, chart_path, has_more_pages)
        """
        try:
            if comparison_id not in self.comparison_results:
                if comparison_id in self.active_comparisons:
                    status = self.active_comparisons[comparison_id]['status']
                    if status == 'completed':
                        return "❌ Results not available. Please try again.", None, False
                    else:
                        return f"⏳ Comparison still {status}. Use `/compare_status {comparison_id}` to check progress.", None, False
                else:
                    return "❌ Comparison not found. Use `/compare_recent` to see available comparisons.", None, False
            
            comparison = self.comparison_results[comparison_id]
            
            # Format results using the comparator's Telegram formatting
            formatted_text, has_more, chart_path = self.comparator.format_comparison_summary_telegram(
                comparison, page, self.max_strategies_per_page
            )
            
            return formatted_text, chart_path, has_more
            
        except Exception as e:
            self.logger.error(f"Error getting comparison result: {e}")
            return f"❌ Error getting results: {str(e)}", None, False
    
    async def get_comparison_rankings(self, comparison_id: str, metric: str = 'total_pnl_percentage') -> str:
        """Get strategy rankings for specific metric"""
        try:
            if comparison_id not in self.comparison_results:
                return "❌ Comparison not found or not completed."
            
            comparison = self.comparison_results[comparison_id]
            return self.comparator.format_strategy_rankings_telegram(comparison, metric)
            
        except Exception as e:
            self.logger.error(f"Error getting rankings: {e}")
            return f"❌ Error getting rankings: {str(e)}"
    
    async def get_comparison_recommendations(self, comparison_id: str) -> str:
        """Get recommendations for specific comparison"""
        try:
            if comparison_id not in self.comparison_results:
                return "❌ Comparison not found or not completed."
            
            comparison = self.comparison_results[comparison_id]
            return self.comparator.format_recommendations_telegram(comparison)
            
        except Exception as e:
            self.logger.error(f"Error getting recommendations: {e}")
            return f"❌ Error getting recommendations: {str(e)}"
    
    async def get_recent_comparisons(self, user_id: int, limit: int = 10) -> str:
        """Get list of recent comparisons for user"""
        try:
            user_comparisons = []
            
            # Check active comparisons
            for comp_id, comp_info in self.active_comparisons.items():
                if comp_info['user_id'] == user_id:
                    user_comparisons.append((comp_id, comp_info))
            
            # Sort by start time (most recent first)
            user_comparisons.sort(key=lambda x: x[1]['start_time'], reverse=True)
            user_comparisons = user_comparisons[:limit]
            
            if not user_comparisons:
                return "📭 No comparisons found. Use `/compare_run` to start a new comparison."
            
            text = f"📊 *Your Recent Comparisons:*\n\n"
            
            for comp_id, comp_info in user_comparisons:
                status = comp_info['status']
                start_time = comp_info['start_time'].strftime('%m-%d %H:%M')
                
                status_emoji = {
                    'starting': '🔄',
                    'running': '⏳',
                    'completed': '✅',
                    'error': '❌'
                }.get(status, '❓')
                
                text += f"{status_emoji} `{comp_id}`\n"
                text += f"  📅 {start_time} | Status: {status.title()}\n"
                
                if status == 'completed':
                    text += f"  📱 `/compare_result {comp_id}`\n"
                elif status in ['running', 'starting']:
                    text += f"  📊 `/compare_status {comp_id}`\n"
                
                text += "\n"
            
            return text
            
        except Exception as e:
            self.logger.error(f"Error getting recent comparisons: {e}")
            return f"❌ Error getting recent comparisons: {str(e)}"
    
    def _update_progress_callback(self, comparison_id: str):
        """Create a progress callback function for a specific comparison"""
        def callback(progress_percent: int, message: str = ""):
            if comparison_id in self.active_comparisons:
                self.active_comparisons[comparison_id]['progress'] = progress_percent
                if message:
                    self.active_comparisons[comparison_id]['status_message'] = message
                self.logger.info(f"📊 {comparison_id}: {progress_percent}% - {message}")
        return callback
    
    async def cleanup_old_comparisons(self, max_age_hours: int = 24):
        """Clean up old comparison data to prevent memory leaks"""
        try:
            current_time = datetime.now()
            cleanup_count = 0
            
            # Clean up active comparisons
            to_remove = []
            for comp_id, comp_info in self.active_comparisons.items():
                age_hours = (current_time - comp_info['start_time']).total_seconds() / 3600
                if age_hours > max_age_hours:
                    to_remove.append(comp_id)
            
            for comp_id in to_remove:
                del self.active_comparisons[comp_id]
                if comp_id in self.comparison_results:
                    del self.comparison_results[comp_id]
                cleanup_count += 1
            
            if cleanup_count > 0:
                self.logger.info(f"🧹 Cleaned up {cleanup_count} old comparisons")
            
        except Exception as e:
            self.logger.error(f"Error cleaning up comparisons: {e}")
    
    def get_available_metrics(self) -> List[str]:
        """Get list of available metrics for rankings"""
        return [
            'total_pnl_percentage',
            'win_rate', 
            'profit_factor',
            'sharpe_ratio',
            'max_drawdown_percentage',
            'total_trades',
            'avg_trade_duration',
            'trades_per_day'
        ]
    
    async def get_help_text(self) -> str:
        """Get help text for strategy comparison commands"""
        text = """
🏆 *Strategy Comparison Commands:*

🔍 *Basic Commands:*
• `/strategies` - List available strategies
• `/compare_run` - Start new comparison with defaults
• `/compare_recent` - Show your recent comparisons

⚙️ *Advanced Usage:*
• `/compare_run BTCUSDT,ETHUSDT 7` - Compare on specific pairs for 7 days
• `/compare_run default 30 Ultimate,Momentum` - Compare specific strategies

📊 *Results Commands:*
• `/compare_status <id>` - Check comparison progress
• `/compare_result <id>` - Show comparison results
• `/compare_rankings <id> <metric>` - Show rankings by metric
• `/compare_tips <id>` - Get recommendations

📈 *Available Metrics:*
• `total_pnl_percentage` - Total profit/loss
• `win_rate` - Percentage of winning trades
• `profit_factor` - Profit/loss ratio
• `sharpe_ratio` - Risk-adjusted returns
• `max_drawdown_percentage` - Maximum loss
• `total_trades` - Number of trades
• `trades_per_day` - Trading frequency

🎯 *Examples:*
• `/compare_run` - Quick comparison with defaults
• `/compare_result tg_123456789_20250912_141530`
• `/compare_rankings tg_123456789_20250912_141530 win_rate`
"""
        return text