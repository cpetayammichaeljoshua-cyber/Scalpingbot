#!/usr/bin/env python3
"""
Parallel Strategy Executor
High-performance concurrent execution of multiple trading strategies
Supports Time-Fibonacci, MACD Anti, and other strategy implementations with intelligent load balancing
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple, Callable, Union
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict, deque
import traceback
import json
from datetime import datetime
import importlib
import inspect

from parallel_processing_core import get_parallel_core, ParallelTask
from parallel_technical_indicators import get_technical_indicators

@dataclass
class StrategyRequest:
    """Strategy execution request"""
    strategy_name: str
    symbol: str
    timeframe: str
    market_data: Dict[str, Any]
    parameters: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5
    timeout: float = 15.0
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class StrategyResult:
    """Strategy execution result"""
    strategy_name: str
    symbol: str
    timeframe: str
    signal: Optional[Any] = None
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    error: Optional[str] = None
    timestamp: str = ""

class StrategyLoadBalancer:
    """Load balancer for strategy execution"""
    
    def __init__(self):
        self.strategy_loads = defaultdict(float)  # Track CPU load per strategy
        self.execution_times = defaultdict(deque)  # Track execution times
        self.error_rates = defaultdict(float)  # Track error rates
        
    def get_optimal_strategy_order(self, requests: List[StrategyRequest]) -> List[StrategyRequest]:
        """Order strategies by optimal execution sequence"""
        # Sort by priority first, then by expected load
        def sort_key(req):
            avg_time = self._get_average_execution_time(req.strategy_name)
            error_rate = self.error_rates.get(req.strategy_name, 0)
            load_penalty = self.strategy_loads.get(req.strategy_name, 0)
            
            # Higher priority, lower time, lower error rate = better
            return (-req.priority, avg_time, error_rate, load_penalty)
        
        return sorted(requests, key=sort_key)
    
    def _get_average_execution_time(self, strategy_name: str) -> float:
        """Get average execution time for strategy"""
        times = self.execution_times.get(strategy_name, [])
        return sum(times) / len(times) if times else 1.0
    
    def update_performance(self, strategy_name: str, execution_time: float, success: bool):
        """Update performance metrics"""
        # Update execution times
        self.execution_times[strategy_name].append(execution_time)
        if len(self.execution_times[strategy_name]) > 100:
            self.execution_times[strategy_name].popleft()
        
        # Update error rates
        current_rate = self.error_rates.get(strategy_name, 0)
        new_rate = current_rate * 0.95 + (0 if success else 1) * 0.05
        self.error_rates[strategy_name] = new_rate
        
        # Update load
        self.strategy_loads[strategy_name] = execution_time

class ParallelStrategyExecutor:
    """High-performance parallel strategy executor"""
    
    def __init__(self, max_strategy_workers: int = None):
        self.logger = logging.getLogger(__name__)
        self.parallel_core = get_parallel_core()
        self.technical_indicators = get_technical_indicators()
        
        # Strategy workers
        import multiprocessing as mp
        cpu_count = mp.cpu_count()
        self.max_strategy_workers = max_strategy_workers or min(cpu_count * 2, 16)
        self.strategy_executor = ThreadPoolExecutor(
            max_workers=self.max_strategy_workers,
            thread_name_prefix="StrategyExec"
        )
        
        # Strategy registry and load balancer
        self.strategy_registry = {}
        self.load_balancer = StrategyLoadBalancer()
        
        # Performance tracking
        self.execution_stats = {
            'total_executions': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'average_execution_time': 0.0,
            'concurrent_executions': 0,
            'peak_concurrency': 0
        }
        
        # Strategy dependency graph
        self.dependency_graph = {}
        
        # Initialize available strategies
        self._initialize_strategies()
        
        self.logger.info(f"🎯 Parallel Strategy Executor initialized")
        self.logger.info(f"⚙️ Strategy workers: {self.max_strategy_workers}")
        self.logger.info(f"📊 Available strategies: {len(self.strategy_registry)}")
    
    def _initialize_strategies(self):
        """Initialize and register available trading strategies"""
        try:
            # Import and register built-in strategies
            strategy_modules = [
                ('advanced_time_fibonacci_strategy', 'AdvancedTimeFibonacciStrategy'),
                ('macd_anti_strategy', 'MACDAntiStrategy'),
                ('ultimate_scalping_strategy', 'UltimateScalpingStrategy'),
                ('momentum_scalping_strategy', 'MomentumScalpingStrategy'),
                ('volume_breakout_scalping_strategy', 'VolumeBreakoutScalpingStrategy'),
                ('lightning_scalping_strategy', 'LightningScalpingStrategy')
            ]
            
            for module_name, class_name in strategy_modules:
                try:
                    module = importlib.import_module(module_name)
                    strategy_class = getattr(module, class_name)
                    
                    # Create instance
                    strategy_instance = strategy_class()
                    
                    # Register strategy
                    self.strategy_registry[class_name] = {
                        'instance': strategy_instance,
                        'module': module_name,
                        'class': class_name,
                        'analyze_method': getattr(strategy_instance, 'analyze_symbol', None) or 
                                        getattr(strategy_instance, 'analyze', None),
                        'metadata': {
                            'description': getattr(strategy_instance, '__doc__', ''),
                            'timeframes': getattr(strategy_instance, 'timeframes', ['1m', '5m', '15m', '1h']),
                            'parameters': self._extract_strategy_parameters(strategy_instance)
                        }
                    }
                    
                    self.logger.debug(f"✅ Registered strategy: {class_name}")
                    
                except Exception as e:
                    self.logger.warning(f"Failed to register strategy {class_name}: {e}")
            
            # Register custom strategy wrappers
            self._register_custom_strategies()
            
        except Exception as e:
            self.logger.error(f"Error initializing strategies: {e}")
    
    def _register_custom_strategies(self):
        """Register custom strategy implementations"""
        # Multi-timeframe confluence strategy
        self.strategy_registry['MultiTimeframeConfluence'] = {
            'instance': None,
            'module': 'custom',
            'class': 'MultiTimeframeConfluence',
            'analyze_method': self._execute_multi_timeframe_confluence,
            'metadata': {
                'description': 'Multi-timeframe confluence analysis',
                'timeframes': ['5m', '15m', '1h', '4h'],
                'parameters': {'min_timeframes': 3, 'confluence_threshold': 75}
            }
        }
        
        # Volume profile strategy
        self.strategy_registry['VolumeProfile'] = {
            'instance': None,
            'module': 'custom',
            'class': 'VolumeProfile',
            'analyze_method': self._execute_volume_profile_strategy,
            'metadata': {
                'description': 'Volume profile based trading signals',
                'timeframes': ['15m', '1h', '4h'],
                'parameters': {'profile_bins': 20, 'poc_threshold': 1.5}
            }
        }
        
        # Smart money concepts strategy
        self.strategy_registry['SmartMoneyConcepts'] = {
            'instance': None,
            'module': 'custom',
            'class': 'SmartMoneyConcepts',
            'analyze_method': self._execute_smart_money_strategy,
            'metadata': {
                'description': 'Smart money concepts analysis',
                'timeframes': ['1h', '4h', '1d'],
                'parameters': {'liquidity_threshold': 2.0, 'imbalance_ratio': 1.5}
            }
        }
    
    def _extract_strategy_parameters(self, strategy_instance) -> Dict[str, Any]:
        """Extract strategy parameters from instance"""
        try:
            parameters = {}
            
            # Check for common parameter attributes
            for attr in ['timeframes', 'min_signal_strength', 'risk_percentage', 'leverage']:
                if hasattr(strategy_instance, attr):
                    parameters[attr] = getattr(strategy_instance, attr)
            
            # Check for parameter dictionaries
            for attr in ['strategy_params', 'config', 'parameters']:
                if hasattr(strategy_instance, attr):
                    param_dict = getattr(strategy_instance, attr)
                    if isinstance(param_dict, dict):
                        parameters.update(param_dict)
            
            return parameters
            
        except Exception as e:
            self.logger.debug(f"Error extracting strategy parameters: {e}")
            return {}
    
    async def execute_strategies_parallel(self, requests: List[StrategyRequest]) -> List[StrategyResult]:
        """Execute multiple strategies in parallel"""
        try:
            start_time = time.time()
            
            if not requests:
                return []
            
            # Load balance and optimize execution order
            optimized_requests = self.load_balancer.get_optimal_strategy_order(requests)
            
            # Group by dependencies
            dependency_groups = self._resolve_strategy_dependencies(optimized_requests)
            
            all_results = []
            
            # Execute dependency groups sequentially, strategies within groups in parallel
            for group in dependency_groups:
                group_results = await self._execute_strategy_group(group)
                all_results.extend(group_results)
            
            # Update statistics
            execution_time = time.time() - start_time
            self.execution_stats['total_executions'] += len(requests)
            self.execution_stats['average_execution_time'] = (
                (self.execution_stats['average_execution_time'] * 0.9) + 
                (execution_time * 0.1)
            )
            
            success_count = sum(1 for r in all_results if r.error is None)
            self.execution_stats['successful_executions'] += success_count
            self.execution_stats['failed_executions'] += len(all_results) - success_count
            
            self.logger.info(
                f"🎯 Parallel strategies completed: {success_count}/{len(requests)} "
                f"in {execution_time:.2f}s ({success_count/execution_time:.1f} strategies/s)"
            )
            
            return all_results
            
        except Exception as e:
            self.logger.error(f"❌ Parallel strategy execution failed: {e}")
            self.logger.debug(traceback.format_exc())
            return []
    
    async def execute_symbol_all_strategies(self, symbol: str, market_data: Dict[str, Any],
                                          strategies: List[str] = None) -> Dict[str, StrategyResult]:
        """Execute all strategies for a symbol in parallel"""
        try:
            # Default strategy set if none specified
            if strategies is None:
                strategies = list(self.strategy_registry.keys())
            
            # Determine optimal timeframe for each strategy
            requests = []
            for strategy_name in strategies:
                if strategy_name in self.strategy_registry:
                    strategy_info = self.strategy_registry[strategy_name]
                    preferred_timeframes = strategy_info['metadata'].get('timeframes', ['15m'])
                    
                    # Use the first available timeframe from market data
                    timeframe = '15m'  # Default
                    for tf in preferred_timeframes:
                        if tf in market_data:
                            timeframe = tf
                            break
                    
                    request = StrategyRequest(
                        strategy_name=strategy_name,
                        symbol=symbol,
                        timeframe=timeframe,
                        market_data=market_data,
                        priority=8,
                        timeout=20.0
                    )
                    requests.append(request)
            
            # Execute all strategies
            results = await self.execute_strategies_parallel(requests)
            
            # Convert to dictionary
            result_dict = {}
            for result in results:
                result_dict[result.strategy_name] = result
            
            return result_dict
            
        except Exception as e:
            self.logger.error(f"❌ Failed to execute all strategies for {symbol}: {e}")
            return {}
    
    def _resolve_strategy_dependencies(self, requests: List[StrategyRequest]) -> List[List[StrategyRequest]]:
        """Resolve strategy dependencies and create execution groups"""
        try:
            # Simple dependency resolution - group by dependency levels
            dependency_levels = defaultdict(list)
            
            for request in requests:
                level = len(request.dependencies)
                dependency_levels[level].append(request)
            
            # Convert to ordered list
            groups = []
            for level in sorted(dependency_levels.keys()):
                groups.append(dependency_levels[level])
            
            return groups
            
        except Exception as e:
            self.logger.error(f"Error resolving dependencies: {e}")
            return [requests]  # Fallback to single group
    
    async def _execute_strategy_group(self, requests: List[StrategyRequest]) -> List[StrategyResult]:
        """Execute a group of strategies in parallel"""
        try:
            # Create parallel tasks
            tasks = []
            for request in requests:
                task = ParallelTask(
                    task_id=f"strategy_{request.strategy_name}_{request.symbol}",
                    function=self._execute_single_strategy,
                    args=(request,),
                    priority=request.priority,
                    timeout=request.timeout,
                    retry_count=2
                )
                tasks.append(task)
            
            # Execute in parallel
            self.execution_stats['concurrent_executions'] = len(tasks)
            self.execution_stats['peak_concurrency'] = max(
                self.execution_stats['peak_concurrency'],
                len(tasks)
            )
            
            task_results = await self.parallel_core.execute_parallel(tasks)
            
            # Convert to strategy results
            results = []
            for task_id, result in task_results:
                if isinstance(result, StrategyResult):
                    results.append(result)
                elif isinstance(result, Exception):
                    # Create error result
                    strategy_name = task_id.split('_')[1] if '_' in task_id else 'unknown'
                    symbol = task_id.split('_')[2] if len(task_id.split('_')) > 2 else 'unknown'
                    
                    error_result = StrategyResult(
                        strategy_name=strategy_name,
                        symbol=symbol,
                        timeframe='unknown',
                        error=str(result),
                        timestamp=datetime.now().isoformat()
                    )
                    results.append(error_result)
            
            self.execution_stats['concurrent_executions'] = 0
            
            return results
            
        except Exception as e:
            self.logger.error(f"❌ Strategy group execution failed: {e}")
            return []
    
    async def _execute_single_strategy(self, request: StrategyRequest) -> StrategyResult:
        """Execute a single strategy"""
        try:
            start_time = time.time()
            
            # Get strategy info
            strategy_info = self.strategy_registry.get(request.strategy_name)
            if not strategy_info:
                raise ValueError(f"Unknown strategy: {request.strategy_name}")
            
            # Get analyze method
            analyze_method = strategy_info['analyze_method']
            if not analyze_method:
                raise ValueError(f"No analyze method for strategy: {request.strategy_name}")
            
            # Prepare arguments
            args = await self._prepare_strategy_arguments(request, strategy_info)
            
            # Execute strategy
            loop = asyncio.get_running_loop()
            
            if asyncio.iscoroutinefunction(analyze_method):
                signal = await analyze_method(**args)
            else:
                signal = await loop.run_in_executor(
                    self.strategy_executor,
                    lambda: analyze_method(**args)
                )
            
            execution_time = time.time() - start_time
            
            # Update load balancer
            self.load_balancer.update_performance(
                request.strategy_name, 
                execution_time, 
                signal is not None
            )
            
            # Create result
            result = StrategyResult(
                strategy_name=request.strategy_name,
                symbol=request.symbol,
                timeframe=request.timeframe,
                signal=signal,
                confidence=self._extract_signal_confidence(signal),
                metadata={
                    'parameters': request.parameters,
                    'execution_method': 'async' if asyncio.iscoroutinefunction(analyze_method) else 'sync'
                },
                execution_time=execution_time,
                timestamp=datetime.now().isoformat()
            )
            
            return result
            
        except Exception as e:
            self.logger.warning(f"Strategy {request.strategy_name} failed for {request.symbol}: {e}")
            
            # Update load balancer with failure
            self.load_balancer.update_performance(request.strategy_name, 0, False)
            
            return StrategyResult(
                strategy_name=request.strategy_name,
                symbol=request.symbol,
                timeframe=request.timeframe,
                error=str(e),
                timestamp=datetime.now().isoformat()
            )
    
    async def _prepare_strategy_arguments(self, request: StrategyRequest, strategy_info: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare arguments for strategy execution"""
        try:
            args = {
                'symbol': request.symbol,
                'ohlcv_data': request.market_data
            }
            
            # Add timeframe-specific data if available
            if request.timeframe in request.market_data:
                args['ohlcv_data'] = {request.timeframe: request.market_data[request.timeframe]}
            
            # Add strategy parameters
            args.update(request.parameters)
            
            # Add ML analyzer if strategy supports it
            analyze_method = strategy_info['analyze_method']
            if analyze_method and 'ml_analyzer' in inspect.signature(analyze_method).parameters:
                # Create a simple ML analyzer proxy
                args['ml_analyzer'] = type('MLAnalyzer', (), {
                    'predict_trade_outcome': lambda self, data: {
                        'prediction': 'favorable',
                        'confidence': 75.0,
                        'expected_profit': 1.5,
                        'risk_probability': 25.0
                    }
                })()
            
            return args
            
        except Exception as e:
            self.logger.error(f"Error preparing strategy arguments: {e}")
            return {'symbol': request.symbol, 'ohlcv_data': request.market_data}
    
    def _extract_signal_confidence(self, signal: Any) -> float:
        """Extract confidence from strategy signal"""
        try:
            if signal is None:
                return 0.0
            
            # Check for confidence attribute
            if hasattr(signal, 'signal_strength'):
                return float(signal.signal_strength)
            elif hasattr(signal, 'confidence'):
                return float(signal.confidence)
            elif isinstance(signal, dict):
                return float(signal.get('signal_strength', signal.get('confidence', 50.0)))
            else:
                return 75.0  # Default confidence for valid signals
                
        except Exception:
            return 50.0  # Fallback confidence
    
    # Custom Strategy Implementations
    
    async def _execute_multi_timeframe_confluence(self, symbol: str, ohlcv_data: Dict[str, Any], **kwargs) -> Optional[Any]:
        """Multi-timeframe confluence strategy"""
        try:
            min_timeframes = kwargs.get('min_timeframes', 3)
            confluence_threshold = kwargs.get('confluence_threshold', 75)
            
            # Available timeframes
            timeframes = ['5m', '15m', '1h', '4h']
            available_tfs = [tf for tf in timeframes if tf in ohlcv_data]
            
            if len(available_tfs) < min_timeframes:
                return None
            
            # Calculate indicators for each timeframe
            tf_signals = []
            
            for tf in available_tfs[:4]:  # Limit to 4 timeframes
                data = ohlcv_data[tf]
                if data is None or len(data) < 50:
                    continue
                
                # Calculate basic signals
                sma_20 = data['close'].rolling(20).mean()
                sma_50 = data['close'].rolling(50).mean()
                rsi = self.technical_indicators._calculate_rsi(data, 14)
                
                current_price = data['close'].iloc[-1]
                current_rsi = rsi.iloc[-1]
                
                signal_strength = 0
                
                # Trend signal
                if len(sma_20) > 0 and len(sma_50) > 0:
                    if sma_20.iloc[-1] > sma_50.iloc[-1]:
                        signal_strength += 30
                    else:
                        signal_strength -= 30
                
                # RSI signal
                if current_rsi < 30:
                    signal_strength += 20
                elif current_rsi > 70:
                    signal_strength -= 20
                
                # Price momentum
                if len(data) >= 10:
                    price_change = (current_price - data['close'].iloc[-10]) / data['close'].iloc[-10]
                    if price_change > 0.02:
                        signal_strength += 25
                    elif price_change < -0.02:
                        signal_strength -= 25
                
                tf_signals.append({
                    'timeframe': tf,
                    'signal_strength': signal_strength,
                    'direction': 'BUY' if signal_strength > 0 else 'SELL'
                })
            
            # Calculate confluence
            if len(tf_signals) >= min_timeframes:
                avg_strength = sum(abs(s['signal_strength']) for s in tf_signals) / len(tf_signals)
                
                if avg_strength >= confluence_threshold:
                    # Determine overall direction
                    bullish_count = sum(1 for s in tf_signals if s['signal_strength'] > 0)
                    bearish_count = len(tf_signals) - bullish_count
                    
                    direction = 'BUY' if bullish_count > bearish_count else 'SELL'
                    
                    return {
                        'symbol': symbol,
                        'direction': direction,
                        'signal_strength': avg_strength,
                        'timeframe_confluence': tf_signals,
                        'confluence_count': len(tf_signals)
                    }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Multi-timeframe confluence error: {e}")
            return None
    
    async def _execute_volume_profile_strategy(self, symbol: str, ohlcv_data: Dict[str, Any], **kwargs) -> Optional[Any]:
        """Volume profile strategy"""
        try:
            timeframe = '1h'  # Use 1h for volume profile
            if timeframe not in ohlcv_data:
                return None
            
            data = ohlcv_data[timeframe]
            if data is None or len(data) < 100:
                return None
            
            # Calculate volume profile
            volume_profile = self.technical_indicators._calculate_volume_profile(data, bins=20)
            poc = volume_profile['poc']
            
            current_price = data['close'].iloc[-1]
            
            # Distance from POC
            poc_distance = abs(current_price - poc) / current_price
            
            # Volume analysis
            recent_volume = data['volume'].tail(20).mean()
            avg_volume = data['volume'].mean()
            volume_ratio = recent_volume / avg_volume
            
            signal_strength = 0
            
            # POC proximity signal
            if poc_distance < 0.01:  # Within 1% of POC
                signal_strength += 40
            
            # Volume confirmation
            if volume_ratio > 1.5:
                signal_strength += 30
            
            # Price direction
            price_momentum = (current_price - data['close'].iloc[-5]) / data['close'].iloc[-5]
            if price_momentum > 0.005:
                signal_strength += 20
                direction = 'BUY'
            elif price_momentum < -0.005:
                signal_strength += 20
                direction = 'SELL'
            else:
                direction = 'HOLD'
            
            if signal_strength >= 60 and direction != 'HOLD':
                return {
                    'symbol': symbol,
                    'direction': direction,
                    'signal_strength': signal_strength,
                    'poc': poc,
                    'current_price': current_price,
                    'volume_ratio': volume_ratio
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Volume profile strategy error: {e}")
            return None
    
    async def _execute_smart_money_strategy(self, symbol: str, ohlcv_data: Dict[str, Any], **kwargs) -> Optional[Any]:
        """Smart money concepts strategy"""
        try:
            timeframe = '4h'  # Use 4h for smart money analysis
            if timeframe not in ohlcv_data:
                return None
            
            data = ohlcv_data[timeframe]
            if data is None or len(data) < 50:
                return None
            
            # Identify liquidity zones (recent highs/lows)
            recent_high = data['high'].tail(20).max()
            recent_low = data['low'].tail(20).min()
            current_price = data['close'].iloc[-1]
            
            # Calculate ATR for context
            atr = self.technical_indicators._calculate_atr(data, 14).iloc[-1]
            
            # Order block detection (simplified)
            order_blocks = []
            for i in range(len(data) - 20, len(data) - 5):
                if i > 0:
                    if (data['high'].iloc[i] > data['high'].iloc[i-1] and 
                        data['high'].iloc[i] > data['high'].iloc[i+1]):
                        order_blocks.append({
                            'type': 'resistance',
                            'price': data['high'].iloc[i],
                            'strength': data['volume'].iloc[i]
                        })
                    
                    if (data['low'].iloc[i] < data['low'].iloc[i-1] and 
                        data['low'].iloc[i] < data['low'].iloc[i+1]):
                        order_blocks.append({
                            'type': 'support',
                            'price': data['low'].iloc[i],
                            'strength': data['volume'].iloc[i]
                        })
            
            signal_strength = 0
            direction = 'HOLD'
            
            # Liquidity sweep detection
            if current_price > recent_high * 0.999:  # Near recent high
                signal_strength += 35
                direction = 'SELL'  # Potential reversal
            elif current_price < recent_low * 1.001:  # Near recent low
                signal_strength += 35
                direction = 'BUY'  # Potential reversal
            
            # Order block interaction
            for block in order_blocks:
                distance = abs(current_price - block['price']) / current_price
                if distance < 0.005:  # Within 0.5%
                    signal_strength += 25
                    if block['type'] == 'support' and direction != 'SELL':
                        direction = 'BUY'
                    elif block['type'] == 'resistance' and direction != 'BUY':
                        direction = 'SELL'
            
            # Volume confirmation
            recent_volume = data['volume'].tail(5).mean()
            avg_volume = data['volume'].mean()
            if recent_volume > avg_volume * 1.5:
                signal_strength += 20
            
            if signal_strength >= 70 and direction != 'HOLD':
                return {
                    'symbol': symbol,
                    'direction': direction,
                    'signal_strength': signal_strength,
                    'liquidity_zones': {
                        'high': recent_high,
                        'low': recent_low
                    },
                    'order_blocks': order_blocks[:3],  # Top 3 order blocks
                    'current_price': current_price
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Smart money strategy error: {e}")
            return None
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        try:
            total_executions = self.execution_stats['total_executions']
            success_rate = (self.execution_stats['successful_executions'] / 
                          max(1, total_executions)) * 100
            
            return {
                'execution_stats': self.execution_stats.copy(),
                'success_rate': success_rate,
                'registered_strategies': len(self.strategy_registry),
                'strategy_workers': self.max_strategy_workers,
                'load_balancer': {
                    'strategy_loads': dict(self.load_balancer.strategy_loads),
                    'error_rates': dict(self.load_balancer.error_rates),
                    'average_times': {
                        name: sum(times) / len(times) if times else 0
                        for name, times in self.load_balancer.execution_times.items()
                    }
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error getting performance stats: {e}")
            return {}
    
    def get_available_strategies(self) -> Dict[str, Dict[str, Any]]:
        """Get list of available strategies"""
        return {
            name: {
                'module': info['module'],
                'class': info['class'],
                'metadata': info['metadata']
            }
            for name, info in self.strategy_registry.items()
        }

# Global instance
_strategy_executor = None

def get_strategy_executor(max_strategy_workers: int = None) -> ParallelStrategyExecutor:
    """Get global strategy executor instance"""
    global _strategy_executor
    if _strategy_executor is None:
        _strategy_executor = ParallelStrategyExecutor(max_strategy_workers)
    return _strategy_executor