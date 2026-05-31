#!/usr/bin/env python3
"""
Dynamic Leveraging Stop Loss System
Implements percentage below trigger stop loss with leverage optimization
"""

import logging
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
import numpy as np

@dataclass
class DynamicStopLoss:
    """Dynamic stop loss with leverage adjustment"""
    base_stop_loss: float
    trigger_price: float
    percentage_below: float
    adjusted_stop_loss: float
    leverage: int
    confidence: float
    reasoning: str
    volatility_factor: float
    market_regime: str

class DynamicLeveragingStopLoss:
    """
    Advanced stop loss system with dynamic leveraging based on:
    - Percentage below trigger price
    - Market volatility
    - Position leverage
    - Market regime
    - Trend strength
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.config = {
            'default_percentage_below': 0.015,  # 1.5% default
            'min_leverage': 3,
            'max_leverage': 75,
            'high_volatility_threshold': 0.025,  # 2.5% ATR
            'low_volatility_threshold': 0.008,   # 0.8% ATR
            'min_confidence': 60.0,
            'max_confidence': 100.0
        }
        
        # Leverage adjustment factors
        self.leverage_factors = {
            'high_volatility': {'leverage_mult': 0.7, 'pct_below_mult': 1.3},
            'medium_volatility': {'leverage_mult': 1.0, 'pct_below_mult': 1.0},
            'low_volatility': {'leverage_mult': 1.2, 'pct_below_mult': 0.8}
        }
        
        # Market regime factors
        self.regime_factors = {
            'trending_bullish': {'leverage_mult': 1.1, 'confidence_bonus': 10},
            'trending_bearish': {'leverage_mult': 0.9, 'confidence_bonus': 5},
            'volatile': {'leverage_mult': 0.8, 'confidence_bonus': -10},
            'ranging': {'leverage_mult': 1.0, 'confidence_bonus': 0},
            'unknown': {'leverage_mult': 1.0, 'confidence_bonus': 0}
        }
        
        self.logger.info("✅ Dynamic Leveraging Stop Loss System initialized")
    
    def calculate_dynamic_sl(
        self,
        entry_price: float,
        direction: str,
        trigger_price: float,
        percentage_below: Optional[float] = None,
        current_leverage: int = 20,
        atr_percentage: float = 0.015,
        market_regime: str = "ranging",
        trend_strength: float = 0.5,
        order_flow_strength: float = 50.0,
        confidence_base: float = 80.0
    ) -> DynamicStopLoss:
        """
        Calculate dynamic stop loss with leverage optimization
        
        Args:
            entry_price: Entry price of the position
            direction: "LONG" or "SHORT"
            trigger_price: Trigger price (current price or resistance/support)
            percentage_below: Optional custom percentage below trigger
            current_leverage: Current position leverage
            atr_percentage: ATR as percentage of price
            market_regime: Current market regime
            trend_strength: Trend strength 0-1
            order_flow_strength: Order flow strength 0-100
            confidence_base: Base confidence score
            
        Returns:
            DynamicStopLoss with adjusted values
        """
        try:
            # Use default or custom percentage
            pct_below = percentage_below or self.config['default_percentage_below']
            
            # Determine volatility regime
            vol_regime = self._classify_volatility(atr_percentage)
            
            # Get adjustment factors
            vol_factors = self.leverage_factors[vol_regime]
            regime_factors = self.regime_factors.get(market_regime, self.regime_factors['unknown'])
            
            # Adjust percentage based on volatility and regime
            adjusted_pct = pct_below * vol_factors['pct_below_mult']
            
            # Calculate base stop loss from trigger
            if direction.upper() == "LONG":
                base_sl = trigger_price * (1 - adjusted_pct)
                if base_sl > entry_price:
                    base_sl = entry_price - (entry_price * 0.005)
            else:  # SHORT
                base_sl = trigger_price * (1 + adjusted_pct)
                if base_sl < entry_price:
                    base_sl = entry_price + (entry_price * 0.005)
            
            # Calculate adjusted leverage based on market conditions
            adjusted_leverage = self._calculate_adjusted_leverage(
                current_leverage,
                vol_regime,
                market_regime,
                trend_strength,
                vol_factors,
                regime_factors
            )
            
            # Calculate volatility factor (0.5-1.5)
            volatility_factor = self._calculate_volatility_factor(atr_percentage)
            
            # Fine-tune SL based on volatility factor
            if direction.upper() == "LONG":
                adjusted_sl = base_sl * (1 - (volatility_factor - 1.0) * 0.1)
            else:
                adjusted_sl = base_sl * (1 + (volatility_factor - 1.0) * 0.1)
            
            # Calculate confidence score
            confidence = self._calculate_confidence(
                confidence_base,
                vol_regime,
                market_regime,
                order_flow_strength,
                trend_strength,
                regime_factors
            )
            
            # Generate reasoning
            reasoning = self._generate_reasoning(
                direction,
                trigger_price,
                adjusted_pct,
                base_sl,
                adjusted_sl,
                adjusted_leverage,
                vol_regime,
                market_regime,
                volatility_factor
            )
            
            return DynamicStopLoss(
                base_stop_loss=base_sl,
                trigger_price=trigger_price,
                percentage_below=adjusted_pct,
                adjusted_stop_loss=adjusted_sl,
                leverage=adjusted_leverage,
                confidence=confidence,
                reasoning=reasoning,
                volatility_factor=volatility_factor,
                market_regime=market_regime
            )
            
        except Exception as e:
            self.logger.error(f"Error calculating dynamic SL: {e}")
            return self._fallback_sl(entry_price, direction, current_leverage, market_regime)
    
    def _classify_volatility(self, atr_pct: float) -> str:
        """Classify market volatility"""
        if atr_pct > self.config['high_volatility_threshold']:
            return 'high_volatility'
        elif atr_pct < self.config['low_volatility_threshold']:
            return 'low_volatility'
        else:
            return 'medium_volatility'
    
    def _calculate_volatility_factor(self, atr_pct: float) -> float:
        """Calculate volatility factor (0.5-1.5)"""
        if atr_pct == 0:
            return 1.0
        
        # Normalize ATR percentage to 0-1 scale
        normalized = min(max(atr_pct / self.config['high_volatility_threshold'], 0), 2)
        
        # Map to 0.5-1.5 range
        return 0.5 + (normalized * 0.5)
    
    def _calculate_adjusted_leverage(
        self,
        base_leverage: int,
        vol_regime: str,
        market_regime: str,
        trend_strength: float,
        vol_factors: Dict[str, float],
        regime_factors: Dict[str, Any]
    ) -> int:
        """Calculate leverage adjusted for market conditions"""
        
        # Apply volatility adjustment
        adjusted = base_leverage * vol_factors['leverage_mult']
        
        # Apply market regime adjustment
        adjusted = adjusted * regime_factors['leverage_mult']
        
        # Apply trend strength adjustment
        trend_mult = 0.9 + (trend_strength * 0.4)  # 0.9 - 1.3x
        adjusted = adjusted * trend_mult
        
        # Constrain to allowed range
        adjusted = max(self.config['min_leverage'], min(adjusted, self.config['max_leverage']))
        
        return int(adjusted)
    
    def _calculate_confidence(
        self,
        base_confidence: float,
        vol_regime: str,
        market_regime: str,
        order_flow_strength: float,
        trend_strength: float,
        regime_factors: Dict[str, Any]
    ) -> float:
        """Calculate confidence score"""
        
        confidence = base_confidence
        
        # Apply market regime bonus/penalty
        confidence += regime_factors.get('confidence_bonus', 0)
        
        # Apply volatility penalty
        if vol_regime == 'high_volatility':
            confidence -= 5
        elif vol_regime == 'low_volatility':
            confidence += 5
        
        # Apply order flow bonus
        confidence += (order_flow_strength - 50) * 0.1
        
        # Apply trend strength bonus
        confidence += trend_strength * 10
        
        # Constrain to range
        confidence = max(self.config['min_confidence'], min(confidence, self.config['max_confidence']))
        
        return confidence
    
    def _generate_reasoning(
        self,
        direction: str,
        trigger_price: float,
        percentage_below: float,
        base_sl: float,
        adjusted_sl: float,
        leverage: int,
        vol_regime: str,
        market_regime: str,
        volatility_factor: float
    ) -> str:
        """Generate detailed reasoning for SL calculation"""
        
        pct_display = percentage_below * 100
        distance = abs(trigger_price - adjusted_sl)
        distance_pct = (distance / trigger_price) * 100
        
        reasoning = (
            f"Dynamic SL for {direction}: "
            f"Trigger={trigger_price:.5f}, "
            f"SL={adjusted_sl:.5f} ({distance_pct:.3f}% away), "
            f"Pct Below={pct_display:.2f}%, "
            f"Leverage={leverage}x, "
            f"VolRegime={vol_regime}, "
            f"Market={market_regime}, "
            f"VolFactor={volatility_factor:.2f}"
        )
        
        return reasoning
    
    def _fallback_sl(
        self,
        entry_price: float,
        direction: str,
        leverage: int,
        market_regime: str
    ) -> DynamicStopLoss:
        """Fallback stop loss calculation"""
        
        sl_distance = entry_price * 0.02  # 2% from entry
        
        if direction.upper() == "LONG":
            adjusted_sl = entry_price - sl_distance
        else:
            adjusted_sl = entry_price + sl_distance
        
        return DynamicStopLoss(
            base_stop_loss=adjusted_sl,
            trigger_price=entry_price,
            percentage_below=0.02,
            adjusted_stop_loss=adjusted_sl,
            leverage=leverage,
            confidence=70.0,
            reasoning=f"Fallback SL (2% from entry, {market_regime} regime)",
            volatility_factor=1.0,
            market_regime=market_regime
        )
    
    def update_trailing_stop_loss(
        self,
        current_price: float,
        current_sl: float,
        entry_price: float,
        direction: str,
        trailing_percent: float = 0.01,
        min_profit_percent: float = 0.005
    ) -> Tuple[float, str]:
        """
        Update trailing stop loss
        
        Args:
            current_price: Current market price
            current_sl: Current stop loss level
            entry_price: Entry price
            direction: "LONG" or "SHORT"
            trailing_percent: Trailing stop percentage
            min_profit_percent: Minimum profit to activate trailing
            
        Returns:
            Updated SL and reasoning
        """
        try:
            if direction.upper() == "LONG":
                profit_pct = (current_price - entry_price) / entry_price
                
                if profit_pct > min_profit_percent:
                    # Activate trailing stop
                    trailing_sl = current_price * (1 - trailing_percent)
                    
                    if trailing_sl > current_sl:
                        reasoning = f"Trailing SL activated: {trailing_sl:.5f} (+{(trailing_sl - current_sl) / current_sl * 100:.2f}%)"
                        return trailing_sl, reasoning
            else:  # SHORT
                profit_pct = (entry_price - current_price) / entry_price
                
                if profit_pct > min_profit_percent:
                    # Activate trailing stop
                    trailing_sl = current_price * (1 + trailing_percent)
                    
                    if trailing_sl < current_sl:
                        reasoning = f"Trailing SL activated: {trailing_sl:.5f} (-{(current_sl - trailing_sl) / current_sl * 100:.2f}%)"
                        return trailing_sl, reasoning
            
            return current_sl, "SL unchanged - profit threshold not met"
            
        except Exception as e:
            self.logger.error(f"Error updating trailing SL: {e}")
            return current_sl, f"Error updating trailing SL: {e}"

# Singleton instance
_dynamic_sl_system = None

def get_dynamic_leveraging_sl():
    """Get singleton instance"""
    global _dynamic_sl_system
    if _dynamic_sl_system is None:
        _dynamic_sl_system = DynamicLeveragingStopLoss()
    return _dynamic_sl_system
