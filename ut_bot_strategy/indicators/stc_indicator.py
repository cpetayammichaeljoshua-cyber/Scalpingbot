"""
STC (Schaff Trend Cycle) Colored Indicator
Converted from TradingView Pine Script to Python

This indicator combines MACD and Stochastic concepts for trend detection.
Modified settings as per strategy requirements:
- Length: 80 (changed from 12)
- FastLength: 27 (changed from 26)
- SlowLength: 50 (unchanged)
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict


def calculate_ema(data: pd.Series, period: int) -> pd.Series:
    """Calculate Exponential Moving Average"""
    return data.ewm(span=period, adjust=False).mean()


class STCIndicator:
    """
    Schaff Trend Cycle (STC) Indicator
    
    A momentum oscillator that combines MACD with stochastic concepts.
    Oscillates between 0-100, with 25 and 75 as key threshold levels.
    
    Color Logic:
    - Green: When STC > previous STC (rising) and STC < 75
    - Red: When STC < previous STC (falling) and STC > 25
    """
    
    def __init__(self, length: int = 80, fast_length: int = 27, 
                 slow_length: int = 50, aaa_factor: float = 0.5):
        """
        Initialize STC Indicator
        
        Args:
            length: Stochastic length (default 80, modified from original 12)
            fast_length: Fast EMA period (default 27, modified from original 26)
            slow_length: Slow EMA period (default 50)
            aaa_factor: Smoothing factor (default 0.5)
        """
        self.length = length
        self.fast_length = fast_length
        self.slow_length = slow_length
        self.aaa_factor = aaa_factor
    
    def _calculate_macd_diff(self, close: pd.Series) -> pd.Series:
        """Calculate MACD difference (fast EMA - slow EMA)"""
        fast_ma = calculate_ema(close, self.fast_length)
        slow_ma = calculate_ema(close, self.slow_length)
        return fast_ma - slow_ma
    
    def _stochastic_calculation(self, data: pd.Series, length: int) -> Tuple[pd.Series, pd.Series]:
        """
        Calculate stochastic values
        
        Returns:
            Tuple of (lowest, highest) over the period
        """
        lowest = data.rolling(window=length).min()
        highest = data.rolling(window=length).max()
        return lowest, highest
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate STC indicator values
        
        Args:
            df: DataFrame with 'close' column
            
        Returns:
            DataFrame with additional columns:
            - macd_diff: MACD difference
            - stc: STC oscillator value (0-100)
            - stc_color: 'green' or 'red' based on trend
            - stc_slope: 'up' or 'down' based on direction
            - stc_prev: Previous STC value
        """
        result = df.copy()
        close = df['close']
        
        macd_diff = self._calculate_macd_diff(close)
        
        ccc = pd.Series(index=df.index, dtype=float)
        ddd = pd.Series(index=df.index, dtype=float)
        ddddd = pd.Series(index=df.index, dtype=float)
        eeeee = pd.Series(index=df.index, dtype=float)
        stc = pd.Series(index=df.index, dtype=float)
        
        ccc.iloc[:] = 0.0
        ddd.iloc[:] = 0.0
        ddddd.iloc[:] = 0.0
        eeeee.iloc[:] = 0.0
        stc.iloc[:] = 0.0
        
        for i in range(self.length, len(df)):
            window = macd_diff.iloc[max(0, i-self.length+1):i+1]
            lowest_macd = window.min()
            highest_macd = window.max()
            
            diff_range = highest_macd - lowest_macd
            if diff_range > 0:
                ccccc = ((macd_diff.iloc[i] - lowest_macd) / diff_range) * 100
            else:
                ccccc = ccc.iloc[i-1] if i > 0 else 0
            
            if i > 0 and not np.isnan(ddd.iloc[i-1]):
                ddd.iloc[i] = ddd.iloc[i-1] + self.aaa_factor * (ccccc - ddd.iloc[i-1])
            else:
                ddd.iloc[i] = ccccc
            
            if i >= self.length:
                ddd_window = ddd.iloc[max(0, i-self.length+1):i+1]
                lowest_ddd = ddd_window.min()
                highest_ddd = ddd_window.max()
                
                ddd_range = highest_ddd - lowest_ddd
                if ddd_range > 0:
                    ddddd.iloc[i] = ((ddd.iloc[i] - lowest_ddd) / ddd_range) * 100
                else:
                    ddddd.iloc[i] = ddddd.iloc[i-1] if i > 0 and not np.isnan(ddddd.iloc[i-1]) else 0
                
                if i > 0 and not np.isnan(eeeee.iloc[i-1]):
                    eeeee.iloc[i] = eeeee.iloc[i-1] + self.aaa_factor * (ddddd.iloc[i] - eeeee.iloc[i-1])
                else:
                    eeeee.iloc[i] = ddddd.iloc[i]
                
                stc.iloc[i] = eeeee.iloc[i]
        
        stc_prev = stc.shift(1)
        
        stc_color = pd.Series(index=df.index, dtype=str)
        stc_slope = pd.Series(index=df.index, dtype=str)
        
        for i in range(len(df)):
            curr_stc = stc.iloc[i]
            prev_stc = stc_prev.iloc[i] if i > 0 else 0
            
            if not np.isnan(curr_stc) and not np.isnan(prev_stc):
                if curr_stc > prev_stc:
                    stc_slope.iloc[i] = 'up'
                else:
                    stc_slope.iloc[i] = 'down'
                
                is_rising = curr_stc > prev_stc
                
                if i >= 3:
                    stc_3 = stc.iloc[i]
                    stc_2 = stc.iloc[i-1] if i >= 1 else stc_3
                    stc_1 = stc.iloc[i-2] if i >= 2 else stc_2
                    
                    if stc_3 <= stc_2 and stc_2 > stc_1 and stc_3 > 75:
                        stc_color.iloc[i] = 'red'
                    elif stc_3 >= stc_2 and stc_2 < stc_1 and stc_3 < 25:
                        stc_color.iloc[i] = 'green'
                    elif is_rising and curr_stc < 75:
                        stc_color.iloc[i] = 'green'
                    elif not is_rising and curr_stc > 25:
                        stc_color.iloc[i] = 'red'
                    else:
                        stc_color.iloc[i] = 'green' if curr_stc < 50 else 'red'
                else:
                    if is_rising:
                        stc_color.iloc[i] = 'green'
                    else:
                        stc_color.iloc[i] = 'red'
            else:
                stc_color.iloc[i] = 'neutral'
                stc_slope.iloc[i] = 'neutral'
        
        result['macd_diff'] = macd_diff
        result['stc'] = stc
        result['stc_prev'] = stc_prev
        result['stc_color'] = stc_color
        result['stc_slope'] = stc_slope
        result['stc_above_75'] = stc > 75
        result['stc_below_25'] = stc < 25
        result['stc_between'] = (stc >= 25) & (stc <= 75)
        
        return result
    
    def get_latest_state(self, df: pd.DataFrame) -> Dict:
        """
        Get the latest STC state
        
        Args:
            df: Calculated DataFrame with STC values
            
        Returns:
            Dictionary with latest STC information
        """
        if len(df) < 2:
            return {
                'stc': None,
                'color': 'neutral',
                'slope': 'neutral',
                'above_75': False,
                'below_25': False,
                'valid_long': False,
                'valid_short': False
            }
        
        latest = df.iloc[-1]
        
        valid_long = (
            latest['stc_color'] == 'green' and 
            latest['stc_slope'] == 'up' and 
            latest['stc'] < 75
        )
        
        valid_short = (
            latest['stc_color'] == 'red' and 
            latest['stc_slope'] == 'down' and 
            latest['stc'] > 25
        )
        
        return {
            'stc': latest['stc'],
            'stc_prev': latest['stc_prev'],
            'color': latest['stc_color'],
            'slope': latest['stc_slope'],
            'above_75': latest['stc_above_75'],
            'below_25': latest['stc_below_25'],
            'valid_long': valid_long,
            'valid_short': valid_short
        }
