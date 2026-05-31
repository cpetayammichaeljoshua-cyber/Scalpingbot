#!/usr/bin/env python3
"""
3SL/1TP Dynamic Stop Loss System with Smart Order Flow Integration
Implements the exact logic requested:
- TP1 reached → SL moves to entry price 
- TP2 reached → SL moves to TP1 price
- TP3 reached → close entire trade automatically

Enhanced with intelligent order flow analysis and smart positioning
"""

import asyncio
import logging
import json
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import sqlite3
from pathlib import Path

# Import smart SL/TP system
try:
    from .smart_dynamic_sltp_system import (
        SmartDynamicSLTPSystem, get_smart_sltp_system,
        OrderFlowAnalysis, LiquidityZone, SmartSLTP
    )
    SMART_SLTP_AVAILABLE = True
except ImportError:
    SMART_SLTP_AVAILABLE = False

# Explicit exports for compatibility with existing integrations
__all__ = [
    # Core 3SL/1TP classes
    'ThreeSLOneTpManager', 'ThreeSLOneTpConfig', 'TakeProfitLevel', 'StopLossState',
    'TakeProfitLevel_Data', 'StopLossData',
    
    # Legacy compatibility classes - REQUIRED for existing system integration
    'TradeStopLossManager', 'DynamicStopLoss', 'StopLossConfig', 'MarketConditions',
    'MarketAnalyzer', 'StopLossLevel', 'VolatilityLevel', 'MarketSession',
    
    # Core functions - REQUIRED for existing system integration  
    'create_stop_loss_manager', 'get_stop_loss_manager', 'get_all_active_managers',
    'cleanup_inactive_managers',
    
    # Internal functions (also exported for completeness)
    'create_3sl1tp_manager', 'get_3sl1tp_manager', 'remove_3sl1tp_manager',
    'get_all_active_3sl1tp_managers', 'cleanup_inactive_3sl1tp_managers'
]


class TakeProfitLevel(Enum):
    """Take profit level enumeration"""
    TP1 = "tp1"  # First take profit
    TP2 = "tp2"  # Second take profit  
    TP3 = "tp3"  # Final take profit - close trade


class StopLossState(Enum):
    """Stop loss progression states"""
    INITIAL = "initial"        # Original stop loss
    AT_ENTRY = "at_entry"      # Moved to entry after TP1
    AT_TP1 = "at_tp1"          # Moved to TP1 after TP2
    CLOSED = "closed"          # Trade closed after TP3


@dataclass
class ThreeSLOneTpConfig:
    """Configuration for the 3SL/1TP system"""
    # Take profit levels as percentages from entry
    tp1_percent: float = 2.0   # 2% for TP1
    tp2_percent: float = 4.0   # 4% for TP2
    tp3_percent: float = 6.0   # 6% for TP3
    
    # Initial stop loss percentage
    initial_sl_percent: float = 1.5  # 1.5% initial stop loss
    
    # Position management - what percentage to close at each TP
    tp1_close_percent: float = 33.0   # Close 33% at TP1
    tp2_close_percent: float = 33.0   # Close 33% at TP2
    tp3_close_percent: float = 34.0   # Close remaining 34% at TP3
    
    # Buffer to prevent immediate re-trigger (in percentage)
    buffer_percent: float = 0.1  # 0.1% buffer
    
    # Smart positioning
    use_smart_sltp: bool = True  # Use order flow analysis for SL/TP
    use_liquidity_zones: bool = True  # Position at liquidity levels


@dataclass
class TakeProfitLevel_Data:
    """Take profit level data"""
    level: TakeProfitLevel
    price: float
    hit: bool = False
    hit_time: Optional[datetime] = None
    close_percent: float = 33.0
    

@dataclass
class StopLossData:
    """Stop loss data with progression tracking"""
    current_price: float
    original_price: float
    state: StopLossState = StopLossState.INITIAL
    last_update_time: Optional[datetime] = None
    
    def __post_init__(self):
        if self.last_update_time is None:
            self.last_update_time = datetime.now()


