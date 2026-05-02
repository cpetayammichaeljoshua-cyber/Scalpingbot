"""
UT Bot Alerts Indicator
Converted from TradingView Pine Script to Python

This indicator uses ATR-based trailing stop to generate buy/sell signals.
Settings:
- Key Value (sensitivity): 1 (default, can be adjusted)
- ATR Period: 10 (default)
- Heikin Ashi option for smoother signals
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10) -> pd.Series:
    """Calculate Average True Range (ATR)"""
    high_low = high - low
    high_close = np.abs(high - close.shift(1))
    low_close = np.abs(low - close.shift(1))
    
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()
    
    return atr


def calculate_heikin_ashi(open_price: pd.Series, high: pd.Series, 
                          low: pd.Series, close: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Calculate Heikin Ashi candles"""
    ha_close = (open_price + high + low + close) / 4
    
    ha_open = pd.Series(index=open_price.index, dtype=float)
    ha_open.iloc[0] = (open_price.iloc[0] + close.iloc[0]) / 2
    
    for i in range(1, len(open_price)):
        ha_open.iloc[i] = (ha_open.iloc[i-1] + ha_close.iloc[i-1]) / 2
    
    ha_high = pd.concat([high, ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([low, ha_open, ha_close], axis=1).min(axis=1)
    
    return ha_open, ha_high, ha_low, ha_close


def calculate_ema(data: pd.Series, period: int) -> pd.Series:
    """Calculate Exponential Moving Average"""
    return data.ewm(span=period, adjust=False).mean()


class UTBotAlerts:
    """
    UT Bot Alerts Indicator
    
    Generates buy/sell signals based on ATR trailing stop crossovers.
    """
    
    def __init__(self, key_value: float = 2.0, atr_period: int = 6, 
                 use_heikin_ashi: bool =True, ema_period: int = 1):
        """
        Initialize UT Bot Alerts
        
        Args:
            key_value: Sensitivity multiplier for ATR (default 2)
            atr_period: Period for ATR calculation (default 6)
            use_heikin_ashi: Use Heikin Ashi candles for signals (default True)
            ema_period: EMA period for trend detection (default 1)
        """
        self.key_value = key_value
        self.atr_period = atr_period
        self.use_heikin_ashi = use_heikin_ashi
        self.ema_period = ema_period
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate UT Bot Alerts signals
        
        Args:
            df: DataFrame with 'open', 'high', 'low', 'close' columns
            
        Returns:
            DataFrame with additional columns:
            - atr: Average True Range
            - trailing_stop: ATR trailing stop level
            - buy_signal: Boolean buy signals
            - sell_signal: Boolean sell signals
            - position: Current position direction (1=long, -1=short, 0=none)
            - bar_color: 'green' for buy zone, 'red' for sell zone
        """
        result = df.copy()
        
        if self.use_heikin_ashi:
            ha_open, ha_high, ha_low, ha_close = calculate_heikin_ashi(
                df['open'], df['high'], df['low'], df['close']
            )
            src = ha_close
            high = ha_high
            low = ha_low
        else:
            src = df['close']
            high = df['high']
            low = df['low']
        
        xatr = calculate_atr(high, low, src, self.atr_period)
        n_loss = self.key_value * xatr
        
        trailing_stop = pd.Series(index=df.index, dtype=float)
        trailing_stop.iloc[0] = 0.0
        
        for i in range(1, len(df)):
            prev_stop = trailing_stop.iloc[i-1] if not np.isnan(trailing_stop.iloc[i-1]) else 0.0
            curr_src = src.iloc[i]
            prev_src = src.iloc[i-1]
            curr_loss = n_loss.iloc[i] if not np.isnan(n_loss.iloc[i]) else 0.0
            
            if curr_src > prev_stop and prev_src > prev_stop:
                trailing_stop.iloc[i] = max(prev_stop, curr_src - curr_loss)
            elif curr_src < prev_stop and prev_src < prev_stop:
                trailing_stop.iloc[i] = min(prev_stop, curr_src + curr_loss)
            elif curr_src > prev_stop:
                trailing_stop.iloc[i] = curr_src - curr_loss
            else:
                trailing_stop.iloc[i] = curr_src + curr_loss
        
        position = pd.Series(index=df.index, dtype=int)
        position.iloc[0] = 0
        
        for i in range(1, len(df)):
            curr_src = src.iloc[i]
            prev_src = src.iloc[i-1]
            curr_stop = trailing_stop.iloc[i]
            prev_stop = trailing_stop.iloc[i-1] if not np.isnan(trailing_stop.iloc[i-1]) else 0.0
            prev_pos = position.iloc[i-1]
            
            if curr_src > curr_stop and prev_src <= prev_stop:
                position.iloc[i] = 1
            elif curr_src < curr_stop and prev_src >= prev_stop:
                position.iloc[i] = -1
            else:
                if prev_pos == 0:
                    if curr_src > curr_stop:
                        position.iloc[i] = 1
                    else:
                        position.iloc[i] = -1
                else:
                    position.iloc[i] = prev_pos
        
        ema = calculate_ema(src, self.ema_period)
        above = (src > trailing_stop) & (src.shift(1) <= trailing_stop.shift(1))
        below = (src < trailing_stop) & (src.shift(1) >= trailing_stop.shift(1))
        
        buy_signal = (src > trailing_stop) & above
        sell_signal = (src < trailing_stop) & below
        
        bar_buy = src > trailing_stop
        bar_sell = src < trailing_stop
        
        result['atr'] = xatr
        result['trailing_stop'] = trailing_stop
        result['n_loss'] = n_loss
        result['src'] = src
        result['ema'] = ema
        result['buy_signal'] = buy_signal
        result['sell_signal'] = sell_signal
        result['position'] = position
        result['bar_color'] = np.where(bar_buy, 'green', 'red')
        result['above_stop'] = src > trailing_stop
        result['below_stop'] = src < trailing_stop
        
        return result
    
    def get_latest_signal(self, df: pd.DataFrame) -> dict:
        """
        Get the latest signal information
        
        Args:
            df: Calculated DataFrame with signals
            
        Returns:
            Dictionary with latest signal information
        """
        if len(df) < 2:
            return {
                'signal': None,
                'price': None,
                'trailing_stop': None,
                'position': 0
            }
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        signal = None
        if latest['buy_signal']:
            signal = 'BUY'
        elif latest['sell_signal']:
            signal = 'SELL'
        
        return {
            'signal': signal,
            'price': latest['close'],
            'trailing_stop': latest['trailing_stop'],
            'position': latest['position'],
            'bar_color': latest['bar_color'],
            'above_stop': latest['above_stop'],
            'below_stop': latest['below_stop'],
            'atr': latest['atr']
        }
