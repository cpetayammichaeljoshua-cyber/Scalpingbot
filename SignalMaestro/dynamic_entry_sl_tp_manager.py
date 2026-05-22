#!/usr/bin/env python3
"""
Dynamic Entry, SL, and TP Manager
Calculates adaptive position sizes and levels based on market conditions and risk
"""

import numpy as np
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MarketCondition(Enum):
    EXTREME_VOLATILITY = "extreme"
    HIGH_VOLATILITY = "high"
    NORMAL = "normal"
    LOW_VOLATILITY = "low"

@dataclass
class PositionConfig:
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    position_size: float
    risk_per_trade: float
    risk_reward_ratio: float
    market_condition: MarketCondition

class DynamicSLTPManager:
    """Manages dynamic stop loss and take profit calculation"""
    
    def __init__(self, account_balance: float = 1000.0, risk_per_trade_pct: float = 2.0):
        self.account_balance = account_balance
        self.risk_per_trade_pct = risk_per_trade_pct
        self.trade_history = []
        self.win_rate = 0.5
        self.avg_win = 0.0
        self.avg_loss = 0.0
    
    def calculate_position_config(self, 
                                  symbol: str,
                                  entry_price: float,
                                  direction: str,
                                  atr: float,
                                  volatility_pct: float,
                                  rsi: float,
                                  volume_ratio: float,
                                  ml_confidence: float = 0.5) -> Optional[PositionConfig]:
        """
        Calculate complete position configuration based on multiple factors
        """
        
        # Determine market condition
        market_condition = self._determine_market_condition(volatility_pct, rsi, volume_ratio)
        
        # Calculate base risk distance from ATR
        risk_distance = self._calculate_risk_distance(atr, market_condition, ml_confidence)
        
        # Calculate SL and TPs
        if direction.upper() == 'BUY':
            stop_loss = entry_price - risk_distance
            tp1 = entry_price + (risk_distance * 1.0)
            tp2 = entry_price + (risk_distance * 2.0)
            tp3 = entry_price + (risk_distance * 3.0)
        else:  # SELL
            stop_loss = entry_price + risk_distance
            tp1 = entry_price - (risk_distance * 1.0)
            tp2 = entry_price - (risk_distance * 2.0)
            tp3 = entry_price - (risk_distance * 3.0)
        
        # Validate levels
        if not self._validate_sl_tp_levels(entry_price, stop_loss, tp1, tp2, tp3, direction):
            logger.warning(f"Invalid SL/TP levels for {symbol}, using fallback")
            return self._get_fallback_config(entry_price, direction)
        
        # Calculate position size
        risk_amount = self.account_balance * (self.risk_per_trade_pct / 100)
        distance_to_sl = abs(entry_price - stop_loss)
        
        if distance_to_sl > 0:
            position_size = risk_amount / distance_to_sl
        else:
            position_size = self.account_balance * 0.01
        
        # Adjust for market conditions
        position_size = self._adjust_position_size(position_size, market_condition, ml_confidence)
        
        # Calculate risk reward ratio
        risk_reward_ratio = abs(tp3 - entry_price) / abs(entry_price - stop_loss) if distance_to_sl > 0 else 3.0
        
        return PositionConfig(
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            position_size=position_size,
            risk_per_trade=risk_amount,
            risk_reward_ratio=risk_reward_ratio,
            market_condition=market_condition
        )
    
    def _determine_market_condition(self, volatility_pct: float, rsi: float, 
                                    volume_ratio: float) -> MarketCondition:
        """Determine market condition from multiple indicators"""
        
        volatility_score = 0
        
        # Volatility assessment
        if volatility_pct > 4.0:
            volatility_score += 4
        elif volatility_pct > 2.5:
            volatility_score += 3
        elif volatility_pct > 1.5:
            volatility_score += 2
        elif volatility_pct > 0.5:
            volatility_score += 1
        
        # RSI extremes indicate high volatility
        if rsi > 80 or rsi < 20:
            volatility_score += 2
        elif rsi > 70 or rsi < 30:
            volatility_score += 1
        
        # Volume indicates activity level
        if volume_ratio > 1.5:
            volatility_score += 1
        
        if volatility_score >= 5:
            return MarketCondition.EXTREME_VOLATILITY
        elif volatility_score >= 3:
            return MarketCondition.HIGH_VOLATILITY
        elif volatility_score >= 1:
            return MarketCondition.NORMAL
        else:
            return MarketCondition.LOW_VOLATILITY
    
    def _calculate_risk_distance(self, atr: float, market_condition: MarketCondition,
                                 ml_confidence: float) -> float:
        """Calculate risk distance based on ATR and market conditions"""
        
        # Base multiplier by market condition
        condition_multipliers = {
            MarketCondition.EXTREME_VOLATILITY: 2.0,
            MarketCondition.HIGH_VOLATILITY: 1.5,
            MarketCondition.NORMAL: 1.0,
            MarketCondition.LOW_VOLATILITY: 0.8
        }
        
        base_multiplier = condition_multipliers.get(market_condition, 1.0)
        
        # ML confidence adjusts the multiplier (more confident = wider stops)
        ml_adjustment = 0.8 + (ml_confidence * 0.4)  # 0.8 to 1.2
        
        risk_distance = atr * base_multiplier * ml_adjustment
        
        # Minimum risk distance
        return max(atr * 0.5, risk_distance)
    
    def _validate_sl_tp_levels(self, entry: float, sl: float, tp1: float, 
                               tp2: float, tp3: float, direction: str) -> bool:
        """Validate that SL and TP levels make sense"""
        
        if direction.upper() == 'BUY':
            return (sl < entry < tp1 < tp2 < tp3) and (tp3 - entry) > 0
        else:
            return (tp3 < tp2 < tp1 < entry < sl) and (entry - tp3) > 0
    
    def _get_fallback_config(self, entry_price: float, direction: str) -> Optional[PositionConfig]:
        """Return fallback configuration with safe percentages"""
        
        if direction.upper() == 'BUY':
            stop_loss = entry_price * 0.98
            tp1 = entry_price * 1.01
            tp2 = entry_price * 1.02
            tp3 = entry_price * 1.03
        else:
            stop_loss = entry_price * 1.02
            tp1 = entry_price * 0.99
            tp2 = entry_price * 0.98
            tp3 = entry_price * 0.97
        
        position_size = self.account_balance * 0.01
        risk_amount = self.account_balance * (self.risk_per_trade_pct / 100)
        
        return PositionConfig(
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            position_size=position_size,
            risk_per_trade=risk_amount,
            risk_reward_ratio=3.0,
            market_condition=MarketCondition.NORMAL
        )
    
    def _adjust_position_size(self, base_size: float, market_condition: MarketCondition,
                             ml_confidence: float) -> float:
        """Adjust position size based on risk conditions"""
        
        # Reduce size in extreme conditions
        condition_factors = {
            MarketCondition.EXTREME_VOLATILITY: 0.5,
            MarketCondition.HIGH_VOLATILITY: 0.75,
            MarketCondition.NORMAL: 1.0,
            MarketCondition.LOW_VOLATILITY: 1.1
        }
        
        condition_factor = condition_factors.get(market_condition, 1.0)
        
        # Increase with ML confidence
        ml_factor = 0.7 + (ml_confidence * 0.3)  # 0.7 to 1.0
        
        adjusted_size = base_size * condition_factor * ml_factor
        
        # Cap at max position size (10% of account)
        max_position = self.account_balance * 0.10
        
        return min(adjusted_size, max_position)
    
    def record_trade_result(self, entry: float, exit: float, direction: str, 
                           take_profit_level: int = 0):
        """Record trade result for statistics"""
        
        if direction.upper() == 'BUY':
            pnl = exit - entry
        else:
            pnl = entry - exit
        
        won = pnl > 0
        
        # Update stats
        self.trade_history.append({
            'entry': entry,
            'exit': exit,
            'pnl': pnl,
            'won': won,
            'tp_level': take_profit_level
        })
        
        if len(self.trade_history) > 0:
            wins = sum(1 for t in self.trade_history if t['won'])
            self.win_rate = wins / len(self.trade_history)
            
            winning_trades = [t['pnl'] for t in self.trade_history if t['won']]
            losing_trades = [t['pnl'] for t in self.trade_history if not t['won']]
            
            self.avg_win = np.mean(winning_trades) if winning_trades else 0
            self.avg_loss = np.mean(losing_trades) if losing_trades else 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get trading statistics"""
        return {
            'total_trades': len(self.trade_history),
            'win_rate': self.win_rate,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
            'account_balance': self.account_balance
        }

class AdaptiveRiskManager:
    """Manages adaptive risk based on recent performance"""
    
    def __init__(self, lookback_trades: int = 20):
        self.lookback_trades = lookback_trades
        self.trade_results = []
    
    def add_trade_result(self, pnl: float, risk_taken: float):
        """Record trade result"""
        self.trade_results.append({'pnl': pnl, 'risk': risk_taken})
    
    def get_adjusted_risk_percentage(self, base_risk_pct: float) -> float:
        """Get adjusted risk percentage based on recent performance"""
        
        if not self.trade_results:
            return base_risk_pct
        
        recent = self.trade_results[-self.lookback_trades:]
        recent_pnl = sum(t['pnl'] for t in recent)
        recent_win_rate = sum(1 for t in recent if t['pnl'] > 0) / len(recent)
        
        # If losing streak, reduce risk
        if recent_pnl < 0:
            return max(0.5, base_risk_pct * 0.7)
        
        # If high win rate, increase risk slightly
        if recent_win_rate > 0.65:
            return min(base_risk_pct * 1.2, 5.0)  # Cap at 5%
        
        return base_risk_pct
