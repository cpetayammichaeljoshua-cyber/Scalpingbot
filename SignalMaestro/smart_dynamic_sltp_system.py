
#!/usr/bin/env python3
"""
Smart Dynamic SL/TP System
Advanced order flow analysis for intelligent stop loss and take profit positioning
Dynamically adjusts based on market microstructure, liquidity zones, and momentum
"""

import asyncio
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import aiohttp

class OrderFlowDirection(Enum):
    """Order flow direction classification"""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"

class LiquidityZoneType(Enum):
    """Liquidity zone classification"""
    SUPPORT = "support"
    RESISTANCE = "resistance"
    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"
    PIVOT = "pivot"

@dataclass
class OrderFlowAnalysis:
    """Order flow analysis result"""
    direction: OrderFlowDirection
    strength: float  # 0-100
    volume_imbalance: float
    aggressive_buy_ratio: float
    aggressive_sell_ratio: float
    net_delta: float
    cumulative_delta: float
    absorption_zones: List[float]
    rejection_zones: List[float]

@dataclass
class LiquidityZone:
    """Liquidity zone definition"""
    price: float
    zone_type: LiquidityZoneType
    strength: float  # 0-100
    volume: float
    touches: int
    last_test_time: Optional[datetime]
    distance_from_current: float

@dataclass
class SmartSLTP:
    """Smart stop loss and take profit levels"""
    entry_price: float
    
    # Stop Loss Levels
    stop_loss: float
    stop_loss_buffer: float  # Distance beyond key level
    stop_loss_reasoning: str
    
    # Take Profit Levels
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    tp1_percentage: float
    tp2_percentage: float
    tp3_percentage: float
    tp_reasoning: str
    
    # Risk Management
    risk_reward_ratio: float
    position_size_multiplier: float
    confidence_score: float
    
    # Market Context
    order_flow_direction: OrderFlowDirection
    dominant_liquidity_zones: List[LiquidityZone]
    market_regime: str
    volatility_adjustment: float