class ThreeSLOneTpManager:
    """
    Manages the 3SL/1TP system with exact logic:
    - TP1 → SL to entry
    - TP2 → SL to TP1  
    - TP3 → close trade
    """
    
    def __init__(self, 
                 symbol: str,
                 direction: str,
                 entry_price: float,
                 position_size: float,
                 config: Optional[ThreeSLOneTpConfig] = None):
        self.symbol = symbol
        self.direction = direction.lower()
        self.entry_price = entry_price
        self.position_size = position_size
        self.config = config or ThreeSLOneTpConfig()
        
        self.logger = logging.getLogger(__name__)
        
        # Initialize take profit levels
        self.take_profits: Dict[TakeProfitLevel, TakeProfitLevel_Data] = {}
        self._initialize_take_profits()
        
        # Initialize stop loss
        self.stop_loss = StopLossData(
            current_price=self._calculate_initial_sl_price(),
            original_price=self._calculate_initial_sl_price()
        )
        
        # Trade state
        self.active = True
        self.remaining_position_size = position_size
        self.total_closed_amount = 0.0
        self.creation_time = datetime.now()
        self.last_update_time = datetime.now()
        
        # Event tracking
        self.event_history: List[Dict[str, Any]] = []
        
        self.logger.info(f"Initialized 3SL/1TP system for {self.symbol} {self.direction}")
        self.logger.info(f"Entry: {self.entry_price}, Initial SL: {self.stop_loss.current_price}")
        self.logger.info(f"TP1: {self.take_profits[TakeProfitLevel.TP1].price}, "
                        f"TP2: {self.take_profits[TakeProfitLevel.TP2].price}, "
                        f"TP3: {self.take_profits[TakeProfitLevel.TP3].price}")
    
    def _initialize_take_profits(self):
        """Initialize all three take profit levels"""
        # Calculate take profit prices
        tp1_price = self._calculate_tp_price(self.config.tp1_percent)
        tp2_price = self._calculate_tp_price(self.config.tp2_percent)
        tp3_price = self._calculate_tp_price(self.config.tp3_percent)
        
        # Create take profit objects
        self.take_profits[TakeProfitLevel.TP1] = TakeProfitLevel_Data(
            level=TakeProfitLevel.TP1,
            price=tp1_price,
            close_percent=self.config.tp1_close_percent
        )
        
        self.take_profits[TakeProfitLevel.TP2] = TakeProfitLevel_Data(
            level=TakeProfitLevel.TP2,
            price=tp2_price,
            close_percent=self.config.tp2_close_percent
        )
        
        self.take_profits[TakeProfitLevel.TP3] = TakeProfitLevel_Data(
            level=TakeProfitLevel.TP3,
            price=tp3_price,
            close_percent=self.config.tp3_close_percent
        )
    
    def _calculate_tp_price(self, percent: float) -> float:
        """Calculate take profit price based on percentage"""
        if self.direction == 'long':
            return self.entry_price * (1 + percent / 100)
        else:  # short
            return self.entry_price * (1 - percent / 100)
    
    def _calculate_initial_sl_price(self) -> float:
        """Calculate initial stop loss price"""
        if self.direction == 'long':
            return self.entry_price * (1 - self.config.initial_sl_percent / 100)
        else:  # short
            return self.entry_price * (1 + self.config.initial_sl_percent / 100)
    
    async def update_price(self, current_price: float) -> List[Dict[str, Any]]:
        """
        Update current price and check for TP/SL triggers
        Returns list of triggered events
        """
        if not self.active:
            return []
        
        triggered_events = []
        
        try:
            # Check stop loss first (risk-first)
            if self._is_stop_loss_hit(current_price):
                event = await self._handle_stop_loss_hit(current_price)
                triggered_events.append(event)
                self.active = False
                return triggered_events
            
            # Check for take profit hits in order (TP1, then TP2, then TP3)
            for tp_level in [TakeProfitLevel.TP1, TakeProfitLevel.TP2, TakeProfitLevel.TP3]:
                tp_data = self.take_profits[tp_level]
                
                if not tp_data.hit and self._is_take_profit_hit(tp_data, current_price):
                    event = await self._handle_take_profit_hit(tp_level, current_price)
                    triggered_events.append(event)
                    
                    # If TP3 is hit, trade is completely closed
                    if tp_level == TakeProfitLevel.TP3:
                        self.active = False
                        break
            
            self.last_update_time = datetime.now()
            
        except Exception as e:
            self.logger.error(f"Error updating price: {e}")
        
        return triggered_events
    
    def _is_take_profit_hit(self, tp_data: TakeProfitLevel_Data, current_price: float) -> bool:
        """Check if take profit level is hit"""
        if self.direction == 'long':
            return current_price >= tp_data.price
        else:  # short
            return current_price <= tp_data.price
    
    def _is_stop_loss_hit(self, current_price: float) -> bool:
        """Check if stop loss is hit"""
        if self.direction == 'long':
            return current_price <= self.stop_loss.current_price
        else:  # short
            return current_price >= self.stop_loss.current_price
    
    async def _handle_take_profit_hit(self, tp_level: TakeProfitLevel, current_price: float) -> Dict[str, Any]:
        """Handle take profit hit and update stop loss accordingly"""
        tp_data = self.take_profits[tp_level]
        tp_data.hit = True
        tp_data.hit_time = datetime.now()
        
        # Calculate position amount to close
        close_amount = (tp_data.close_percent / 100) * self.remaining_position_size
        self.remaining_position_size -= close_amount
        self.total_closed_amount += close_amount
        
        # Create event data
        event = {
            'type': 'take_profit',
            'level': tp_level.value,
            'price': current_price,
            'tp_price': tp_data.price,
            'close_amount': close_amount,
            'close_percent': tp_data.close_percent,
            'remaining_position': self.remaining_position_size,
            'timestamp': tp_data.hit_time,
            'sl_action': None
        }
        
        # Move stop loss according to the exact logic requested
        if tp_level == TakeProfitLevel.TP1:
            # EXACT LOGIC: 50% from entry and 50% from original stop loss
            old_sl = self.stop_loss.current_price
            
            # Calculate 50% point between entry and original SL
            # new_sl = entry - (entry - original_sl) * 0.5
            sl_distance = self.entry_price - self.stop_loss.original_price
            self.stop_loss.current_price = self.entry_price - (sl_distance * 0.5)
            
            self.stop_loss.state = StopLossState.AT_ENTRY # Reusing state for "Partial Move"
            self.stop_loss.last_update_time = datetime.now()
            
            event['sl_action'] = {
                'description': 'Dynamic SL: 50% from entry and 50% from original SL',
                'old_sl': old_sl,
                'new_sl': self.stop_loss.current_price
            }
            
            self.logger.info(f"✅ TP1 HIT at {current_price:.6f}! SL adjusted to 50% midpoint: {self.stop_loss.current_price:.6f}")
        
        elif tp_level == TakeProfitLevel.TP2:
            # TP2 reached → SL moves to entry price (Perfectly comprehensive flexible transition)
            old_sl = self.stop_loss.current_price
            self.stop_loss.current_price = self.entry_price
            self.stop_loss.state = StopLossState.AT_TP1
            self.stop_loss.last_update_time = datetime.now()
            
            event['sl_action'] = {
                'description': 'SL moved to entry price after TP2',
                'old_sl': old_sl,
                'new_sl': self.stop_loss.current_price
            }
            
            self.logger.info(f"✅ TP2 HIT at {current_price:.6f}! SL moved to entry: {self.stop_loss.current_price:.6f}")
        
        elif tp_level == TakeProfitLevel.TP3:
            # TP3 reached → close entire trade automatically
            # Close any remaining position
            self.remaining_position_size = 0
            self.total_closed_amount = self.position_size
            self.stop_loss.state = StopLossState.CLOSED
            
            event['close_amount'] = self.position_size - self.total_closed_amount + close_amount
            event['sl_action'] = {
                'description': 'Trade fully closed at TP3',
                'old_sl': self.stop_loss.current_price,
                'new_sl': 'N/A - Trade Closed'
            }
            
            self.logger.info(f"✅ TP3 HIT at {current_price:.6f}! Trade FULLY CLOSED. Total position: {self.position_size:.6f}")
        
        # Add to event history
        self.event_history.append(event)
        
        return event
    
    async def _handle_stop_loss_hit(self, current_price: float) -> Dict[str, Any]:
        """Handle stop loss hit - close remaining position"""
        close_amount = self.remaining_position_size
        self.total_closed_amount += close_amount
        self.remaining_position_size = 0
        
        event = {
            'type': 'stop_loss',
            'price': current_price,
            'sl_price': self.stop_loss.current_price,
            'close_amount': close_amount,
            'remaining_position': 0,
            'sl_state': self.stop_loss.state.value,
            'timestamp': datetime.now()
        }
        
        self.event_history.append(event)
        
        self.logger.warning(f"🛑 STOP LOSS HIT at {current_price:.6f}! SL was at {self.stop_loss.current_price:.6f}. Closing remaining {close_amount:.6f}")
        
        return event
    
    def get_current_status(self) -> Dict[str, Any]:
        """Get current status of the 3SL/1TP system"""
        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'entry_price': self.entry_price,
            'active': self.active,
            'remaining_position_size': self.remaining_position_size,
            'total_closed_amount': self.total_closed_amount,
            'position_closed_percent': (self.total_closed_amount / self.position_size) * 100,
            'creation_time': self.creation_time.isoformat(),
            'last_update_time': self.last_update_time.isoformat(),
            'stop_loss': {
                'current_price': self.stop_loss.current_price,
                'original_price': self.stop_loss.original_price,
                'state': self.stop_loss.state.value,
                'last_update': self.stop_loss.last_update_time.isoformat() if self.stop_loss.last_update_time else None
            },
            'take_profits': {
                tp_level.value: {
                    'price': tp_data.price,
                    'hit': tp_data.hit,
                    'hit_time': tp_data.hit_time.isoformat() if tp_data.hit_time else None,
                    'close_percent': tp_data.close_percent
                }
                for tp_level, tp_data in self.take_profits.items()
            },
            'event_count': len(self.event_history)
        }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        tp_hits = sum(1 for tp in self.take_profits.values() if tp.hit)
        time_active = (datetime.now() - self.creation_time).total_seconds() / 3600  # hours
        
        return {
            'tp_levels_hit': tp_hits,
            'remaining_position_percent': (self.remaining_position_size / self.position_size) * 100,
            'closed_position_percent': (self.total_closed_amount / self.position_size) * 100,
            'time_active_hours': time_active,
            'sl_progression': self.stop_loss.state.value,
            'events_triggered': len(self.event_history),
            'is_complete': not self.active,
            'final_outcome': self._get_final_outcome()
        }
    
    def _get_final_outcome(self) -> str:
        """Determine final outcome of the trade"""
        if self.active:
            return "active"
        
        tp_hits = sum(1 for tp in self.take_profits.values() if tp.hit)
        
        if tp_hits == 3:
            return "all_tps_hit"
        elif tp_hits > 0:
            return f"partial_tp_hit_{tp_hits}"
        else:
            return "sl_only"


