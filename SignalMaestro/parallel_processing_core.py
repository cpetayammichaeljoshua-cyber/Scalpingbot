#!/usr/bin/env python3
"""
Parallel Processing Core for Trading Bot
High-performance parallel signal generation and analysis system
Implements asyncio-based concurrency with comprehensive error handling
"""

import asyncio
import aiohttp
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Tuple, Union
from datetime import datetime, timedelta
from collections import defaultdict, deque
import queue
import json
import traceback
from contextlib import asynccontextmanager
import weakref
import psutil
import gc

# Performance monitoring
@dataclass
class PerformanceMetrics:
    """Real-time performance monitoring"""
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    average_processing_time: float = 0.0
    peak_concurrency: int = 0
    current_concurrency: int = 0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    operations_per_second: float = 0.0
    processing_times: deque = field(default_factory=lambda: deque(maxlen=1000))
    start_time: datetime = field(default_factory=datetime.now)
    
    def update_timing(self, processing_time: float):
        """Update timing metrics"""
        self.processing_times.append(processing_time)
        self.total_operations += 1
        self.average_processing_time = sum(self.processing_times) / len(self.processing_times)
        
        # Calculate operations per second
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if elapsed > 0:
            self.operations_per_second = self.total_operations / elapsed

@dataclass 
class ParallelTask:
    """Parallel task definition"""
    task_id: str
    function: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    priority: int = 5  # 1-10, 10 being highest priority
    timeout: float = 30.0
    retry_count: int = 3
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

