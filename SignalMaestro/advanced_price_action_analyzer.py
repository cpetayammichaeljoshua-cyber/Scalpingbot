
#!/usr/bin/env python3
"""
Advanced Price Action Analyzer
Implements sophisticated price action analysis with liquidity mapping, timing optimization,
Schelling points identification, order flow analysis, and strategic positioning
"""

import asyncio
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json

class LiquidityZone(Enum):
    """Liquidity zone types"""
    BUYING_CLIMAX = "buying_climax"
    SELLING_CLIMAX = "selling_climax"
    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"
    STOP_HUNT = "stop_hunt"
    INSTITUTIONAL_LEVEL = "institutional_level"

class OrderFlowDirection(Enum):
    """Order flow directions"""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    ABSORPTION = "absorption"

class SchelloingPoint(Enum):
    """Schelling point types"""
    PSYCHOLOGICAL = "psychological"  # Round numbers
    TECHNICAL = "technical"          # S/R levels
    INSTITUTIONAL = "institutional"  # Major levels
    SEASONAL = "seasonal"            # Time-based

@dataclass
class PriceActionSignal:
    """Advanced price action signal"""
    symbol: str
    timestamp: datetime
    signal_type: str
    direction: str
    strength: float
    entry_price: float
    stop_loss: float
    take_profit: List[float]
    liquidity_analysis: Dict[str, Any]
    timing_score: float
    schelling_points: List[Dict[str, Any]]
    order_flow_analysis: Dict[str, Any]
    strategic_positioning: Dict[str, Any]
    confidence: float
    risk_reward_ratio: float

