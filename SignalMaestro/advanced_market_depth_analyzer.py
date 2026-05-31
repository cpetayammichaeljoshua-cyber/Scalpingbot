#!/usr/bin/env python3
"""
Advanced Market Depth Analyzer
Analyzes DOM depth, aggressive/passive interactions, and market microstructure
Integrates time & sales (tape) analysis with footprint detection
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from collections import deque
import asyncio


class DOMDepthSignal(Enum):
    EXTREME_BUY = "EXTREME_BUY"
    STRONG_BUY = "STRONG_BUY"
    MODERATE_BUY = "MODERATE_BUY"
    BALANCED = "BALANCED"
    MODERATE_SELL = "MODERATE_SELL"
    STRONG_SELL = "STRONG_SELL"
    EXTREME_SELL = "EXTREME_SELL"


class TapePattern(Enum):
    AGGRESSIVE_BUYING = "AGGRESSIVE_BUYING"
    AGGRESSIVE_SELLING = "AGGRESSIVE_SELLING"
    MIXED_ACTIVITY = "MIXED_ACTIVITY"
    QUIET = "QUIET"
    BREAKOUT = "BREAKOUT"


class FootprintType(Enum):
    ABSORPTION = "ABSORPTION"
    EXHAUSTION = "EXHAUSTION"
    IMBALANCE = "IMBALANCE"
    SUPPORT_BUILD = "SUPPORT_BUILD"
    RESISTANCE_BUILD = "RESISTANCE_BUILD"
    ACCUMULATION = "ACCUMULATION"
    DISTRIBUTION = "DISTRIBUTION"


@dataclass
class DOMDepthMetrics:
    """DOM depth analysis metrics"""
    spread: float
    mid_price: float
    depth_imbalance: float  # -1 to 1 (negative=buy, positive=sell)
    aggressive_buy_pressure: float  # 0-100
    aggressive_sell_pressure: float  # 0-100
    passive_depth_ratio: float  # bid depth / ask depth
    level_1_dominance: float  # L1 volume as % of total
    stacked_levels: int  # Consecutive levels with high volume
    depth_signal: DOMDepthSignal
    signal_strength: float  # 0-100


@dataclass
class TapeAnalysis:
    """Time & Sales tape analysis"""
    pattern: TapePattern
    buy_volume: float
    sell_volume: float
    buy_aggression: float  # 0-100
    sell_aggression: float  # 0-100
    trend_direction: str  # "UP", "DOWN", "NEUTRAL"
    momentum: float  # -100 to 100
    profile_type: str  # "balanced", "buy_heavy", "sell_heavy"
    recent_large_trades: List[Dict]
    confidence: float  # 0-100


@dataclass
class FootprintAnalysis:
    """Advanced footprint analysis"""
    footprint_type: FootprintType
    location_price: float
    strength: float  # 0-100
    duration: int  # number of candles
    volume_ratio: float  # imbalance level
    absorption_level: float  # 0-100 (how much volume absorbed)
    rejection_level: float  # 0-100 (how much volume rejected)
    profile: str  # P=point control, B=breakout, T=trend
    next_move_probability: float  # 0-100


class AdvancedMarketDepthAnalyzer:
    """Advanced market depth analysis combining DOM, tape, and footprint"""
    
    def __init__(self, symbol: str = "BTCUSDT"):
        self.logger = logging.getLogger(__name__)
        self.symbol = symbol
        
        # DOM depth parameters
        self.dom_levels = 20
        self.spread_threshold = 0.0001
        self.volume_threshold = 0.3
        
        # Tape analysis parameters
        self.tape_window = 50  # last 50 trades
        self.tape_history = deque(maxlen=self.tape_window)
        self.aggression_threshold = 0.6
        
        # Footprint parameters
        self.footprint_history = deque(maxlen=100)
        self.absorption_threshold = 1.3
        self.exhaustion_threshold = 0.4
        
        # Cache
        self.last_depths = []
        self.volume_clusters = {}
        
        self.logger.info("✅ Advanced Market Depth Analyzer initialized")
    
    async def analyze_dom_depth(self, depth: Dict[str, Any], current_price: float) -> DOMDepthMetrics:
        """Analyze depth of market interactions"""
        try:
            bids = np.array(depth.get('bids', [])[:self.dom_levels], dtype=float)
            asks = np.array(depth.get('asks', [])[:self.dom_levels], dtype=float)
            
            if len(bids) < 5 or len(asks) < 5:
                return self._fallback_dom_depth(current_price)
            
            bid_prices, bid_vols = bids[:, 0], bids[:, 1]
            ask_prices, ask_vols = asks[:, 0], asks[:, 1]
            
            # Calculate spread and mid
            spread = float(ask_prices[0] - bid_prices[0])
            mid_price = float((bid_prices[0] + ask_prices[0]) / 2)
            
            # Aggressive/Passive analysis
            aggressive_buy = bid_vols[0]  # L1 bid (willing to buy NOW)
            aggressive_sell = ask_vols[0]  # L1 ask (willing to sell NOW)
            aggressive_ratio = aggressive_buy / (aggressive_sell + 0.001)
            
            # Passive depth (levels 2-5)
            passive_bid = np.sum(bid_vols[1:5])
            passive_ask = np.sum(ask_vols[1:5])
            passive_ratio = passive_bid / (passive_ask + 0.001)
            
            # Total volumes
            total_bid = np.sum(bid_vols)
            total_ask = np.sum(ask_vols)
            
            # Depth imbalance (-1 buy heavy, +1 sell heavy)
            depth_imbalance = (total_ask - total_bid) / (total_bid + total_ask + 0.001)
            
            # Aggressive pressure
            aggressive_buy_pct = (aggressive_buy / (total_bid + 0.001)) * 100
            aggressive_sell_pct = (aggressive_sell / (total_ask + 0.001)) * 100
            
            # Level 1 dominance
            l1_dominance = (aggressive_buy + aggressive_sell) / (total_bid + total_ask + 0.001)
            
            # Stacked levels detection
            stacked = 0
            for i in range(1, min(5, len(bid_vols))):
                if bid_vols[i] > bid_vols[i-1] * 0.8:
                    stacked += 1
                else:
                    break
            
            # Determine signal
            depth_score = (aggressive_ratio - 1.0) * 100  # negative = buy, positive = sell
            
            if depth_score < -40:
                signal = DOMDepthSignal.EXTREME_BUY
            elif depth_score < -20:
                signal = DOMDepthSignal.STRONG_BUY
            elif depth_score < -10:
                signal = DOMDepthSignal.MODERATE_BUY
            elif depth_score > 40:
                signal = DOMDepthSignal.EXTREME_SELL
            elif depth_score > 20:
                signal = DOMDepthSignal.STRONG_SELL
            elif depth_score > 10:
                signal = DOMDepthSignal.MODERATE_SELL
            else:
                signal = DOMDepthSignal.BALANCED
            
            signal_strength = min(abs(depth_score), 100.0)
            
            return DOMDepthMetrics(
                spread=spread,
                mid_price=mid_price,
                depth_imbalance=float(depth_imbalance),
                aggressive_buy_pressure=float(aggressive_buy_pct),
                aggressive_sell_pressure=float(aggressive_sell_pct),
                passive_depth_ratio=float(passive_ratio),
                level_1_dominance=float(l1_dominance),
                stacked_levels=stacked,
                depth_signal=signal,
                signal_strength=float(signal_strength)
            )
        except Exception as e:
            self.logger.error(f"❌ DOM depth analysis error: {e}")
            return self._fallback_dom_depth(current_price)
    
    async def analyze_time_sales_tape(self, trades: List[Dict]) -> TapeAnalysis:
        """Analyze time and sales tape for pressure detection"""
        try:
            if not trades or len(trades) < 5:
                return self._fallback_tape_analysis()
            
            # Recent trades - safe type conversion
            recent = trades[-self.tape_window:]
            
            buy_vol = 0.0
            sell_vol = 0.0
            large_buys = []
            large_sells = []
            
            # Calculate avg price using pure Python to avoid dtype issues
            prices = []
            for t in recent:
                try:
                    p = float(t.get('price', 0))
                    prices.append(p)
                except (ValueError, TypeError):
                    pass
            avg_price = sum(prices) / len(prices) if prices else 1.0
            
            for trade in recent:
                try:
                    price = float(trade.get('price', 0))
                    qty = float(trade.get('qty', 0))
                    is_buyer_maker = trade.get('m', False)
                    
                    if is_buyer_maker:
                        sell_vol += qty
                        if qty > avg_price * 0.001:
                            large_sells.append({'price': price, 'qty': qty})
                    else:
                        buy_vol += qty
                        if qty > avg_price * 0.001:
                            large_buys.append({'price': price, 'qty': qty})
                except (ValueError, TypeError):
                    pass
            
            total_vol = buy_vol + sell_vol
            buy_aggression = (buy_vol / (total_vol + 0.001)) * 100
            sell_aggression = (sell_vol / (total_vol + 0.001)) * 100
            momentum = (buy_vol - sell_vol) / (total_vol + 0.001) * 100
            
            # Pattern detection - pure Python calculation
            if buy_vol > sell_vol * 1.5:
                pattern = TapePattern.AGGRESSIVE_BUYING
                profile = "buy_heavy"
            elif sell_vol > buy_vol * 1.5:
                pattern = TapePattern.AGGRESSIVE_SELLING
                profile = "sell_heavy"
            else:
                # Calculate historical average using pure Python (no numpy)
                hist_vols = []
                try:
                    for tape_data in list(self.tape_history)[-5:]:
                        if isinstance(tape_data, (int, float)):
                            hist_vols.append(float(tape_data))
                except:
                    pass
                
                if hist_vols:
                    hist_avg = sum(hist_vols) / len(hist_vols)
                    if total_vol < hist_avg * 0.5:
                        pattern = TapePattern.QUIET
                        profile = "balanced"
                    else:
                        pattern = TapePattern.MIXED_ACTIVITY
                        profile = "balanced"
                else:
                    pattern = TapePattern.MIXED_ACTIVITY
                    profile = "balanced"
            
            # Trend direction
            if momentum > 20:
                trend = "UP"
            elif momentum < -20:
                trend = "DOWN"
            else:
                trend = "NEUTRAL"
            
            # Confidence
            confidence = min((abs(momentum) / 100) * 100, 100.0)
            
            # Store volume as float
            self.tape_history.append(float(total_vol))
            
            return TapeAnalysis(
                pattern=pattern,
                buy_volume=float(buy_vol),
                sell_volume=float(sell_vol),
                buy_aggression=float(buy_aggression),
                sell_aggression=float(sell_aggression),
                trend_direction=trend,
                momentum=float(momentum),
                profile_type=profile,
                recent_large_trades=large_buys + large_sells,
                confidence=float(confidence)
            )
        except Exception as e:
            self.logger.error(f"❌ Tape analysis error: {e}")
            return self._fallback_tape_analysis()
    
    async def analyze_footprint(self, ohlcv_data: pd.DataFrame, 
                               current_price: float) -> FootprintAnalysis:
        """Analyze footprint patterns: absorption, exhaustion, imbalances"""
        try:
            if len(ohlcv_data) < 10:
                return self._fallback_footprint()
            
            # Get recent candles
            recent = ohlcv_data.iloc[-10:].copy()
            
            # Safe OHLCV column handling - add defaults if missing
            if 'volume' not in recent.columns:
                recent['volume'] = 1.0
            if 'high' not in recent.columns:
                recent['high'] = current_price
            if 'low' not in recent.columns:
                recent['low'] = current_price
            if 'close' not in recent.columns:
                recent['close'] = current_price
            if 'open' not in recent.columns:
                recent['open'] = current_price
            
            # Convert all to float arrays safely
            volumes = np.array(recent['volume'].values, dtype=np.float64)
            highs = np.array(recent['high'].values, dtype=np.float64)
            lows = np.array(recent['low'].values, dtype=np.float64)
            closes = np.array(recent['close'].values, dtype=np.float64)
            opens = np.array(recent['open'].values, dtype=np.float64)
            
            avg_vol = float(np.mean(volumes)) if len(volumes) > 0 else 1.0
            recent_vol = float(volumes[-1]) if len(volumes) > 0 else 1.0
            
            # Calculate absorption/rejection
            total_range = np.sum(highs - lows)
            body_range = np.sum(np.abs(closes - opens))
            wick_range = total_range - body_range
            
            absorption = (body_range / (total_range + 0.001)) * 100
            rejection = (wick_range / (total_range + 0.001)) * 100
            
            # Footprint type detection
            if recent_vol > avg_vol * 1.5 and absorption > 70:
                footprint_type = FootprintType.ABSORPTION
                strength = min(absorption, 100.0)
            elif recent_vol < avg_vol * 0.6:
                footprint_type = FootprintType.EXHAUSTION
                strength = min(100 - absorption, 100.0)
            elif absorption < 30:
                footprint_type = FootprintType.IMBALANCE
                strength = min(rejection, 100.0)
            elif closes[-1] > opens[-1] and recent_vol > avg_vol:
                footprint_type = FootprintType.ACCUMULATION
                strength = min(float((recent_vol / avg_vol) * 50), 100.0)
            elif closes[-1] < opens[-1] and recent_vol > avg_vol:
                footprint_type = FootprintType.DISTRIBUTION
                strength = min(float((recent_vol / avg_vol) * 50), 100.0)
            elif closes[-1] > highs[-2]:
                footprint_type = FootprintType.SUPPORT_BUILD
                strength = 50.0
            elif closes[-1] < lows[-2]:
                footprint_type = FootprintType.RESISTANCE_BUILD
                strength = 50.0
            else:
                footprint_type = FootprintType.IMBALANCE
                strength = 25.0
            
            # Volume profile
            if absorption > 70:
                profile = "P"  # Point control
            elif recent_vol > avg_vol * 1.2:
                profile = "B"  # Breakout
            else:
                profile = "T"  # Trend
            
            # Next move probability based on footprint
            if footprint_type == FootprintType.ABSORPTION and closes[-1] > opens[-1]:
                next_move_prob = 70.0  # Likely continuation up
            elif footprint_type == FootprintType.EXHAUSTION:
                next_move_prob = 65.0  # Likely reversal
            elif footprint_type == FootprintType.ACCUMULATION:
                next_move_prob = 60.0  # Accumulation = upcoming move
            else:
                next_move_prob = 45.0
            
            volume_ratio = recent_vol / (avg_vol + 0.001)
            
            return FootprintAnalysis(
                footprint_type=footprint_type,
                location_price=float(current_price),
                strength=float(strength),
                duration=len(recent),
                volume_ratio=float(volume_ratio),
                absorption_level=float(absorption),
                rejection_level=float(rejection),
                profile=profile,
                next_move_probability=float(next_move_prob)
            )
        except Exception as e:
            self.logger.error(f"❌ Footprint analysis error: {e}")
            return self._fallback_footprint()
    
    async def get_market_depth_signal(self, depth: Dict, trades: List, 
                                      ohlcv: pd.DataFrame, price: float) -> Dict[str, Any]:
        """Get combined market depth signal"""
        try:
            # Analyze all three dimensions
            dom_metrics = await self.analyze_dom_depth(depth, price)
            tape_analysis = await self.analyze_time_sales_tape(trades)
            footprint = await self.analyze_footprint(ohlcv, price)
            
            # Calculate combined confidence
            dom_confidence = dom_metrics.signal_strength / 100.0
            tape_confidence = tape_analysis.confidence / 100.0
            footprint_confidence = footprint.strength / 100.0
            
            combined_confidence = (dom_confidence * 0.35 + tape_confidence * 0.35 + footprint_confidence * 0.30) * 100
            
            # Determine overall direction
            buy_score = 0
            sell_score = 0
            
            # DOM contribution
            if dom_metrics.depth_signal in [DOMDepthSignal.EXTREME_BUY, DOMDepthSignal.STRONG_BUY]:
                buy_score += 30
            elif dom_metrics.depth_signal in [DOMDepthSignal.EXTREME_SELL, DOMDepthSignal.STRONG_SELL]:
                sell_score += 30
            
            # Tape contribution
            if tape_analysis.pattern == TapePattern.AGGRESSIVE_BUYING:
                buy_score += 25
            elif tape_analysis.pattern == TapePattern.AGGRESSIVE_SELLING:
                sell_score += 25
            
            # Footprint contribution
            if footprint.footprint_type in [FootprintType.ABSORPTION, FootprintType.ACCUMULATION]:
                buy_score += 25
            elif footprint.footprint_type == FootprintType.DISTRIBUTION:
                sell_score += 25
            
            direction = "BUY" if buy_score > sell_score else "SELL" if sell_score > buy_score else "NEUTRAL"
            
            return {
                "direction": direction,
                "confidence": float(min(combined_confidence, 100.0)),
                "dom_metrics": {
                    "signal": dom_metrics.depth_signal.value,
                    "strength": float(dom_metrics.signal_strength),
                    "aggressive_buy_pressure": float(dom_metrics.aggressive_buy_pressure),
                    "aggressive_sell_pressure": float(dom_metrics.aggressive_sell_pressure),
                    "passive_depth_ratio": float(dom_metrics.passive_depth_ratio),
                },
                "tape_analysis": {
                    "pattern": tape_analysis.pattern.value,
                    "momentum": float(tape_analysis.momentum),
                    "trend": tape_analysis.trend_direction,
                    "large_trades": len(tape_analysis.recent_large_trades),
                },
                "footprint": {
                    "type": footprint.footprint_type.value,
                    "strength": float(footprint.strength),
                    "profile": footprint.profile,
                    "next_move_probability": float(footprint.next_move_probability),
                }
            }
        except Exception as e:
            self.logger.error(f"❌ Combined analysis error: {e}")
            return {"direction": "NEUTRAL", "confidence": 0.0}
    
    def _fallback_dom_depth(self, price: float) -> DOMDepthMetrics:
        """Fallback DOM depth"""
        return DOMDepthMetrics(
            spread=0.0001,
            mid_price=price,
            depth_imbalance=0.0,
            aggressive_buy_pressure=50.0,
            aggressive_sell_pressure=50.0,
            passive_depth_ratio=1.0,
            level_1_dominance=0.1,
            stacked_levels=0,
            depth_signal=DOMDepthSignal.BALANCED,
            signal_strength=0.0
        )
    
    def _fallback_tape_analysis(self) -> TapeAnalysis:
        """Fallback tape analysis"""
        return TapeAnalysis(
            pattern=TapePattern.QUIET,
            buy_volume=0.0,
            sell_volume=0.0,
            buy_aggression=50.0,
            sell_aggression=50.0,
            trend_direction="NEUTRAL",
            momentum=0.0,
            profile_type="balanced",
            recent_large_trades=[],
            confidence=0.0
        )
    
    def _fallback_footprint(self) -> FootprintAnalysis:
        """Fallback footprint"""
        return FootprintAnalysis(
            footprint_type=FootprintType.IMBALANCE,
            location_price=0.0,
            strength=0.0,
            duration=0,
            volume_ratio=1.0,
            absorption_level=50.0,
            rejection_level=50.0,
            profile="T",
            next_move_probability=50.0
        )


# Global instance
_market_depth_analyzer = None

def get_market_depth_analyzer(symbol: str = "BTCUSDT") -> AdvancedMarketDepthAnalyzer:
    """Get or create analyzer instance"""
    global _market_depth_analyzer
    if _market_depth_analyzer is None:
        _market_depth_analyzer = AdvancedMarketDepthAnalyzer(symbol)
    return _market_depth_analyzer
