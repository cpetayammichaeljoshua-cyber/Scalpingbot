#!/usr/bin/env python3
"""
Volume Breakout Scalping Strategy - High-Frequency Volume-Based Trading
Specialized for rapid execution during volume surges and breakout confirmations
- Timeframes: 1m, 3m, 5m for ultra-fast scalping
- Volume spike detection (2x+ average)
- Support/resistance breakouts with volume confirmation
- 8 trades/hour maximum, 1-minute minimum between trades
- Dynamic leverage 20-50x based on volume strength
- Target 3-7 minute trade durations
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
class VolumeBreakoutSignal:
    """Volume breakout scalping signal with fast execution parameters"""
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    signal_strength: float
    leverage: int = 35
    margin_type: str = "cross"
    risk_reward_ratio: float = 2.5
    timeframe: str = "Multi-TF"
    
    # Volume-specific attributes
    volume_spike_ratio: float = 1.0
    breakout_strength: float = 0.0
    volume_confirmation: bool = False
    pattern_type: str = "breakout"
    consolidation_duration: int = 0
    expected_duration_minutes: int = 5
    
    # Breakout-specific attributes
    breakout_level: float = 0.0
    resistance_strength: float = 0.0
    momentum_score: float = 0.0
    
    timestamp: Optional[datetime] = None

class VolumeBreakoutScalpingStrategy:
    """High-frequency volume breakout scalping strategy"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Fast scalping parameters
        self.timeframes = ['1m', '3m', '5m']  # Ultra-fast timeframes only
        self.max_leverage = 50  # Maximum leverage for strong signals
        self.min_leverage = 20  # Minimum leverage for weak signals
        self.margin_type = "cross"
        self.risk_percentage = 1.2  # Aggressive risk for scalping
        
        # High-frequency trading limits
        self.max_trades_per_hour = 8  # High frequency during volume surges
        self.min_trade_interval = 60  # 1 minute minimum between trades
        self.last_trade_times = {}
        self.hourly_trade_counts = {}
        
        # Volume analysis parameters
        self.volume_spike_threshold = 1.5  # 150% of average volume minimum
        self.volume_periods = [10, 20, 50]  # Volume moving average periods
        self.min_signal_strength = 70  # Lower threshold for more opportunities
        
        # Breakout detection parameters
        self.breakout_threshold = 0.3  # Minimum breakout percentage
        self.resistance_lookback = 20  # Periods to look back for S/R levels
        self.consolidation_min_periods = 5  # Minimum consolidation duration
        
        # Signal weighting for volume breakout strategy
        self.signal_weights = {
            'volume_spike': 0.25,           # Primary volume confirmation
            'breakout_strength': 0.20,      # Breakout level penetration
            'momentum_confirmation': 0.15,  # Price momentum alignment
            'pattern_quality': 0.15,        # Consolidation pattern quality
            'support_resistance': 0.10,     # S/R level strength
            'volume_trend': 0.10,           # Volume trend direction
            'price_action': 0.05            # Candle pattern confirmation
        }
        
        # Risk management for fast scalping
        self.tight_stop_loss_pct = [0.8, 1.2, 1.5]  # Tight SL options
        self.quick_target_ratios = [1.5, 2.0, 2.5]  # Quick TP ratios
        
        # Pattern recognition parameters
        self.consolidation_range_pct = 2.0  # Max range for consolidation pattern
        self.breakout_volume_multiplier = 2.0  # Volume spike for valid breakout
        
    async def analyze_symbol(self, symbol: str, ohlcv_data: Dict[str, List]) -> Optional[VolumeBreakoutSignal]:
        """Analyze symbol for volume breakout opportunities"""
        try:
            # Check high-frequency trading limits
            if not self._can_trade_symbol(symbol):
                return None
            
            # Prepare fast timeframe data
            tf_data = {}
            for tf in self.timeframes:
                if tf in ohlcv_data and len(ohlcv_data[tf]) >= 50:
                    tf_data[tf] = self._prepare_dataframe(ohlcv_data[tf])
            
            if len(tf_data) < 2:  # Need at least 2 timeframes
                return None
            
            # Primary analysis on 3m timeframe
            primary_tf = '3m' if '3m' in tf_data else '1m' if '1m' in tf_data else '5m'
            primary_df = tf_data[primary_tf]
            
            # Calculate volume analysis
            volume_analysis = await self._calculate_volume_analysis(primary_df, tf_data)
            
            if not volume_analysis or volume_analysis['volume_spike_ratio'] < self.volume_spike_threshold:
                return None
            
            # Detect breakout patterns
            breakout_analysis = await self._detect_breakout_patterns(primary_df, volume_analysis)
            
            if not breakout_analysis or breakout_analysis['breakout_strength'] < 0.5:
                return None
            
            # Generate high-frequency signal
            signal = await self._generate_volume_breakout_signal(
                symbol, primary_df, volume_analysis, breakout_analysis, tf_data
            )
            
            if signal and signal.signal_strength >= self.min_signal_strength:
                # Record trade timing
                current_time = datetime.now()
                self.last_trade_times[symbol] = current_time
                
                # Update hourly counter
                if symbol not in self.hourly_trade_counts:
                    self.hourly_trade_counts[symbol] = deque()
                self.hourly_trade_counts[symbol].append(current_time)
                
                # Log signal details
                self.logger.info(f"🎯 Volume Breakout Signal: {symbol} | "
                               f"Vol Spike: {volume_analysis['volume_spike_ratio']:.1f}x | "
                               f"Breakout: {breakout_analysis['breakout_strength']:.1f}% | "
                               f"Strength: {signal.signal_strength:.1f}%")
                
                return signal
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error analyzing {symbol} for volume breakout: {e}")
            return None
    
    def _can_trade_symbol(self, symbol: str) -> bool:
        """Check high-frequency trading limits (8/hour, 1-min cooldown)"""
        current_time = datetime.now()
        
        # Check 1-minute cooldown
        if symbol in self.last_trade_times:
            time_diff = (current_time - self.last_trade_times[symbol]).total_seconds()
            if time_diff < self.min_trade_interval:
                remaining = int(self.min_trade_interval - time_diff)
                self.logger.debug(f"⏱️ {symbol}: 1-min cooldown active, {remaining}s remaining")
                return False
        
        # Initialize hourly tracking
        if symbol not in self.hourly_trade_counts:
            self.hourly_trade_counts[symbol] = deque()
        
        # Clean old timestamps (older than 1 hour)
        cutoff_time = current_time - timedelta(hours=1)
        trade_times = self.hourly_trade_counts[symbol]
        while trade_times and trade_times[0] < cutoff_time:
            trade_times.popleft()
        
        # Check hourly limit
        if len(trade_times) >= self.max_trades_per_hour:
            oldest_trade = trade_times[0]
            wait_time = int((oldest_trade + timedelta(hours=1) - current_time).total_seconds())
            self.logger.debug(f"📊 {symbol}: Max 8 trades/hour reached, next in {wait_time}s")
            return False
        
        return True
    
    def _prepare_dataframe(self, ohlcv: List[List]) -> pd.DataFrame:
        """Prepare OHLCV dataframe for analysis"""
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df.dropna()
    
    async def _calculate_volume_analysis(self, df: pd.DataFrame, tf_data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Calculate comprehensive volume analysis"""
        try:
            volume = df['volume'].values
            close = df['close'].values
            
            if len(volume) < max(self.volume_periods):
                return None
            
            # Calculate volume moving averages
            volume_ma = {}
            for period in self.volume_periods:
                if len(volume) >= period:
                    volume_ma[f'ma_{period}'] = np.mean(volume[-period:])
            
            current_volume = volume[-1]
            recent_avg_volume = volume_ma.get('ma_20', current_volume)
            
            # Volume spike ratio
            volume_spike_ratio = current_volume / recent_avg_volume if recent_avg_volume > 0 else 1.0
            
            # Volume trend analysis
            if len(volume) >= 10:
                recent_volume_trend = np.polyfit(range(10), volume[-10:], 1)[0]
                volume_trend_direction = 'increasing' if recent_volume_trend > 0 else 'decreasing'
            else:
                volume_trend_direction = 'neutral'
            
            # Volume-Price Trend (VPT)
            if len(df) >= 2:
                price_change = (close[-1] - close[-2]) / close[-2]
                vpt_signal = price_change * current_volume
            else:
                vpt_signal = 0
            
            # On-Balance Volume (OBV) simplified
            obv_change = 0
            if len(df) >= 2:
                if close[-1] > close[-2]:
                    obv_change = current_volume
                elif close[-1] < close[-2]:
                    obv_change = -current_volume
            
            # Volume rate of change
            volume_roc = 0
            if len(volume) >= 5:
                prev_volume = np.mean(volume[-5:-1])
                volume_roc = (current_volume - prev_volume) / prev_volume * 100 if prev_volume > 0 else 0
            
            # Calculate volume strength score
            volume_strength = min(100, max(0, (
                (volume_spike_ratio - 1) * 50 +  # Spike contribution
                min(volume_roc, 100) * 0.3 +     # ROC contribution
                (50 if volume_trend_direction == 'increasing' else 20)  # Trend contribution
            )))
            
            return {
                'volume_spike_ratio': volume_spike_ratio,
                'current_volume': current_volume,
                'average_volume': recent_avg_volume,
                'volume_trend': volume_trend_direction,
                'volume_roc': volume_roc,
                'vpt_signal': vpt_signal,
                'obv_change': obv_change,
                'volume_strength': volume_strength,
                'volume_ma': volume_ma
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating volume analysis: {e}")
            return None
    
    async def _detect_breakout_patterns(self, df: pd.DataFrame, volume_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Detect breakout patterns with volume confirmation"""
        try:
            high = df['high'].values
            low = df['low'].values
            close = df['close'].values
            
            if len(close) < self.resistance_lookback:
                return None
            
            current_price = close[-1]
            
            # Find recent support and resistance levels
            lookback_data = df.tail(self.resistance_lookback)
            resistance_level = lookback_data['high'].max()
            support_level = lookback_data['low'].min()
            
            # Calculate consolidation range
            price_range = resistance_level - support_level
            range_percentage = (price_range / current_price) * 100
            
            # Detect consolidation pattern
            is_consolidating = range_percentage <= self.consolidation_range_pct
            
            # Check for breakout
            breakout_direction = None
            breakout_strength = 0
            
            if current_price > resistance_level:
                breakout_direction = 'bullish'
                breakout_strength = ((current_price - resistance_level) / resistance_level) * 100
            elif current_price < support_level:
                breakout_direction = 'bearish'
                breakout_strength = ((support_level - current_price) / support_level) * 100
            
            # Volume confirmation for breakout
            volume_confirmed = volume_analysis['volume_spike_ratio'] >= self.breakout_volume_multiplier
            
            # Calculate resistance/support strength
            resistance_touches = sum(1 for h in high[-self.resistance_lookback:] 
                                   if abs(h - resistance_level) / resistance_level < 0.002)
            support_touches = sum(1 for l in low[-self.resistance_lookback:] 
                                if abs(l - support_level) / support_level < 0.002)
            
            level_strength = min(100, (resistance_touches + support_touches) * 15)
            
            # Momentum confirmation
            momentum_score = 0
            if len(close) >= 5:
                price_momentum = (close[-1] - close[-5]) / close[-5] * 100
                momentum_score = min(100, abs(price_momentum) * 10)
            
            # Pattern quality assessment
            pattern_quality = 0
            if is_consolidating and breakout_direction and volume_confirmed:
                pattern_quality = min(100, (
                    50 +  # Base quality for valid pattern
                    level_strength * 0.3 +  # Level strength contribution
                    min(breakout_strength * 10, 30) +  # Breakout strength
                    min(volume_analysis['volume_strength'] * 0.2, 20)  # Volume contribution
                ))
            
            return {
                'breakout_direction': breakout_direction,
                'breakout_strength': breakout_strength,
                'resistance_level': resistance_level,
                'support_level': support_level,
                'is_consolidating': is_consolidating,
                'volume_confirmed': volume_confirmed,
                'level_strength': level_strength,
                'momentum_score': momentum_score,
                'pattern_quality': pattern_quality,
                'range_percentage': range_percentage
            }
            
        except Exception as e:
            self.logger.error(f"Error detecting breakout patterns: {e}")
            return None
    
    async def _generate_volume_breakout_signal(self, symbol: str, df: pd.DataFrame, 
                                             volume_analysis: Dict[str, Any], 
                                             breakout_analysis: Dict[str, Any],
                                             tf_data: Dict[str, pd.DataFrame]) -> Optional[VolumeBreakoutSignal]:
        """Generate volume breakout scalping signal"""
        try:
            current_price = df['close'].iloc[-1]
            breakout_direction = breakout_analysis['breakout_direction']
            
            if not breakout_direction:
                return None
            
            # Calculate signal strength
            signal_strength = self._calculate_signal_strength(volume_analysis, breakout_analysis)
            
            if signal_strength < self.min_signal_strength:
                return None
            
            # Dynamic leverage based on signal strength and volume
            base_leverage = self.min_leverage
            strength_bonus = ((signal_strength - 70) / 30) * (self.max_leverage - self.min_leverage)
            volume_bonus = min(10, (volume_analysis['volume_spike_ratio'] - 1) * 5)
            
            leverage = int(min(self.max_leverage, base_leverage + strength_bonus + volume_bonus))
            
            # Calculate entry, stop loss, and take profits
            if breakout_direction == 'bullish':
                direction = 'BUY'
                
                # Tight stop loss below recent support
                stop_loss_pct = self._get_dynamic_stop_loss(breakout_analysis['breakout_strength'])
                stop_loss = current_price * (1 - stop_loss_pct / 100)
                
                # Quick take profits
                risk_amount = current_price - stop_loss
                tp1 = current_price + (risk_amount * self.quick_target_ratios[0])
                tp2 = current_price + (risk_amount * self.quick_target_ratios[1])
                tp3 = current_price + (risk_amount * self.quick_target_ratios[2])
                
            else:  # bearish
                direction = 'SELL'
                
                # Tight stop loss above recent resistance
                stop_loss_pct = self._get_dynamic_stop_loss(breakout_analysis['breakout_strength'])
                stop_loss = current_price * (1 + stop_loss_pct / 100)
                
                # Quick take profits
                risk_amount = stop_loss - current_price
                tp1 = current_price - (risk_amount * self.quick_target_ratios[0])
                tp2 = current_price - (risk_amount * self.quick_target_ratios[1])
                tp3 = current_price - (risk_amount * self.quick_target_ratios[2])
            
            # Calculate risk/reward ratio
            risk_amount = abs(current_price - stop_loss)
            reward_amount = abs(tp2 - current_price)  # Use TP2 for R:R calculation
            risk_reward_ratio = reward_amount / risk_amount if risk_amount > 0 else 0
            
            # Expected trade duration (3-7 minutes based on volatility)
            volatility_factor = breakout_analysis['breakout_strength'] / 2
            expected_duration = int(3 + min(4, volatility_factor))
            
            return VolumeBreakoutSignal(
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
                volume_spike_ratio=volume_analysis['volume_spike_ratio'],
                breakout_strength=breakout_analysis['breakout_strength'],
                volume_confirmation=breakout_analysis['volume_confirmed'],
                pattern_type=f"{breakout_direction}_breakout",
                consolidation_duration=0,  # Could be enhanced to track actual duration
                expected_duration_minutes=expected_duration,
                breakout_level=breakout_analysis['resistance_level'] if breakout_direction == 'bullish' 
                              else breakout_analysis['support_level'],
                resistance_strength=breakout_analysis['level_strength'],
                momentum_score=breakout_analysis['momentum_score'],
                timestamp=datetime.now()
            )
            
        except Exception as e:
            self.logger.error(f"Error generating volume breakout signal: {e}")
            return None
    
    def _calculate_signal_strength(self, volume_analysis: Dict[str, Any], 
                                 breakout_analysis: Dict[str, Any]) -> float:
        """Calculate overall signal strength using weighted factors"""
        try:
            components = {
                'volume_spike': min(100, (volume_analysis['volume_spike_ratio'] - 1) * 50),
                'breakout_strength': min(100, breakout_analysis['breakout_strength'] * 20),
                'momentum_confirmation': breakout_analysis['momentum_score'],
                'pattern_quality': breakout_analysis['pattern_quality'],
                'support_resistance': breakout_analysis['level_strength'],
                'volume_trend': 80 if volume_analysis['volume_trend'] == 'increasing' else 40,
                'price_action': 70 if breakout_analysis['volume_confirmed'] else 30
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
    
    def _get_dynamic_stop_loss(self, breakout_strength: float) -> float:
        """Get dynamic stop loss percentage based on breakout strength"""
        # Stronger breakouts can tolerate slightly wider stops
        if breakout_strength > 2.0:
            return self.tight_stop_loss_pct[2]  # 1.5%
        elif breakout_strength > 1.0:
            return self.tight_stop_loss_pct[1]  # 1.2%
        else:
            return self.tight_stop_loss_pct[0]  # 0.8%
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get strategy configuration info"""
        return {
            'strategy_name': 'Volume Breakout Scalping',
            'timeframes': self.timeframes,
            'max_trades_per_hour': self.max_trades_per_hour,
            'min_trade_interval_seconds': self.min_trade_interval,
            'leverage_range': f"{self.min_leverage}-{self.max_leverage}x",
            'min_signal_strength': self.min_signal_strength,
            'volume_spike_threshold': f"{self.volume_spike_threshold}x",
            'target_duration': '3-7 minutes',
            'risk_reward_ratios': self.quick_target_ratios
        }