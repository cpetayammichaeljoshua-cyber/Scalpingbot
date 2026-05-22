#!/usr/bin/env python3
"""
Lightning Scalping Strategy - Ultra-High Frequency Trading System
The fastest scalping strategy optimized for sub-minute timeframes
- Timeframes: 30s, 1m, 2m for maximum speed
- Simple but effective indicators for low latency
- 20 trades/hour maximum, 10-second minimum between trades
- Dynamic leverage 10-30x based on signal clarity
- Target 30-120 second trade durations
- Focus on momentum bursts and micro-movements
"""

import asyncio
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from collections import deque
import time

try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False

@dataclass
class LightningScalpingSignal:
    """Lightning fast scalping signal with ultra-short execution parameters"""
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    signal_strength: float
    leverage: int = 20
    margin_type: str = "cross"
    risk_reward_ratio: float = 1.5
    timeframe: str = "Multi-TF"
    
    # Lightning-specific attributes
    momentum_burst_strength: float = 0.0
    price_acceleration: float = 0.0
    micro_trend_alignment: bool = False
    volume_surge_ratio: float = 1.0
    order_flow_bias: str = "neutral"
    expected_hold_seconds: int = 60
    
    # Speed-optimized attributes
    signal_latency_ms: float = 0.0
    execution_urgency: str = "normal"
    micro_support_resistance: float = 0.0
    tick_momentum_score: float = 0.0
    
    timestamp: Optional[datetime] = None