class ParallelProcessingCore:
    """Core parallel processing engine for trading bot operations"""
    
    def __init__(self, max_workers: int = None, max_async_tasks: int = None):
        self.logger = logging.getLogger(__name__)
        
        # Auto-detect optimal worker counts
        cpu_count = psutil.cpu_count(logical=True)
        self.max_workers = max_workers or min(32, (cpu_count * 2) + 4)
        self.max_async_tasks = max_async_tasks or min(100, cpu_count * 10)
        
        # Thread pools for different types of operations
        self.io_executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="SignalIO"
        )
        self.cpu_executor = ThreadPoolExecutor(
            max_workers=min(cpu_count, 8),
            thread_name_prefix="SignalCPU"
        )
        self.process_executor = ProcessPoolExecutor(
            max_workers=min(cpu_count, 4)
        )
        
        # Async task management
        self.active_tasks = set()
        self.task_semaphore = asyncio.Semaphore(self.max_async_tasks)
        self.task_queue = asyncio.Queue(maxsize=1000)
        self.priority_queue = queue.PriorityQueue()
        
        # Performance monitoring
        self.metrics = PerformanceMetrics()
        self.performance_history = deque(maxlen=1000)
        
        # Task registry and dependency management
        self.task_registry = {}
        self.completed_tasks = set()
        self.failed_tasks = set()
        
        # Circuit breaker for error handling
        self.error_counts = defaultdict(int)
        self.circuit_breaker_thresholds = {
            'market_data': 10,
            'indicators': 5,
            'ml_analysis': 8,
            'cornix': 15
        }
        
        # Resource monitoring
        self.resource_monitor_active = True
        self.memory_threshold_mb = 1024  # 1GB memory limit
        self.cpu_threshold_percent = 90
        
        self.logger.info(f"🚀 Parallel Processing Core initialized")
        self.logger.info(f"⚙️ Workers: IO={self.max_workers}, CPU={min(cpu_count, 8)}, Process={min(cpu_count, 4)}")
        self.logger.info(f"📊 Max async tasks: {self.max_async_tasks}")
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start_background_tasks()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.shutdown()
        
    async def start_background_tasks(self):
        """Start background monitoring and management tasks"""
        # Start resource monitor
        asyncio.create_task(self._resource_monitor())
        
        # Start task queue processor
        asyncio.create_task(self._process_task_queue())
        
        # Start performance metrics collector
        asyncio.create_task(self._collect_performance_metrics())
        
    async def execute_parallel(self, tasks: List[ParallelTask], 
                             batch_size: int = None) -> List[Tuple[str, Any]]:
        """Execute multiple tasks in parallel with dependency resolution"""
        try:
            start_time = time.time()
            
            if not tasks:
                return []
                
            batch_size = batch_size or min(len(tasks), self.max_async_tasks // 2)
            
            # Resolve dependencies and create execution order
            execution_order = self._resolve_dependencies(tasks)
            
            results = []
            
            # Process tasks in dependency-resolved batches
            for batch in self._create_batches(execution_order, batch_size):
                batch_results = await self._execute_batch(batch)
                results.extend(batch_results)
                
                # Update completed tasks for dependency resolution
                for task_id, result in batch_results:
                    if not isinstance(result, Exception):
                        self.completed_tasks.add(task_id)
                    else:
                        self.failed_tasks.add(task_id)
            
            processing_time = time.time() - start_time
            self.metrics.update_timing(processing_time)
            
            self.logger.info(f"✅ Parallel execution completed: {len(tasks)} tasks in {processing_time:.2f}s")
            
            return results
            
        except Exception as e:
            self.logger.error(f"❌ Parallel execution failed: {e}")
            self.logger.debug(traceback.format_exc())
            return [(task.task_id, e) for task in tasks]
    
    async def execute_async_batch(self, functions: List[Callable], 
                                args_list: List[tuple] = None,
                                kwargs_list: List[dict] = None,
                                timeout: float = 30.0) -> List[Any]:
        """Execute async functions in parallel batch"""
        try:
            if not functions:
                return []
                
            args_list = args_list or [() for _ in functions]
            kwargs_list = kwargs_list or [{} for _ in functions]
            
            # Create semaphore-controlled tasks
            async def execute_with_semaphore(func, args, kwargs):
                async with self.task_semaphore:
                    try:
                        if asyncio.iscoroutinefunction(func):
                            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
                        else:
                            # Run sync function in thread
                            loop = asyncio.get_running_loop()
                            return await loop.run_in_executor(
                                self.io_executor, 
                                lambda: func(*args, **kwargs)
                            )
                    except Exception as e:
                        self.logger.warning(f"Task failed: {e}")
                        return e
            
            # Create and execute tasks
            tasks = [
                execute_with_semaphore(func, args, kwargs)
                for func, args, kwargs in zip(functions, args_list, kwargs_list)
            ]
            
            # Track active tasks
            self.active_tasks.update(tasks)
            self.metrics.current_concurrency = len(self.active_tasks)
            self.metrics.peak_concurrency = max(self.metrics.peak_concurrency, len(self.active_tasks))
            
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                return results
            finally:
                # Clean up task tracking
                self.active_tasks -= set(tasks)
                self.metrics.current_concurrency = len(self.active_tasks)
                
        except Exception as e:
            self.logger.error(f"❌ Async batch execution failed: {e}")
            return [e for _ in functions]
    
    async def execute_cpu_intensive(self, functions: List[Callable],
                                  args_list: List[tuple] = None,
                                  use_processes: bool = False) -> List[Any]:
        """Execute CPU-intensive tasks in parallel"""
        try:
            if not functions:
                return []
                
            args_list = args_list or [() for _ in functions]
            executor = self.process_executor if use_processes else self.cpu_executor
            
            loop = asyncio.get_running_loop()
            
            # Submit all tasks
            futures = [
                loop.run_in_executor(executor, func, *args)
                for func, args in zip(functions, args_list)
            ]
            
            # Wait for completion with timeout
            results = await asyncio.gather(*futures, return_exceptions=True)
            
            # Count successes and failures
            successes = sum(1 for r in results if not isinstance(r, Exception))
            failures = len(results) - successes
            
            self.metrics.successful_operations += successes
            self.metrics.failed_operations += failures
            
            self.logger.debug(f"CPU tasks completed: {successes} success, {failures} failed")
            
            return results
            
        except Exception as e:
            self.logger.error(f"❌ CPU intensive execution failed: {e}")
            return [e for _ in functions]
    
    async def parallel_market_data_fetch(self, symbol_timeframe_pairs: List[Tuple[str, str]],
                                       fetch_function: Callable) -> Dict[Tuple[str, str], Any]:
        """Parallel market data fetching for multiple symbol-timeframe combinations"""
        try:
            start_time = time.time()
            
            # Create async tasks for each symbol-timeframe pair
            async def fetch_with_retry(symbol: str, timeframe: str, retries: int = 3):
                for attempt in range(retries):
                    try:
                        result = await fetch_function(symbol, timeframe)
                        return (symbol, timeframe), result
                    except Exception as e:
                        if attempt == retries - 1:
                            self.logger.warning(f"Failed to fetch {symbol} {timeframe} after {retries} attempts: {e}")
                            return (symbol, timeframe), None
                        await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff
            
            # Execute all fetches in parallel
            tasks = [fetch_with_retry(symbol, tf) for symbol, tf in symbol_timeframe_pairs]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Convert to dictionary
            result_dict = {}
            for result in results:
                if isinstance(result, Exception):
                    continue
                if result and len(result) == 2:
                    key, data = result
                    if data is not None:
                        result_dict[key] = data
            
            processing_time = time.time() - start_time
            self.logger.info(f"📊 Parallel market data fetch completed: {len(result_dict)}/{len(symbol_timeframe_pairs)} pairs in {processing_time:.2f}s")
            
            return result_dict
            
        except Exception as e:
            self.logger.error(f"❌ Parallel market data fetch failed: {e}")
            return {}
    
    def _resolve_dependencies(self, tasks: List[ParallelTask]) -> List[List[ParallelTask]]:
        """Resolve task dependencies and create execution order"""
        task_map = {task.task_id: task for task in tasks}
        resolved = []
        remaining = set(task.task_id for task in tasks)
        
        while remaining:
            # Find tasks with no unresolved dependencies
            ready = []
            for task_id in remaining:
                task = task_map[task_id]
                if all(dep in self.completed_tasks or dep not in task_map for dep in task.dependencies):
                    ready.append(task)
            
            if not ready:
                # Break circular dependencies by selecting highest priority
                self.logger.warning("Circular dependencies detected, breaking with priority selection")
                ready = [max((task_map[tid] for tid in remaining), key=lambda t: t.priority)]
            
            resolved.append(ready)
            remaining -= {task.task_id for task in ready}
        
        return resolved
    
    def _create_batches(self, execution_order: List[List[ParallelTask]], 
                       batch_size: int) -> List[List[ParallelTask]]:
        """Create execution batches from dependency-resolved tasks"""
        batches = []
        for level in execution_order:
            # Split level into batches if it's too large
            for i in range(0, len(level), batch_size):
                batches.append(level[i:i + batch_size])
        return batches
    
    async def _execute_batch(self, batch: List[ParallelTask]) -> List[Tuple[str, Any]]:
        """Execute a batch of tasks"""
        results = []
        
        async def execute_task(task: ParallelTask):
            try:
                start_time = time.time()
                
                # Execute with timeout and retries
                for attempt in range(task.retry_count):
                    try:
                        if asyncio.iscoroutinefunction(task.function):
                            result = await asyncio.wait_for(
                                task.function(*task.args, **task.kwargs),
                                timeout=task.timeout
                            )
                        else:
                            loop = asyncio.get_running_loop()
                            result = await loop.run_in_executor(
                                self.io_executor,
                                lambda: task.function(*task.args, **task.kwargs)
                            )
                        
                        processing_time = time.time() - start_time
                        self.metrics.update_timing(processing_time)
                        return task.task_id, result
                        
                    except Exception as e:
                        if attempt == task.retry_count - 1:
                            self.logger.warning(f"Task {task.task_id} failed after {task.retry_count} attempts: {e}")
                            return task.task_id, e
                        await asyncio.sleep(0.1 * (attempt + 1))
                        
            except Exception as e:
                self.logger.error(f"Task {task.task_id} execution error: {e}")
                return task.task_id, e
        
        # Execute all tasks in batch
        batch_results = await asyncio.gather(*[execute_task(task) for task in batch], return_exceptions=True)
        
        for result in batch_results:
            if isinstance(result, Exception):
                results.append(("unknown", result))
            else:
                results.append(result)
        
        return results
    
    async def _resource_monitor(self):
        """Monitor system resources and throttle if necessary"""
        while self.resource_monitor_active:
            try:
                # Check memory usage
                memory_mb = psutil.virtual_memory().used / 1024 / 1024
                cpu_percent = psutil.cpu_percent(interval=1)
                
                self.metrics.memory_usage_mb = memory_mb
                self.metrics.cpu_usage_percent = cpu_percent
                
                # Throttle if resources are high
                if memory_mb > self.memory_threshold_mb or cpu_percent > self.cpu_threshold_percent:
                    self.logger.warning(f"High resource usage: Memory {memory_mb:.0f}MB, CPU {cpu_percent:.1f}%")
                    # Reduce concurrency temporarily
                    self.task_semaphore = asyncio.Semaphore(max(1, self.max_async_tasks // 2))
                    await asyncio.sleep(2)
                else:
                    # Restore normal concurrency
                    self.task_semaphore = asyncio.Semaphore(self.max_async_tasks)
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                self.logger.error(f"Resource monitor error: {e}")
                await asyncio.sleep(10)
    
    async def _process_task_queue(self):
        """Process queued tasks"""
        while True:
            try:
                task = await self.task_queue.get()
                if task is None:  # Shutdown signal
                    break
                    
                await self._execute_batch([task])
                self.task_queue.task_done()
                
            except Exception as e:
                self.logger.error(f"Task queue processing error: {e}")
                await asyncio.sleep(1)
    
    async def _collect_performance_metrics(self):
        """Collect and log performance metrics"""
        while True:
            try:
                # Create performance snapshot
                snapshot = {
                    'timestamp': datetime.now().isoformat(),
                    'operations_per_second': self.metrics.operations_per_second,
                    'average_processing_time': self.metrics.average_processing_time,
                    'current_concurrency': self.metrics.current_concurrency,
                    'peak_concurrency': self.metrics.peak_concurrency,
                    'memory_usage_mb': self.metrics.memory_usage_mb,
                    'cpu_usage_percent': self.metrics.cpu_usage_percent,
                    'success_rate': (self.metrics.successful_operations / 
                                   max(1, self.metrics.total_operations)) * 100
                }
                
                self.performance_history.append(snapshot)
                
                # Log metrics every minute
                if len(self.performance_history) % 12 == 0:  # Every 12 * 5s = 1 minute
                    self.logger.info(
                        f"📊 Performance: {snapshot['operations_per_second']:.1f} ops/s, "
                        f"{snapshot['average_processing_time']:.3f}s avg, "
                        f"{snapshot['current_concurrency']} active, "
                        f"{snapshot['success_rate']:.1f}% success"
                    )
                
                await asyncio.sleep(5)  # Collect metrics every 5 seconds
                
            except Exception as e:
                self.logger.error(f"Performance metrics collection error: {e}")
                await asyncio.sleep(30)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get current performance statistics"""
        return {
            'metrics': {
                'total_operations': self.metrics.total_operations,
                'successful_operations': self.metrics.successful_operations,
                'failed_operations': self.metrics.failed_operations,
                'success_rate': (self.metrics.successful_operations / 
                               max(1, self.metrics.total_operations)) * 100,
                'operations_per_second': self.metrics.operations_per_second,
                'average_processing_time': self.metrics.average_processing_time,
                'current_concurrency': self.metrics.current_concurrency,
                'peak_concurrency': self.metrics.peak_concurrency,
                'memory_usage_mb': self.metrics.memory_usage_mb,
                'cpu_usage_percent': self.metrics.cpu_usage_percent
            },
            'executors': {
                'io_workers': self.max_workers,
                'cpu_workers': min(psutil.cpu_count(logical=True), 8),
                'process_workers': min(psutil.cpu_count(logical=True), 4),
                'max_async_tasks': self.max_async_tasks
            },
            'active_tasks': len(self.active_tasks),
            'queue_size': self.task_queue.qsize() if hasattr(self.task_queue, 'qsize') else 0
        }
    
    async def shutdown(self):
        """Graceful shutdown of parallel processing system"""
        try:
            self.logger.info("🔄 Shutting down parallel processing system...")
            
            # Stop resource monitoring
            self.resource_monitor_active = False
            
            # Cancel active tasks
            for task in self.active_tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for active tasks to complete or cancel
            if self.active_tasks:
                await asyncio.gather(*self.active_tasks, return_exceptions=True)
            
            # Shutdown executors
            self.io_executor.shutdown(wait=True)
            self.cpu_executor.shutdown(wait=True)
            self.process_executor.shutdown(wait=True)
            
            # Signal task queue to stop
            await self.task_queue.put(None)
            
            self.logger.info("✅ Parallel processing system shutdown complete")
            
        except Exception as e:
            self.logger.error(f"❌ Error during shutdown: {e}")

# Global instance for singleton access
_parallel_core_instance = None

def get_parallel_core(max_workers: int = None, max_async_tasks: int = None) -> ParallelProcessingCore:
    """Get global parallel processing core instance"""
    global _parallel_core_instance
    if _parallel_core_instance is None:
        _parallel_core_instance = ParallelProcessingCore(max_workers, max_async_tasks)
    return _parallel_core_instance

async def shutdown_parallel_core():
    """Shutdown global parallel processing core"""
    global _parallel_core_instance
    if _parallel_core_instance:
        await _parallel_core_instance.shutdown()
        _parallel_core_instance = None