class AdvancedPriceActionAnalyzer:
    """Advanced price action analyzer with sophisticated market structure analysis"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Analysis parameters
        self.lookback_periods = {
            'short': 20,
            'medium': 50,
            'long': 200
        }
        
        # Liquidity detection parameters
        self.volume_threshold = 1.5  # Volume spike threshold
        self.wick_threshold = 0.3    # Wick percentage threshold
        self.accumulation_periods = 10
        
        # Order flow parameters
        self.order_flow_periods = 14
        self.delta_threshold = 0.6
        
        # Schelling point tolerances
        self.psychological_tolerance = 0.001  # 0.1% for round numbers
        self.technical_tolerance = 0.002     # 0.2% for S/R levels
    
    async def analyze_market_structure(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """Comprehensive market structure analysis"""
        try:
            if len(df) < 100:
                return {'error': 'Insufficient data for analysis'}
            
            # Core price action analysis
            swing_analysis = await self._analyze_swing_structure(df)
            trend_structure = await self._analyze_trend_structure(df)
            support_resistance = await self._identify_key_levels(df)
            
            # Advanced liquidity analysis
            liquidity_zones = await self._analyze_liquidity_zones(df)
            engineered_liquidity = await self._detect_engineered_liquidity(df)
            
            # Advanced timing analysis
            timing_analysis = await self._analyze_sequential_moves(df)
            session_timing = await self._analyze_session_timing(df)
            
            # Schelling points identification
            schelling_points = await self._identify_schelling_points(df, symbol)
            
            # Order flow analysis
            order_flow = await self._analyze_order_flow(df)
            
            # Strategic positioning
            strategic_position = await self._calculate_strategic_positioning(
                df, swing_analysis, liquidity_zones, timing_analysis
            )
            
            return {
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'swing_analysis': swing_analysis,
                'trend_structure': trend_structure,
                'support_resistance': support_resistance,
                'liquidity_zones': liquidity_zones,
                'engineered_liquidity': engineered_liquidity,
                'timing_analysis': timing_analysis,
                'session_timing': session_timing,
                'schelling_points': schelling_points,
                'order_flow': order_flow,
                'strategic_positioning': strategic_position,
                'overall_bias': await self._determine_overall_bias(df, swing_analysis, order_flow),
                'confidence_score': await self._calculate_confidence_score(
                    swing_analysis, liquidity_zones, timing_analysis, order_flow
                )
            }
            
        except Exception as e:
            self.logger.error(f"Error in market structure analysis: {e}")
            return {'error': str(e)}
    
    async def _analyze_swing_structure(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze swing highs and lows for market structure"""
        try:
            # Calculate swing points
            swing_highs = []
            swing_lows = []
            
            lookback = 5
            for i in range(lookback, len(df) - lookback):
                # Check for swing high
                if all(df['high'].iloc[i] > df['high'].iloc[i-j] for j in range(1, lookback+1)) and \
                   all(df['high'].iloc[i] > df['high'].iloc[i+j] for j in range(1, lookback+1)):
                    swing_highs.append({
                        'index': i,
                        'timestamp': df.index[i],
                        'price': df['high'].iloc[i],
                        'volume': df['volume'].iloc[i]
                    })
                
                # Check for swing low
                if all(df['low'].iloc[i] < df['low'].iloc[i-j] for j in range(1, lookback+1)) and \
                   all(df['low'].iloc[i] < df['low'].iloc[i+j] for j in range(1, lookback+1)):
                    swing_lows.append({
                        'index': i,
                        'timestamp': df.index[i],
                        'price': df['low'].iloc[i],
                        'volume': df['volume'].iloc[i]
                    })
            
            # Analyze swing structure
            structure_analysis = {
                'swing_highs': swing_highs[-10:],  # Last 10 swing highs
                'swing_lows': swing_lows[-10:],    # Last 10 swing lows
                'higher_highs': 0,
                'lower_highs': 0,
                'higher_lows': 0,
                'lower_lows': 0,
                'structure_bias': 'neutral'
            }
            
            # Count structure patterns
            if len(swing_highs) >= 2:
                for i in range(1, len(swing_highs)):
                    if swing_highs[i]['price'] > swing_highs[i-1]['price']:
                        structure_analysis['higher_highs'] += 1
                    else:
                        structure_analysis['lower_highs'] += 1
            
            if len(swing_lows) >= 2:
                for i in range(1, len(swing_lows)):
                    if swing_lows[i]['price'] > swing_lows[i-1]['price']:
                        structure_analysis['higher_lows'] += 1
                    else:
                        structure_analysis['lower_lows'] += 1
            
            # Determine structure bias
            bullish_count = structure_analysis['higher_highs'] + structure_analysis['higher_lows']
            bearish_count = structure_analysis['lower_highs'] + structure_analysis['lower_lows']
            
            if bullish_count > bearish_count * 1.5:
                structure_analysis['structure_bias'] = 'bullish'
            elif bearish_count > bullish_count * 1.5:
                structure_analysis['structure_bias'] = 'bearish'
            
            return structure_analysis
            
        except Exception as e:
            self.logger.error(f"Error analyzing swing structure: {e}")
            return {'error': str(e)}
    
    async def _analyze_trend_structure(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Advanced trend structure analysis"""
        try:
            # Multiple timeframe EMAs
            ema_8 = df['close'].ewm(span=8).mean()
            ema_21 = df['close'].ewm(span=21).mean()
            ema_50 = df['close'].ewm(span=50).mean()
            ema_200 = df['close'].ewm(span=200).mean()
            
            # Trend strength calculation
            current_price = df['close'].iloc[-1]
            
            trend_alignment = {
                'short_term': 'neutral',
                'medium_term': 'neutral',
                'long_term': 'neutral',
                'overall_trend': 'neutral',
                'trend_strength': 0.0
            }
            
            # Short term (8 vs 21)
            if ema_8.iloc[-1] > ema_21.iloc[-1]:
                trend_alignment['short_term'] = 'bullish'
            elif ema_8.iloc[-1] < ema_21.iloc[-1]:
                trend_alignment['short_term'] = 'bearish'
            
            # Medium term (21 vs 50)
            if ema_21.iloc[-1] > ema_50.iloc[-1]:
                trend_alignment['medium_term'] = 'bullish'
            elif ema_21.iloc[-1] < ema_50.iloc[-1]:
                trend_alignment['medium_term'] = 'bearish'
            
            # Long term (50 vs 200)
            if len(df) >= 200:
                if ema_50.iloc[-1] > ema_200.iloc[-1]:
                    trend_alignment['long_term'] = 'bullish'
                elif ema_50.iloc[-1] < ema_200.iloc[-1]:
                    trend_alignment['long_term'] = 'bearish'
            
            # Calculate trend strength
            bullish_count = sum(1 for trend in [trend_alignment['short_term'], 
                                              trend_alignment['medium_term'], 
                                              trend_alignment['long_term']] 
                               if trend == 'bullish')
            
            bearish_count = sum(1 for trend in [trend_alignment['short_term'], 
                                              trend_alignment['medium_term'], 
                                              trend_alignment['long_term']] 
                               if trend == 'bearish')
            
            if bullish_count > bearish_count:
                trend_alignment['overall_trend'] = 'bullish'
                trend_alignment['trend_strength'] = bullish_count / 3.0
            elif bearish_count > bullish_count:
                trend_alignment['overall_trend'] = 'bearish'
                trend_alignment['trend_strength'] = bearish_count / 3.0
            
            return trend_alignment
            
        except Exception as e:
            self.logger.error(f"Error analyzing trend structure: {e}")
            return {'error': str(e)}
    
    async def _identify_key_levels(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Identify key support and resistance levels"""
        try:
            # Pivot points calculation
            pivots = []
            
            for i in range(10, len(df) - 10):
                # High pivot
                if all(df['high'].iloc[i] >= df['high'].iloc[i-j] for j in range(1, 6)) and \
                   all(df['high'].iloc[i] >= df['high'].iloc[i+j] for j in range(1, 6)):
                    pivots.append({
                        'type': 'resistance',
                        'price': df['high'].iloc[i],
                        'timestamp': df.index[i],
                        'volume': df['volume'].iloc[i],
                        'touches': 1
                    })
                
                # Low pivot
                if all(df['low'].iloc[i] <= df['low'].iloc[i-j] for j in range(1, 6)) and \
                   all(df['low'].iloc[i] <= df['low'].iloc[i+j] for j in range(1, 6)):
                    pivots.append({
                        'type': 'support',
                        'price': df['low'].iloc[i],
                        'timestamp': df.index[i],
                        'volume': df['volume'].iloc[i],
                        'touches': 1
                    })
            
            # Consolidate nearby levels
            consolidated_levels = []
            tolerance = df['close'].iloc[-1] * 0.005  # 0.5% tolerance
            
            for pivot in pivots:
                found_similar = False
                for level in consolidated_levels:
                    if abs(pivot['price'] - level['price']) < tolerance:
                        level['touches'] += 1
                        level['volume'] = max(level['volume'], pivot['volume'])
                        found_similar = True
                        break
                
                if not found_similar:
                    consolidated_levels.append(pivot)
            
            # Sort by strength (touches and volume)
            consolidated_levels.sort(key=lambda x: x['touches'] * x['volume'], reverse=True)
            
            return {
                'support_levels': [l for l in consolidated_levels if l['type'] == 'support'][:5],
                'resistance_levels': [l for l in consolidated_levels if l['type'] == 'resistance'][:5],
                'key_levels_count': len(consolidated_levels)
            }
            
        except Exception as e:
            self.logger.error(f"Error identifying key levels: {e}")
            return {'error': str(e)}
    
    async def _analyze_liquidity_zones(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Advanced liquidity zone analysis"""
        try:
            liquidity_zones = []
            
            # Volume analysis
            volume_mean = df['volume'].rolling(20).mean()
            volume_std = df['volume'].rolling(20).std()
            volume_threshold = volume_mean + (volume_std * 2)
            
            for i in range(20, len(df)):
                current_volume = df['volume'].iloc[i]
                current_high = df['high'].iloc[i]
                current_low = df['low'].iloc[i]
                current_close = df['close'].iloc[i]
                current_open = df['open'].iloc[i]
                
                # High volume zones
                if current_volume > volume_threshold.iloc[i]:
                    # Buying climax detection
                    if current_close > current_open and (current_high - current_close) / (current_high - current_low) > 0.3:
                        liquidity_zones.append({
                            'type': LiquidityZone.BUYING_CLIMAX.value,
                            'price': current_high,
                            'timestamp': df.index[i],
                            'volume': current_volume,
                            'strength': current_volume / volume_mean.iloc[i]
                        })
                    
                    # Selling climax detection
                    elif current_close < current_open and (current_close - current_low) / (current_high - current_low) > 0.3:
                        liquidity_zones.append({
                            'type': LiquidityZone.SELLING_CLIMAX.value,
                            'price': current_low,
                            'timestamp': df.index[i],
                            'volume': current_volume,
                            'strength': current_volume / volume_mean.iloc[i]
                        })
                
                # Accumulation/Distribution zones
                if i >= 30:
                    recent_range = df['high'].iloc[i-10:i].max() - df['low'].iloc[i-10:i].min()
                    recent_volume_avg = df['volume'].iloc[i-10:i].mean()
                    
                    if recent_range < df['close'].iloc[i] * 0.02 and recent_volume_avg > volume_mean.iloc[i]:
                        if df['close'].iloc[i] > df['open'].iloc[i-10:i].mean():
                            liquidity_zones.append({
                                'type': LiquidityZone.ACCUMULATION.value,
                                'price': df['close'].iloc[i],
                                'timestamp': df.index[i],
                                'volume': recent_volume_avg,
                                'strength': recent_volume_avg / volume_mean.iloc[i]
                            })
                        else:
                            liquidity_zones.append({
                                'type': LiquidityZone.DISTRIBUTION.value,
                                'price': df['close'].iloc[i],
                                'timestamp': df.index[i],
                                'volume': recent_volume_avg,
                                'strength': recent_volume_avg / volume_mean.iloc[i]
                            })
            
            return {
                'liquidity_zones': liquidity_zones[-20:],  # Last 20 zones
                'zone_count_by_type': {
                    zone_type.value: len([z for z in liquidity_zones if z['type'] == zone_type.value])
                    for zone_type in LiquidityZone
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing liquidity zones: {e}")
            return {'error': str(e)}
    
    async def _detect_engineered_liquidity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect engineered liquidity patterns"""
        try:
            engineered_patterns = []
            
            for i in range(50, len(df) - 10):
                # Stop hunt pattern detection
                recent_lows = df['low'].iloc[i-20:i]
                recent_highs = df['high'].iloc[i-20:i]
                
                current_low = df['low'].iloc[i]
                current_high = df['high'].iloc[i]
                current_close = df['close'].iloc[i]
                
                # Liquidity grab below recent lows
                if current_low < recent_lows.min() * 0.999:  # Break below by 0.1%
                    if current_close > recent_lows.min():  # But close back above
                        engineered_patterns.append({
                            'type': 'liquidity_grab_low',
                            'timestamp': df.index[i],
                            'grab_price': current_low,
                            'return_price': current_close,
                            'strength': (current_close - current_low) / current_low * 100
                        })
                
                # Liquidity grab above recent highs
                if current_high > recent_highs.max() * 1.001:  # Break above by 0.1%
                    if current_close < recent_highs.max():  # But close back below
                        engineered_patterns.append({
                            'type': 'liquidity_grab_high',
                            'timestamp': df.index[i],
                            'grab_price': current_high,
                            'return_price': current_close,
                            'strength': (current_high - current_close) / current_close * 100
                        })
            
            return {
                'engineered_patterns': engineered_patterns[-10:],
                'liquidity_grabs_count': len(engineered_patterns),
                'recent_manipulation': len([p for p in engineered_patterns[-5:] 
                                          if p['strength'] > 0.5]) > 0
            }
            
        except Exception as e:
            self.logger.error(f"Error detecting engineered liquidity: {e}")
            return {'error': str(e)}
    
    async def _analyze_sequential_moves(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze sequential market moves and timing patterns"""
        try:
            sequential_analysis = {
                'wave_count': 0,
                'current_wave_direction': 'neutral',
                'wave_strength': 0.0,
                'fibonacci_levels': {},
                'timing_cycles': {},
                'momentum_divergence': False
            }
            
            # Wave analysis
            waves = []
            swing_points = []
            
            # Identify swing points
            for i in range(5, len(df) - 5):
                if all(df['high'].iloc[i] >= df['high'].iloc[i-j] for j in range(1, 6)) and \
                   all(df['high'].iloc[i] >= df['high'].iloc[i+j] for j in range(1, 6)):
                    swing_points.append({'type': 'high', 'index': i, 'price': df['high'].iloc[i]})
                
                if all(df['low'].iloc[i] <= df['low'].iloc[i-j] for j in range(1, 6)) and \
                   all(df['low'].iloc[i] <= df['low'].iloc[i+j] for j in range(1, 6)):
                    swing_points.append({'type': 'low', 'index': i, 'price': df['low'].iloc[i]})
            
            # Analyze waves between swing points
            if len(swing_points) >= 3:
                for i in range(len(swing_points) - 2):
                    start_point = swing_points[i]
                    end_point = swing_points[i + 1]
                    
                    wave = {
                        'start': start_point,
                        'end': end_point,
                        'direction': 'up' if end_point['price'] > start_point['price'] else 'down',
                        'magnitude': abs(end_point['price'] - start_point['price']) / start_point['price'],
                        'duration': end_point['index'] - start_point['index']
                    }
                    waves.append(wave)
                
                sequential_analysis['wave_count'] = len(waves)
                if waves:
                    sequential_analysis['current_wave_direction'] = waves[-1]['direction']
                    sequential_analysis['wave_strength'] = waves[-1]['magnitude']
            
            # Fibonacci retracement levels
            if len(swing_points) >= 2:
                last_swing = swing_points[-2]
                current_swing = swing_points[-1]
                
                if last_swing['type'] != current_swing['type']:
                    high_price = max(last_swing['price'], current_swing['price'])
                    low_price = min(last_swing['price'], current_swing['price'])
                    range_price = high_price - low_price
                    
                    fib_levels = {
                        '0.236': high_price - (range_price * 0.236),
                        '0.382': high_price - (range_price * 0.382),
                        '0.500': high_price - (range_price * 0.500),
                        '0.618': high_price - (range_price * 0.618),
                        '0.786': high_price - (range_price * 0.786)
                    }
                    sequential_analysis['fibonacci_levels'] = fib_levels
            
            return sequential_analysis
            
        except Exception as e:
            self.logger.error(f"Error analyzing sequential moves: {e}")
            return {'error': str(e)}
    
    async def _analyze_session_timing(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze market session timing patterns"""
        try:
            session_analysis = {
                'current_session': 'unknown',
                'session_bias': {},
                'optimal_trading_windows': [],
                'session_volatility': {}
            }
            
            # Determine current session
            current_hour = datetime.now().hour
            if 8 <= current_hour < 16:
                session_analysis['current_session'] = 'london'
            elif 13 <= current_hour < 21:
                session_analysis['current_session'] = 'new_york'
            elif 21 <= current_hour or current_hour < 8:
                session_analysis['current_session'] = 'asia'
            
            # Session-based analysis
            df['hour'] = pd.to_datetime(df.index).hour if hasattr(df.index, 'hour') else 12
            
            for session, hours in [('asia', list(range(22, 24)) + list(range(0, 8))),
                                 ('london', list(range(8, 16))),
                                 ('new_york', list(range(13, 21)))]:
                
                session_data = df[df['hour'].isin(hours)] if len(df[df['hour'].isin(hours)]) > 0 else df.tail(20)
                
                if len(session_data) > 5:
                    # Calculate session metrics
                    avg_range = (session_data['high'] - session_data['low']).mean()
                    avg_volume = session_data['volume'].mean()
                    price_change = (session_data['close'] - session_data['open']).mean()
                    
                    session_analysis['session_bias'][session] = {
                        'average_range': avg_range / session_data['close'].mean() * 100,
                        'average_volume': avg_volume,
                        'bias': 'bullish' if price_change > 0 else 'bearish',
                        'volatility': session_data['close'].std() / session_data['close'].mean() * 100
                    }
            
            return session_analysis
            
        except Exception as e:
            self.logger.error(f"Error analyzing session timing: {e}")
            return {'error': str(e)}
    
    async def _identify_schelling_points(self, df: pd.DataFrame, symbol: str) -> List[Dict[str, Any]]:
        """Identify Schelling points - focal points for coordination"""
        try:
            current_price = df['close'].iloc[-1]
            schelling_points = []
            
            # Psychological levels (round numbers)
            price_str = str(int(current_price))
            base_price = float(price_str)
            
            # Major psychological levels
            for multiplier in [0.5, 1.0, 1.5, 2.0]:
                psych_level = base_price * multiplier
                if abs(psych_level - current_price) / current_price < 0.1:  # Within 10%
                    schelling_points.append({
                        'type': SchelloingPoint.PSYCHOLOGICAL.value,
                        'price': psych_level,
                        'distance_percent': abs(psych_level - current_price) / current_price * 100,
                        'strength': 1.0 - abs(psych_level - current_price) / current_price
                    })
            
            # Technical Schelling points (previous highs/lows)
            recent_highs = df['high'].tail(100).nlargest(5)
            recent_lows = df['low'].tail(100).nsmallest(5)
            
            for high in recent_highs:
                if abs(high - current_price) / current_price < 0.05:  # Within 5%
                    schelling_points.append({
                        'type': SchelloingPoint.TECHNICAL.value,
                        'price': high,
                        'distance_percent': abs(high - current_price) / current_price * 100,
                        'strength': 0.8,
                        'level_type': 'resistance'
                    })
            
            for low in recent_lows:
                if abs(low - current_price) / current_price < 0.05:  # Within 5%
                    schelling_points.append({
                        'type': SchelloingPoint.TECHNICAL.value,
                        'price': low,
                        'distance_percent': abs(low - current_price) / current_price * 100,
                        'strength': 0.8,
                        'level_type': 'support'
                    })
            
            # Sort by strength
            schelling_points.sort(key=lambda x: x['strength'], reverse=True)
            
            return schelling_points[:10]  # Top 10 points
            
        except Exception as e:
            self.logger.error(f"Error identifying Schelling points: {e}")
            return []
    
    async def _analyze_order_flow(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Advanced order flow analysis"""
        try:
            order_flow_analysis = {
                'direction': OrderFlowDirection.NEUTRAL.value,
                'strength': 0.0,
                'imbalance': 0.0,
                'delta': 0.0,
                'cumulative_delta': 0.0,
                'absorption_levels': []
            }
            
            # Calculate approximated order flow metrics
            # Since we don't have tick data, we'll use OHLCV to estimate
            
            deltas = []
            for i in range(1, len(df)):
                # Estimate buying/selling pressure
                current = df.iloc[i]
                previous = df.iloc[i-1]
                
                # Price-volume analysis
                price_change = current['close'] - previous['close']
                volume_change = current['volume']
                
                # Estimate delta (buying vs selling pressure)
                if price_change > 0:
                    # Price up - more buying pressure
                    delta = volume_change * (current['close'] - current['low']) / (current['high'] - current['low'])
                elif price_change < 0:
                    # Price down - more selling pressure
                    delta = -volume_change * (current['high'] - current['close']) / (current['high'] - current['low'])
                else:
                    delta = 0
                
                deltas.append(delta)
            
            if deltas:
                recent_delta = np.mean(deltas[-14:])  # Last 14 periods
                cumulative_delta = np.sum(deltas)
                
                order_flow_analysis['delta'] = recent_delta
                order_flow_analysis['cumulative_delta'] = cumulative_delta
                
                # Determine order flow direction
                if recent_delta > 0:
                    order_flow_analysis['direction'] = OrderFlowDirection.BULLISH.value
                    order_flow_analysis['strength'] = min(abs(recent_delta) / df['volume'].tail(14).mean(), 1.0)
                elif recent_delta < 0:
                    order_flow_analysis['direction'] = OrderFlowDirection.BEARISH.value
                    order_flow_analysis['strength'] = min(abs(recent_delta) / df['volume'].tail(14).mean(), 1.0)
                
                # Calculate imbalance
                positive_deltas = [d for d in deltas[-20:] if d > 0]
                negative_deltas = [d for d in deltas[-20:] if d < 0]
                
                if positive_deltas and negative_deltas:
                    order_flow_analysis['imbalance'] = (sum(positive_deltas) + sum(negative_deltas)) / (sum(positive_deltas) - sum(negative_deltas))
            
            return order_flow_analysis
            
        except Exception as e:
            self.logger.error(f"Error analyzing order flow: {e}")
            return {'error': str(e)}
    
    async def _calculate_strategic_positioning(self, df: pd.DataFrame, swing_analysis: Dict,
                                             liquidity_zones: Dict, timing_analysis: Dict) -> Dict[str, Any]:
        """Calculate optimal strategic positioning"""
        try:
            positioning = {
                'optimal_entry_zone': None,
                'risk_level': 'medium',
                'position_sizing_multiplier': 1.0,
                'holding_period_estimate': 'medium',
                'strategic_advantage': 0.0
            }
            
            current_price = df['close'].iloc[-1]
            
            # Analyze current position relative to key levels
            advantages = 0
            total_factors = 0
            
            # Swing structure advantage
            if swing_analysis.get('structure_bias') == 'bullish':
                advantages += 1
            total_factors += 1
            
            # Liquidity zone proximity
            recent_zones = liquidity_zones.get('liquidity_zones', [])[-5:]
            for zone in recent_zones:
                distance = abs(zone['price'] - current_price) / current_price
                if distance < 0.02:  # Within 2%
                    if zone['type'] in ['accumulation', 'buying_climax']:
                        advantages += 1
                    total_factors += 1
            
            # Timing advantage
            if timing_analysis.get('current_wave_direction') == 'up':
                advantages += 1
            total_factors += 1
            
            # Calculate strategic advantage
            if total_factors > 0:
                positioning['strategic_advantage'] = advantages / total_factors
            
            # Determine position sizing multiplier
            if positioning['strategic_advantage'] > 0.7:
                positioning['position_sizing_multiplier'] = 1.5
                positioning['risk_level'] = 'low'
            elif positioning['strategic_advantage'] < 0.3:
                positioning['position_sizing_multiplier'] = 0.5
                positioning['risk_level'] = 'high'
            
            # Estimate holding period
            wave_duration = timing_analysis.get('wave_strength', 0.5)
            if wave_duration > 0.8:
                positioning['holding_period_estimate'] = 'long'
            elif wave_duration < 0.3:
                positioning['holding_period_estimate'] = 'short'
            
            return positioning
            
        except Exception as e:
            self.logger.error(f"Error calculating strategic positioning: {e}")
            return {'error': str(e)}
    
    async def _determine_overall_bias(self, df: pd.DataFrame, swing_analysis: Dict, order_flow: Dict) -> str:
        """Determine overall market bias"""
        try:
            bullish_factors = 0
            bearish_factors = 0
            
            # Swing structure bias
            if swing_analysis.get('structure_bias') == 'bullish':
                bullish_factors += 1
            elif swing_analysis.get('structure_bias') == 'bearish':
                bearish_factors += 1
            
            # Order flow bias
            if order_flow.get('direction') == 'bullish':
                bullish_factors += 1
            elif order_flow.get('direction') == 'bearish':
                bearish_factors += 1
            
            # Price action bias
            recent_closes = df['close'].tail(10)
            if recent_closes.iloc[-1] > recent_closes.mean():
                bullish_factors += 1
            else:
                bearish_factors += 1
            
            if bullish_factors > bearish_factors:
                return 'bullish'
            elif bearish_factors > bullish_factors:
                return 'bearish'
            else:
                return 'neutral'
                
        except Exception as e:
            self.logger.error(f"Error determining overall bias: {e}")
            return 'neutral'
    
    async def _calculate_confidence_score(self, swing_analysis: Dict, liquidity_zones: Dict,
                                        timing_analysis: Dict, order_flow: Dict) -> float:
        """Calculate overall confidence score for analysis"""
        try:
            confidence_factors = []
            
            # Swing analysis confidence
            if swing_analysis.get('structure_bias') != 'neutral':
                structure_strength = (swing_analysis.get('higher_highs', 0) + 
                                    swing_analysis.get('higher_lows', 0) + 
                                    swing_analysis.get('lower_highs', 0) + 
                                    swing_analysis.get('lower_lows', 0))
                if structure_strength > 3:
                    confidence_factors.append(0.8)
                else:
                    confidence_factors.append(0.5)
            else:
                confidence_factors.append(0.3)
            
            # Liquidity analysis confidence
            zone_count = len(liquidity_zones.get('liquidity_zones', []))
            if zone_count > 5:
                confidence_factors.append(0.7)
            elif zone_count > 2:
                confidence_factors.append(0.5)
            else:
                confidence_factors.append(0.3)
            
            # Timing analysis confidence
            wave_strength = timing_analysis.get('wave_strength', 0)
            if wave_strength > 0.05:
                confidence_factors.append(0.8)
            elif wave_strength > 0.02:
                confidence_factors.append(0.6)
            else:
                confidence_factors.append(0.4)
            
            # Order flow confidence
            flow_strength = order_flow.get('strength', 0)
            if flow_strength > 0.7:
                confidence_factors.append(0.9)
            elif flow_strength > 0.4:
                confidence_factors.append(0.6)
            else:
                confidence_factors.append(0.4)
            
            return np.mean(confidence_factors) if confidence_factors else 0.5
            
        except Exception as e:
            self.logger.error(f"Error calculating confidence score: {e}")
            return 0.5
    
    async def generate_trading_signal(self, df: pd.DataFrame, symbol: str) -> Optional[PriceActionSignal]:
        """Generate advanced trading signal based on comprehensive analysis"""
        try:
            # Perform comprehensive market analysis
            market_analysis = await self.analyze_market_structure(df, symbol)
            
            if 'error' in market_analysis:
                return None
            
            current_price = df['close'].iloc[-1]
            
            # Determine if we have a valid signal
            overall_bias = market_analysis['overall_bias']
            confidence = market_analysis['confidence_score']
            
            if confidence < 0.6 or overall_bias == 'neutral':
                return None
            
            # Calculate entry, stop loss, and take profit
            atr = self._calculate_atr(df)
            
            if overall_bias == 'bullish':
                direction = 'LONG'
                stop_loss = current_price - (atr * 2)
                take_profits = [
                    current_price + (atr * 1.5),  # TP1
                    current_price + (atr * 3),    # TP2
                    current_price + (atr * 4.5)   # TP3
                ]
            else:  # bearish
                direction = 'SHORT'
                stop_loss = current_price + (atr * 2)
                take_profits = [
                    current_price - (atr * 1.5),  # TP1
                    current_price - (atr * 3),    # TP2
                    current_price - (atr * 4.5)   # TP3
                ]
            
            # Calculate risk-reward ratio
            risk = abs(current_price - stop_loss)
            reward = abs(take_profits[1] - current_price)  # Use TP2 for R:R calculation
            risk_reward = reward / risk if risk > 0 else 0
            
            # Create signal
            signal = PriceActionSignal(
                symbol=symbol,
                timestamp=datetime.now(),
                signal_type='advanced_price_action',
                direction=direction,
                strength=confidence * 100,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profits,
                liquidity_analysis=market_analysis.get('liquidity_zones', {}),
                timing_score=market_analysis.get('timing_analysis', {}).get('wave_strength', 0),
                schelling_points=market_analysis.get('schelling_points', []),
                order_flow_analysis=market_analysis.get('order_flow', {}),
                strategic_positioning=market_analysis.get('strategic_positioning', {}),
                confidence=confidence,
                risk_reward_ratio=risk_reward
            )
            
            return signal
            
        except Exception as e:
            self.logger.error(f"Error generating trading signal: {e}")
            return None
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range"""
        try:
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            
            true_range = np.maximum(high_low, np.maximum(high_close, low_close))
            atr = true_range.rolling(window=period).mean().iloc[-1]
            
            return atr if not np.isnan(atr) else df['close'].iloc[-1] * 0.02
            
        except Exception as e:
            self.logger.error(f"Error calculating ATR: {e}")
            return df['close'].iloc[-1] * 0.02  # 2% fallback