class LightningScalpingStrategy:
    """Ultra-high frequency lightning scalping strategy"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Lightning-fast scalping parameters
        self.timeframes = ['30s', '1m', '2m']  # Sub-minute timeframes
        self.max_leverage = 30  # Conservative max for ultra-fast trades
        self.min_leverage = 10  # Minimum leverage
        self.margin_type = "cross"
        self.risk_percentage = 0.5  # Ultra-tight risk for speed
        
        # Ultra-high frequency trading limits
        self.max_trades_per_hour = 20  # Maximum high-frequency limit
        self.min_trade_interval = 10   # 10 second minimum between trades
        self.last_trade_times = {}
        self.hourly_trade_counts = {}
        
        # Lightning-fast indicator parameters (simplified for speed)
        self.ema_periods = [3, 7, 14]  # Ultra-fast EMAs
        self.momentum_period = 5       # Very short momentum calculation
        self.volume_period = 10        # Short volume analysis
        
        # Signal strength weighting optimized for speed
        self.signal_weights = {
            'momentum_burst': 0.30,        # Primary speed signal
            'micro_trend_alignment': 0.25, # Short-term trend confirmation
            'price_acceleration': 0.20,    # Rate of price change
            'volume_surge': 0.15,          # Volume confirmation
            'order_flow': 0.10             # Market microstructure
        }
        
        # Minimum signal strength for ultra-fast entry
        self.min_signal_strength = 68  # Lower for more opportunities but still quality
        
        # Lightning-fast risk management
        self.micro_stop_loss_pct = [0.3, 0.5, 0.8]  # Ultra-micro stops
        self.lightning_target_ratios = [1.2, 1.5, 2.0]  # Quick profit ratios
        
        # Speed-optimized parameters
        self.momentum_threshold = 0.1    # Minimum momentum for signal
        self.acceleration_threshold = 0.05  # Minimum acceleration
        self.volume_surge_threshold = 1.3   # 130% of average volume
        
    async def analyze_symbol(self, symbol: str, ohlcv_data: Dict[str, List]) -> Optional[LightningScalpingSignal]:
        """Analyze symbol for lightning scalping opportunities"""
        try:
            start_time = time.time()
            
            # Check ultra-high frequency trading limits
            if not self._can_trade_symbol(symbol):
                return None
            
            # Prepare lightning-fast timeframe data
            tf_data = {}
            for tf in self.timeframes:
                if tf in ohlcv_data and len(ohlcv_data[tf]) >= 30:
                    tf_data[tf] = self._prepare_dataframe(ohlcv_data[tf])
            
            if len(tf_data) < 2:  # Need at least 2 timeframes
                return None
            
            # Primary analysis on 1m timeframe for speed/accuracy balance
            primary_tf = '1m' if '1m' in tf_data else '30s' if '30s' in tf_data else '2m'
            primary_df = tf_data[primary_tf]
            
            # Lightning-fast momentum burst detection
            momentum_analysis = await self._detect_momentum_burst(primary_df)
            
            if not momentum_analysis or momentum_analysis['burst_strength'] < 0.5:
                return None
            
            # Micro-trend alignment analysis
            trend_analysis = await self._analyze_micro_trends(primary_df, tf_data)
            
            # Price acceleration calculation
            acceleration_analysis = await self._calculate_price_acceleration(primary_df)
            
            # Volume surge detection
            volume_analysis = await self._detect_volume_surge(primary_df)
            
            # Order flow bias estimation
            flow_analysis = await self._estimate_order_flow_bias(primary_df)
            
            # Generate lightning scalping signal
            signal = await self._generate_lightning_signal(
                symbol, primary_df, momentum_analysis, trend_analysis,
                acceleration_analysis, volume_analysis, flow_analysis
            )
            
            if signal and signal.signal_strength >= self.min_signal_strength:
                # Record ultra-fast trade timing
                current_time = datetime.now()
                self.last_trade_times[symbol] = current_time
                
                # Update high-frequency counter
                if symbol not in self.hourly_trade_counts:
                    self.hourly_trade_counts[symbol] = deque()
                self.hourly_trade_counts[symbol].append(current_time)
                
                # Calculate signal latency
                signal.signal_latency_ms = (time.time() - start_time) * 1000
                
                # Log lightning signal details
                self.logger.info(f"⚡ Lightning Scalping Signal: {symbol} | "
                               f"Momentum: {momentum_analysis['burst_strength']:.1f}% | "
                               f"Accel: {acceleration_analysis['acceleration_score']:.1f}% | "
                               f"Vol Surge: {volume_analysis['surge_ratio']:.1f}x | "
                               f"Strength: {signal.signal_strength:.1f}% | "
                               f"Latency: {signal.signal_latency_ms:.1f}ms")
                
                return signal
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error analyzing {symbol} for lightning scalping: {e}")
            return None
    
    def _can_trade_symbol(self, symbol: str) -> bool:
        """Check ultra-high frequency trading limits (20/hour, 10s cooldown)"""
        current_time = datetime.now()
        
        # Check 10-second ultra-fast cooldown
        if symbol in self.last_trade_times:
            time_diff = (current_time - self.last_trade_times[symbol]).total_seconds()
            if time_diff < self.min_trade_interval:
                remaining = int(self.min_trade_interval - time_diff)
                self.logger.debug(f"⚡ {symbol}: 10s cooldown active, {remaining}s remaining")
                return False
        
        # Initialize ultra-high frequency tracking
        if symbol not in self.hourly_trade_counts:
            self.hourly_trade_counts[symbol] = deque()
        
        # Clean old timestamps (older than 1 hour)
        cutoff_time = current_time - timedelta(hours=1)
        trade_times = self.hourly_trade_counts[symbol]
        while trade_times and trade_times[0] < cutoff_time:
            trade_times.popleft()
        
        # Check ultra-high frequency limit
        if len(trade_times) >= self.max_trades_per_hour:
            oldest_trade = trade_times[0]
            wait_time = int((oldest_trade + timedelta(hours=1) - current_time).total_seconds())
            self.logger.debug(f"⚡ {symbol}: Max 20 lightning trades/hour reached, next in {wait_time}s")
            return False
        
        return True
    
    def _prepare_dataframe(self, ohlcv: List[List]) -> pd.DataFrame:
        """Prepare OHLCV dataframe for ultra-fast analysis"""
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df.dropna()
    
    async def _detect_momentum_burst(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect momentum bursts for lightning-fast entries"""
        try:
            close = df['close'].values
            
            if len(close) < self.momentum_period:
                return None
            
            # Calculate ultra-short momentum
            recent_momentum = (close[-1] - close[-self.momentum_period]) / close[-self.momentum_period]
            
            # Rate of change acceleration
            if len(close) >= self.momentum_period * 2:
                prev_momentum = (close[-self.momentum_period] - close[-self.momentum_period*2]) / close[-self.momentum_period*2]
                momentum_acceleration = recent_momentum - prev_momentum
            else:
                momentum_acceleration = 0
            
            # Momentum strength scoring
            momentum_strength = abs(recent_momentum) * 100
            acceleration_bonus = abs(momentum_acceleration) * 500  # Amplify acceleration
            
            burst_strength = min(100, momentum_strength + acceleration_bonus)
            
            # Direction determination
            burst_direction = 'bullish' if recent_momentum > 0 else 'bearish'
            
            # Strength threshold check
            if burst_strength < 30:  # Minimum burst threshold
                return None
            
            return {
                'burst_strength': burst_strength,
                'burst_direction': burst_direction,
                'momentum_value': recent_momentum,
                'acceleration': momentum_acceleration,
                'momentum_score': momentum_strength
            }
            
        except Exception as e:
            self.logger.error(f"Error detecting momentum burst: {e}")
            return None
    
    async def _analyze_micro_trends(self, df: pd.DataFrame, tf_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Analyze ultra-short micro trends across timeframes"""
        try:
            trend_alignments = {}
            
            for tf, tf_df in tf_data.items():
                close = tf_df['close'].values
                
                if len(close) < max(self.ema_periods):
                    continue
                
                # Calculate ultra-fast EMAs
                ema_3 = close[-3:].mean() if len(close) >= 3 else close[-1]
                ema_7 = close[-7:].mean() if len(close) >= 7 else close[-1]
                ema_14 = close[-14:].mean() if len(close) >= 14 else close[-1]
                
                current_price = close[-1]
                
                # Micro-trend alignment
                bullish_alignment = current_price > ema_3 > ema_7 > ema_14
                bearish_alignment = current_price < ema_3 < ema_7 < ema_14
                
                if bullish_alignment:
                    trend_alignments[tf] = 'bullish'
                elif bearish_alignment:
                    trend_alignments[tf] = 'bearish'
                else:
                    trend_alignments[tf] = 'neutral'
            
            # Calculate overall alignment strength
            alignment_count = len([t for t in trend_alignments.values() if t != 'neutral'])
            total_tfs = len(trend_alignments)
            
            if total_tfs == 0:
                return {'alignment_strength': 0, 'dominant_trend': 'neutral'}
            
            # Find dominant trend
            bullish_count = len([t for t in trend_alignments.values() if t == 'bullish'])
            bearish_count = len([t for t in trend_alignments.values() if t == 'bearish'])
            
            if bullish_count > bearish_count:
                dominant_trend = 'bullish'
                alignment_strength = (bullish_count / total_tfs) * 100
            elif bearish_count > bullish_count:
                dominant_trend = 'bearish'
                alignment_strength = (bearish_count / total_tfs) * 100
            else:
                dominant_trend = 'neutral'
                alignment_strength = 50
            
            return {
                'alignment_strength': alignment_strength,
                'dominant_trend': dominant_trend,
                'timeframe_trends': trend_alignments,
                'aligned_timeframes': alignment_count
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing micro trends: {e}")
            return {'alignment_strength': 0, 'dominant_trend': 'neutral'}
    
    async def _calculate_price_acceleration(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate price acceleration for momentum confirmation"""
        try:
            close = df['close'].values
            
            if len(close) < 6:  # Need at least 6 points for acceleration
                return {'acceleration_score': 0, 'direction': 'neutral'}
            
            # Calculate velocity (price change rate)
            velocities = []
            for i in range(3, len(close)):
                velocity = (close[i] - close[i-3]) / close[i-3]
                velocities.append(velocity)
            
            if len(velocities) < 3:
                return {'acceleration_score': 0, 'direction': 'neutral'}
            
            # Calculate acceleration (change in velocity)
            recent_velocity = velocities[-1]
            prev_velocity = velocities[-2] if len(velocities) > 1 else 0
            acceleration = recent_velocity - prev_velocity
            
            # Score the acceleration magnitude
            acceleration_score = min(100, abs(acceleration) * 1000)  # Scale up for visibility
            
            # Direction
            direction = 'bullish' if acceleration > 0 else 'bearish' if acceleration < 0 else 'neutral'
            
            return {
                'acceleration_score': acceleration_score,
                'acceleration_value': acceleration,
                'recent_velocity': recent_velocity,
                'direction': direction
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating price acceleration: {e}")
            return {'acceleration_score': 0, 'direction': 'neutral'}
    
    async def _detect_volume_surge(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect volume surges for confirmation"""
        try:
            volume = df['volume'].values
            
            if len(volume) < self.volume_period:
                return {'surge_ratio': 1.0, 'surge_detected': False}
            
            current_volume = volume[-1]
            avg_volume = np.mean(volume[-self.volume_period:])
            
            surge_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            surge_detected = surge_ratio >= self.volume_surge_threshold
            
            # Volume trend
            if len(volume) >= 5:
                recent_volume_trend = np.mean(volume[-3:]) / np.mean(volume[-5:-2])
            else:
                recent_volume_trend = 1.0
            
            # Volume strength score
            volume_strength = min(100, ((surge_ratio - 1) * 100) + ((recent_volume_trend - 1) * 50))
            
            return {
                'surge_ratio': surge_ratio,
                'surge_detected': surge_detected,
                'volume_strength': max(0, volume_strength),
                'current_volume': current_volume,
                'average_volume': avg_volume,
                'trend_ratio': recent_volume_trend
            }
            
        except Exception as e:
            self.logger.error(f"Error detecting volume surge: {e}")
            return {'surge_ratio': 1.0, 'surge_detected': False}
    
    async def _estimate_order_flow_bias(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Estimate order flow bias from price action"""
        try:
            high = df['high'].values
            low = df['low'].values  
            close = df['close'].values
            volume = df['volume'].values
            
            if len(close) < 5:
                return {'bias': 'neutral', 'strength': 50}
            
            # Simplified order flow estimation
            recent_bars = min(5, len(close))
            
            # Calculate buying/selling pressure approximation
            buying_pressure = 0
            selling_pressure = 0
            
            for i in range(-recent_bars, 0):
                bar_range = high[i] - low[i]
                if bar_range > 0:
                    # Estimate where price closed in the range
                    close_position = (close[i] - low[i]) / bar_range
                    bar_volume = volume[i]
                    
                    # Weight by volume
                    if close_position > 0.6:  # Closed in upper part
                        buying_pressure += bar_volume * close_position
                    elif close_position < 0.4:  # Closed in lower part
                        selling_pressure += bar_volume * (1 - close_position)
                    else:
                        # Neutral
                        buying_pressure += bar_volume * 0.5
                        selling_pressure += bar_volume * 0.5
            
            total_pressure = buying_pressure + selling_pressure
            
            if total_pressure > 0:
                buy_ratio = buying_pressure / total_pressure
                
                if buy_ratio > 0.6:
                    bias = 'bullish'
                    strength = min(100, buy_ratio * 100)
                elif buy_ratio < 0.4:
                    bias = 'bearish'
                    strength = min(100, (1 - buy_ratio) * 100)
                else:
                    bias = 'neutral'
                    strength = 50
            else:
                bias = 'neutral'
                strength = 50
            
            return {
                'bias': bias,
                'strength': strength,
                'buy_pressure_ratio': buy_ratio if total_pressure > 0 else 0.5
            }
            
        except Exception as e:
            self.logger.error(f"Error estimating order flow bias: {e}")
            return {'bias': 'neutral', 'strength': 50}
    
    async def _generate_lightning_signal(self, symbol: str, df: pd.DataFrame,
                                       momentum_analysis: Dict[str, Any],
                                       trend_analysis: Dict[str, Any], 
                                       acceleration_analysis: Dict[str, Any],
                                       volume_analysis: Dict[str, Any],
                                       flow_analysis: Dict[str, Any]) -> Optional[LightningScalpingSignal]:
        """Generate lightning scalping signal"""
        try:
            current_price = df['close'].iloc[-1]
            
            # Determine trade direction from momentum and trend alignment
            momentum_direction = momentum_analysis['burst_direction']
            trend_direction = trend_analysis['dominant_trend']
            acceleration_direction = acceleration_analysis['direction']
            flow_direction = flow_analysis['bias']
            
            # Majority vote for direction
            directions = [momentum_direction, trend_direction, acceleration_direction, flow_direction]
            bullish_votes = directions.count('bullish')
            bearish_votes = directions.count('bearish')
            
            if bullish_votes > bearish_votes:
                direction = 'BUY'
            elif bearish_votes > bullish_votes:
                direction = 'SELL'
            else:
                return None  # No clear direction
            
            # Calculate signal strength
            signal_strength = self._calculate_lightning_signal_strength(
                momentum_analysis, trend_analysis, acceleration_analysis, 
                volume_analysis, flow_analysis
            )
            
            if signal_strength < self.min_signal_strength:
                return None
            
            # Dynamic leverage based on signal clarity
            base_leverage = self.min_leverage
            strength_bonus = ((signal_strength - 70) / 30) * (self.max_leverage - self.min_leverage)
            leverage = int(min(self.max_leverage, base_leverage + strength_bonus))
            
            # Calculate ultra-tight entry, stop loss, and take profits
            if direction == 'BUY':
                # Ultra-micro stop loss below entry
                stop_loss_pct = self._get_micro_stop_loss(signal_strength)
                stop_loss = current_price * (1 - stop_loss_pct / 100)
                
                # Lightning-fast take profits
                risk_amount = current_price - stop_loss
                tp1 = current_price + (risk_amount * self.lightning_target_ratios[0])
                tp2 = current_price + (risk_amount * self.lightning_target_ratios[1])
                tp3 = current_price + (risk_amount * self.lightning_target_ratios[2])
                
            else:  # SELL
                # Ultra-micro stop loss above entry
                stop_loss_pct = self._get_micro_stop_loss(signal_strength)
                stop_loss = current_price * (1 + stop_loss_pct / 100)
                
                # Lightning-fast take profits
                risk_amount = stop_loss - current_price
                tp1 = current_price - (risk_amount * self.lightning_target_ratios[0])
                tp2 = current_price - (risk_amount * self.lightning_target_ratios[1])
                tp3 = current_price - (risk_amount * self.lightning_target_ratios[2])
            
            # Calculate risk/reward ratio
            risk_amount = abs(current_price - stop_loss)
            reward_amount = abs(tp2 - current_price)  # Use TP2
            risk_reward_ratio = reward_amount / risk_amount if risk_amount > 0 else 0
            
            # Expected hold time (30-120 seconds based on momentum)
            momentum_factor = momentum_analysis['burst_strength'] / 100
            expected_hold = int(30 + (90 * (1 - momentum_factor)))  # Stronger momentum = shorter hold
            
            # Execution urgency based on momentum burst strength
            if momentum_analysis['burst_strength'] > 80:
                execution_urgency = 'critical'
            elif momentum_analysis['burst_strength'] > 60:
                execution_urgency = 'high'
            else:
                execution_urgency = 'normal'
            
            return LightningScalpingSignal(
                symbol=symbol,
                direction=direction,
                entry_price=current_price,
                stop_loss=stop_loss,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                signal_strength=signal_strength,
                leverage=leverage,
                risk_reward_ratio=risk_reward_ratio,
                momentum_burst_strength=momentum_analysis['burst_strength'],
                price_acceleration=acceleration_analysis['acceleration_score'],
                micro_trend_alignment=trend_analysis['alignment_strength'] > 60,
                volume_surge_ratio=volume_analysis['surge_ratio'],
                order_flow_bias=flow_analysis['bias'],
                expected_hold_seconds=expected_hold,
                execution_urgency=execution_urgency,
                micro_support_resistance=current_price,  # Simplified
                tick_momentum_score=momentum_analysis['momentum_score'],
                timestamp=datetime.now()
            )
            
        except Exception as e:
            self.logger.error(f"Error generating lightning signal: {e}")
            return None
    
    def _calculate_lightning_signal_strength(self, momentum_analysis: Dict[str, Any],
                                           trend_analysis: Dict[str, Any],
                                           acceleration_analysis: Dict[str, Any],
                                           volume_analysis: Dict[str, Any],
                                           flow_analysis: Dict[str, Any]) -> float:
        """Calculate lightning signal strength using weighted components"""
        try:
            components = {
                'momentum_burst': momentum_analysis['burst_strength'],
                'micro_trend_alignment': trend_analysis['alignment_strength'],
                'price_acceleration': acceleration_analysis['acceleration_score'],
                'volume_surge': min(100, volume_analysis['volume_strength']),
                'order_flow': flow_analysis['strength']
            }
            
            # Calculate weighted score
            weighted_score = 0
            for component, value in components.items():
                weight = self.signal_weights.get(component, 0)
                weighted_score += value * weight
            
            return min(100, max(0, weighted_score))
            
        except Exception as e:
            self.logger.error(f"Error calculating signal strength: {e}")
            return 0
    
    def _get_micro_stop_loss(self, signal_strength: float) -> float:
        """Get ultra-micro stop loss percentage based on signal strength"""
        # Stronger signals can use slightly wider stops
        if signal_strength > 85:
            return self.micro_stop_loss_pct[2]  # 0.8%
        elif signal_strength > 75:
            return self.micro_stop_loss_pct[1]  # 0.5%
        else:
            return self.micro_stop_loss_pct[0]  # 0.3%
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get strategy configuration info"""
        return {
            'strategy_name': 'Lightning Scalping',
            'timeframes': self.timeframes,
            'max_trades_per_hour': self.max_trades_per_hour,
            'min_trade_interval_seconds': self.min_trade_interval,
            'leverage_range': f"{self.min_leverage}-{self.max_leverage}x",
            'min_signal_strength': self.min_signal_strength,
            'target_duration': '30-120 seconds',
            'risk_reward_ratios': self.lightning_target_ratios,
            'stop_loss_range': f"{self.micro_stop_loss_pct[0]}-{self.micro_stop_loss_pct[2]}%"
        }