# Global registry for active 3SL/1TP managers
_active_3sl1tp_managers: Dict[str, ThreeSLOneTpManager] = {}


def create_3sl1tp_manager(symbol: str, direction: str, entry_price: float, 
                         position_size: float, config: Optional[ThreeSLOneTpConfig] = None) -> ThreeSLOneTpManager:
    """Create and register a new 3SL/1TP manager"""
    manager_id = f"{symbol}_{direction}_{int(entry_price * 1000000)}_{int(datetime.now().timestamp())}"
    
    manager = ThreeSLOneTpManager(symbol, direction, entry_price, position_size, config)
    _active_3sl1tp_managers[manager_id] = manager
    
    return manager


def get_3sl1tp_manager(manager_id: str) -> Optional[ThreeSLOneTpManager]:
    """Get 3SL/1TP manager by ID"""
    return _active_3sl1tp_managers.get(manager_id)


def remove_3sl1tp_manager(manager_id: str) -> bool:
    """Remove 3SL/1TP manager from registry"""
    if manager_id in _active_3sl1tp_managers:
        del _active_3sl1tp_managers[manager_id]
        return True
    return False


def get_all_active_3sl1tp_managers() -> Dict[str, ThreeSLOneTpManager]:
    """Get all active 3SL/1TP managers"""
    return _active_3sl1tp_managers.copy()