class SmartDynamicSLTPSystem:
    """
    Intelligent dynamic SL/TP system with order flow analysis
    """
    
    def __init__(self, symbol: str = "BTCUSDT"):
        self.logger = logging.getLogger(__name__)
        self.symbol = symbol
        
        # Order flow parameters
        self.order_flow_config = {
            'volume_lookback': 100,
            'delta_sensitivity': 0.65,
            'absorption_threshold': 1.5,
            'aggressive_ratio_threshold': 0.6,
            'cumulative_delta_periods': 50
        }
        
        # Liquidity zone detection
        self.liquidity_config = {
            'min_touches': 2,
            'zone_width_pct': 0.002,  # 0.2% zone width
            'volume_threshold': 1.3,
            'strength_decay_hours': 24,
            'max_zones': 10
        }
        
        # SL/TP optimization
        self.sltp_config = {
            'min_risk_reward': 1.8,
            'optimal_risk_reward': 2.5,
            'max_risk_reward': 4.0,
            'sl_buffer_pct': 0.0015,  # 0.15% buffer beyond key level
            'tp_scale_factor': 1.2,
            'volatility_multiplier': 1.0
        }
        
        # Market regime detection
        self.regime_thresholds = {
            'trending_adx': 25,
            'volatile_atr_pct': 0.025,
            'ranging_bb_width': 0.015,
            'momentum_rsi_extreme': 30
        }
        
        self.logger.info(f"🎯 Smart Dynamic SL/TP System initialized for {symbol}")
    
    async def analyze_order_flow(self, market_data: pd.DataFrame, 
                                current_price: float) -> OrderFlowAnalysis:
        """
        Comprehensive order flow analysis
        """
        try:
            if len(market_data) < self.order_flow_config['volume_lookback']:
                return self._fallback_order_flow(current_price)
            
            # Extract OHLCV data as proper numpy arrays
            high = np.asarray(market_data['high'].values, dtype=np.float64)
            low = np.asarray(market_data['low'].values, dtype=np.float64)
            close = np.asarray(market_data['close'].values, dtype=np.float64)
            volume = np.asarray(market_data['volume'].values, dtype=np.float64)
            
            # Calculate volume delta (buy vs sell pressure)
            buy_volume = []
            sell_volume = []
            
            for i in range(len(market_data)):
                if i == 0:
                    buy_volume.append(volume[i] * 0.5)
                    sell_volume.append(volume[i] * 0.5)
                    continue
                
                # Price-volume analysis
                price_change = close[i] - close[i-1]
                
                if price_change > 0:
                    # Price up = more buying
                    buy_ratio = 0.5 + min(0.5, abs(price_change) / close[i-1] * 10)
                    buy_volume.append(volume[i] * buy_ratio)
                    sell_volume.append(volume[i] * (1 - buy_ratio))
                elif price_change < 0:
                    # Price down = more selling
                    sell_ratio = 0.5 + min(0.5, abs(price_change) / close[i-1] * 10)
                    sell_volume.append(volume[i] * sell_ratio)
                    buy_volume.append(volume[i] * (1 - sell_ratio))
                else:
                    buy_volume.append(volume[i] * 0.5)
                    sell_volume.append(volume[i] * 0.5)
            
            buy_volume = np.array(buy_volume)
            sell_volume = np.array(sell_volume)
            
            # Calculate aggressive orders (high volume candles)
            avg_volume = float(np.mean(volume[-50:]))
            aggressive_threshold = avg_volume * self.order_flow_config['absorption_threshold']
            
            aggressive_buy = np.sum(buy_volume[-20:] > aggressive_threshold)
            aggressive_sell = np.sum(sell_volume[-20:] > aggressive_threshold)
            total_aggressive = aggressive_buy + aggressive_sell
            
            aggressive_buy_ratio = aggressive_buy / total_aggressive if total_aggressive > 0 else 0.5
            aggressive_sell_ratio = aggressive_sell / total_aggressive if total_aggressive > 0 else 0.5
            
            # Calculate net delta and cumulative delta
            net_delta = np.sum(buy_volume[-20:]) - np.sum(sell_volume[-20:])
            
            cumulative_delta = []
            delta_sum = 0
            for i in range(len(buy_volume)):
                delta_sum += (buy_volume[i] - sell_volume[i])
                cumulative_delta.append(delta_sum)
            
            cumulative_delta = np.array(cumulative_delta)
            
            # Calculate volume imbalance
            recent_buy_vol = np.sum(buy_volume[-20:])
            recent_sell_vol = np.sum(sell_volume[-20:])
            total_vol = recent_buy_vol + recent_sell_vol
            
            volume_imbalance = (recent_buy_vol - recent_sell_vol) / total_vol if total_vol > 0 else 0
            
            # Detect absorption and rejection zones
            absorption_zones = self._detect_absorption_zones(
                market_data, buy_volume, sell_volume
            )
            rejection_zones = self._detect_rejection_zones(
                market_data, buy_volume, sell_volume
            )
            
            # Determine order flow direction
            flow_strength = abs(volume_imbalance) * 100
            
            if volume_imbalance > 0.3 and aggressive_buy_ratio > 0.65:
                direction = OrderFlowDirection.STRONG_BUY
            elif volume_imbalance > 0.1:
                direction = OrderFlowDirection.BUY
            elif volume_imbalance < -0.3 and aggressive_sell_ratio > 0.65:
                direction = OrderFlowDirection.STRONG_SELL
            elif volume_imbalance < -0.1:
                direction = OrderFlowDirection.SELL
            else:
                direction = OrderFlowDirection.NEUTRAL
            
            return OrderFlowAnalysis(
                direction=direction,
                strength=min(100, flow_strength),
                volume_imbalance=volume_imbalance,
                aggressive_buy_ratio=aggressive_buy_ratio,
                aggressive_sell_ratio=aggressive_sell_ratio,
                net_delta=net_delta,
                cumulative_delta=cumulative_delta[-1],
                absorption_zones=absorption_zones,
                rejection_zones=rejection_zones
            )
            
        except Exception as e:
            self.logger.error(f"Order flow analysis error: {e}")
            return self._fallback_order_flow(current_price)
    
    def _detect_absorption_zones(self, market_data: pd.DataFrame,
                                 buy_volume: np.ndarray,
                                 sell_volume: np.ndarray) -> List[float]:
        """Detect price levels where orders are absorbed (high volume, small price movement)"""
        absorption_zones = []
        
        try:
            close = np.asarray(market_data['close'].values, dtype=np.float64)
            high = np.asarray(market_data['high'].values, dtype=np.float64)
            low = np.asarray(market_data['low'].values, dtype=np.float64)
            
            for i in range(10, len(market_data)):
                # High volume but small price range = absorption
                avg_combined = float(np.mean(buy_volume + sell_volume))
                volume_surge = (buy_volume[i] + sell_volume[i]) > avg_combined * 1.5
                price_range = (high[i] - low[i]) / close[i]
                
                if volume_surge and price_range < 0.003:  # Less than 0.3% range
                    absorption_zones.append(float(close[i]))
            
            # Cluster nearby zones
            if absorption_zones:
                absorption_zones = self._cluster_price_levels(absorption_zones)
            
        except Exception as e:
            self.logger.error(f"Absorption zone detection error: {e}")
        
        return absorption_zones[-5:] if absorption_zones else []
    
    def _detect_rejection_zones(self, market_data: pd.DataFrame,
                                buy_volume: np.ndarray,
                                sell_volume: np.ndarray) -> List[float]:
        """Detect price levels where orders are rejected (wicks, reversals)"""
        rejection_zones = []
        
        try:
            close = np.asarray(market_data['close'].values, dtype=np.float64)
            high = np.asarray(market_data['high'].values, dtype=np.float64)
            low = np.asarray(market_data['low'].values, dtype=np.float64)
            open_price = np.asarray(market_data['open'].values, dtype=np.float64)
            
            for i in range(10, len(market_data)):
                # Long wicks indicate rejection
                body_size = abs(close[i] - open_price[i])
                upper_wick = high[i] - max(close[i], open_price[i])
                lower_wick = min(close[i], open_price[i]) - low[i]
                
                # Upper rejection (resistance)
                if upper_wick > body_size * 2:
                    rejection_zones.append(float(high[i]))
                
                # Lower rejection (support)
                if lower_wick > body_size * 2:
                    rejection_zones.append(float(low[i]))
            
            # Cluster nearby zones
            if rejection_zones:
                rejection_zones = self._cluster_price_levels(rejection_zones)
            
        except Exception as e:
            self.logger.error(f"Rejection zone detection error: {e}")
        
        return rejection_zones[-5:] if rejection_zones else []
    
    async def detect_liquidity_zones(self, market_data: pd.DataFrame,
                                    current_price: float) -> List[LiquidityZone]:
        """
        Detect key liquidity zones using volume profile and price action
        """
        try:
            liquidity_zones = []
            
            high = np.asarray(market_data['high'].values, dtype=np.float64)
            low = np.asarray(market_data['low'].values, dtype=np.float64)
            close = np.asarray(market_data['close'].values, dtype=np.float64)
            volume = np.asarray(market_data['volume'].values, dtype=np.float64)
            
            # Find swing highs and lows (potential liquidity zones)
            swing_highs = []
            swing_lows = []
            
            for i in range(5, len(market_data) - 5):
                # Swing high
                if all(high[i] >= high[i-j] for j in range(1, 6)) and \
                   all(high[i] >= high[i+j] for j in range(1, 6)):
                    touches = sum(1 for j in range(max(0, i-20), min(len(high), i+20))
                                if abs(high[j] - high[i]) / high[i] < 0.001)
                    
                    zone_volume = float(np.sum(volume[max(0, i-5):min(len(volume), i+5)]))
                    avg_volume = float(np.mean(volume))
                    
                    if zone_volume > avg_volume * self.liquidity_config['volume_threshold']:
                        swing_highs.append({
                            'price': float(high[i]),
                            'touches': touches,
                            'volume': float(zone_volume),
                            'index': i
                        })
                
                # Swing low
                if all(low[i] <= low[i-j] for j in range(1, 6)) and \
                   all(low[i] <= low[i+j] for j in range(1, 6)):
                    touches = sum(1 for j in range(max(0, i-20), min(len(low), i+20))
                                if abs(low[j] - low[i]) / low[i] < 0.001)
                    
                    zone_volume = float(np.sum(volume[max(0, i-5):min(len(volume), i+5)]))
                    avg_volume = float(np.mean(volume))
                    
                    if zone_volume > avg_volume * self.liquidity_config['volume_threshold']:
                        swing_lows.append({
                            'price': float(low[i]),
                            'touches': touches,
                            'volume': float(zone_volume),
                            'index': i
                        })
            
            # Create liquidity zones from swing points
            avg_vol = float(np.mean(volume))
            for swing in swing_highs:
                if swing['touches'] >= self.liquidity_config['min_touches']:
                    strength = min(100, (swing['touches'] * 20 + 
                                       (swing['volume'] / avg_vol) * 30))
                    
                    liquidity_zones.append(LiquidityZone(
                        price=swing['price'],
                        zone_type=LiquidityZoneType.RESISTANCE,
                        strength=strength,
                        volume=swing['volume'],
                        touches=swing['touches'],
                        last_test_time=None,
                        distance_from_current=abs(swing['price'] - current_price) / current_price
                    ))
            
            for swing in swing_lows:
                if swing['touches'] >= self.liquidity_config['min_touches']:
                    strength = min(100, (swing['touches'] * 20 + 
                                       (swing['volume'] / avg_vol) * 30))
                    
                    liquidity_zones.append(LiquidityZone(
                        price=swing['price'],
                        zone_type=LiquidityZoneType.SUPPORT,
                        strength=strength,
                        volume=swing['volume'],
                        touches=swing['touches'],
                        last_test_time=None,
                        distance_from_current=abs(swing['price'] - current_price) / current_price
                    ))
            
            # Sort by distance from current price
            liquidity_zones.sort(key=lambda x: x.distance_from_current)
            
            return liquidity_zones[:self.liquidity_config['max_zones']]
            
        except Exception as e:
            self.logger.error(f"Liquidity zone detection error: {e}")
            return []
    
    async def calculate_smart_sltp(self, direction: str, entry_price: float,
                                  market_data: pd.DataFrame,
                                  order_flow: OrderFlowAnalysis,
                                  liquidity_zones: List[LiquidityZone]) -> SmartSLTP:
        """
        Calculate intelligent SL/TP based on order flow and liquidity analysis
        """
        try:
            direction = direction.upper()
            
            # Detect market regime
            market_regime = await self._detect_market_regime(market_data)
            
            # Calculate volatility adjustment
            atr = self._calculate_atr(np.asarray(market_data['high'].values, dtype=np.float64), 
                                     np.asarray(market_data['low'].values, dtype=np.float64),
                                     np.asarray(market_data['close'].values, dtype=np.float64))
            atr_pct = (atr / entry_price) * 100
            volatility_adjustment = max(0.8, min(1.5, atr_pct / 0.02))
            
            # Separate support and resistance zones
            support_zones = [z for z in liquidity_zones if z.zone_type == LiquidityZoneType.SUPPORT]
            resistance_zones = [z for z in liquidity_zones if z.zone_type == LiquidityZoneType.RESISTANCE]
            
            if direction in ['LONG', 'BUY']:
                # LONG position
                stop_loss, sl_reasoning = self._calculate_long_stop_loss(
                    entry_price, support_zones, order_flow, atr
                )
                
                tp1, tp2, tp3, tp_reasoning = self._calculate_long_take_profits(
                    entry_price, resistance_zones, order_flow, atr, market_regime
                )
                
            else:
                # SHORT position
                stop_loss, sl_reasoning = self._calculate_short_stop_loss(
                    entry_price, resistance_zones, order_flow, atr
                )
                
                tp1, tp2, tp3, tp_reasoning = self._calculate_short_take_profits(
                    entry_price, support_zones, order_flow, atr, market_regime
                )
            
            # Calculate risk/reward ratio
            risk = abs(entry_price - stop_loss)
            reward = abs(tp3 - entry_price)
            risk_reward_ratio = reward / risk if risk > 0 else 2.0
            
            # Adjust position size based on order flow confidence
            flow_confidence = order_flow.strength / 100
            position_multiplier = 0.5 + (flow_confidence * 0.5)  # 0.5x to 1.0x
            
            # Overall confidence score
            confidence_score = (
                flow_confidence * 0.4 +
                ((min(liquidity_zones, key=lambda x: x.distance_from_current).strength / 100) if liquidity_zones else 0.5) * 0.3 +
                (risk_reward_ratio / self.sltp_config['max_risk_reward']) * 0.3
            ) * 100
            
            return SmartSLTP(
                entry_price=entry_price,
                stop_loss=stop_loss,
                stop_loss_buffer=abs(stop_loss - entry_price) * self.sltp_config['sl_buffer_pct'],
                stop_loss_reasoning=sl_reasoning,
                take_profit_1=tp1,
                take_profit_2=tp2,
                take_profit_3=tp3,
                tp1_percentage=33.0,
                tp2_percentage=33.0,
                tp3_percentage=34.0,
                tp_reasoning=tp_reasoning,
                risk_reward_ratio=risk_reward_ratio,
                position_size_multiplier=position_multiplier,
                confidence_score=min(100, confidence_score),
                order_flow_direction=order_flow.direction,
                dominant_liquidity_zones=liquidity_zones[:3],
                market_regime=market_regime,
                volatility_adjustment=volatility_adjustment
            )
            
        except Exception as e:
            self.logger.error(f"Smart SL/TP calculation error: {e}")
            return self._fallback_sltp(direction, entry_price)
    
    def _calculate_long_stop_loss(self, entry_price: float,
                                  support_zones: List[LiquidityZone],
                                  order_flow: OrderFlowAnalysis,
                                  atr: float) -> Tuple[float, str]:
        """Calculate intelligent stop loss for LONG position"""
        
        # Find nearest support below entry
        valid_supports = [z for z in support_zones if z.price < entry_price]
        
        # Support-based SL
        support_sl = 0
        if valid_supports:
            nearest_support = max(valid_supports, key=lambda x: x.price)
            buffer = entry_price * self.sltp_config['sl_buffer_pct']
            support_sl = nearest_support.price - buffer
            
        # ATR-based SL
        sl_distance = atr * 1.5
        atr_sl = entry_price - sl_distance
        
        # EXACT DYNAMIC LOGIC: Midpoint between entry and most conservative SL
        # "Strictly add a stop loss 50% from the entry and 50% from the original stop loss"
        base_sl = support_sl if (support_sl > 0 and support_sl < entry_price) else atr_sl
        dynamic_sl = entry_price - ((entry_price - base_sl) * 0.5)
        
        stop_loss = dynamic_sl
        reasoning = f"Dynamic Midpoint SL (50% from entry/base). Base: {base_sl:.6f}"
        
        # Check order flow absorption zones
        if order_flow.absorption_zones:
            absorption_below = [z for z in order_flow.absorption_zones if z < entry_price]
            if absorption_below:
                potential_sl = max(absorption_below) - (entry_price * 0.001)
                if potential_sl > stop_loss:
                    stop_loss = potential_sl
                    reasoning = f"Below absorption zone at {max(absorption_below):.6f}"
        
        return stop_loss, reasoning
    
    def _calculate_short_stop_loss(self, entry_price: float,
                                   resistance_zones: List[LiquidityZone],
                                   order_flow: OrderFlowAnalysis,
                                   atr: float) -> Tuple[float, str]:
        """Calculate intelligent stop loss for SHORT position"""
        
        # Find nearest resistance above entry
        valid_resistances = [z for z in resistance_zones if z.price > entry_price]
        
        # Resistance-based SL
        resistance_sl = 0
        if valid_resistances:
            nearest_resistance = max(valid_resistances, key=lambda x: x.strength)
            buffer = entry_price * self.sltp_config['sl_buffer_pct']
            resistance_sl = nearest_resistance.price + buffer
            
        # ATR-based SL
        sl_distance = atr * 1.5
        atr_sl = entry_price + sl_distance
        
        # EXACT DYNAMIC LOGIC: Midpoint between entry and most conservative SL
        base_sl = resistance_sl if (resistance_sl > 0 and resistance_sl > entry_price) else atr_sl
        dynamic_sl = entry_price + ((base_sl - entry_price) * 0.5)
        
        stop_loss = dynamic_sl
        reasoning = f"Dynamic Midpoint SL (50% from entry/base). Base: {base_sl:.6f}"
        
        # Check order flow absorption zones
        if order_flow.absorption_zones:
            absorption_above = [z for z in order_flow.absorption_zones if z > entry_price]
            if absorption_above:
                potential_sl = min(absorption_above) + (entry_price * 0.001)
                if potential_sl < stop_loss:
                    stop_loss = potential_sl
                    reasoning = f"Above absorption zone at {min(absorption_above):.6f}"
        
        return stop_loss, reasoning
    
    def _calculate_long_take_profits(self, entry_price: float,
                                     resistance_zones: List[LiquidityZone],
                                     order_flow: OrderFlowAnalysis,
                                     atr: float,
                                     market_regime: str) -> Tuple[float, float, float, str]:
        """Calculate intelligent take profits for LONG position - ENHANCED FOR MAXIMUM PROFITABILITY"""
        
        # Find resistances above entry
        valid_resistances = [z for z in resistance_zones if z.price > entry_price]
        valid_resistances.sort(key=lambda x: x.price)
        
        # ENHANCED: Order flow-based TP scaling
        flow_strength = order_flow.strength / 100.0  # 0-1
        flow_multiplier = 0.8 + (flow_strength * 0.6)  # 0.8 - 1.4x scaling
        
        if len(valid_resistances) >= 3:
            # Use actual resistance levels with flow-based extension
            tp1 = valid_resistances[0].price
            tp2 = valid_resistances[1].price
            tp3 = valid_resistances[2].price
            
            # ENHANCED: Extend TP3 based on order flow strength
            if order_flow.direction in [OrderFlowDirection.STRONG_BUY, OrderFlowDirection.BUY]:
                extension = (tp3 - entry_price) * (flow_multiplier - 1.0) * 0.5
                tp3 = tp3 + extension
                reasoning = f"Resistance-based TPs (Flow-extended): {tp1:.6f}, {tp2:.6f}, {tp3:.6f}"
            else:
                reasoning = f"Resistance-based TPs: {tp1:.6f}, {tp2:.6f}, {tp3:.6f}"
            
        elif len(valid_resistances) == 2:
            tp1 = valid_resistances[0].price
            tp2 = valid_resistances[1].price
            # ENHANCED: Better TP3 scaling with momentum
            tp3 = entry_price + (atr * 5 * flow_multiplier)
            reasoning = f"Mixed TPs (Momentum-optimized): R1={tp1:.6f}, R2={tp2:.6f}, ATR-extended={tp3:.6f}"
            
        elif len(valid_resistances) == 1:
            tp1 = valid_resistances[0].price
            # ENHANCED: Improved scaling for aggressive market
            tp2 = entry_price + (atr * 3.5 * flow_multiplier)
            tp3 = entry_price + (atr * 5.5 * flow_multiplier)
            reasoning = f"R1={tp1:.6f}, ATR-optimized TPs (Momentum)"
            
        else:
            # Full ATR-based with enhanced scaling
            base_tp1 = entry_price + (atr * 1.8)
            base_tp2 = entry_price + (atr * 3.2)
            base_tp3 = entry_price + (atr * 5.0)
            
            tp1 = base_tp1 * flow_multiplier if flow_multiplier > 1.0 else base_tp1
            tp2 = base_tp2 * flow_multiplier if flow_multiplier > 1.0 else base_tp2
            tp3 = base_tp3 * flow_multiplier if flow_multiplier > 1.0 else base_tp3
            reasoning = f"ATR-optimized TPs (Flow: {flow_multiplier:.2f}x, {order_flow.direction.value})"
        
        # ENHANCED: Aggressive regime adjustment for maximum profitability
        if market_regime == "trending_bullish":
            trend_extension = (tp3 - entry_price) * 0.35  # 35% extension in strong trends
            tp3 = tp3 + trend_extension
            tp2 = tp2 + (trend_extension * 0.25)  # Also boost TP2
            reasoning += " | STRONG TREND: TPs extended +35%"
        elif market_regime == "volatile" and order_flow.strength > 70:
            # In volatile markets with strong order flow, keep aggressive TPs
            tp1 = entry_price + (atr * 1.5)
            reasoning += " | Volatile + Strong Flow: Aggressive TP1"
        elif market_regime == "ranging":
            # In ranging markets, take quicker profits
            tp1 = entry_price + (atr * 1.2)
            tp2 = entry_price + (atr * 2.3)
            reasoning += " | Ranging: Quick-profit mode"
        
        # Ensure TP3 > TP2 > TP1 > Entry (sanity check)
        tp1 = max(tp1, entry_price + (atr * 0.5))
        tp2 = max(tp2, tp1 + (atr * 0.3))
        tp3 = max(tp3, tp2 + (atr * 0.5))
        
        return tp1, tp2, tp3, reasoning
    
    def _calculate_short_take_profits(self, entry_price: float,
                                      support_zones: List[LiquidityZone],
                                      order_flow: OrderFlowAnalysis,
                                      atr: float,
                                      market_regime: str) -> Tuple[float, float, float, str]:
        """Calculate intelligent take profits for SHORT position - ENHANCED FOR MAXIMUM PROFITABILITY"""
        
        # Find supports below entry
        valid_supports = [z for z in support_zones if z.price < entry_price]
        valid_supports.sort(key=lambda x: x.price, reverse=True)
        
        # ENHANCED: Order flow-based TP scaling for SHORT
        flow_strength = order_flow.strength / 100.0  # 0-1
        flow_multiplier = 0.8 + (flow_strength * 0.6)  # 0.8 - 1.4x scaling
        
        if len(valid_supports) >= 3:
            tp1 = valid_supports[0].price
            tp2 = valid_supports[1].price
            tp3 = valid_supports[2].price
            
            # ENHANCED: Extend TP3 based on order flow strength (downward for SHORT)
            if order_flow.direction in [OrderFlowDirection.STRONG_SELL, OrderFlowDirection.SELL]:
                extension = (entry_price - tp3) * (flow_multiplier - 1.0) * 0.5
                tp3 = tp3 - extension
                reasoning = f"Support-based TPs (Flow-extended): {tp1:.6f}, {tp2:.6f}, {tp3:.6f}"
            else:
                reasoning = f"Support-based TPs: {tp1:.6f}, {tp2:.6f}, {tp3:.6f}"
            
        elif len(valid_supports) == 2:
            tp1 = valid_supports[0].price
            tp2 = valid_supports[1].price
            # ENHANCED: Better TP3 scaling with momentum (downward)
            tp3 = entry_price - (atr * 5 * flow_multiplier)
            reasoning = f"Mixed TPs (Momentum-optimized): S1={tp1:.6f}, S2={tp2:.6f}, ATR-extended={tp3:.6f}"
            
        elif len(valid_supports) == 1:
            tp1 = valid_supports[0].price
            # ENHANCED: Improved scaling for aggressive market (downward)
            tp2 = entry_price - (atr * 3.5 * flow_multiplier)
            tp3 = entry_price - (atr * 5.5 * flow_multiplier)
            reasoning = f"S1={tp1:.6f}, ATR-optimized TPs (Momentum)"
            
        else:
            # Full ATR-based with enhanced scaling (SHORT: downward)
            base_tp1 = entry_price - (atr * 1.8)
            base_tp2 = entry_price - (atr * 3.2)
            base_tp3 = entry_price - (atr * 5.0)
            
            tp1 = base_tp1 * flow_multiplier if flow_multiplier > 1.0 else base_tp1
            tp2 = base_tp2 * flow_multiplier if flow_multiplier > 1.0 else base_tp2
            tp3 = base_tp3 * flow_multiplier if flow_multiplier > 1.0 else base_tp3
            reasoning = f"ATR-optimized TPs (Flow: {flow_multiplier:.2f}x, {order_flow.direction.value})"
        
        # ENHANCED: Aggressive regime adjustment for maximum profitability
        if market_regime == "trending_bearish":
            trend_extension = (entry_price - tp3) * 0.35  # 35% extension downward
            tp3 = tp3 - trend_extension
            tp2 = tp2 - (trend_extension * 0.25)  # Also boost TP2 downward
            reasoning += " | STRONG TREND: TPs extended -35%"
        elif market_regime == "volatile" and order_flow.strength > 70:
            # In volatile markets with strong order flow, keep aggressive TPs
            tp1 = entry_price - (atr * 1.5)
            reasoning += " | Volatile + Strong Flow: Aggressive TP1"
        elif market_regime == "ranging":
            # In ranging markets, take quicker profits
            tp1 = entry_price - (atr * 1.2)
            tp2 = entry_price - (atr * 2.3)
            reasoning += " | Ranging: Quick-profit mode"
        
        # Ensure TP3 < TP2 < TP1 < Entry (sanity check for SHORT)
        tp1 = min(tp1, entry_price - (atr * 0.5))
        tp2 = min(tp2, tp1 - (atr * 0.3))
        tp3 = min(tp3, tp2 - (atr * 0.5))
        
        return tp1, tp2, tp3, reasoning
    
    async def _detect_market_regime(self, market_data: pd.DataFrame) -> str:
        """Detect current market regime"""
        try:
            close = np.asarray(market_data['close'].values, dtype=np.float64)
            high = np.asarray(market_data['high'].values, dtype=np.float64)
            low = np.asarray(market_data['low'].values, dtype=np.float64)
            
            # ADX for trend strength
            adx = self._calculate_adx(high, low, close)
            
            # ATR for volatility
            atr = self._calculate_atr(high, low, close)
            atr_pct = (atr / close[-1]) * 100
            
            # Price trend
            sma_20 = float(np.mean(close[-20:]))
            trend = (close[-1] - sma_20) / sma_20
            
            if adx > self.regime_thresholds['trending_adx']:
                if trend > 0.01:
                    return "trending_bullish"
                elif trend < -0.01:
                    return "trending_bearish"
            
            if atr_pct > self.regime_thresholds['volatile_atr_pct']:
                return "volatile"
            
            return "ranging"
            
        except:
            return "unknown"
    
    def _calculate_atr(self, high: np.ndarray, low: np.ndarray, 
                      close: np.ndarray, period: int = 14) -> float:
        """Calculate Average True Range"""
        try:
            tr = np.maximum(high[1:] - low[1:],
                          np.maximum(np.abs(high[1:] - close[:-1]),
                                    np.abs(low[1:] - close[:-1])))
            return float(np.mean(tr[-period:]))
        except:
            return 0.001
    
    def _calculate_adx(self, high: np.ndarray, low: np.ndarray,
                      close: np.ndarray, period: int = 14) -> float:
        """Calculate Average Directional Index"""
        try:
            plus_dm = np.maximum(high[1:] - high[:-1], 0)
            minus_dm = np.maximum(low[:-1] - low[1:], 0)

            tr = np.maximum(high[1:] - low[1:],
                          np.maximum(np.abs(high[1:] - close[:-1]),
                                    np.abs(low[1:] - close[:-1])))
            
            plus_di = 100 * (np.mean(plus_dm[-period:]) / np.mean(tr[-period:]))
            minus_di = 100 * (np.mean(minus_dm[-period:]) / np.mean(tr[-period:]))
            
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
            
            return float(dx)
        except:
            return 20.0
    
    def _cluster_price_levels(self, prices: List[float], 
                             tolerance_pct: float = 0.002) -> List[float]:
        """Cluster nearby price levels"""
        if not prices:
            return []
        
        prices = sorted(prices)
        clusters = []
        current_cluster = [prices[0]]
        
        for i in range(1, len(prices)):
            if abs(prices[i] - current_cluster[-1]) / current_cluster[-1] < tolerance_pct:
                current_cluster.append(prices[i])
            else:
                clusters.append(np.mean(current_cluster))
                current_cluster = [prices[i]]
        
        clusters.append(np.mean(current_cluster))
        return clusters
    
    def _fallback_order_flow(self, current_price: float) -> OrderFlowAnalysis:
        """Fallback order flow analysis"""
        return OrderFlowAnalysis(
            direction=OrderFlowDirection.NEUTRAL,
            strength=50.0,
            volume_imbalance=0.0,
            aggressive_buy_ratio=0.5,
            aggressive_sell_ratio=0.5,
            net_delta=0.0,
            cumulative_delta=0.0,
            absorption_zones=[],
            rejection_zones=[]
        )
    
    def _fallback_sltp(self, direction: str, entry_price: float) -> SmartSLTP:
        """Fallback SL/TP calculation"""
        sl_distance = entry_price * 0.015
        tp_distance = entry_price * 0.035
        
        if direction.upper() in ['LONG', 'BUY']:
            return SmartSLTP(
                entry_price=entry_price,
                stop_loss=entry_price - sl_distance,
                stop_loss_buffer=sl_distance * 0.1,
                stop_loss_reasoning="Conservative ATR-based",
                take_profit_1=entry_price + tp_distance * 0.5,
                take_profit_2=entry_price + tp_distance * 0.8,
                take_profit_3=entry_price + tp_distance,
                tp1_percentage=33.0,
                tp2_percentage=33.0,
                tp3_percentage=34.0,
                tp_reasoning="Conservative ATR-scaled",
                risk_reward_ratio=2.0,
                position_size_multiplier=0.7,
                confidence_score=50.0,
                order_flow_direction=OrderFlowDirection.NEUTRAL,
                dominant_liquidity_zones=[],
                market_regime="unknown",
                volatility_adjustment=1.0
            )
        else:
            return SmartSLTP(
                entry_price=entry_price,
                stop_loss=entry_price + sl_distance,
                stop_loss_buffer=sl_distance * 0.1,
                stop_loss_reasoning="Conservative ATR-based",
                take_profit_1=entry_price - tp_distance * 0.5,
                take_profit_2=entry_price - tp_distance * 0.8,
                take_profit_3=entry_price - tp_distance,
                tp1_percentage=33.0,
                tp2_percentage=33.0,
                tp3_percentage=34.0,
                tp_reasoning="Conservative ATR-scaled",
                risk_reward_ratio=2.0,
                position_size_multiplier=0.7,
                confidence_score=50.0,
                order_flow_direction=OrderFlowDirection.NEUTRAL,
                dominant_liquidity_zones=[],
                market_regime="unknown",
                volatility_adjustment=1.0
            )


