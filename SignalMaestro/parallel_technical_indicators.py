#!/usr/bin/env python3
"""
Parallel Technical Indicators Calculator
High-performance concurrent calculation of technical indicators across multiple symbols and timeframes
Optimized for maximum throughput with intelligent caching and vectorized computations
"""

import asyncio
import logging
import time
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple, Callable, Union
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from collections import defaultdict, deque
import traceback
import multiprocessing as mp
from functools import partial
import json

from parallel_processing_core import get_parallel_core, ParallelTask

# Try to import talib for advanced indicators
try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    
# Try to import pandas_ta for additional indicators
try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False

@dataclass
class IndicatorRequest:
    """Technical indicator calculation request"""
    symbol: str
    timeframe: str
    indicator_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    data: Optional[pd.DataFrame] = None
    priority: int = 5
    timeout: float = 5.0
    cache_enabled: bool = True

@dataclass
class IndicatorResult:
    """Technical indicator calculation result"""
    symbol: str
    timeframe: str
    indicator_name: str
    result: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    calculation_time: float = 0.0
    timestamp: str = ""

class ParallelTechnicalIndicators:
    """High-performance parallel technical indicators calculator"""
    
    def __init__(self, max_cpu_workers: int = None, enable_vectorization: bool = True):
        self.logger = logging.getLogger(__name__)
        self.parallel_core = get_parallel_core()
        
        # CPU workers for indicator calculations
        cpu_count = mp.cpu_count()
        self.max_cpu_workers = max_cpu_workers or min(cpu_count, 8)
        self.cpu_executor = ThreadPoolExecutor(
            max_workers=self.max_cpu_workers,
            thread_name_prefix="IndicatorCPU"
        )
        
        # Vectorization support
        self.enable_vectorization = enable_vectorization and PANDAS_TA_AVAILABLE
        
        # Indicator registry
        self.indicator_registry = self._build_indicator_registry()
        
        # Performance optimization
        self.batch_size = 50  # Process indicators in batches
        self.cache = {}
        self.cache_ttl = 60  # 1 minute cache TTL for most indicators
        
        # Performance metrics
        self.calculation_times = defaultdict(deque)  # Track per-indicator performance
        self.batch_performance = deque(maxlen=100)
        
        self.logger.info(f"🧮 Parallel Technical Indicators initialized")
        self.logger.info(f"⚙️ CPU workers: {self.max_cpu_workers}, Vectorization: {self.enable_vectorization}")
        self.logger.info(f"📊 Available indicators: {len(self.indicator_registry)}")
    
    def _build_indicator_registry(self) -> Dict[str, Callable]:
        """Build registry of available technical indicators"""
        registry = {}
        
        # Basic indicators (always available)
        registry.update({
            'sma': self._calculate_sma,
            'ema': self._calculate_ema,
            'rsi': self._calculate_rsi,
            'macd': self._calculate_macd,
            'bollinger_bands': self._calculate_bollinger_bands,
            'stochastic': self._calculate_stochastic,
            'atr': self._calculate_atr,
            'adx': self._calculate_adx,
            'williams_r': self._calculate_williams_r,
            'cci': self._calculate_cci,
            'mfi': self._calculate_mfi,
            'obv': self._calculate_obv,
            'vwap': self._calculate_vwap,
            'supertrend': self._calculate_supertrend,
            'heikin_ashi': self._calculate_heikin_ashi,
            'volume_profile': self._calculate_volume_profile,
            'support_resistance': self._calculate_support_resistance
        })
        
        # TALib indicators (if available)
        if TALIB_AVAILABLE:
            registry.update({
                'talib_rsi': lambda df, **kwargs: talib.RSI(df['close'].values, 
                                                           timeperiod=kwargs.get('period', 14)),
                'talib_macd': lambda df, **kwargs: talib.MACD(df['close'].values),
                'talib_bbands': lambda df, **kwargs: talib.BBANDS(df['close'].values),
                'talib_atr': lambda df, **kwargs: talib.ATR(df['high'].values, 
                                                           df['low'].values, 
                                                           df['close'].values),
                'talib_adx': lambda df, **kwargs: talib.ADX(df['high'].values,
                                                           df['low'].values,
                                                           df['close'].values)
            })
        
        # Pandas TA indicators (if available)
        if PANDAS_TA_AVAILABLE:
            registry.update({
                'ta_rsi': lambda df, **kwargs: ta.rsi(df['close'], length=kwargs.get('period', 14)),
                'ta_macd': lambda df, **kwargs: ta.macd(df['close']),
                'ta_bbands': lambda df, **kwargs: ta.bbands(df['close']),
                'ta_supertrend': lambda df, **kwargs: ta.supertrend(df['high'], df['low'], df['close']),
                'ta_vwap': lambda df, **kwargs: ta.vwap(df['high'], df['low'], df['close'], df['volume'])
            })
        
        return registry
    
    async def calculate_indicators_parallel(self, requests: List[IndicatorRequest]) -> List[IndicatorResult]:
        """Calculate multiple indicators in parallel"""
        try:
            start_time = time.time()
            
            if not requests:
                return []
            
            # Group requests by data source for efficiency
            data_groups = self._group_requests_by_data(requests)
            
            all_results = []
            
            # Process each data group in parallel
            group_tasks = []
            for group_key, group_requests in data_groups.items():
                task = ParallelTask(
                    task_id=f"indicator_group_{group_key}",
                    function=self._calculate_indicator_group,
                    args=(group_requests,),
                    priority=8,
                    timeout=30.0
                )
                group_tasks.append(task)
            
            # Execute all groups in parallel
            group_results = await self.parallel_core.execute_parallel(group_tasks)
            
            # Flatten results
            for task_id, results in group_results:
                if not isinstance(results, Exception) and results:
                    all_results.extend(results)
            
            processing_time = time.time() - start_time
            self.batch_performance.append(processing_time)
            
            success_count = len(all_results)
            total_count = len(requests)
            
            self.logger.info(
                f"🧮 Parallel indicators completed: {success_count}/{total_count} "
                f"in {processing_time:.2f}s ({success_count/processing_time:.1f} indicators/s)"
            )
            
            return all_results
            
        except Exception as e:
            self.logger.error(f"❌ Parallel indicator calculation failed: {e}")
            self.logger.debug(traceback.format_exc())
            return []
    
    async def calculate_symbol_all_indicators(self, symbol: str, timeframe: str, 
                                            data: pd.DataFrame, 
                                            indicators: List[str] = None) -> Dict[str, Any]:
        """Calculate all indicators for a symbol in parallel"""
        try:
            # Default indicator set if none specified
            if indicators is None:
                indicators = [
                    'sma_20', 'sma_50', 'ema_12', 'ema_26', 'rsi', 'macd',
                    'bollinger_bands', 'atr', 'supertrend', 'vwap', 'stochastic'
                ]
            
            # Create requests for all indicators
            requests = []
            for indicator in indicators:
                # Parse indicator name and parameters
                if '_' in indicator:
                    parts = indicator.split('_')
                    indicator_name = parts[0]
                    parameters = {}
                    if len(parts) > 1 and parts[1].isdigit():
                        parameters['period'] = int(parts[1])
                else:
                    indicator_name = indicator
                    parameters = {}
                
                request = IndicatorRequest(
                    symbol=symbol,
                    timeframe=timeframe,
                    indicator_name=indicator_name,
                    parameters=parameters,
                    data=data.copy(),
                    priority=7
                )
                requests.append(request)
            
            # Calculate all indicators in parallel
            results = await self.calculate_indicators_parallel(requests)
            
            # Convert to dictionary
            indicator_dict = {}
            for result in results:
                key = result.indicator_name
                if result.metadata.get('period'):
                    key += f"_{result.metadata['period']}"
                indicator_dict[key] = result.result
            
            return indicator_dict
            
        except Exception as e:
            self.logger.error(f"❌ Failed to calculate all indicators for {symbol}: {e}")
            return {}
    
    def _group_requests_by_data(self, requests: List[IndicatorRequest]) -> Dict[str, List[IndicatorRequest]]:
        """Group requests by symbol-timeframe for efficient processing"""
        groups = defaultdict(list)
        
        for request in requests:
            key = f"{request.symbol}_{request.timeframe}"
            groups[key].append(request)
        
        return dict(groups)
    
    async def _calculate_indicator_group(self, requests: List[IndicatorRequest]) -> List[IndicatorResult]:
        """Calculate a group of indicators for the same data source"""
        try:
            if not requests:
                return []
            
            # Get the data (should be the same for all requests in group)
            first_request = requests[0]
            data = first_request.data
            
            if data is None or data.empty:
                self.logger.warning(f"No data for {first_request.symbol} {first_request.timeframe}")
                return []
            
            # Prepare data for calculations
            data = self._prepare_data(data)
            
            # Calculate all indicators for this data
            results = []
            
            # Process indicators in batches to avoid memory issues
            for i in range(0, len(requests), self.batch_size):
                batch = requests[i:i + self.batch_size]
                batch_results = await self._calculate_indicator_batch(batch, data)
                results.extend(batch_results)
            
            return results
            
        except Exception as e:
            self.logger.error(f"❌ Indicator group calculation failed: {e}")
            return []
    
    async def _calculate_indicator_batch(self, requests: List[IndicatorRequest], 
                                       data: pd.DataFrame) -> List[IndicatorResult]:
        """Calculate a batch of indicators"""
        try:
            results = []
            
            # Create tasks for parallel execution
            loop = asyncio.get_running_loop()
            
            calculation_tasks = []
            for request in requests:
                task = loop.run_in_executor(
                    self.cpu_executor,
                    self._calculate_single_indicator,
                    request, data.copy()
                )
                calculation_tasks.append((request, task))
            
            # Wait for all calculations to complete
            for request, task in calculation_tasks:
                try:
                    result = await task
                    if result:
                        results.append(result)
                except Exception as e:
                    self.logger.warning(f"Failed to calculate {request.indicator_name}: {e}")
            
            return results
            
        except Exception as e:
            self.logger.error(f"❌ Indicator batch calculation failed: {e}")
            return []
    
    def _calculate_single_indicator(self, request: IndicatorRequest, data: pd.DataFrame) -> Optional[IndicatorResult]:
        """Calculate a single technical indicator"""
        try:
            start_time = time.time()
            
            # Check cache first
            if request.cache_enabled:
                cache_key = self._generate_cache_key(request, data)
                if cache_key in self.cache:
                    cached_result, cache_time = self.cache[cache_key]
                    if time.time() - cache_time < self.cache_ttl:
                        return cached_result
            
            # Get indicator function
            indicator_func = self.indicator_registry.get(request.indicator_name)
            if not indicator_func:
                self.logger.warning(f"Unknown indicator: {request.indicator_name}")
                return None
            
            # Calculate indicator
            result_value = indicator_func(data, **request.parameters)
            
            calculation_time = time.time() - start_time
            
            # Create result object
            result = IndicatorResult(
                symbol=request.symbol,
                timeframe=request.timeframe,
                indicator_name=request.indicator_name,
                result=result_value,
                metadata={
                    'parameters': request.parameters,
                    'data_length': len(data),
                    'period': request.parameters.get('period', None)
                },
                calculation_time=calculation_time,
                timestamp=pd.Timestamp.now().isoformat()
            )
            
            # Update performance tracking
            self.calculation_times[request.indicator_name].append(calculation_time)
            if len(self.calculation_times[request.indicator_name]) > 100:
                self.calculation_times[request.indicator_name].popleft()
            
            # Cache result
            if request.cache_enabled:
                self.cache[cache_key] = (result, time.time())
            
            return result
            
        except Exception as e:
            self.logger.warning(f"Error calculating {request.indicator_name}: {e}")
            return None
    
    def _prepare_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Prepare data for indicator calculations"""
        try:
            # Ensure required columns exist
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in required_columns:
                if col not in data.columns:
                    self.logger.warning(f"Missing column: {col}")
                    return pd.DataFrame()
            
            # Ensure numeric types
            for col in required_columns:
                data[col] = pd.to_numeric(data[col], errors='coerce')
            
            # Remove any NaN values from the beginning
            data = data.dropna()
            
            # Sort by timestamp
            if not data.index.is_monotonic_increasing:
                data = data.sort_index()
            
            return data
            
        except Exception as e:
            self.logger.error(f"Error preparing data: {e}")
            return pd.DataFrame()
    
    def _generate_cache_key(self, request: IndicatorRequest, data: pd.DataFrame) -> str:
        """Generate cache key for indicator result"""
        try:
            # Create key based on request and data characteristics
            data_hash = hash(tuple(data.index.astype(str)) + tuple(data['close'].round(8)))
            params_str = json.dumps(request.parameters, sort_keys=True)
            
            return f"{request.symbol}_{request.timeframe}_{request.indicator_name}_{params_str}_{data_hash}"
            
        except Exception:
            # Fallback to simple key
            return f"{request.symbol}_{request.timeframe}_{request.indicator_name}_{time.time()}"
    
    # Technical Indicator Implementation Methods
    
    def _calculate_sma(self, data: pd.DataFrame, period: int = 20) -> pd.Series:
        """Simple Moving Average"""
        return data['close'].rolling(window=period).mean()
    
    def _calculate_ema(self, data: pd.DataFrame, period: int = 20) -> pd.Series:
        """Exponential Moving Average"""
        return data['close'].ewm(span=period).mean()
    
    def _calculate_rsi(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Relative Strength Index"""
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_macd(self, data: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
        """MACD Indicator"""
        ema_fast = data['close'].ewm(span=fast).mean()
        ema_slow = data['close'].ewm(span=slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    def _calculate_bollinger_bands(self, data: pd.DataFrame, period: int = 20, std_dev: float = 2) -> Dict[str, pd.Series]:
        """Bollinger Bands"""
        sma = data['close'].rolling(window=period).mean()
        std = data['close'].rolling(window=period).std()
        
        return {
            'upper': sma + (std * std_dev),
            'middle': sma,
            'lower': sma - (std * std_dev)
        }
    
    def _calculate_stochastic(self, data: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Dict[str, pd.Series]:
        """Stochastic Oscillator"""
        low_min = data['low'].rolling(window=k_period).min()
        high_max = data['high'].rolling(window=k_period).max()
        
        k_percent = 100 * ((data['close'] - low_min) / (high_max - low_min))
        d_percent = k_percent.rolling(window=d_period).mean()
        
        return {
            'k': k_percent,
            'd': d_percent
        }
    
    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Average True Range"""
        high_low = data['high'] - data['low']
        high_close = np.abs(data['high'] - data['close'].shift())
        low_close = np.abs(data['low'] - data['close'].shift())
        
        true_range = np.maximum(high_low, np.maximum(high_close, low_close))
        return true_range.rolling(window=period).mean()
    
    def _calculate_adx(self, data: pd.DataFrame, period: int = 14) -> Dict[str, pd.Series]:
        """Average Directional Index"""
        high_diff = data['high'].diff()
        low_diff = -data['low'].diff()
        
        plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
        minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)
        
        atr = self._calculate_atr(data, period)
        
        plus_di = 100 * (plus_dm.ewm(span=period).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(span=period).mean() / atr)
        
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.ewm(span=period).mean()
        
        return {
            'adx': adx,
            'plus_di': plus_di,
            'minus_di': minus_di
        }
    
    def _calculate_williams_r(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Williams %R"""
        high_max = data['high'].rolling(window=period).max()
        low_min = data['low'].rolling(window=period).min()
        
        return -100 * ((high_max - data['close']) / (high_max - low_min))
    
    def _calculate_cci(self, data: pd.DataFrame, period: int = 20) -> pd.Series:
        """Commodity Channel Index"""
        typical_price = (data['high'] + data['low'] + data['close']) / 3
        sma_tp = typical_price.rolling(window=period).mean()
        mad = typical_price.rolling(window=period).apply(lambda x: np.mean(np.abs(x - x.mean())))
        
        return (typical_price - sma_tp) / (0.015 * mad)
    
    def _calculate_mfi(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Money Flow Index"""
        typical_price = (data['high'] + data['low'] + data['close']) / 3
        money_flow = typical_price * data['volume']
        
        positive_flow = money_flow.where(typical_price > typical_price.shift(), 0).rolling(window=period).sum()
        negative_flow = money_flow.where(typical_price < typical_price.shift(), 0).rolling(window=period).sum()
        
        mfi = 100 - (100 / (1 + positive_flow / negative_flow))
        return mfi
    
    def _calculate_obv(self, data: pd.DataFrame) -> pd.Series:
        """On-Balance Volume"""
        obv = pd.Series(index=data.index, dtype=float)
        obv.iloc[0] = data['volume'].iloc[0]
        
        for i in range(1, len(data)):
            if data['close'].iloc[i] > data['close'].iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] + data['volume'].iloc[i]
            elif data['close'].iloc[i] < data['close'].iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] - data['volume'].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]
        
        return obv
    
    def _calculate_vwap(self, data: pd.DataFrame) -> pd.Series:
        """Volume Weighted Average Price"""
        typical_price = (data['high'] + data['low'] + data['close']) / 3
        vwap = (typical_price * data['volume']).cumsum() / data['volume'].cumsum()
        return vwap
    
    def _calculate_supertrend(self, data: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> Dict[str, pd.Series]:
        """SuperTrend Indicator"""
        hl2 = (data['high'] + data['low']) / 2
        atr = self._calculate_atr(data, period)
        
        upper_band = hl2 + (multiplier * atr)
        lower_band = hl2 - (multiplier * atr)
        
        # Initialize series
        supertrend = pd.Series(index=data.index, dtype=float)
        direction = pd.Series(index=data.index, dtype=int)
        
        # First value
        supertrend.iloc[0] = lower_band.iloc[0]
        direction.iloc[0] = 1
        
        for i in range(1, len(data)):
            if data['close'].iloc[i-1] > supertrend.iloc[i-1]:
                supertrend.iloc[i] = max(lower_band.iloc[i], supertrend.iloc[i-1])
                direction.iloc[i] = 1
            else:
                supertrend.iloc[i] = min(upper_band.iloc[i], supertrend.iloc[i-1])
                direction.iloc[i] = -1
        
        return {
            'supertrend': supertrend,
            'direction': direction,
            'upper_band': upper_band,
            'lower_band': lower_band
        }
    
    def _calculate_heikin_ashi(self, data: pd.DataFrame) -> Dict[str, pd.Series]:
        """Heikin Ashi Candles"""
        ha_close = (data['open'] + data['high'] + data['low'] + data['close']) / 4
        ha_open = pd.Series(index=data.index, dtype=float)
        ha_open.iloc[0] = (data['open'].iloc[0] + data['close'].iloc[0]) / 2
        
        for i in range(1, len(data)):
            ha_open.iloc[i] = (ha_open.iloc[i-1] + ha_close.iloc[i-1]) / 2
        
        ha_high = pd.concat([data['high'], ha_open, ha_close], axis=1).max(axis=1)
        ha_low = pd.concat([data['low'], ha_open, ha_close], axis=1).min(axis=1)
        
        return {
            'ha_open': ha_open,
            'ha_high': ha_high,
            'ha_low': ha_low,
            'ha_close': ha_close
        }
    
    def _calculate_volume_profile(self, data: pd.DataFrame, bins: int = 20) -> Dict[str, Any]:
        """Volume Profile Analysis"""
        try:
            price_range = data['high'].max() - data['low'].min()
            bin_size = price_range / bins
            
            volume_profile = {}
            for i in range(bins):
                price_level = data['low'].min() + (i * bin_size)
                volume_at_level = data[
                    (data['low'] <= price_level) & (data['high'] >= price_level)
                ]['volume'].sum()
                volume_profile[price_level] = volume_at_level
            
            # Find Point of Control (highest volume)
            poc = max(volume_profile, key=volume_profile.get)
            
            return {
                'profile': volume_profile,
                'poc': poc,
                'total_volume': data['volume'].sum()
            }
            
        except Exception as e:
            self.logger.warning(f"Volume profile calculation error: {e}")
            return {'profile': {}, 'poc': 0, 'total_volume': 0}
    
    def _calculate_support_resistance(self, data: pd.DataFrame, window: int = 5) -> Dict[str, List[float]]:
        """Support and Resistance Levels"""
        try:
            highs = data['high'].rolling(window=window, center=True).max()
            lows = data['low'].rolling(window=window, center=True).min()
            
            resistance_levels = []
            support_levels = []
            
            for i in range(window, len(data) - window):
                if data['high'].iloc[i] == highs.iloc[i]:
                    resistance_levels.append(data['high'].iloc[i])
                
                if data['low'].iloc[i] == lows.iloc[i]:
                    support_levels.append(data['low'].iloc[i])
            
            # Remove duplicates and sort
            resistance_levels = sorted(list(set(resistance_levels)))[-10:]  # Keep top 10
            support_levels = sorted(list(set(support_levels)), reverse=True)[:10]  # Keep top 10
            
            return {
                'resistance': resistance_levels,
                'support': support_levels
            }
            
        except Exception as e:
            self.logger.warning(f"Support/resistance calculation error: {e}")
            return {'resistance': [], 'support': []}
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        try:
            stats = {
                'total_indicators': len(self.indicator_registry),
                'cache_size': len(self.cache),
                'cpu_workers': self.max_cpu_workers,
                'vectorization_enabled': self.enable_vectorization,
                'average_batch_time': np.mean(self.batch_performance) if self.batch_performance else 0,
                'indicator_performance': {}
            }
            
            # Per-indicator performance
            for indicator, times in self.calculation_times.items():
                if times:
                    stats['indicator_performance'][indicator] = {
                        'average_time': np.mean(times),
                        'min_time': np.min(times),
                        'max_time': np.max(times),
                        'calculations': len(times)
                    }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting performance stats: {e}")
            return {}
    
    async def clear_cache(self):
        """Clear indicator cache"""
        self.cache.clear()
        self.logger.info("🧮 Technical indicators cache cleared")

# Global instance
_technical_indicators = None

def get_technical_indicators(max_cpu_workers: int = None, enable_vectorization: bool = True) -> ParallelTechnicalIndicators:
    """Get global technical indicators instance"""
    global _technical_indicators
    if _technical_indicators is None:
        _technical_indicators = ParallelTechnicalIndicators(max_cpu_workers, enable_vectorization)
    return _technical_indicators