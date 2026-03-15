#!/usr/bin/env python3
"""
Enhanced Trading Methods
Additional methods for the UltimateTradingBot with comprehensive error handling and stop loss integration
"""

import asyncio
import aiohttp
import logging
import time
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional, List

# Import enhanced systems with fallback
try:
    from advanced_error_handler import (
        ErrorDetails, ErrorCategory, ErrorSeverity,
        RateLimitException, APIException, NetworkException
    )
    from dynamic_stop_loss_system import create_stop_loss_manager
    ENHANCED_SYSTEMS_AVAILABLE = True
except ImportError:
    ENHANCED_SYSTEMS_AVAILABLE = False
    
    class ErrorDetails:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    class ErrorCategory:
        API = "api"
        TRADING = "trading"
    
    class ErrorSeverity:
        MEDIUM = "medium"
        HIGH = "high"
    
    class RateLimitException(Exception):
        def __init__(self, message, retry_after=None):
            super().__init__(message)
            self.retry_after = retry_after


class EnhancedTradingMethods:
    """Enhanced methods for comprehensive error handling and stop loss management"""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.logger = bot_instance.logger
        
    async def enhanced_send_message(self, chat_id: str, text: str, parse_mode='Markdown') -> bool:
        """Enhanced send_message with comprehensive error handling and resilience"""
        if not hasattr(self.bot, 'enhanced_systems_active') or not self.bot.enhanced_systems_active:
            return await self.fallback_send_message(chat_id, text, parse_mode)
        
        try:
            # Use resilient API call if available
            if hasattr(self.bot, 'resilience_manager') and self.bot.resilience_manager:
                return await self.bot.resilience_manager.make_resilient_api_call(
                    "telegram",
                    self.telegram_api_call,
                    chat_id, text, parse_mode
                )
            else:
                return await self.fallback_send_message(chat_id, text, parse_mode)
                
        except Exception as e:
            # Log error and attempt fallback
            if hasattr(self.bot, 'error_logger') and self.bot.error_logger:
                error_details = ErrorDetails(
                    error_id=f"telegram_send_{int(time.time())}",
                    timestamp=datetime.now(),
                    error_type=type(e).__name__,
                    error_message=str(e),
                    category=ErrorCategory.API,
                    severity=ErrorSeverity.MEDIUM,
                    source_function="enhanced_send_message",
                    context={"chat_id": chat_id, "text_length": len(text)}
                )
                await self.bot.error_logger.log_error(error_details)
            
            self.logger.error(f"Enhanced send_message failed: {e}")
            return await self.fallback_send_message(chat_id, text, parse_mode)
    
    async def telegram_api_call(self, chat_id: str, text: str, parse_mode: str) -> bool:
        """Core Telegram API call for resilience manager"""
        url = f"{self.bot.base_url}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode,
            'disable_web_page_preview': True
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    raise RateLimitException(f"Telegram rate limit", retry_after=retry_after)
                
                response.raise_for_status()
                result = await response.json()
                return result.get('ok', False)
    
    async def fallback_send_message(self, chat_id: str, text: str, parse_mode: str) -> bool:
        """Fallback send_message implementation"""
        try:
            url = f"{self.bot.base_url}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get('ok', False)
                    return False
        except Exception as e:
            self.logger.error(f"Fallback send_message failed: {e}")
            return False
    
    async def enhanced_get_binance_data(self, symbol: str, interval: str = '1h', limit: int = 100) -> Optional[pd.DataFrame]:
        """Enhanced get_binance_data with API resilience and error handling"""
        if not hasattr(self.bot, 'enhanced_systems_active') or not self.bot.enhanced_systems_active:
            return await self.fallback_get_binance_data(symbol, interval, limit)
        
        try:
            # Use resilient API call if available
            if hasattr(self.bot, 'resilience_manager') and self.bot.resilience_manager:
                klines_data = await self.bot.resilience_manager.make_resilient_api_call(
                    "binance",
                    self.binance_klines_call,
                    symbol, interval, limit
                )
            else:
                klines_data = await self.binance_klines_call(symbol, interval, limit)
            
            if not klines_data:
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(klines_data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            # Convert to proper data types
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            return df
            
        except Exception as e:
            # Log error and attempt fallback
            if hasattr(self.bot, 'error_logger') and self.bot.error_logger:
                error_details = ErrorDetails(
                    error_id=f"binance_data_{int(time.time())}",
                    timestamp=datetime.now(),
                    error_type=type(e).__name__,
                    error_message=str(e),
                    category=ErrorCategory.API,
                    severity=ErrorSeverity.HIGH,
                    source_function="enhanced_get_binance_data",
                    context={"symbol": symbol, "interval": interval, "limit": limit}
                )
                await self.bot.error_logger.log_error(error_details)
            
            self.logger.error(f"Enhanced get_binance_data failed for {symbol}: {e}")
            return await self.fallback_get_binance_data(symbol, interval, limit)
    
    async def binance_klines_call(self, symbol: str, interval: str, limit: int) -> List[List]:
        """Core Binance klines API call for resilience manager"""
        url = "https://api.binance.com/api/v3/klines"
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 429:
                    raise RateLimitException(f"Binance rate limit exceeded")
                
                if response.status == 418:
                    raise RateLimitException(f"Binance IP banned", retry_after=300)
                
                response.raise_for_status()
                return await response.json()
    
    async def fallback_get_binance_data(self, symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
        """Fallback get_binance_data implementation"""
        try:
            url = "https://api.binance.com/api/v3/klines"
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    if not data:
                        return None
                    
                    df = pd.DataFrame(data, columns=[
                        'timestamp', 'open', 'high', 'low', 'close', 'volume',
                        'close_time', 'quote_asset_volume', 'number_of_trades',
                        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                    ])
                    
                    numeric_columns = ['open', 'high', 'low', 'close', 'volume']
                    for col in numeric_columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df.set_index('timestamp', inplace=True)
                    
                    return df
                    
        except Exception as e:
            self.logger.error(f"Fallback get_binance_data failed for {symbol}: {e}")
            return None
    
    async def create_stop_loss_manager_for_signal(self, signal: Dict[str, Any]) -> Optional[str]:
        """Create and manage 3-level stop loss system for a trading signal"""
        if not ENHANCED_SYSTEMS_AVAILABLE:
            self.logger.warning("Enhanced systems not available, skipping stop loss creation")
            return None
        
        if not hasattr(self.bot, 'enhanced_systems_active') or not self.bot.enhanced_systems_active:
            self.logger.warning("Enhanced systems not active, skipping stop loss creation")
            return None
        
        try:
            symbol = signal.get('symbol')
            direction = signal.get('direction', 'long').lower()
            entry_price = signal.get('price', 0)
            
            if not symbol or not entry_price:
                self.logger.error(f"Invalid signal data for stop loss creation: {signal}")
                return None
            
            # Calculate position size based on risk management
            position_size = self.calculate_position_size(signal)
            
            # Get market data for analysis
            df = await self.enhanced_get_binance_data(symbol, '1h', 100)
            if df is None or len(df) < 20:
                self.logger.warning(f"Insufficient market data for {symbol} stop loss analysis")
                market_conditions = None
            else:
                # Analyze market conditions if market analyzer is available
                if hasattr(self.bot, 'market_analyzer') and self.bot.market_analyzer:
                    price_data = [{
                        'high': row['high'],
                        'low': row['low'],
                        'close': row['close'],
                        'volume': row['volume']
                    } for _, row in df.iterrows()]
                    
                    market_conditions = self.bot.market_analyzer.analyze_market_conditions(
                        symbol, price_data, entry_price
                    )
                else:
                    market_conditions = None
            
            # Create stop loss manager
            manager = create_stop_loss_manager(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                position_size=position_size,
                config=getattr(self.bot, 'stop_loss_config', None)
            )
            
            # Store manager
            manager_id = f"{symbol}_{direction}_{int(entry_price * 1000000)}"
            if not hasattr(self.bot, 'active_stop_loss_managers'):
                self.bot.active_stop_loss_managers = {}
            
            self.bot.active_stop_loss_managers[manager_id] = manager
            
            self.logger.info(
                f"🛡️ Created 3-level stop loss manager for {symbol} {direction} @ {entry_price:.6f}"
            )
            
            return manager_id
            
        except Exception as e:
            if hasattr(self.bot, 'error_logger') and self.bot.error_logger:
                error_details = ErrorDetails(
                    error_id=f"stop_loss_create_{int(time.time())}",
                    timestamp=datetime.now(),
                    error_type=type(e).__name__,
                    error_message=str(e),
                    category=ErrorCategory.TRADING,
                    severity=ErrorSeverity.HIGH,
                    source_function="create_stop_loss_manager_for_signal",
                    context={"signal": signal}
                )
                await self.bot.error_logger.log_error(error_details)
            
            self.logger.error(f"Error creating stop loss manager: {e}")
            return None
    
    def calculate_position_size(self, signal: Dict[str, Any]) -> float:
        """Calculate position size based on risk management"""
        try:
            # Use existing risk management logic
            risk_amount = getattr(self.bot, 'risk_per_trade_amount', 1.0)  # Default $1.00 per trade
            entry_price = signal.get('price', 0)
            
            if not entry_price:
                return 0.0
            
            # Calculate position size based on 1% stop loss
            position_size = risk_amount / (entry_price * 0.01)
            
            return max(10.0, min(position_size, 1000.0))  # Limit between $10-$1000
            
        except Exception as e:
            self.logger.error(f"Error calculating position size: {e}")
            return 100.0  # Default fallback
    
    async def monitor_stop_losses(self):
        """Monitor all active stop loss managers and handle triggers"""
        if not hasattr(self.bot, 'active_stop_loss_managers') or not self.bot.active_stop_loss_managers:
            return
        
        try:
            triggered_stops = []
            
            for manager_id, manager in list(self.bot.active_stop_loss_managers.items()):
                try:
                    # Get current price
                    current_price = await self.get_current_price(manager.symbol)
                    if not current_price:
                        continue
                    
                    # Update stop losses with current market conditions
                    triggered_levels = await manager.update_market_conditions(current_price)
                    
                    if triggered_levels:
                        triggered_stops.extend([
                            {**trigger, 'manager_id': manager_id, 'symbol': manager.symbol}
                            for trigger in triggered_levels
                        ])
                        
                        # Notify about triggered stop losses
                        await self.handle_stop_loss_triggers(manager_id, triggered_levels)
                    
                    # Remove completed managers
                    if not manager.active:
                        del self.bot.active_stop_loss_managers[manager_id]
                        self.logger.info(f"🏁 Completed stop loss manager for {manager.symbol}")
                
                except Exception as e:
                    self.logger.error(f"Error monitoring stop loss {manager_id}: {e}")
                    continue
            
            if triggered_stops:
                self.logger.info(f"🛑 Processed {len(triggered_stops)} stop loss triggers")
                
        except Exception as e:
            self.logger.error(f"Error in stop loss monitoring: {e}")
    
    async def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for symbol"""
        try:
            # Use enhanced method if available
            df = await self.enhanced_get_binance_data(symbol, '1m', 1)
            if df is not None and len(df) > 0:
                return float(df['close'].iloc[-1])
            return None
        except Exception as e:
            self.logger.error(f"Error getting current price for {symbol}: {e}")
            return None
    
    async def handle_stop_loss_triggers(self, manager_id: str, triggered_levels: List[Dict]):
        """Handle stop loss trigger notifications and actions"""
        try:
            for trigger in triggered_levels:
                level = trigger.get('level')
                symbol = trigger.get('symbol')
                trigger_price = trigger.get('trigger_price')
                close_amount = trigger.get('close_amount')
                
                # Create notification message
                message = f"🛑 **STOP LOSS TRIGGERED**\n\n"
                message += f"**Symbol:** {symbol}\n"
                message += f"**Level:** {level.upper()}\n"
                message += f"**Trigger Price:** {trigger_price:.6f}\n"
                message += f"**Position Closed:** {close_amount:.6f} ({trigger.get('position_percent', 0):.1f}%)\n"
                message += f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                message += f"⚠️ **Remaining Position:** {trigger.get('remaining_position', 0):.6f}"
                
                # Send notification to admin if available
                if hasattr(self.bot, 'admin_chat_id') and self.bot.admin_chat_id:
                    await self.enhanced_send_message(self.bot.admin_chat_id, message)
                
                # Log trigger event
                self.logger.warning(
                    f"🛑 {level.upper()} triggered for {symbol} at {trigger_price:.6f}"
                )
                
        except Exception as e:
            self.logger.error(f"Error handling stop loss triggers: {e}")
    
    def get_enhanced_system_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all enhanced systems"""
        status = {
            'enhanced_systems_active': getattr(self.bot, 'enhanced_systems_active', False),
            'timestamp': datetime.now().isoformat()
        }
        
        if getattr(self.bot, 'enhanced_systems_active', False):
            try:
                # Error handling status
                if hasattr(self.bot, 'error_handler') and self.bot.error_handler:
                    status['error_handler'] = self.bot.error_handler.get_error_statistics()
                
                # Error logging status  
                if hasattr(self.bot, 'error_logger') and self.bot.error_logger:
                    status['error_logger'] = self.bot.error_logger.get_error_summary()
                
                # API resilience status
                if hasattr(self.bot, 'resilience_manager') and self.bot.resilience_manager:
                    status['api_resilience'] = self.bot.resilience_manager.get_service_health()
                
                # Stop loss system status
                active_managers = getattr(self.bot, 'active_stop_loss_managers', {})
                status['stop_loss_system'] = {
                    'active_managers': len(active_managers),
                    'managers': {
                        manager_id: manager.get_stop_loss_status()
                        for manager_id, manager in active_managers.items()
                    }
                }
                
            except Exception as e:
                status['error'] = f"Error getting system status: {e}"
        
        return status


# Integration helper function
def integrate_enhanced_methods(bot_instance):
    """Integrate enhanced methods into the bot instance"""
    try:
        enhanced_methods = EnhancedTradingMethods(bot_instance)
        
        # Store original methods
        bot_instance._original_send_message = getattr(bot_instance, 'send_message', None)
        bot_instance._original_get_binance_data = getattr(bot_instance, 'get_binance_data', None)
        
        # Replace with enhanced methods
        bot_instance.send_message = enhanced_methods.enhanced_send_message
        bot_instance.get_binance_data = enhanced_methods.enhanced_get_binance_data
        bot_instance.create_stop_loss_manager_for_signal = enhanced_methods.create_stop_loss_manager_for_signal
        bot_instance.monitor_stop_losses = enhanced_methods.monitor_stop_losses
        bot_instance.get_enhanced_system_status = enhanced_methods.get_enhanced_system_status
        
        # Store reference to enhanced methods
        bot_instance._enhanced_methods = enhanced_methods
        
        bot_instance.logger.info("✅ Enhanced methods integrated successfully")
        return True
        
    except Exception as e:
        bot_instance.logger.error(f"Error integrating enhanced methods: {e}")
        return False