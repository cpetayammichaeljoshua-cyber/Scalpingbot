#!/usr/bin/env python3
"""
Insider Trading Analyzer - Fixed version with column handling
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any
import pandas as pd
import numpy as np

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

@dataclass
class InsiderSignal:
    detected: bool
    confidence: float
    activity_type: str
    description: str
    recommendation: str
    strength: float

class InsiderTradingAnalyzer:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def detect_insider_activity(self, market_data) -> InsiderSignal:
        try:
            df = _normalize_ohlcv(market_data)
            if df is None or len(df) < 50:
                return InsiderSignal(False, 0, "none", "Insufficient data", "Wait", 0)
            
            recent = df.tail(50).copy()
            avg_volume = float(recent['volume'].mean())
            current_volume = float(recent['volume'].iloc[-1])
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            
            if volume_ratio > 3.0:
                return InsiderSignal(True, 85.0, "whale_activity", "🐋 Large volume spike detected", "🎯 High probability move incoming", volume_ratio * 20)
            
            recent['close_position'] = (recent['close'] - recent['low']) / (recent['high'] - recent['low'])
            accumulation_score = float((recent['close_position'] > 0.7).sum() / len(recent) * 100)
            
            if accumulation_score > 70 and volume_ratio > 1.5:
                return InsiderSignal(True, 78.0, "accumulation", "📈 Accumulation pattern detected", "🎯 Bullish signal", accumulation_score)
            
            distribution_score = float((recent['close_position'] < 0.3).sum() / len(recent) * 100)
            
            if distribution_score > 70 and volume_ratio > 1.5:
                return InsiderSignal(True, 78.0, "distribution", "📉 Distribution pattern detected", "🎯 Bearish signal", distribution_score)
            
            if volume_ratio > 1.8:
                return InsiderSignal(True, 72.0, "volume_surge", "📊 Volume surge detected", "⚠️ Increased volatility expected", volume_ratio * 15)
            
            return InsiderSignal(False, 0, "none", "🟢 No unusual activity", "Monitor", 0)
        except Exception as e:
            self.logger.error(f"Insider activity detection error: {e}")
            return InsiderSignal(False, 0, "none", "Error analyzing", "Wait", 0)

# Global instance
insider_analyzer = InsiderTradingAnalyzer()
