#!/usr/bin/env python3
"""
Market Intelligence Analyzer - Fixed version with column handling
"""

import asyncio
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta

def _normalize_ohlcv(data):
    """Normalize OHLCV data (handle 5 or 6 columns)"""
    if isinstance(data, list):
        if not data or len(data) == 0:
            return None
        first = data[0] if isinstance(data[0], (list, tuple)) else None
        col_count = len(first) if first else 5
        if col_count == 6:
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df = df.drop('timestamp', axis=1)
        else:
            df = pd.DataFrame(data, columns=['open', 'high', 'low', 'close', 'volume'])
        return df
    elif isinstance(data, pd.DataFrame):
        if 'timestamp' in data.columns:
            data = data.drop('timestamp', axis=1)
        return data
    return None

class MarketIntelligence(Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"

class InstitutionalActivity(Enum):
    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"
    RANGING = "ranging"
    BREAKOUT = "breakout"
    NONE = "none"

@dataclass
class VolumeAnalysis:
    total_volume: float
    buy_volume: float
    sell_volume: float
    volume_ratio: float
    volume_imbalance: float
    avg_volume_period: float
    volume_trend: str
    unusual_volume: bool

@dataclass
class OrderFlowIntelligence:
    market_structure: str
    support_levels: List[float]
    resistance_levels: List[float]
    volume_poc: float
    institutional_signal: InstitutionalActivity
    momentum_score: float
    trend_strength: float
    volatility_regime: str

class MarketIntelligenceAnalyzer:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.min_bars_for_analysis = 100
        self.volume_threshold_multiplier = 1.5
    
    async def analyze_volume_profile(self, ohlcv_data) -> VolumeAnalysis:
        try:
            df = _normalize_ohlcv(ohlcv_data)
            if df is None or len(df) == 0:
                return VolumeAnalysis(0, 0, 0, 0, 0, 0, "stable", False)
            if len(df) < self.min_bars_for_analysis:
                raise ValueError(f"Insufficient data")
            
            total_volume = float(df['volume'].sum())
            df['price_change'] = df['close'] - df['open']
            df['is_bullish'] = df['price_change'] >= 0
            
            buy_volume = float(df[df['is_bullish']]['volume'].sum())
            sell_volume = float(df[~df['is_bullish']]['volume'].sum())
            
            volume_ratio = buy_volume / sell_volume if sell_volume > 0 else 0
            volume_imbalance = (buy_volume - sell_volume) / total_volume if total_volume > 0 else 0
            
            avg_volume = float(df['volume'].rolling(20).mean().iloc[-1])
            current_volume = float(df['volume'].iloc[-1])
            unusual_volume = current_volume > (avg_volume * self.volume_threshold_multiplier)
            
            recent_volume = float(df['volume'].iloc[-20:].mean())
            older_volume = float(df['volume'].iloc[-50:-20].mean())
            if recent_volume > older_volume * 1.1:
                volume_trend = "increasing"
            elif recent_volume < older_volume * 0.9:
                volume_trend = "decreasing"
            else:
                volume_trend = "stable"
            
            return VolumeAnalysis(total_volume, buy_volume, sell_volume, volume_ratio, volume_imbalance, avg_volume, volume_trend, unusual_volume)
        except Exception as e:
            self.logger.error(f"Volume analysis error: {e}")
            return VolumeAnalysis(0, 0, 0, 0, 0, 0, "stable", False)
    
    async def analyze_order_flow(self, ohlcv_data, current_price: float) -> OrderFlowIntelligence:
        try:
            df = _normalize_ohlcv(ohlcv_data)
            if df is None or len(df) < 50:
                return OrderFlowIntelligence("neutral", [], [], current_price, InstitutionalActivity.NONE, 0, 0, "normal")
            
            # Simple support/resistance
            resistance_levels = [float(df['high'].max())]
            support_levels = [float(df['low'].min())]
            
            # Volume POC — guard against all-zero volume (avoids np.average ZeroDivisionError)
            _vol_weights = df['volume'].values.copy()
            if _vol_weights.sum() == 0:
                _vol_weights = np.ones(len(_vol_weights))
            volume_poc = float(np.average(df['close'].values, weights=_vol_weights))
            
            # Momentum
            close = df['close'].values
            momentum = (close[-1] - close[-20]) / close[-20] * 100 if close[-20] != 0 else 0
            
            # Trend strength
            high_trend = np.mean(df['high'].values[-20:]) > np.mean(df['high'].values[-50:-20])
            trend_strength = 75.0 if high_trend else 25.0
            
            # Volatility
            returns = np.diff(np.log(close[-20:]))
            volatility = float(np.std(returns) * 100)
            if volatility > 5:
                vol_regime = "high"
            elif volatility > 2:
                vol_regime = "normal"
            else:
                vol_regime = "low"
            
            # Institutional signal
            inst_signal = InstitutionalActivity.ACCUMULATION if momentum > 0 else InstitutionalActivity.DISTRIBUTION
            
            market_structure = "bullish" if momentum > 0 else ("bearish" if momentum < 0 else "ranging")
            
            return OrderFlowIntelligence(market_structure, support_levels, resistance_levels, volume_poc, inst_signal, momentum, trend_strength, vol_regime)
        except Exception as e:
            self.logger.error(f"Order flow analysis error: {e}")
            return OrderFlowIntelligence("neutral", [], [], current_price, InstitutionalActivity.NONE, 0, 0, "normal")
    
    async def get_market_intelligence_summary(self, ohlcv_data, current_price: float) -> Dict[str, Any]:
        try:
            vol_analysis = await self.analyze_volume_profile(ohlcv_data)
            flow_analysis = await self.analyze_order_flow(ohlcv_data, current_price)
            
            signal = "STRONG_BUY" if flow_analysis.momentum_score > 5 and vol_analysis.unusual_volume else ("BUY" if flow_analysis.momentum_score > 0 else "NEUTRAL")
            
            return {
                'volume': {'total': vol_analysis.total_volume, 'buy': vol_analysis.buy_volume, 'sell': vol_analysis.sell_volume, 'ratio': vol_analysis.volume_ratio, 'trend': vol_analysis.volume_trend, 'unusual': vol_analysis.unusual_volume},
                'orderflow': {'market': flow_analysis.market_structure, 'momentum': flow_analysis.momentum_score, 'strength': flow_analysis.trend_strength, 'volatility': flow_analysis.volatility_regime},
                'signal': signal
            }
        except Exception as e:
            self.logger.error(f"Market intelligence summary error: {e}")
            return {'signal': 'NEUTRAL'}

# Global instance
market_analyzer = MarketIntelligenceAnalyzer()