# Global instance
_smart_sltp_system = None

def get_smart_sltp_system(symbol: str = "BTCUSDT") -> SmartDynamicSLTPSystem:
    """Get or create smart SL/TP system instance"""
    global _smart_sltp_system
    if _smart_sltp_system is None:
        _smart_sltp_system = SmartDynamicSLTPSystem(symbol)
    return _smart_sltp_system


if __name__ == "__main__":
    # Test the system
    async def test_smart_sltp():
        logging.basicConfig(level=logging.INFO)

        system = SmartDynamicSLTPSystem("BTCUSDT")
        
        # Generate test market data
        np.random.seed(42)
        dates = pd.date_range(start='2025-01-01', periods=200, freq='1H')
        prices = 2.10 + np.cumsum(np.random.randn(200) * 0.001)
        
        test_data = pd.DataFrame({
            'timestamp': dates,
            'open': prices + np.random.randn(200) * 0.0005,
            'high': prices + np.abs(np.random.randn(200) * 0.001),
            'low': prices - np.abs(np.random.randn(200) * 0.001),
            'close': prices,
            'volume': np.random.uniform(100000, 500000, 200)
        })
        
        current_price = float(test_data['close'].iloc[-1])
        
        print("🎯 Testing Smart Dynamic SL/TP System")
        print(f"Current Price: {current_price:.6f}\n")
        
        # Analyze order flow
        order_flow = await system.analyze_order_flow(test_data, current_price)
        print(f"📊 Order Flow: {order_flow.direction.value}")
        print(f"   Strength: {order_flow.strength:.1f}%")
        print(f"   Volume Imbalance: {order_flow.volume_imbalance:.3f}")
        print(f"   Absorption Zones: {len(order_flow.absorption_zones)}")
        print(f"   Rejection Zones: {len(order_flow.rejection_zones)}\n")
        
        # Detect liquidity zones
        liquidity_zones = await system.detect_liquidity_zones(test_data, current_price)
        print(f"🎯 Liquidity Zones Found: {len(liquidity_zones)}")
        for zone in liquidity_zones[:3]:
            print(f"   {zone.zone_type.value}: {zone.price:.6f} (strength: {zone.strength:.0f})")
        print()
        
        # Calculate smart SL/TP for LONG
        sltp = await system.calculate_smart_sltp(
            "LONG", current_price, test_data, order_flow, liquidity_zones
        )
        
        print(f"📈 LONG Position SL/TP:")
        print(f"   Entry: {sltp.entry_price:.6f}")
        print(f"   Stop Loss: {sltp.stop_loss:.6f}")
        print(f"   - Reasoning: {sltp.stop_loss_reasoning}")
        print(f"   Take Profit 1: {sltp.take_profit_1:.6f} (33%)")
        print(f"   Take Profit 2: {sltp.take_profit_2:.6f} (33%)")
        print(f"   Take Profit 3: {sltp.take_profit_3:.6f} (34%)")
        print(f"   - Reasoning: {sltp.tp_reasoning}")
        print(f"   Risk/Reward: 1:{sltp.risk_reward_ratio:.2f}")
        print(f"   Confidence: {sltp.confidence_score:.1f}%")
        print(f"   Market Regime: {sltp.market_regime}")
        print(f"   Position Multiplier: {sltp.position_size_multiplier:.2f}x")
    
    asyncio.run(test_smart_sltp())
