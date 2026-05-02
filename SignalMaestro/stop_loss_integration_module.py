#!/usr/bin/env python3
"""
Stop Loss Integration Module
Provides complete integration of dynamic stop loss system into live trading pipeline
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass

# Enhanced systems imports with fallback
try:
    from SignalMaestro.dynamic_stop_loss_system import (
        create_stop_loss_manager, DynamicStopLoss, StopLossConfig,
        StopLossLevel, VolatilityLevel, MarketSession, get_stop_loss_manager
    )
    ENHANCED_SYSTEMS_AVAILABLE = True
except ImportError:
    ENHANCED_SYSTEMS_AVAILABLE = False
    
# Error handling imports with fallback
try:
    from advanced_error_handler import handle_errors, APIException, TradingException
    from api_resilience_layer import resilient_api_call
    ERROR_HANDLING_AVAILABLE = True
except ImportError:
    ERROR_HANDLING_AVAILABLE = False
    
    # Create fallback classes when error handling is not available
    class APIException(Exception):
        pass
    
    class TradingException(Exception):
        pass
    
    def handle_errors(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    
    def resilient_api_call(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

# Fallback for when enhanced systems are not available
if not ENHANCED_SYSTEMS_AVAILABLE:
    class StopLossConfig:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
    
    async def create_stop_loss_manager(*args, **kwargs):
        # Return a mock manager object
        class MockStopLossManager:
            async def update_price(self, price):
                return []
            def get_current_status(self):
                return {'stop_loss': {'current_price': 0}}
        return MockStopLossManager()


@dataclass
class StopLossAction:
    """Represents a stop loss action that needs to be executed"""
    symbol: str
    level: str  # 'SL1', 'SL2', 'SL3'
    percentage: float  # Percentage of position to close
    price: float  # Current price when triggered
    reason: str  # Reason for closure


class StopLossIntegrator:
    """Integrates dynamic stop loss system into trading bots"""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.logger = logging.getLogger(__name__)
        self.stop_loss_managers: Dict[str, Any] = {}
        self.enhanced_systems_active = ENHANCED_SYSTEMS_AVAILABLE
        
        if ENHANCED_SYSTEMS_AVAILABLE:
            # Configure stop loss for scalping strategy
            self.stop_loss_config = StopLossConfig(
                sl1_base_percent=1.5,  # Tight SL for scalping
                sl2_base_percent=3.0,  # Medium SL
                sl3_base_percent=5.0,  # Wide SL
                sl1_position_percent=33.0,  # Close 33% at SL1
                sl2_position_percent=33.0,  # Close 33% at SL2
                sl3_position_percent=34.0,  # Close 34% at SL3
                trailing_enabled=True,
                trailing_distance_percent=0.5  # 0.5% trailing for scalping
            )
            self.logger.info("✅ Stop loss integration initialized successfully")
        else:
            self.logger.warning("⚠️ Enhanced stop loss system not available")
    
    async def create_trade_stop_loss(self, symbol: str, direction: str, entry_price: float, position_size: Optional[float] = None) -> bool:
        """Create stop loss manager for a new trade"""
        if not self.enhanced_systems_active:
            self.logger.warning(f"⚠️ Stop loss creation not available for {symbol}")
            return False
            
        try:
            # CRITICAL FIX: Compute actual position size instead of hardcoded 100.0
            actual_position_size = position_size
            if actual_position_size is None:
                # Calculate position size based on risk management
                actual_position_size = await self._calculate_position_size(symbol, entry_price, direction)
                self.logger.info(f"🧮 Calculated position size for {symbol}: {actual_position_size}")
            else:
                self.logger.info(f"📊 Using provided position size for {symbol}: {actual_position_size}")
            
            # Create stop loss manager with REAL position size
            stop_loss_manager = await create_stop_loss_manager(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                position_size=actual_position_size,
                config=self.stop_loss_config
            )
            
            # Store the manager
            self.stop_loss_managers[symbol] = stop_loss_manager
            
            self.logger.info(f"🛡️ Dynamic stop loss system activated for {symbol}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to create stop loss manager for {symbol}: {e}")
            return False
    
    async def update_stop_loss_price(self, symbol: str, current_price: float) -> List[StopLossAction]:
        """Update stop loss with current price and return any triggered actions"""
        if not self.enhanced_systems_active or symbol not in self.stop_loss_managers:
            return []
            
        try:
            stop_loss_manager = self.stop_loss_managers[symbol]
            
            # Update with current price
            sl_actions = await stop_loss_manager.update_price(current_price)
            
            # Convert 3SL/1TP events to StopLossAction objects
            actions = []
            for event in sl_actions:
                if event.get('type') == 'take_profit':
                    # Map TP events to concrete actions
                    tp_level = event.get('level')  # 'tp1', 'tp2', 'tp3'
                    close_percent = event.get('close_percent', 33.0)
                    
                    actions.append(StopLossAction(
                        symbol=symbol,
                        level=f"TP{tp_level.upper()[-1]}" if tp_level else "TP",  # Convert tp1 -> TP1
                        percentage=close_percent,
                        price=current_price,
                        reason=f"TP{tp_level.upper()[-1]} hit - partial close {close_percent}%" if tp_level else "TP hit"
                    ))
                elif event.get('type') == 'stop_loss':
                    # Handle stop loss events - get actual remaining position percentage
                    stop_loss_manager = self.stop_loss_managers[symbol]
                    if hasattr(stop_loss_manager, 'remaining_position_size') and hasattr(stop_loss_manager, 'position_size'):
                        remaining_percent = (stop_loss_manager.remaining_position_size / stop_loss_manager.position_size) * 100
                    else:
                        remaining_percent = 100.0  # Fallback to close all
                    
                    actions.append(StopLossAction(
                        symbol=symbol,
                        level="SL",
                        percentage=remaining_percent,
                        price=current_price,
                        reason=f"Stop loss triggered - close remaining {remaining_percent:.1f}% position"
                    ))
            
            return actions
            
        except Exception as e:
            self.logger.error(f"❌ Stop loss update error for {symbol}: {e}")
            return []
    
    async def _calculate_position_size(self, symbol: str, entry_price: float, direction: str) -> float:
        """Calculate actual position size based on risk management"""
        try:
            # Default position size if no risk manager available
            default_position_size = 0.001  # Conservative default (0.001 BTC for example)
            
            # Try to use bot's risk manager if available
            if hasattr(self.bot, 'risk_manager') and self.bot.risk_manager:
                # Create a basic signal dict for risk calculation
                signal = {
                    'symbol': symbol,
                    'price': entry_price,
                    'action': 'LONG' if direction.lower() == 'long' else 'SHORT',
                    'stop_loss': entry_price * 0.985 if direction.lower() == 'long' else entry_price * 1.015  # 1.5% SL
                }
                
                risk_result = await self.bot.risk_manager.calculate_risk_metrics(signal)
                if risk_result and 'position_size' in risk_result:
                    calculated_size = risk_result['position_size']
                    self.logger.info(f"📊 Risk manager calculated position size: {calculated_size}")
                    return max(calculated_size, 0.0001)  # Minimum position size
                    
            # Fallback: Calculate based on available balance (if accessible)
            if hasattr(self.bot, 'binance_trader') and self.bot.binance_trader:
                try:
                    # Try to get account balance
                    balance = await self.bot.binance_trader.get_account_balance()
                    if balance and balance > 0:
                        # Risk 1% of balance
                        risk_amount = balance * 0.01
                        sl_distance = entry_price * 0.015  # 1.5% stop loss
                        position_size = risk_amount / sl_distance
                        self.logger.info(f"💰 Calculated position size from balance: {position_size}")
                        return max(position_size, 0.0001)
                except Exception as e:
                    self.logger.warning(f"⚠️ Could not get balance for position calculation: {e}")
            
            # Final fallback
            self.logger.warning(f"⚠️ Using default position size for {symbol}: {default_position_size}")
            return default_position_size
            
        except Exception as e:
            self.logger.error(f"❌ Error calculating position size: {e}")
            return 0.001  # Safe fallback
    
    async def execute_stop_loss_action(self, action: StopLossAction) -> bool:
        """Execute a stop loss partial closure action"""
        try:
            self.logger.info(f"🚨 Executing {action.level} for {action.symbol}: {action.percentage}% at {action.price}")
            
            # Execute partial closure via Binance if available
            if hasattr(self.bot, 'binance_trader') and self.bot.binance_trader:
                success = await self._execute_binance_partial_close(action)
                if not success:
                    self.logger.warning(f"⚠️ Binance partial close failed for {action.symbol}")
            
            # Execute partial closure via Cornix if available
            if hasattr(self.bot, 'cornix') and self.bot.cornix:
                cornix_success = await self._execute_cornix_partial_close(action)
                if not cornix_success:
                    self.logger.warning(f"⚠️ Cornix partial close failed for {action.symbol}")
            
            # Send notification if rate limiter allows
            if hasattr(self.bot, 'rate_limiter') and self.bot.rate_limiter.can_send_message():
                await self._send_stop_loss_notification(action)
            
            self.logger.info(f"✅ {action.level} executed for {action.symbol}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to execute stop loss action: {e}")
            if ENHANCED_SYSTEMS_AVAILABLE:
                raise TradingException(f"Stop loss execution failed: {e}")
            return False
    
    async def _execute_binance_partial_close(self, action: StopLossAction) -> bool:
        """Execute REAL partial position closure via Binance with proper exchange filters"""
        try:
            self.logger.info(f"🔥 REAL BINANCE PARTIAL CLOSE: {action.symbol} {action.percentage}% - {action.level}")
            
            if not (hasattr(self.bot, 'binance_trader') and self.bot.binance_trader):
                self.logger.warning(f"⚠️ Binance trader not available for {action.symbol}")
                return False
                
            binance = self.bot.binance_trader
            
            # STEP 1: Get current price and verify it's valid
            current_price = await binance.get_current_price(action.symbol)
            if not current_price:
                self.logger.error(f"❌ CRITICAL: Could not get current price for {action.symbol}")
                return False
            
            self.logger.info(f"📊 Current price for {action.symbol}: {current_price}")
            
            # STEP 2: Get current position information
            try:
                position_info = await binance.get_position_info(action.symbol)
                if not position_info:
                    self.logger.error(f"❌ CRITICAL: No position found for {action.symbol}")
                    return False
                    
                current_position_size = abs(float(position_info.get('positionAmt', 0)))
                if current_position_size <= 0:
                    self.logger.warning(f"⚠️ No open position for {action.symbol}")
                    return True  # Nothing to close
                    
                self.logger.info(f"📈 Current position size: {current_position_size}")
                
            except Exception as e:
                self.logger.error(f"❌ Failed to get position info: {e}")
                return False
            
            # STEP 3: Calculate actual quantity to close with exchange filters
            try:
                close_quantity = (action.percentage / 100.0) * current_position_size
                
                # Apply Binance filters (get exchange info)
                exchange_info = await binance.get_exchange_info(action.symbol)
                if exchange_info:
                    # Apply lot size filter
                    for filter_info in exchange_info.get('filters', []):
                        if filter_info['filterType'] == 'LOT_SIZE':
                            min_qty = float(filter_info['minQty'])
                            max_qty = float(filter_info['maxQty'])
                            step_size = float(filter_info['stepSize'])
                            
                            # Round to step size
                            close_quantity = round(close_quantity / step_size) * step_size
                            close_quantity = max(min_qty, min(close_quantity, max_qty))
                            break
                            
                self.logger.info(f"🧮 Calculated close quantity (filtered): {close_quantity}")
                
            except Exception as e:
                self.logger.error(f"❌ Failed to calculate close quantity: {e}")
                return False
            
            # STEP 4: Execute REAL market order for partial close
            try:
                if action.level in ['TP1', 'TP2', 'TP3']:
                    self.logger.critical(f"🎯 EXECUTING REAL {action.level} PARTIAL CLOSE:")
                    self.logger.critical(f"   Symbol: {action.symbol}")
                    self.logger.critical(f"   Quantity: {close_quantity}")
                    self.logger.critical(f"   Price: {current_price}")
                    self.logger.critical(f"   Percentage: {action.percentage}%")
                    
                    # Execute the actual close order
                    order_result = await binance.place_market_order(
                        symbol=action.symbol,
                        side='SELL',  # Always sell for partial close
                        quantity=close_quantity,
                        order_type='MARKET'
                    )
                    
                    if order_result and order_result.get('status') == 'FILLED':
                        filled_qty = float(order_result.get('executedQty', 0))
                        avg_price = float(order_result.get('avgPrice', current_price))
                        
                        self.logger.critical(f"✅ {action.level} EXECUTED SUCCESSFULLY:")
                        self.logger.critical(f"   Filled quantity: {filled_qty}")
                        self.logger.critical(f"   Average price: {avg_price}")
                        self.logger.critical(f"   Order ID: {order_result.get('orderId')}")
                        return True
                    else:
                        self.logger.error(f"❌ CRITICAL: {action.level} order failed: {order_result}")
                        return False
                        
                elif action.level == "SL":
                    self.logger.critical(f"🛑 EXECUTING REAL STOP LOSS CLOSE:")
                    self.logger.critical(f"   Symbol: {action.symbol}")
                    self.logger.critical(f"   Quantity: {close_quantity}")
                    self.logger.critical(f"   Price: {current_price}")
                    
                    # Execute stop loss close
                    order_result = await binance.place_market_order(
                        symbol=action.symbol,
                        side='SELL',  # Always sell for stop loss
                        quantity=close_quantity,
                        order_type='MARKET'
                    )
                    
                    if order_result and order_result.get('status') == 'FILLED':
                        self.logger.critical(f"✅ STOP LOSS EXECUTED - Position protected")
                        return True
                    else:
                        self.logger.critical(f"❌ CRITICAL: Stop loss order failed: {order_result}")
                        return False
                        
            except Exception as e:
                self.logger.critical(f"❌ CRITICAL FAILURE: Binance order execution failed: {e}")
                return False
            
        except Exception as e:
            self.logger.critical(f"❌ CRITICAL FAILURE in Binance partial close: {e}")
            return False
    
    async def _execute_cornix_partial_close(self, action: StopLossAction) -> bool:
        """Execute partial position closure via Cornix with proper TP/SL logic"""
        try:
            if hasattr(self.bot, 'cornix') and self.bot.cornix:
                cornix = self.bot.cornix
                
                # Handle different action types properly
                if action.level in ['TP1', 'TP2']:
                    # Partial take profit + SL move
                    tp_level = int(action.level.replace('TP', ''))
                    
                    # Execute partial take profit
                    if hasattr(cornix, 'partial_take_profit'):
                        tp_result = await cornix.partial_take_profit(
                            action.symbol,
                            tp_level,
                            int(action.percentage)
                        )
                        
                        if tp_result.get('success', False):
                            self.logger.info(f"✅ Cornix partial TP executed: {action.symbol} {action.level} ({action.percentage}%)")
                            
                            # Now move the stop loss
                            await self._execute_cornix_sl_move(action, tp_level)
                            return True
                        else:
                            self.logger.warning(f"⚠️ Cornix partial TP failed: {tp_result.get('error')}")
                            return False
                    else:
                        # Fallback to regular close_position
                        return await self._execute_cornix_regular_close(action)
                        
                elif action.level == 'TP3':
                    # Final TP - close entire remaining position
                    if hasattr(cornix, 'close_position'):
                        result = await cornix.close_position(
                            action.symbol,
                            "TP3 hit - final closure",
                            100  # Close remaining position
                        )
                        success = result.get('success', False) if isinstance(result, dict) else bool(result)
                        if success:
                            self.logger.info(f"🏆 Cornix TP3 full closure executed: {action.symbol}")
                        return success
                    else:
                        return await self._execute_cornix_regular_close(action)
                        
                elif action.level == 'SL':
                    # Stop loss hit - close remaining position
                    if hasattr(cornix, 'close_position'):
                        result = await cornix.close_position(
                            action.symbol,
                            "Stop loss hit - emergency closure",
                            100
                        )
                        success = result.get('success', False) if isinstance(result, dict) else bool(result)
                        if success:
                            self.logger.warning(f"🛑 Cornix SL closure executed: {action.symbol}")
                        return success
                    else:
                        return await self._execute_cornix_regular_close(action)
                        
                else:
                    self.logger.warning(f"⚠️ Unknown action level: {action.level}")
                    return False
            else:
                self.logger.warning(f"⚠️ Cornix integration not available")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Cornix execution error: {e}")
            return False
    
    async def _execute_cornix_sl_move(self, action: StopLossAction, tp_level: int) -> bool:
        """Execute stop loss move after TP hit"""
        try:
            cornix = self.bot.cornix
            
            # Get the new SL price from the stop loss manager
            if action.symbol in self.stop_loss_managers:
                manager = self.stop_loss_managers[action.symbol]
                status = manager.get_current_status()
                new_sl_price = status.get('stop_loss', {}).get('current_price')
                
                if new_sl_price and hasattr(cornix, 'update_stop_loss'):
                    sl_reason = f"TP{tp_level} hit - SL moved"
                    if tp_level == 1:
                        sl_reason = "TP1 hit - SL moved to entry price"
                    elif tp_level == 2:
                        sl_reason = "TP2 hit - SL moved to TP1 price"
                    
                    sl_result = await cornix.update_stop_loss(
                        action.symbol,
                        new_sl_price,
                        sl_reason
                    )
                    
                    success = sl_result.get('success', False) if isinstance(sl_result, dict) else bool(sl_result)
                    if success:
                        self.logger.info(f"✅ Cornix SL moved: {action.symbol} -> {new_sl_price:.6f}")
                    else:
                        self.logger.warning(f"⚠️ Cornix SL move failed: {sl_result.get('error')}")
                    return success
                else:
                    self.logger.warning(f"⚠️ Could not determine new SL price or update_stop_loss not available")
                    return False
            else:
                self.logger.warning(f"⚠️ No stop loss manager found for {action.symbol}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ SL move error: {e}")
            return False
    
    async def _execute_cornix_regular_close(self, action: StopLossAction) -> bool:
        """Fallback to regular close_position method"""
        try:
            if hasattr(self.bot.cornix, 'close_position'):
                result = await self.bot.cornix.close_position(
                    action.symbol,
                    f"{action.level} triggered - {action.reason}",
                    int(action.percentage)
                )
                return result.get('success', False) if isinstance(result, dict) else bool(result)
            else:
                self.logger.warning(f"⚠️ Cornix close_position method not available")
                return False
        except Exception as e:
            self.logger.error(f"❌ Cornix regular close error: {e}")
            return False
    
    async def _send_stop_loss_notification(self, action: StopLossAction):
        """Send stop loss notification"""
        try:
            level_emoji = {"SL1": "🟡", "SL2": "🟠", "SL3": "🔴"}.get(action.level, "🚨")
            
            msg = f"""{level_emoji} **{action.level} TRIGGERED** - {action.symbol}

