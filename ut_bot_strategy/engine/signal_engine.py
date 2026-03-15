"""
Signal Engine for UT Bot + STC Strategy

Combines UT Bot Alerts and STC indicators to generate trading signals.
Implements the complete strategy rules:
- LONG: UT Bot buy signal + STC green + STC pointing up + STC < 75
- SHORT: UT Bot sell signal + STC red + STC pointing down + STC > 25
- Stop loss at recent swing high/low
- Take profit at 1.5x risk
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple
import pandas as pd
import numpy as np

from ..indicators.ut_bot_alerts import UTBotAlerts
from ..indicators.stc_indicator import STCIndicator

logger = logging.getLogger(__name__)


class SignalEngine:
    """
    Combined Signal Engine for UT Bot + STC Strategy
    
    Generates confirmed trading signals by combining:
    1. UT Bot Alerts for entry signals
    2. STC indicator for confirmation
    3. Swing detection for stop loss
    4. Risk:Reward calculation for take profit
    """
    
    def __init__(self, 
                 ut_key_value: float = 1.0,
                 ut_atr_period: int = 10,
                 ut_use_heikin_ashi: bool = False,
                 stc_length: int = 80,
                 stc_fast_length: int = 27,
                 stc_slow_length: int = 50,
                 swing_lookback: int = 5,
                 risk_reward_ratio: float = 1.5,
                 min_risk_percent: float = 0.5,
                 max_risk_percent: float = 3.0):
        """
        Initialize Signal Engine
        
        Args:
            ut_key_value: UT Bot sensitivity (default 1.0)
            ut_atr_period: UT Bot ATR period (default 10)
            ut_use_heikin_ashi: Use Heikin Ashi for UT Bot (default False)
            stc_length: STC stochastic length (default 80)
            stc_fast_length: STC fast EMA period (default 27)
            stc_slow_length: STC slow EMA period (default 50)
            swing_lookback: Bars to look back for swing detection (default 5)
            risk_reward_ratio: Target R:R ratio (default 1.5)
            min_risk_percent: Minimum risk percentage (default 0.5%)
            max_risk_percent: Maximum risk percentage (default 3.0%)
        """
        self.ut_bot = UTBotAlerts(
            key_value=ut_key_value,
            atr_period=ut_atr_period,
            use_heikin_ashi=ut_use_heikin_ashi
        )
        
        self.stc = STCIndicator(
            length=stc_length,
            fast_length=stc_fast_length,
            slow_length=stc_slow_length
        )
        
        self.swing_lookback = swing_lookback
        self.risk_reward_ratio = risk_reward_ratio
        self.min_risk_percent = min_risk_percent
        self.max_risk_percent = max_risk_percent
        
        self._last_signal_time: Optional[datetime] = None
        self._last_signal_type: Optional[str] = None
        self._signal_history: List[Dict] = []
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all indicators on the data
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with all indicator values
        """
        df_ut = self.ut_bot.calculate(df)
        
        df_combined = self.stc.calculate(df_ut)
        
        return df_combined
    
    def find_swing_high(self, df: pd.DataFrame, lookback: Optional[int] = None) -> float:
        """
        Find recent swing high for stop loss (SHORT positions)
        
        Args:
            df: DataFrame with OHLCV data
            lookback: Number of bars to look back
            
        Returns:
            Swing high price
        """
        lookback = lookback or self.swing_lookback
        recent_data = df.tail(lookback + 1)
        return float(recent_data['high'].max())
    
    def find_swing_low(self, df: pd.DataFrame, lookback: Optional[int] = None) -> float:
        """
        Find recent swing low for stop loss (LONG positions)
        
        Args:
            df: DataFrame with OHLCV data
            lookback: Number of bars to look back
            
        Returns:
            Swing low price
        """
        lookback = lookback or self.swing_lookback
        recent_data = df.tail(lookback + 1)
        return float(recent_data['low'].min())
    
    def calculate_risk_reward(self, entry_price: float, stop_loss: float, 
                             direction: str) -> Tuple[float, float, float]:
        """
        Calculate take profit based on risk:reward ratio
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            direction: 'LONG' or 'SHORT'
            
        Returns:
            Tuple of (take_profit, risk_amount, reward_amount)
        """
        risk = abs(entry_price - stop_loss)
        reward = risk * self.risk_reward_ratio
        
        if direction == 'LONG':
            take_profit = entry_price + reward
        else:
            take_profit = entry_price - reward
        
        return take_profit, risk, reward
    
    def calculate_risk_percent(self, entry_price: float, stop_loss: float) -> float:
        """
        Calculate risk as percentage of entry
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            
        Returns:
            Risk percentage
        """
        return abs(entry_price - stop_loss) / entry_price * 100
    
    def check_long_conditions(self, df: pd.DataFrame) -> Dict:
        """
        Check if LONG entry conditions are met
        
        Conditions:
        1. UT Bot gives BUY signal
        2. STC is GREEN color
        3. STC is pointing UP
        4. STC value is below 75
        
        Args:
            df: DataFrame with calculated indicators
            
        Returns:
            Dictionary with signal details
        """
        if len(df) < 3:
            return {'valid': False, 'reason': 'Insufficient data'}
        
        latest = df.iloc[-1]
        
        ut_buy_signal = latest.get('buy_signal', False)
        ut_above_stop = latest.get('above_stop', False)
        
        stc_value = latest.get('stc', 50)
        stc_color = latest.get('stc_color', 'neutral')
        stc_slope = latest.get('stc_slope', 'neutral')
        
        conditions = {
            'ut_buy_signal': bool(ut_buy_signal),
            'ut_above_stop': bool(ut_above_stop),
            'stc_green': stc_color == 'green',
            'stc_up': stc_slope == 'up',
            'stc_below_75': float(stc_value) < 75 if not pd.isna(stc_value) else False
        }
        
        all_conditions_met = all([
            conditions['ut_buy_signal'] or conditions['ut_above_stop'],
            conditions['stc_green'],
            conditions['stc_up'],
            conditions['stc_below_75']
        ])
        
        primary_signal = conditions['ut_buy_signal']
        
        return {
            'valid': all_conditions_met and primary_signal,
            'conditions': conditions,
            'stc_value': stc_value,
            'reason': self._get_condition_reason(conditions, 'LONG')
        }
    
    def check_short_conditions(self, df: pd.DataFrame) -> Dict:
        """
        Check if SHORT entry conditions are met
        
        Conditions:
        1. UT Bot gives SELL signal
        2. STC is RED color
        3. STC is pointing DOWN
        4. STC value is above 25
        
        Args:
            df: DataFrame with calculated indicators
            
        Returns:
            Dictionary with signal details
        """
        if len(df) < 3:
            return {'valid': False, 'reason': 'Insufficient data'}
        
        latest = df.iloc[-1]
        
        ut_sell_signal = latest.get('sell_signal', False)
        ut_below_stop = latest.get('below_stop', False)
        
        stc_value = latest.get('stc', 50)
        stc_color = latest.get('stc_color', 'neutral')
        stc_slope = latest.get('stc_slope', 'neutral')
        
        conditions = {
            'ut_sell_signal': bool(ut_sell_signal),
            'ut_below_stop': bool(ut_below_stop),
            'stc_red': stc_color == 'red',
            'stc_down': stc_slope == 'down',
            'stc_above_25': float(stc_value) > 25 if not pd.isna(stc_value) else False
        }
        
        all_conditions_met = all([
            conditions['ut_sell_signal'] or conditions['ut_below_stop'],
            conditions['stc_red'],
            conditions['stc_down'],
            conditions['stc_above_25']
        ])
        
        primary_signal = conditions['ut_sell_signal']
        
        return {
            'valid': all_conditions_met and primary_signal,
            'conditions': conditions,
            'stc_value': stc_value,
            'reason': self._get_condition_reason(conditions, 'SHORT')
        }
    
    def _get_condition_reason(self, conditions: Dict, direction: str) -> str:
        """Generate human-readable reason for signal validity"""
        failed = []
        
        if direction == 'LONG':
            if not conditions.get('ut_buy_signal'):
                failed.append('No UT Bot BUY signal')
            if not conditions.get('stc_green'):
                failed.append('STC not green')
            if not conditions.get('stc_up'):
                failed.append('STC not pointing up')
            if not conditions.get('stc_below_75'):
                failed.append('STC above 75')
        else:
            if not conditions.get('ut_sell_signal'):
                failed.append('No UT Bot SELL signal')
            if not conditions.get('stc_red'):
                failed.append('STC not red')
            if not conditions.get('stc_down'):
                failed.append('STC not pointing down')
            if not conditions.get('stc_above_25'):
                failed.append('STC below 25')
        
        if not failed:
            return 'All conditions met'
        return ', '.join(failed)
    
    def generate_signal(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Generate trading signal based on strategy rules
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            Signal dictionary or None if no valid signal
        """
        if len(df) < 100:
            logger.warning("Insufficient data for signal generation")
            return None
        
        df_calculated = self.calculate_indicators(df)
        
        latest = df_calculated.iloc[-1]
        index_value = df_calculated.index[-1]
        # Handle various datetime types from pandas index
        if isinstance(index_value, datetime):
            current_time = index_value
        elif isinstance(index_value, pd.Timestamp):
            current_time = index_value.to_pydatetime()
        elif hasattr(index_value, 'timestamp') and callable(getattr(index_value, 'timestamp', None)):
            current_time = datetime.fromtimestamp(index_value.timestamp())
        else:
            current_time = datetime.now()
        entry_price = float(latest['close'])
        
        long_check = self.check_long_conditions(df_calculated)
        short_check = self.check_short_conditions(df_calculated)
        
        signal = None
        
        if long_check['valid']:
            stop_loss = self.find_swing_low(df_calculated)
            take_profit, risk, reward = self.calculate_risk_reward(entry_price, stop_loss, 'LONG')
            risk_percent = self.calculate_risk_percent(entry_price, stop_loss)
            
            if self.min_risk_percent <= risk_percent <= self.max_risk_percent:
                signal = {
                    'type': 'LONG',
                    'symbol': 'ETH/USDT',
                    'timeframe': '5m',
                    'entry_price': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'risk_amount': risk,
                    'reward_amount': reward,
                    'risk_percent': risk_percent,
                    'risk_reward_ratio': self.risk_reward_ratio,
                    'timestamp': current_time,
                    'conditions': long_check['conditions'],
                    'stc_value': long_check['stc_value'],
                    'ut_trailing_stop': float(latest.get('trailing_stop', 0)),
                    'atr': float(latest.get('atr', 0)),
                    'reason': long_check['reason'],
                    'recommended_leverage': 16,
                    'leverage_config': {
                        'base_leverage': 12,
                        'margin_type': 'CROSS',
                        'auto_add_margin': True
                    }
                }
            else:
                logger.info(f"LONG signal rejected: Risk {risk_percent:.2f}% outside acceptable range")
        
        elif short_check['valid']:
            stop_loss = self.find_swing_high(df_calculated)
            take_profit, risk, reward = self.calculate_risk_reward(entry_price, stop_loss, 'SHORT')
            risk_percent = self.calculate_risk_percent(entry_price, stop_loss)
            
            if self.min_risk_percent <= risk_percent <= self.max_risk_percent:
                signal = {
                    'type': 'SHORT',
                    'symbol': 'ETH/USDT',
                    'timeframe': '5m',
                    'entry_price': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'risk_amount': risk,
                    'reward_amount': reward,
                    'risk_percent': risk_percent,
                    'risk_reward_ratio': self.risk_reward_ratio,
                    'timestamp': current_time,
                    'conditions': short_check['conditions'],
                    'stc_value': short_check['stc_value'],
                    'ut_trailing_stop': float(latest.get('trailing_stop', 0)),
                    'atr': float(latest.get('atr', 0)),
                    'reason': short_check['reason'],
                    'recommended_leverage': 16,
                    'leverage_config': {
                        'base_leverage': 12,
                        'margin_type': 'CROSS',
                        'auto_add_margin': True
                    }
                }
            else:
                logger.info(f"SHORT signal rejected: Risk {risk_percent:.2f}% outside acceptable range")
        
        if signal:
            if (self._last_signal_time == current_time and 
                self._last_signal_type == signal['type']):
                logger.debug("Duplicate signal detected, skipping")
                return None
            
            self._last_signal_time = current_time
            self._last_signal_type = signal['type']
            self._signal_history.append(signal)
            
            if len(self._signal_history) > 100:
                self._signal_history = self._signal_history[-100:]
            
            logger.info(f"Generated {signal['type']} signal at {entry_price}")
        
        return signal
    
    def get_market_state(self, df: pd.DataFrame) -> Dict:
        """
        Get current market state without generating a signal
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            Dictionary with current market state
        """
        if len(df) < 100:
            return {'error': 'Insufficient data'}
        
        df_calculated = self.calculate_indicators(df)
        latest = df_calculated.iloc[-1]
        
        return {
            'timestamp': df_calculated.index[-1],
            'price': float(latest['close']),
            'ut_position': int(latest.get('position', 0)),
            'ut_bar_color': latest.get('bar_color', 'neutral'),
            'ut_trailing_stop': float(latest.get('trailing_stop', 0)),
            'stc_value': float(latest.get('stc', 0)),
            'stc_color': latest.get('stc_color', 'neutral'),
            'stc_slope': latest.get('stc_slope', 'neutral'),
            'atr': float(latest.get('atr', 0)),
            'long_conditions': self.check_long_conditions(df_calculated),
            'short_conditions': self.check_short_conditions(df_calculated)
        }
    
    def get_signal_history(self) -> List[Dict]:
        """Get recent signal history"""
        return self._signal_history.copy()
