#!/usr/bin/env python3
"""
Parallel Trade Processor - Concurrent signal analysis and execution
Processes multiple trading signals simultaneously with proper resource management
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional, Coroutine
from dataclasses import dataclass
from datetime import datetime
import logging
from enum import Enum
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProcessPriority(Enum):
    HIGH = 1
    MEDIUM = 2
    LOW = 3

@dataclass
class ProcessTask:
    symbol: str
    task_type: str  # 'analyze', 'execute', 'monitor'
    priority: ProcessPriority
    coro: Coroutine
    created_at: datetime
    timeout: float = 30.0

class ParallelTradeProcessor:
    """Manages parallel processing of trading operations"""
    
    def __init__(self, max_concurrent_tasks: int = 10, max_workers: int = 4):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.completed_tasks: List[Dict[str, Any]] = []
        self.failed_tasks: List[Dict[str, Any]] = []
        self.task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.stats = {
            'total_processed': 0,
            'successful': 0,
            'failed': 0,
            'avg_process_time': 0.0,
            'peak_concurrent': 0
        }
        self._process_times = []
    
    async def submit_task(self, symbol: str, task_type: str, coro: Coroutine,
                         priority: ProcessPriority = ProcessPriority.MEDIUM) -> Optional[Any]:
        """Submit a task for parallel processing"""
        
        if len(self.active_tasks) >= self.max_concurrent_tasks:
            logger.warning(f"Task queue full for {symbol}. Waiting for slot...")
            await self._wait_for_slot()
        
        task_id = f"{symbol}_{task_type}_{int(time.time()*1000)}"
        
        try:
            # Create task with timeout
            task = asyncio.create_task(
                self._execute_with_timeout(coro, task_id, symbol, priority.value)
            )
            self.active_tasks[task_id] = task
            
            # Update peak concurrent
            self.stats['peak_concurrent'] = max(self.stats['peak_concurrent'], len(self.active_tasks))
            
            # Return result and clean up
            result = await task
            return result
            
        except asyncio.TimeoutError:
            logger.error(f"Task {task_id} timed out")
            self.failed_tasks.append({
                'task_id': task_id,
                'symbol': symbol,
                'type': task_type,
                'error': 'Timeout',
                'timestamp': datetime.now()
            })
            return None
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            self.failed_tasks.append({
                'task_id': task_id,
                'symbol': symbol,
                'type': task_type,
                'error': str(e),
                'timestamp': datetime.now()
            })
            return None
        finally:
            self.active_tasks.pop(task_id, None)
    
    async def submit_batch(self, tasks: List[tuple]) -> List[Any]:
        """
        Submit multiple tasks for parallel processing
        tasks: list of (symbol, task_type, coro) tuples
        Returns: list of results in order
        """
        coros = []
        for symbol, task_type, coro in tasks:
            coros.append(self.submit_task(symbol, task_type, coro))
        
        results = await asyncio.gather(*coros, return_exceptions=True)
        return results
    
    async def _execute_with_timeout(self, coro: Coroutine, task_id: str, 
                                    symbol: str, priority: int) -> Any:
        """Execute coroutine with timeout and tracking"""
        start_time = time.time()
        
        try:
            # Default timeout varies by priority
            timeout = 30.0 if priority <= 2 else 20.0
            result = await asyncio.wait_for(coro, timeout=timeout)
            
            elapsed = time.time() - start_time
            self._process_times.append(elapsed)
            
            # Keep last 100 times for average
            if len(self._process_times) > 100:
                self._process_times.pop(0)
            
            self.stats['avg_process_time'] = sum(self._process_times) / len(self._process_times)
            self.stats['total_processed'] += 1
            self.stats['successful'] += 1
            
            self.completed_tasks.append({
                'task_id': task_id,
                'symbol': symbol,
                'duration': elapsed,
                'timestamp': datetime.now()
            })
            
            return result
            
        except asyncio.TimeoutError:
            self.stats['total_processed'] += 1
            self.stats['failed'] += 1
            raise
    
    async def _wait_for_slot(self):
        """Wait for a task slot to become available"""
        while len(self.active_tasks) >= self.max_concurrent_tasks:
            await asyncio.sleep(0.1)
    
    async def process_signals_parallel(self, signals: List[Dict[str, Any]],
                                       signal_processor_func) -> List[Dict[str, Any]]:
        """Process multiple signals in parallel"""
        tasks = []
        
        for signal in signals:
            coro = signal_processor_func(signal)
            tasks.append((signal['symbol'], 'process_signal', coro))
        
        results = await self.submit_batch(tasks)
        return [r for r in results if r is not None]
    
    async def monitor_trades_parallel(self, active_trades: Dict[str, Any],
                                     trade_monitor_func) -> List[Dict[str, Any]]:
        """Monitor multiple trades in parallel"""
        tasks = []
        
        for symbol, trade_info in active_trades.items():
            coro = trade_monitor_func(symbol, trade_info)
            tasks.append((symbol, 'monitor_trade', coro))
        
        results = await self.submit_batch(tasks)
        return [r for r in results if r is not None]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get processor statistics"""
        return {
            **self.stats,
            'active_tasks': len(self.active_tasks),
            'completed_count': len(self.completed_tasks),
            'failed_count': len(self.failed_tasks),
            'executor_stats': f"{self.executor._max_workers} workers"
        }
    
    async def shutdown(self):
        """Shutdown processor and cleanup"""
        logger.info("Shutting down parallel processor...")
        
        # Cancel all pending tasks
        for task in self.active_tasks.values():
            if not task.done():
                task.cancel()
        
        # Wait for cancellation
        if self.active_tasks:
            await asyncio.gather(*self.active_tasks.values(), return_exceptions=True)
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        logger.info("Parallel processor shutdown complete")

class BatchProcessor:
    """Process items in optimized batches"""
    
    def __init__(self, batch_size: int = 5, batch_timeout: float = 2.0):
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.pending_items: List[Any] = []
        self.last_flush = time.time()
    
    def should_flush(self) -> bool:
        """Check if batch should be flushed"""
        return (
            len(self.pending_items) >= self.batch_size or
            (time.time() - self.last_flush) >= self.batch_timeout
        )
    
    def add_item(self, item: Any) -> Optional[List[Any]]:
        """Add item to batch, return batch if ready to process"""
        self.pending_items.append(item)
        
        if self.should_flush():
            batch = self.pending_items
            self.pending_items = []
            self.last_flush = time.time()
            return batch
        
        return None
    
    def flush(self) -> List[Any]:
        """Force flush remaining items"""
        batch = self.pending_items
        self.pending_items = []
        self.last_flush = time.time()
        return batch

class RateLimiter:
    """Rate limit parallel operations"""
    
    def __init__(self, max_operations_per_second: float = 10.0):
        self.max_ops = max_operations_per_second
        self.operation_times: List[float] = []
        self.semaphore = asyncio.Semaphore(int(max_operations_per_second))
    
    async def acquire(self):
        """Acquire operation slot"""
        now = time.time()
        
        # Remove old operation times
        self.operation_times = [t for t in self.operation_times if now - t < 1.0]
        
        # Wait if at limit
        while len(self.operation_times) >= self.max_ops:
            await asyncio.sleep(0.01)
            now = time.time()
            self.operation_times = [t for t in self.operation_times if now - t < 1.0]
        
        self.operation_times.append(now)
    
    async def execute(self, coro: Coroutine) -> Any:
        """Execute coroutine with rate limiting"""
        await self.acquire()
        return await coro