🚨 **Stop Loss Hit:** {action.price:.4f}
📊 **Position Closed:** {action.percentage}%
💡 **Reason:** {action.reason}
🛡️ **Risk Management:** Active"""

            if hasattr(self.bot, 'send_rate_limited_message'):
                await self.bot.send_rate_limited_message(self.bot.admin_chat_id, msg)
            
        except Exception as e:
            self.logger.error(f"❌ Notification error: {e}")
    
    def cleanup_stop_loss_manager(self, symbol: str):
        """Clean up stop loss manager for completed trade"""
        if symbol in self.stop_loss_managers:
            try:
                del self.stop_loss_managers[symbol]
                self.logger.debug(f"🧹 Stop loss manager cleaned up for {symbol}")
            except Exception as e:
                self.logger.error(f"❌ Error cleaning up stop loss manager for {symbol}: {e}")
    
    def get_active_stop_losses(self) -> List[str]:
        """Get list of symbols with active stop loss managers"""
        return list(self.stop_loss_managers.keys())
    
    def is_stop_loss_active(self, symbol: str) -> bool:
        """Check if stop loss is active for a symbol"""
        return symbol in self.stop_loss_managers and self.enhanced_systems_active


# Export the integrator for easy import
__all__ = ['StopLossIntegrator', 'StopLossAction']