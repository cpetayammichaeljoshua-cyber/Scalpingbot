#!/usr/bin/env python3
"""
DynamicLeverageEngine - Calculates optimal leverage (10x-75x) based on market conditions
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, List
import logging

class DynamicLeverageEngine:
    """Dynamic leverage calculation with efficiency tracking"""
    
    def __init__(self, min_leverage: int = 10, max_leverage: int = 75):
        self.min_leverage = min_leverage
        self.max_leverage = max_leverage
        self.logger = logging.getLogger(__name__)
        
        # Performance tracking
        self.leverage_performance = {}  # Track PnL per leverage level
        self.total_leverage_used = 0
        self.leverage_count = 0
    
    def calculate_optimal_leverage(self, market_data: Dict[str, Any]) -> Tuple[int, str, float]:
        """
        Calculate optimal leverage based on market conditions
        
        Args:
            market_data: Dict containing atr_percentage, volume_ratio, trend_strength
        
        Returns:
            (leverage, volatility_category, efficiency_percentage)
        """
        
        try:
            atr_percentage = market_data.get('atr_percentage', 1.0)
            volume_ratio = market_data.get('volume_ratio', 1.0)
            trend_strength = market_data.get('trend_strength', 0.5)
            
            # Base leverage calculation (inverse relationship with volatility)
            base_leverage, vol_category = self._calculate_base_leverage(atr_percentage)
            
            # Volume adjustment
            volume_adjusted_leverage = self._apply_volume_adjustment(base_leverage, volume_ratio)
            
            # Trend strength adjustment
            final_leverage = self._apply_trend_adjustment(volume_adjusted_leverage, trend_strength)
            
            # Ensure within bounds
            final_leverage = max(self.min_leverage, min(self.max_leverage, int(final_leverage)))
            
            # Calculate efficiency
            efficiency = self._calculate_leverage_efficiency(final_leverage, atr_percentage)
            
            # Track usage
            self.total_leverage_used += final_leverage
            self.leverage_count += 1
            
            self.logger.debug(f"Leverage calculation: ATR={atr_percentage:.3f}% -> {final_leverage}x "
                            f"({vol_category}, {efficiency:.1f}% efficiency)")
            
            return final_leverage, vol_category, efficiency
            
        except Exception as e:
            self.logger.error(f"Leverage calculation error: {e}")
            return 35, "MEDIUM", 47.0  # Safe default
    
    def _calculate_base_leverage(self, atr_percentage: float) -> Tuple[int, str]:
        """Calculate base leverage from volatility (ATR percentage)"""
        
        if atr_percentage <= 0.3:  # Ultra low volatility
            return 75, "ULTRA LOW"
        elif atr_percentage <= 0.5:  # Very low volatility
            return 70, "VERY LOW"
        elif atr_percentage <= 0.8:  # Low volatility
            return 65, "LOW"
        elif atr_percentage <= 1.2:  # Medium-low volatility
            return 60, "MEDIUM-LOW"
        elif atr_percentage <= 1.8:  # Medium volatility
            return 55, "MEDIUM"
        elif atr_percentage <= 2.5:  # Medium-high volatility
            return 45, "MEDIUM-HIGH"
        elif atr_percentage <= 3.5:  # High volatility
            return 35, "HIGH"
        elif atr_percentage <= 5.0:  # Very high volatility
            return 20, "VERY HIGH"
        else:  # Extreme volatility
            return 10, "EXTREME"
    
    def _apply_volume_adjustment(self, base_leverage: int, volume_ratio: float) -> float:
        """Adjust leverage based on volume conditions"""
        
        if volume_ratio > 2.0:  # Very high volume (potential manipulation)
            return base_leverage * 0.95
        elif volume_ratio > 1.5:  # High volume (good liquidity)
            return base_leverage * 1.05
        elif volume_ratio > 1.2:  # Above average volume
            return base_leverage * 1.02
        elif volume_ratio < 0.6:  # Very low volume (poor liquidity)
            return base_leverage * 0.90
        elif volume_ratio < 0.8:  # Low volume
            return base_leverage * 0.95
        else:  # Normal volume
            return base_leverage
    
    def _apply_trend_adjustment(self, leverage: float, trend_strength: float) -> float:
        """Adjust leverage based on trend strength"""
        
        if trend_strength > 0.8:  # Very strong trend
            return leverage * 1.05  # Slightly higher leverage in strong trends
        elif trend_strength > 0.6:  # Strong trend
            return leverage * 1.02
        elif trend_strength < 0.3:  # Weak/choppy market
            return leverage * 0.95  # Reduce leverage in choppy conditions
        else:  # Normal trend
            return leverage
    
    def _calculate_leverage_efficiency(self, leverage: int, atr_percentage: float) -> float:
        """
        Calculate leverage efficiency as percentage of maximum possible leverage
        Adjusted for market conditions
        """
        
        # Base efficiency
        base_efficiency = (leverage / self.max_leverage) * 100
        
        # Adjust for market conditions
        # In very low volatility, high leverage is more efficient
        if atr_percentage <= 0.5 and leverage >= 65:
            efficiency_bonus = 5  # Bonus for using high leverage in low vol
        elif atr_percentage >= 3.0 and leverage <= 20:
            efficiency_bonus = 5  # Bonus for conservative leverage in high vol
        else:
            efficiency_bonus = 0
        
        final_efficiency = min(100.0, base_efficiency + efficiency_bonus)
        return final_efficiency
    
    def get_average_leverage_used(self) -> float:
        """Get average leverage used across all calculations"""
        if self.leverage_count == 0:
            return 0.0
        return self.total_leverage_used / self.leverage_count
    
    def track_leverage_performance(self, leverage: int, pnl: float):
        """Track PnL performance per leverage level for optimization"""
        
        if leverage not in self.leverage_performance:
            self.leverage_performance[leverage] = {'total_pnl': 0.0, 'trade_count': 0}
        
        self.leverage_performance[leverage]['total_pnl'] += pnl
        self.leverage_performance[leverage]['trade_count'] += 1
    
    def get_leverage_performance_report(self) -> Dict[str, Any]:
        """Get performance analysis by leverage level"""
        
        report = {
            'average_leverage_used': self.get_average_leverage_used(),
            'total_calculations': self.leverage_count,
            'leverage_distribution': {},
            'performance_by_leverage': {}
        }
        
        # Performance by leverage
        for leverage, stats in self.leverage_performance.items():
            if stats['trade_count'] > 0:
                avg_pnl = stats['total_pnl'] / stats['trade_count']
                report['performance_by_leverage'][leverage] = {
                    'avg_pnl_per_trade': avg_pnl,
                    'total_pnl': stats['total_pnl'],
                    'trade_count': stats['trade_count']
                }
        
        return report
    
    def get_recommended_improvements(self) -> List[str]:
        """Analyze performance and suggest leverage improvements"""
        
        recommendations = []
        
        if self.leverage_count == 0:
            return ["No leverage data available for analysis"]
        
        avg_leverage = self.get_average_leverage_used()
        
        # Analyze performance patterns
        if len(self.leverage_performance) > 0:
            best_performing_leverage = None
            best_avg_pnl = float('-inf')
            
            for leverage, stats in self.leverage_performance.items():
                if stats['trade_count'] >= 2:  # Need minimum trades for reliability
                    avg_pnl = stats['total_pnl'] / stats['trade_count']
                    if avg_pnl > best_avg_pnl:
                        best_avg_pnl = avg_pnl
                        best_performing_leverage = leverage
            
            if best_performing_leverage:
                if best_performing_leverage > avg_leverage * 1.2:
                    recommendations.append(
                        f"Consider using higher leverage more often (best performer: {best_performing_leverage}x "
                        f"vs current avg: {avg_leverage:.1f}x)"
                    )
                elif best_performing_leverage < avg_leverage * 0.8:
                    recommendations.append(
                        f"Consider using lower leverage more often (best performer: {best_performing_leverage}x "
                        f"vs current avg: {avg_leverage:.1f}x)"
                    )
        
        # General recommendations
        if avg_leverage > 60:
            recommendations.append("High average leverage usage - ensure volatility filtering is working correctly")
        elif avg_leverage < 25:
            recommendations.append("Low average leverage usage - consider optimizing for higher efficiency in low volatility periods")
        
        if not recommendations:
            recommendations.append("Leverage usage appears optimal based on current performance")
        
        return recommendations

def calculate_dynamic_leverage(atr_percentage: float, volume_ratio: float = 1.0, 
                             trend_strength: float = 0.5, min_leverage: int = 10, 
                             max_leverage: int = 75) -> Tuple[int, str, float]:
    """
    Convenience function for standalone leverage calculation
    
    Args:
        atr_percentage: Market volatility as ATR percentage
        volume_ratio: Volume relative to average
        trend_strength: Trend strength (0-1 scale)
        min_leverage: Minimum allowed leverage
        max_leverage: Maximum allowed leverage
    
    Returns:
        (leverage, volatility_category, efficiency_percentage)
    """
    
    engine = DynamicLeverageEngine(min_leverage, max_leverage)
    
    market_data = {
        'atr_percentage': atr_percentage,
        'volume_ratio': volume_ratio,
        'trend_strength': trend_strength
    }
    
    return engine.calculate_optimal_leverage(market_data)