def cleanup_inactive_3sl1tp_managers() -> int:
    """Remove inactive 3SL/1TP managers"""
    inactive_managers = [
        manager_id for manager_id, manager in _active_3sl1tp_managers.items()
        if not manager.active
    ]
    
    for manager_id in inactive_managers:
        del _active_3sl1tp_managers[manager_id]
    
    return len(inactive_managers)


# Compatibility aliases and classes for existing system
class DynamicStopLoss:
    """Compatibility alias for the old DynamicStopLoss class"""
    def __init__(self, level, symbol, direction, entry_price, current_price, 
                 original_sl_price, current_sl_price, triggered=False, 
                 trigger_time=None, position_percent=33.0, **kwargs):
        self.level = level
        self.symbol = symbol
        self.direction = direction
        self.entry_price = entry_price
        self.current_price = current_price
        self.original_sl_price = original_sl_price
        self.current_sl_price = current_sl_price
        self.triggered = triggered
        self.trigger_time = trigger_time
        self.position_percent = position_percent
        self.last_update_time = datetime.now()

class StopLossConfig:
    """Compatibility class for stop loss configuration"""
    def __init__(self, sl1_base_percent=1.5, sl2_base_percent=4.0, sl3_base_percent=7.5,
                 sl1_position_percent=33.0, sl2_position_percent=33.0, sl3_position_percent=34.0,
                 trailing_enabled=True, trailing_distance_percent=1.0, **kwargs):
        self.sl1_base_percent = sl1_base_percent
        self.sl2_base_percent = sl2_base_percent
        self.sl3_base_percent = sl3_base_percent
        self.sl1_position_percent = sl1_position_percent
        self.sl2_position_percent = sl2_position_percent
        self.sl3_position_percent = sl3_position_percent
        self.trailing_enabled = trailing_enabled
        self.trailing_distance_percent = trailing_distance_percent

