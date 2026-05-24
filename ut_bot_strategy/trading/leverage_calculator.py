"""
Advanced Auto-Leverage Calculator

Dynamically calculates optimal leverage based on:
- Market volatility (ATR-based)
- Signal strength and confidence
- Account balance and risk parameters
- Position sizing rules
"""

import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class LeverageResult:
    """Result of leverage calculation"""
    leverage: int
    position_size: float
    position_value: float
    margin_required: float
    risk_amount: float
    reason: str
    confidence: float


class LeverageCalculator:
    """
    Advanced auto-leverage calculator with intelligent position sizing
    
    Features:
    - Volatility-adjusted leverage
    - Signal strength multiplier
    - Dynamic risk management
    - Position size optimization
    """
    
    def __init__(
        self,
        min_leverage: int = 1,
        max_leverage: int = 20,
        base_leverage: int = 5,
        risk_per_trade_percent: float = 2.0,
        max_position_percent: float = 50.0,
        volatility_low_threshold: float = 1.0,
        volatility_high_threshold: float = 3.0,
        signal_strength_multiplier: bool = True
    ):
        """
        Initialize the leverage calculator
        
        Args:
            min_leverage: Minimum allowed leverage
            max_leverage: Maximum allowed leverage
            base_leverage: Default leverage when conditions are neutral
            risk_per_trade_percent: Maximum risk per trade as % of balance
            max_position_percent: Maximum position size as % of balance
            volatility_low_threshold: ATR% below this = low volatility
            volatility_high_threshold: ATR% above this = high volatility
            signal_strength_multiplier: Adjust leverage based on signal confidence
        """
        self.min_leverage = min_leverage
        self.max_leverage = max_leverage
        self.base_leverage = base_leverage
        self.risk_per_trade = risk_per_trade_percent / 100.0
        self.max_position = max_position_percent / 100.0
        self.vol_low = volatility_low_threshold
        self.vol_high = volatility_high_threshold
        self.use_signal_strength = signal_strength_multiplier
        
        logger.info(f"LeverageCalculator initialized: {min_leverage}x-{max_leverage}x, base={base_leverage}x")
    
    def calculate_volatility_score(self, atr: float, price: float) -> Tuple[float, str]:
        """
        Calculate volatility score from ATR
        
        Args:
            atr: Average True Range value
            price: Current price
            
        Returns:
            Tuple of (volatility_score 0-1, volatility_category)
        """
        atr_percent = (atr / price) * 100.0
        
        if atr_percent <= self.vol_low:
            score = 1.0
            category = "LOW"
        elif atr_percent >= self.vol_high:
            score = 0.3
            category = "HIGH"
        else:
            range_size = self.vol_high - self.vol_low
            score = 1.0 - ((atr_percent - self.vol_low) / range_size) * 0.7
            category = "MEDIUM"
        
        return score, category
    
    def calculate_signal_strength(self, signal: Dict) -> float:
        """
        Calculate signal strength/confidence score
        
        Args:
            signal: Signal dictionary with indicator values
            
        Returns:
            Strength score 0.5-1.5
        """
        strength = 1.0
        
        stc_value = signal.get('stc_value', 50)
        direction = signal.get('direction', 'LONG')
        
        if direction == 'LONG':
            if stc_value < 25:
                strength += 0.3
            elif stc_value < 50:
                strength += 0.15
        else:
            if stc_value > 75:
                strength += 0.3
            elif stc_value > 50:
                strength += 0.15
        
        risk_percent = signal.get('risk_percent', 1.0)
        if risk_percent < 0.5:
            strength += 0.2
        elif risk_percent > 2.0:
            strength -= 0.2
        
        return max(0.5, min(1.5, strength))
    
    def calculate_optimal_leverage(
        self,
        signal: Dict,
        account_balance: float,
        current_price: float,
        atr: float
    ) -> LeverageResult:
        """
        Calculate optimal leverage for a trade
        
        Args:
            signal: Signal dictionary with trade details
            account_balance: Available account balance in USDT
            current_price: Current asset price
            atr: Current ATR value
            
        Returns:
            LeverageResult with optimal settings
        """
        vol_score, vol_category = self.calculate_volatility_score(atr, current_price)
        
        volatility_adjusted = self.base_leverage * vol_score
        
        if self.use_signal_strength:
            signal_strength = self.calculate_signal_strength(signal)
            adjusted_leverage = volatility_adjusted * signal_strength
        else:
            adjusted_leverage = volatility_adjusted
            signal_strength = 1.0
        
        optimal_leverage = int(round(adjusted_leverage))
        optimal_leverage = max(self.min_leverage, min(self.max_leverage, optimal_leverage))
        
        risk_amount = account_balance * self.risk_per_trade
        
        stop_loss = signal.get('stop_loss', current_price * 0.99)
        sl_distance_percent = abs(current_price - stop_loss) / current_price
        
        if sl_distance_percent > 0:
            position_from_risk = risk_amount / sl_distance_percent
        else:
            position_from_risk = account_balance * self.max_position
        
        max_position_value = account_balance * self.max_position * optimal_leverage
        position_value = min(position_from_risk, max_position_value)
        
        position_size = position_value / current_price
        
        margin_required = position_value / optimal_leverage
        
        confidence = (vol_score + signal_strength) / 2.0
        
        reason = (
            f"Volatility: {vol_category} ({vol_score:.2f}), "
            f"Signal Strength: {signal_strength:.2f}, "
            f"Risk: ${risk_amount:.2f}"
        )
        
        logger.info(f"Calculated leverage: {optimal_leverage}x, Position: ${position_value:.2f}")
        logger.info(reason)
        
        return LeverageResult(
            leverage=optimal_leverage,
            position_size=position_size,
            position_value=position_value,
            margin_required=margin_required,
            risk_amount=risk_amount,
            reason=reason,
            confidence=confidence
        )
    
    def validate_trade(
        self,
        leverage_result: LeverageResult,
        account_balance: float,
        min_order_size: float = 0.001
    ) -> Tuple[bool, str]:
        """
        Validate if trade meets all requirements
        
        Args:
            leverage_result: Calculated leverage parameters
            account_balance: Available balance
            min_order_size: Minimum order size for the asset
            
        Returns:
            Tuple of (is_valid, reason)
        """
        if leverage_result.margin_required > account_balance:
            return False, f"Insufficient margin: need ${leverage_result.margin_required:.2f}, have ${account_balance:.2f}"
        
        if leverage_result.position_size < min_order_size:
            return False, f"Position size {leverage_result.position_size:.6f} below minimum {min_order_size}"
        
        if leverage_result.leverage < self.min_leverage:
            return False, f"Leverage {leverage_result.leverage}x below minimum {self.min_leverage}x"
        
        if leverage_result.leverage > self.max_leverage:
            return False, f"Leverage {leverage_result.leverage}x exceeds maximum {self.max_leverage}x"
        
        return True, "Trade validated successfully"
