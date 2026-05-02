#!/usr/bin/env python3
"""
Parallel Market Data Fetcher
High-performance concurrent market data fetching from multiple sources and timeframes
Optimized for maximum throughput with intelligent rate limiting and error handling
"""

import asyncio
import aiohttp
import logging
import time
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict, deque
import json
import traceback
import hashlib
import pickle
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import numpy as np

from parallel_processing_core import get_parallel_core, ParallelTask

@dataclass
class MarketDataRequest:
    """Market data request specification"""
    symbol: str
    timeframe: str
    limit: int = 500
    since: Optional[int] = None
    priority: int = 5
    timeout: float = 10.0
    retry_count: int = 3
    cache_ttl: int = 30  # Cache TTL in seconds

@dataclass
class CachedData:
    """Cached market data with metadata"""
    data: Any
    timestamp: datetime
    ttl: int
    access_count: int = 0
    last_access: datetime = field(default_factory=datetime.now)

class ParallelMarketDataFetcher:
    """High-performance parallel market data fetcher"""
    
    def __init__(self, binance_trader=None, max_concurrent_requests: int = 50):
        self.logger = logging.getLogger(__name__)
        self.binance_trader = binance_trader
        self.parallel_core = get_parallel_core()
        
        # Connection management
        self.max_concurrent_requests = max_concurrent_requests
        self.request_semaphore = asyncio.Semaphore(max_concurrent_requests)
        self.connector_limit = 100
        self.connector_limit_per_host = 20
        
        # Rate limiting (Binance limits: 1200 requests per minute)
        self.rate_limiter = asyncio.Semaphore(20)  # 20 concurrent requests
        self.request_timestamps = deque(maxlen=1200)  # Track last 1200 requests
        self.rate_limit_window = 60  # 60 seconds
        
        # Intelligent caching system
        self.cache = {}
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0
        }
        self.max_cache_size = 1000
        
        # Request batching
        self.batch_requests = defaultdict(list)
        self.batch_timeout = 0.1  # 100ms batch window
        self.max_batch_size = 20
        
        # Performance metrics
        self.request_times = deque(maxlen=1000)
        self.error_counts = defaultdict(int)
        self.success_rate = 100.0
        
        # Connection pooling
        self.session = None
        self._session_lock = asyncio.Lock()
        
        self.logger.info(f"🚀 Parallel Market Data Fetcher initialized with {max_concurrent_requests} max concurrent requests")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self._initialize_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self._cleanup_session()
    
    async def _initialize_session(self):
        """Initialize HTTP session with optimized settings"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            connector = aiohttp.TCPConnector(
                limit=self.connector_limit,
                limit_per_host=self.connector_limit_per_host,
                ttl_dns_cache=300,
                use_dns_cache=True,
                enable_cleanup_closed=True
            )
            
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={'User-Agent': 'SignalMaestro-Bot/1.0'}
            )
            
            self.logger.debug("HTTP session initialized with optimized settings")
    
    async def _cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    async def fetch_multiple_parallel(self, requests: List[MarketDataRequest]) -> Dict[Tuple[str, str], pd.DataFrame]:
        """Fetch multiple market data requests in parallel with intelligent optimization"""
        try:
            start_time = time.time()
            
            if not requests:
                return {}
            
            # Group requests by priority for optimal scheduling
            priority_groups = defaultdict(list)
            for req in requests:
                priority_groups[req.priority].append(req)
            
            # Process high priority requests first
            all_results = {}
            
            for priority in sorted(priority_groups.keys(), reverse=True):
                group_requests = priority_groups[priority]
                
                # Check cache first for this group
                cached_results, uncached_requests = await self._check_cache_batch(group_requests)
                all_results.update(cached_results)
                
                if uncached_requests:
                    # Fetch uncached data in parallel
                    fetch_results = await self._fetch_batch_parallel(uncached_requests)
                    all_results.update(fetch_results)
                    
                    # Update cache
                    await self._update_cache_batch(fetch_results, uncached_requests)
            
            processing_time = time.time() - start_time
            cache_hit_rate = (self.cache_stats['hits'] / max(1, self.cache_stats['hits'] + self.cache_stats['misses'])) * 100
            
            self.logger.info(
                f"📊 Parallel fetch completed: {len(all_results)}/{len(requests)} successful "
                f"in {processing_time:.2f}s (Cache hit rate: {cache_hit_rate:.1f}%)"
            )
            
            return all_results
            
        except Exception as e:
            self.logger.error(f"❌ Parallel market data fetch failed: {e}")
            self.logger.debug(traceback.format_exc())
            return {}
    
    async def fetch_symbol_all_timeframes(self, symbol: str, timeframes: List[str], 
                                        limit: int = 500) -> Dict[str, pd.DataFrame]:
        """Fetch all timeframes for a symbol in parallel"""
        try:
            requests = [
                MarketDataRequest(symbol=symbol, timeframe=tf, limit=limit, priority=8)
                for tf in timeframes
            ]
            
            results = await self.fetch_multiple_parallel(requests)
            
            # Convert to timeframe-keyed dictionary
            timeframe_data = {}
            for (sym, tf), data in results.items():
                if sym == symbol:
                    timeframe_data[tf] = data
            
            return timeframe_data
            
        except Exception as e:
            self.logger.error(f"❌ Failed to fetch all timeframes for {symbol}: {e}")
            return {}
    
    async def fetch_multiple_symbols_timeframe(self, symbols: List[str], timeframe: str,
                                             limit: int = 500) -> Dict[str, pd.DataFrame]:
        """Fetch multiple symbols for same timeframe in parallel"""
        try:
            requests = [
                MarketDataRequest(symbol=symbol, timeframe=timeframe, limit=limit, priority=7)
                for symbol in symbols
            ]
            
            results = await self.fetch_multiple_parallel(requests)
            
            # Convert to symbol-keyed dictionary
            symbol_data = {}
            for (sym, tf), data in results.items():
                if tf == timeframe:
                    symbol_data[sym] = data
            
            return symbol_data
            
        except Exception as e:
            self.logger.error(f"❌ Failed to fetch multiple symbols for {timeframe}: {e}")
            return {}
    
    async def _check_cache_batch(self, requests: List[MarketDataRequest]) -> Tuple[Dict, List]:
        """Check cache for batch of requests"""
        cached_results = {}
        uncached_requests = []
        
        for req in requests:
            cache_key = self._generate_cache_key(req)
            
            if cache_key in self.cache:
                cached_data = self.cache[cache_key]
                
                # Check if cache is still valid
                if self._is_cache_valid(cached_data):
                    cached_results[(req.symbol, req.timeframe)] = cached_data.data
                    cached_data.access_count += 1
                    cached_data.last_access = datetime.now()
                    self.cache_stats['hits'] += 1
                    continue
                else:
                    # Remove expired cache entry
                    del self.cache[cache_key]
            
            uncached_requests.append(req)
            self.cache_stats['misses'] += 1
        
        return cached_results, uncached_requests
    
    async def _fetch_batch_parallel(self, requests: List[MarketDataRequest]) -> Dict[Tuple[str, str], pd.DataFrame]:
        """Fetch batch of requests in parallel with rate limiting"""
        try:
            # Create parallel tasks
            tasks = []
            
            for req in requests:
                task = ParallelTask(
                    task_id=f"{req.symbol}_{req.timeframe}",
                    function=self._fetch_single_with_rate_limit,
                    args=(req,),
                    timeout=req.timeout,
                    retry_count=req.retry_count,
                    priority=req.priority
                )
                tasks.append(task)
            
            # Execute in parallel
            results = await self.parallel_core.execute_parallel(tasks)
            
            # Process results
            successful_results = {}
            for task_id, result in results:
                if not isinstance(result, Exception) and result is not None:
                    symbol, timeframe = task_id.split('_', 1)
                    successful_results[(symbol, timeframe)] = result
                else:
                    if isinstance(result, Exception):
                        self.logger.warning(f"Failed to fetch {task_id}: {result}")
                        self.error_counts[type(result).__name__] += 1
            
            # Update success rate
            success_count = len(successful_results)
            total_count = len(requests)
            batch_success_rate = (success_count / total_count) * 100 if total_count > 0 else 0
            
            # Update rolling success rate
            self.success_rate = (self.success_rate * 0.9) + (batch_success_rate * 0.1)
            
            return successful_results
            
        except Exception as e:
            self.logger.error(f"❌ Batch fetch failed: {e}")
            return {}
    
    async def _fetch_single_with_rate_limit(self, request: MarketDataRequest) -> Optional[pd.DataFrame]:
        """Fetch single market data request with rate limiting"""
        try:
            # Rate limiting
            await self._wait_for_rate_limit()
            
            async with self.request_semaphore:
                start_time = time.time()
                
                # Record request timestamp
                self.request_timestamps.append(time.time())
                
                # Fetch data using binance trader or direct API
                if self.binance_trader:
                    data = await self._fetch_via_binance_trader(request)
                else:
                    data = await self._fetch_via_direct_api(request)
                
                request_time = time.time() - start_time
                self.request_times.append(request_time)
                
                return data
                
        except Exception as e:
            self.logger.warning(f"Failed to fetch {request.symbol} {request.timeframe}: {e}")
            raise
    
    async def _wait_for_rate_limit(self):
        """Intelligent rate limiting"""
        current_time = time.time()
        
        # Remove old timestamps outside the window
        while (self.request_timestamps and 
               current_time - self.request_timestamps[0] > self.rate_limit_window):
            self.request_timestamps.popleft()
        
        # Check if we need to wait
        if len(self.request_timestamps) >= 1000:  # Conservative limit
            oldest_request = self.request_timestamps[0]
            wait_time = self.rate_limit_window - (current_time - oldest_request)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
        
        # Adaptive delay based on recent performance
        if len(self.request_times) > 10:
            avg_request_time = sum(list(self.request_times)[-10:]) / 10
            if avg_request_time > 2.0:  # If requests are slow, add small delay
                await asyncio.sleep(0.1)
    
    async def _fetch_via_binance_trader(self, request: MarketDataRequest) -> Optional[pd.DataFrame]:
        """Fetch data via binance trader"""
        try:
            if not self.binance_trader:
                return None
            
            # Use binance trader's method
            data = await self.binance_trader.get_historical_data(
                request.symbol, 
                request.timeframe, 
                request.limit
            )
            
            if data and len(data) > 0:
                # Convert to DataFrame if needed
                if isinstance(data, list):
                    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df.set_index('timestamp', inplace=True)
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    return df
                elif isinstance(data, pd.DataFrame):
                    return data
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Binance trader fetch error for {request.symbol}: {e}")
            raise
    
    async def _fetch_via_direct_api(self, request: MarketDataRequest) -> Optional[pd.DataFrame]:
        """Fetch data via direct Binance API"""
        try:
            if not self.session:
                await self._initialize_session()
            
            # Binance API endpoint
            url = "https://api.binance.com/api/v3/klines"
            params = {
                'symbol': request.symbol,
                'interval': self._convert_timeframe(request.timeframe),
                'limit': request.limit
            }
            
            if request.since:
                params['startTime'] = request.since
            
            async with self.rate_limiter:
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data:
                            # Convert to DataFrame
                            df = pd.DataFrame(data, columns=[
                                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                                'close_time', 'quote_asset_volume', 'number_of_trades',
                                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                            ])
                            
                            # Keep only OHLCV columns
                            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
                            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                            df.set_index('timestamp', inplace=True)
                            
                            for col in ['open', 'high', 'low', 'close', 'volume']:
                                df[col] = pd.to_numeric(df[col], errors='coerce')
                            
                            return df
                    else:
                        self.logger.warning(f"API request failed with status {response.status}")
                        return None
            
        except Exception as e:
            self.logger.debug(f"Direct API fetch error for {request.symbol}: {e}")
            raise
    
    def _convert_timeframe(self, timeframe: str) -> str:
        """Convert timeframe to Binance format"""
        mapping = {
            '1m': '1m', '3m': '3m', '5m': '5m', '15m': '15m', '30m': '30m',
            '1h': '1h', '2h': '2h', '4h': '4h', '6h': '6h', '8h': '8h', '12h': '12h',
            '1d': '1d', '3d': '3d', '1w': '1w', '1M': '1M'
        }
        return mapping.get(timeframe, timeframe)
    
    def _generate_cache_key(self, request: MarketDataRequest) -> str:
        """Generate cache key for request"""
        key_data = f"{request.symbol}_{request.timeframe}_{request.limit}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _is_cache_valid(self, cached_data: CachedData) -> bool:
        """Check if cached data is still valid"""
        age = (datetime.now() - cached_data.timestamp).total_seconds()
        return age < cached_data.ttl
    
    async def _update_cache_batch(self, results: Dict[Tuple[str, str], pd.DataFrame], 
                                requests: List[MarketDataRequest]):
        """Update cache with batch results"""
        for req in requests:
            key = (req.symbol, req.timeframe)
            if key in results:
                cache_key = self._generate_cache_key(req)
                
                # Cache management - evict old entries if cache is full
                if len(self.cache) >= self.max_cache_size:
                    await self._evict_cache_entries()
                
                self.cache[cache_key] = CachedData(
                    data=results[key],
                    timestamp=datetime.now(),
                    ttl=req.cache_ttl
                )
    
    async def _evict_cache_entries(self):
        """Evict least recently used cache entries"""
        if not self.cache:
            return
        
        # Sort by last access time and remove oldest 20%
        sorted_entries = sorted(
            self.cache.items(),
            key=lambda x: x[1].last_access
        )
        
        evict_count = max(1, len(sorted_entries) // 5)  # Remove 20%
        
        for i in range(evict_count):
            cache_key, _ = sorted_entries[i]
            del self.cache[cache_key]
            self.cache_stats['evictions'] += 1
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        avg_request_time = sum(self.request_times) / len(self.request_times) if self.request_times else 0
        cache_hit_rate = (self.cache_stats['hits'] / max(1, self.cache_stats['hits'] + self.cache_stats['misses'])) * 100
        
        return {
            'performance': {
                'average_request_time': avg_request_time,
                'success_rate': self.success_rate,
                'total_requests': len(self.request_times),
                'cache_hit_rate': cache_hit_rate,
                'requests_per_minute': len([t for t in self.request_timestamps if time.time() - t < 60])
            },
            'cache': {
                'size': len(self.cache),
                'max_size': self.max_cache_size,
                'hits': self.cache_stats['hits'],
                'misses': self.cache_stats['misses'],
                'evictions': self.cache_stats['evictions']
            },
            'errors': dict(self.error_counts),
            'rate_limiting': {
                'current_requests_in_window': len(self.request_timestamps),
                'rate_limit_window': self.rate_limit_window,
                'max_concurrent': self.max_concurrent_requests
            }
        }
    
    async def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        self.cache_stats = {'hits': 0, 'misses': 0, 'evictions': 0}
        self.logger.info("📊 Market data cache cleared")

# Global instance
_market_data_fetcher = None

def get_market_data_fetcher(binance_trader=None, max_concurrent_requests: int = 50) -> ParallelMarketDataFetcher:
    """Get global market data fetcher instance"""
    global _market_data_fetcher
    if _market_data_fetcher is None:
        _market_data_fetcher = ParallelMarketDataFetcher(binance_trader, max_concurrent_requests)
    return _market_data_fetcher