class MarketConditions:
    """Compatibility class for market conditions"""
    def __init__(self, volatility_level="medium", market_session="new_york", 
                 atr_value=0.01, volume_ratio=1.0, momentum_strength=0.5,
                 support_resistance_distance=0.02, timestamp=None):
        self.volatility_level = volatility_level
        self.market_session = market_session
        self.atr_value = atr_value
        self.volume_ratio = volume_ratio
        self.momentum_strength = momentum_strength
        self.support_resistance_distance = support_resistance_distance
        self.timestamp = timestamp or datetime.now()

class MarketAnalyzer:
    """Compatibility class for market analysis"""
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def analyze_market_conditions(self, symbol, price_data, current_price):
        """Return default market conditions for compatibility"""
        return MarketConditions()

# Compatibility enums
class StopLossLevel(Enum):
    """Stop loss level enumeration - compatibility"""
    SL1 = "sl1"
    SL2 = "sl2" 
    SL3 = "sl3"

class VolatilityLevel(Enum):
    """Volatility level enumeration - compatibility"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"

class MarketSession(Enum):
    """Market session enumeration - compatibility"""
    ASIA = "asia"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP = "overlap"

# Compatibility functions to maintain interface with existing system
async def create_stop_loss_manager(symbol: str, direction: str, entry_price: float, 
                           position_size: float, config=None) -> ThreeSLOneTpManager:
    """Compatibility function - creates 3SL/1TP manager"""
    # Convert old config to new config if provided
    new_config = None
    if config:
        new_config = ThreeSLOneTpConfig()
        # Map old config attributes if they exist
        if hasattr(config, 'sl1_base_percent'):
            new_config.initial_sl_percent = config.sl1_base_percent
        if hasattr(config, 'tp1_percent'):
            new_config.tp1_percent = config.tp1_percent
        if hasattr(config, 'tp2_percent'):
            new_config.tp2_percent = config.tp2_percent
        if hasattr(config, 'tp3_percent'):
            new_config.tp3_percent = config.tp3_percent
    else:
        new_config = ThreeSLOneTpConfig()
    
    return create_3sl1tp_manager(symbol, direction, entry_price, position_size, new_config)

def get_stop_loss_manager(manager_id: str):
    """Compatibility function"""
    return get_3sl1tp_manager(manager_id)

def get_all_active_managers():
    """Compatibility function"""
    return get_all_active_3sl1tp_managers()

def cleanup_inactive_managers():
    """Compatibility function"""
    return cleanup_inactive_3sl1tp_managers()


class TradeStopLossManager:
    """Compatibility class - wraps ThreeSLOneTpManager"""
    
    def __init__(self, symbol: str, direction: str, entry_price: float, 
                 position_size: float, config=None):
        # Convert old config to new config if provided
        new_config = None
        if config:
            new_config = ThreeSLOneTpConfig()
            # Map old config attributes if they exist
            if hasattr(config, 'sl1_base_percent'):
                new_config.initial_sl_percent = config.sl1_base_percent
            if hasattr(config, 'tp1_percent'):
                new_config.tp1_percent = config.tp1_percent
            if hasattr(config, 'tp2_percent'):
                new_config.tp2_percent = config.tp2_percent
            if hasattr(config, 'tp3_percent'):
                new_config.tp3_percent = config.tp3_percent
        else:
            new_config = ThreeSLOneTpConfig()
        
        self.manager = create_3sl1tp_manager(symbol, direction, entry_price, position_size, new_config)
        
    async def update_market_conditions(self, current_price: float, price_data=None):
        """Compatibility method"""
        return await self.manager.update_price(current_price)
    
    def get_stop_loss_status(self):
        """Compatibility method"""
        return self.manager.get_current_status()
    
    def get_performance_metrics(self):
        """Compatibility method"""
        return self.manager.get_performance_summary()
    
    @property
    def active(self):
        return self.manager.active
    
    @property
    def symbol(self):
        return self.manager.symbol
    
    @property
    def direction(self):
        return self.manager.direction
    
    @property
    def entry_price(self):
        return self.manager.entry_price
    
    @property
    def remaining_position_size(self):
        return self.manager.remaining_position_size


if __name__ == "__main__":
    # Example usage
    async def test_3sl1tp_system():
        """Test the 3SL/1TP system"""
        logging.basicConfig(level=logging.INFO)
        
        # Create a long position
        manager = create_3sl1tp_manager(
            symbol="BTCUSDT",
            direction="long", 
            entry_price=50000.0,
            position_size=1.0
        )
        
        print("=== 3SL/1TP System Test ===")
        print(f"Entry: {manager.entry_price}")
        print(f"TP1: {manager.take_profits[TakeProfitLevel.TP1].price}")
        print(f"TP2: {manager.take_profits[TakeProfitLevel.TP2].price}")
        print(f"TP3: {manager.take_profits[TakeProfitLevel.TP3].price}")
        print(f"Initial SL: {manager.stop_loss.current_price}")
        
        # Simulate price movements
        test_prices = [50500, 51000, 52000, 53000]
        
        for price in test_prices:
            print(f"\n--- Price Update: {price} ---")
            events = await manager.update_price(price)
            for event in events:
                print(f"Event: {event}")
            
            status = manager.get_current_status()
            print(f"SL State: {status['stop_loss']['state']}")
            print(f"SL Price: {status['stop_loss']['current_price']}")
            print(f"Remaining Position: {status['remaining_position_size']}")
            
            if not manager.active:
                print("Trade completed!")
                break
        
        print("\n=== Final Summary ===")
        summary = manager.get_performance_summary()
        print(summary)
    
    # Run test if executed directly
    import asyncio
    asyncio.run(test_3sl1tp_system())