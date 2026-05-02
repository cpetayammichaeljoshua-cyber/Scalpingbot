#!/usr/bin/env python3
"""
API Resilience Layer
Provides comprehensive resilience for all external API calls with retry mechanisms,
circuit breakers, and graceful degradation
"""

import asyncio
import aiohttp
import logging
import time
import json
from typing import Dict, Any, Optional, Callable, Union, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from functools import wraps
import traceback

from advanced_error_handler import (
    AdvancedErrorHandler, RetryConfig, CircuitBreaker,
    NetworkException, APIException, RateLimitException, TimeoutException,
    handle_errors, RetryConfigs
)


@dataclass
class APICall:
    """Represents an API call with metadata"""
    service_name: str
    endpoint: str
    method: str
    payload: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None
    timeout: float = 30.0
    retry_config: Optional[RetryConfig] = None


class APIMetrics:
    """Track API performance metrics"""
    
    def __init__(self):
        self.call_counts: Dict[str, int] = {}
        self.success_counts: Dict[str, int] = {}
        self.failure_counts: Dict[str, int] = {}
        self.response_times: Dict[str, List[float]] = {}
        self.last_reset = datetime.now()
    
    def record_call(self, service: str, success: bool, response_time: float):
        """Record API call metrics"""
        self.call_counts[service] = self.call_counts.get(service, 0) + 1
        
        if success:
            self.success_counts[service] = self.success_counts.get(service, 0) + 1
        else:
            self.failure_counts[service] = self.failure_counts.get(service, 0) + 1
        
        if service not in self.response_times:
            self.response_times[service] = []
        self.response_times[service].append(response_time)
        
        # Keep only last 100 response times per service
        if len(self.response_times[service]) > 100:
            self.response_times[service] = self.response_times[service][-100:]
    
    def get_service_metrics(self, service: str) -> Dict[str, Any]:
        """Get metrics for a specific service"""
        total_calls = self.call_counts.get(service, 0)
        if total_calls == 0:
            return {"success_rate": 0.0, "avg_response_time": 0.0, "total_calls": 0}
        
        success_rate = (self.success_counts.get(service, 0) / total_calls) * 100
        
        response_times = self.response_times.get(service, [])
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0.0
        
        return {
            "success_rate": success_rate,
            "avg_response_time": avg_response_time,
            "total_calls": total_calls,
            "failures": self.failure_counts.get(service, 0)
        }
    
    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get metrics for all services"""
        return {
            service: self.get_service_metrics(service)
            for service in self.call_counts.keys()
        }
    
    def reset_metrics(self):
        """Reset all metrics"""
        self.call_counts.clear()
        self.success_counts.clear()
        self.failure_counts.clear()
        self.response_times.clear()
        self.last_reset = datetime.now()


class GracefulDegradation:
    """Handles graceful degradation when services are unavailable"""
    
    def __init__(self):
        self.degraded_services: Dict[str, datetime] = {}
        self.fallback_responses: Dict[str, Any] = {}
        self.degradation_callbacks: Dict[str, Callable] = {}
    
    def mark_service_degraded(self, service: str, duration_minutes: int = 30):
        """Mark a service as degraded"""
        self.degraded_services[service] = datetime.now() + timedelta(minutes=duration_minutes)
    
    def is_service_degraded(self, service: str) -> bool:
        """Check if a service is currently degraded"""
        if service not in self.degraded_services:
            return False
        
        if datetime.now() > self.degraded_services[service]:
            del self.degraded_services[service]
            return False
        
        return True
    
    def set_fallback_response(self, service: str, endpoint: str, response: Any):
        """Set fallback response for service endpoint"""
        key = f"{service}_{endpoint}"
        self.fallback_responses[key] = response
    
    def get_fallback_response(self, service: str, endpoint: str) -> Optional[Any]:
        """Get fallback response if available"""
        key = f"{service}_{endpoint}"
        return self.fallback_responses.get(key)
    
    def register_degradation_callback(self, service: str, callback: Callable):
        """Register callback to execute when service is degraded"""
        self.degradation_callbacks[service] = callback
    
    async def handle_degradation(self, service: str, api_call: APICall) -> Optional[Any]:
        """Handle degraded service call"""
        # Try fallback response first
        fallback = self.get_fallback_response(service, api_call.endpoint)
        if fallback is not None:
            return fallback
        
        # Execute degradation callback if available
        if service in self.degradation_callbacks:
            try:
                return await self.degradation_callbacks[service](api_call)
            except Exception:
                pass
        
        # Return service-specific defaults
        return self._get_service_default(service, api_call)
    
    def _get_service_default(self, service: str, api_call: APICall) -> Any:
        """Get default response for degraded service"""
        defaults = {
            "binance": {"status": "degraded", "data": None, "price": 0.0},
            "telegram": {"ok": False, "description": "Service temporarily unavailable"},
            "cornix": {"success": False, "message": "Cornix service unavailable"}
        }
        
        return defaults.get(service.lower(), {"status": "unavailable"})


class RateLimitManager:
    """Manages rate limiting for different services"""
    
    def __init__(self):
        self.rate_limits: Dict[str, Dict[str, Any]] = {
            "binance": {
                "requests_per_minute": 1200,
                "requests_per_second": 10,
                "weight_per_minute": 6000
            },
            "telegram": {
                "requests_per_minute": 30,
                "requests_per_second": 1
            },
            "cornix": {
                "requests_per_minute": 60,
                "requests_per_second": 2
            }
        }
        
        self.request_history: Dict[str, List[float]] = {}
        self.current_weights: Dict[str, int] = {}
    
    async def wait_if_rate_limited(self, service: str, weight: int = 1) -> bool:
        """Wait if rate limited, return True if waited"""
        service_lower = service.lower()
        limits = self.rate_limits.get(service_lower, {})
        
        if not limits:
            return False
        
        now = time.time()
        
        # Initialize request history if needed
        if service not in self.request_history:
            self.request_history[service] = []
        
        # Clean old requests (older than 60 seconds)
        cutoff_time = now - 60
        self.request_history[service] = [
            req_time for req_time in self.request_history[service]
            if req_time > cutoff_time
        ]
        
        # Check requests per minute
        requests_per_minute = limits.get("requests_per_minute", 9999)
        if len(self.request_history[service]) >= requests_per_minute:
            # Wait until we can make another request
            oldest_request = min(self.request_history[service])
            wait_time = 60 - (now - oldest_request) + 0.1  # Add small buffer
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                return True
        
        # Check requests per second
        requests_per_second = limits.get("requests_per_second", 999)
        recent_requests = [
            req_time for req_time in self.request_history[service]
            if req_time > (now - 1)
        ]
        
        if len(recent_requests) >= requests_per_second:
            await asyncio.sleep(1.1)  # Wait just over a second
            return True
        
        # Record this request
        self.request_history[service].append(now)
        return False
    
    def get_rate_limit_status(self, service: str) -> Dict[str, Any]:
        """Get current rate limit status"""
        service_lower = service.lower()
        limits = self.rate_limits.get(service_lower, {})
        
        if service not in self.request_history:
            return {"status": "ok", "requests_remaining": limits.get("requests_per_minute", 999)}
        
        now = time.time()
        recent_requests = [
            req_time for req_time in self.request_history[service]
            if req_time > (now - 60)
        ]
        
        requests_per_minute = limits.get("requests_per_minute", 9999)
        remaining = max(0, requests_per_minute - len(recent_requests))
        
        return {
            "status": "limited" if remaining == 0 else "ok",
            "requests_remaining": remaining,
            "requests_used": len(recent_requests)
        }


class TelegramAPIWrapper:
    """Resilient wrapper for Telegram API calls"""
    
    def __init__(self, bot_token: str, error_handler: AdvancedErrorHandler):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.error_handler = error_handler
        self.logger = logging.getLogger(__name__)
        
    async def send_message(self, chat_id: str, text: str, **kwargs) -> Dict[str, Any]:
        """Send message with resilience"""
        api_call = APICall(
            service_name="telegram",
            endpoint="sendMessage",
            method="POST",
            payload={
                "chat_id": chat_id,
                "text": text,
                **kwargs
            },
            retry_config=RetryConfigs.API_RETRY
        )
        
        return await self._make_resilient_call(api_call)
    
    async def get_updates(self, offset: int = None, timeout: int = 5) -> List[Dict[str, Any]]:
        """Get updates with resilience"""
        api_call = APICall(
            service_name="telegram",
            endpoint="getUpdates",
            method="GET",
            payload={
                "offset": offset,
                "timeout": timeout
            } if offset else {"timeout": timeout},
            timeout=timeout + 5,
            retry_config=RetryConfigs.QUICK_RETRY
        )
        
        result = await self._make_resilient_call(api_call)
        return result.get("result", []) if result.get("ok") else []
    
    async def _make_resilient_call(self, api_call: APICall) -> Dict[str, Any]:
        """Make resilient API call to Telegram"""
        url = f"{self.base_url}/{api_call.endpoint}"
        
        async def make_call():
            async with aiohttp.ClientSession() as session:
                if api_call.method == "GET":
                    async with session.get(url, params=api_call.payload, 
                                         timeout=aiohttp.ClientTimeout(total=api_call.timeout)) as response:
                        if response.status == 429:
                            retry_after = int(response.headers.get('Retry-After', 60))
                            raise RateLimitException(f"Telegram rate limit", retry_after=retry_after)
                        
                        response.raise_for_status()
                        return await response.json()
                else:
                    async with session.post(url, json=api_call.payload,
                                          timeout=aiohttp.ClientTimeout(total=api_call.timeout)) as response:
                        if response.status == 429:
                            retry_after = int(response.headers.get('Retry-After', 60))
                            raise RateLimitException(f"Telegram rate limit", retry_after=retry_after)
                        
                        response.raise_for_status()
                        return await response.json()
        
        return await self.error_handler.execute_with_retry(
            make_call,
            api_call.retry_config,
            "telegram_api",
            {"endpoint": api_call.endpoint, "method": api_call.method}
        )


class BinanceAPIWrapper:
    """Resilient wrapper for Binance API calls"""
    
    def __init__(self, api_key: str, api_secret: str, error_handler: AdvancedErrorHandler,
                 testnet: bool = False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.error_handler = error_handler
        self.logger = logging.getLogger(__name__)
        
        base_url = "https://testnet.binance.vision" if testnet else "https://api.binance.com"
        self.base_url = base_url
    
    async def get_ticker_price(self, symbol: str) -> Dict[str, Any]:
        """Get ticker price with resilience"""
        api_call = APICall(
            service_name="binance",
            endpoint="ticker/price",
            method="GET",
            payload={"symbol": symbol},
            retry_config=RetryConfigs.NETWORK_RETRY
        )
        
        return await self._make_resilient_call(api_call)
    
    async def get_klines(self, symbol: str, interval: str, limit: int = 100) -> List[List]:
        """Get klines with resilience"""
        api_call = APICall(
            service_name="binance",
            endpoint="klines",
            method="GET",
            payload={
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            },
            retry_config=RetryConfigs.NETWORK_RETRY
        )
        
        return await self._make_resilient_call(api_call)
    
    async def _make_resilient_call(self, api_call: APICall) -> Any:
        """Make resilient API call to Binance"""
        url = f"{self.base_url}/api/v3/{api_call.endpoint}"
        
        async def make_call():
            headers = {"X-MBX-APIKEY": self.api_key} if self.api_key else {}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=api_call.payload, headers=headers,
                                     timeout=aiohttp.ClientTimeout(total=api_call.timeout)) as response:
                    if response.status == 429:
                        raise RateLimitException(f"Binance rate limit exceeded")
                    
                    if response.status == 418:
                        raise RateLimitException(f"Binance IP banned", retry_after=300)
                    
                    response.raise_for_status()
                    return await response.json()
        
        return await self.error_handler.execute_with_retry(
            make_call,
            api_call.retry_config,
            "binance_api",
            {"endpoint": api_call.endpoint, "symbol": api_call.payload.get("symbol")}
        )


class CornixAPIWrapper:
    """Resilient wrapper for Cornix API calls"""
    
    def __init__(self, webhook_url: str, error_handler: AdvancedErrorHandler):
        self.webhook_url = webhook_url
        self.error_handler = error_handler
        self.logger = logging.getLogger(__name__)
    
    async def send_signal(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send signal with resilience"""
        api_call = APICall(
            service_name="cornix",
            endpoint="webhook",
            method="POST",
            payload=signal_data,
            retry_config=RetryConfigs.API_RETRY
        )
        
        return await self._make_resilient_call(api_call)
    
    async def _make_resilient_call(self, api_call: APICall) -> Dict[str, Any]:
        """Make resilient API call to Cornix"""
        async def make_call():
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=api_call.payload,
                                      timeout=aiohttp.ClientTimeout(total=api_call.timeout)) as response:
                    response.raise_for_status()
                    
                    # Cornix might return text or JSON
                    content_type = response.headers.get('content-type', '')
                    if 'application/json' in content_type:
                        return await response.json()
                    else:
                        text = await response.text()
                        return {"status": "success", "response": text}
        
        return await self.error_handler.execute_with_retry(
            make_call,
            api_call.retry_config,
            "cornix_api",
            {"endpoint": api_call.endpoint}
        )


class APIResilienceManager:
    """Main manager for API resilience across all services"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.error_handler = AdvancedErrorHandler()
        self.metrics = APIMetrics()
        self.degradation = GracefulDegradation()
        self.rate_limiter = RateLimitManager()
        
        # Initialize API wrappers
        self._init_api_wrappers()
        
        # Setup degradation callbacks
        self._setup_degradation_callbacks()
    
    def _init_api_wrappers(self):
        """Initialize API wrappers"""
        # Telegram wrapper
        if self.config.get("telegram_bot_token"):
            self.telegram = TelegramAPIWrapper(
                self.config["telegram_bot_token"],
                self.error_handler
            )
        else:
            self.telegram = None
        
        # Binance wrapper
        if self.config.get("binance_api_key"):
            self.binance = BinanceAPIWrapper(
                self.config["binance_api_key"],
                self.config.get("binance_api_secret", ""),
                self.error_handler,
                self.config.get("binance_testnet", True)
            )
        else:
            self.binance = None
        
        # Cornix wrapper
        if self.config.get("cornix_webhook_url"):
            self.cornix = CornixAPIWrapper(
                self.config["cornix_webhook_url"],
                self.error_handler
            )
        else:
            self.cornix = None
    
    def _setup_degradation_callbacks(self):
        """Setup degradation callbacks for services"""
        async def binance_degradation_callback(api_call: APICall):
            """Fallback for Binance API failures"""
            if api_call.endpoint == "ticker/price":
                return {"symbol": api_call.payload.get("symbol"), "price": "0.0"}
            elif api_call.endpoint == "klines":
                return []
            return None
        
        async def telegram_degradation_callback(api_call: APICall):
            """Fallback for Telegram API failures"""
            return {"ok": False, "description": "Telegram service degraded"}
        
        self.degradation.register_degradation_callback("binance", binance_degradation_callback)
        self.degradation.register_degradation_callback("telegram", telegram_degradation_callback)
    
    async def make_resilient_api_call(self, service: str, call_func: Callable, 
                                    *args, **kwargs) -> Any:
        """Make a resilient API call with full error handling"""
        start_time = time.time()
        success = False
        result = None
        
        try:
            # Check if service is degraded
            if self.degradation.is_service_degraded(service):
                self.logger.warning(f"Service {service} is degraded, using fallback")
                # Create mock API call for degradation handler
                mock_call = APICall(service, "unknown", "GET")
                return await self.degradation.handle_degradation(service, mock_call)
            
            # Apply rate limiting
            waited = await self.rate_limiter.wait_if_rate_limited(service)
            if waited:
                self.logger.info(f"Rate limited for {service}, waited before proceeding")
            
            # Make the actual call
            result = await call_func(*args, **kwargs)
            success = True
            
            return result
            
        except Exception as e:
            self.logger.error(f"API call failed for {service}: {e}")
            
            # Check if we should mark service as degraded
            if isinstance(e, (APIException, NetworkException)):
                self.degradation.mark_service_degraded(service, duration_minutes=15)
                self.logger.warning(f"Marked {service} as degraded for 15 minutes")
            
            # Try degradation handling
            try:
                mock_call = APICall(service, "unknown", "GET")
                return await self.degradation.handle_degradation(service, mock_call)
            except Exception:
                raise e  # Re-raise original error if degradation also fails
            
        finally:
            # Record metrics
            response_time = time.time() - start_time
            self.metrics.record_call(service, success, response_time)
    
    def get_service_health(self) -> Dict[str, Any]:
        """Get health status of all services"""
        health = {}
        
        for service in ["binance", "telegram", "cornix"]:
            metrics = self.metrics.get_service_metrics(service)
            rate_limit_status = self.rate_limiter.get_rate_limit_status(service)
            is_degraded = self.degradation.is_service_degraded(service)
            
            health[service] = {
                "metrics": metrics,
                "rate_limit": rate_limit_status,
                "degraded": is_degraded,
                "available": metrics["success_rate"] > 50 and not is_degraded
            }
        
        return health
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get comprehensive error statistics"""
        return self.error_handler.get_error_statistics()
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        health_results = {}
        
        # Test Telegram if available
        if self.telegram:
            try:
                result = await self.make_resilient_api_call(
                    "telegram", 
                    self.telegram.get_updates,
                    timeout=2
                )
                health_results["telegram"] = {"status": "healthy", "latency": "low"}
            except Exception as e:
                health_results["telegram"] = {"status": "unhealthy", "error": str(e)}
        
        # Test Binance if available
        if self.binance:
            try:
                result = await self.make_resilient_api_call(
                    "binance",
                    self.binance.get_ticker_price,
                    "BTCUSDT"
                )
                health_results["binance"] = {"status": "healthy", "latency": "low"}
            except Exception as e:
                health_results["binance"] = {"status": "unhealthy", "error": str(e)}
        
        # Overall health
        healthy_services = sum(1 for service in health_results.values() 
                             if service["status"] == "healthy")
        total_services = len(health_results)
        
        overall_health = "healthy" if healthy_services == total_services else "degraded"
        if healthy_services == 0:
            overall_health = "critical"
        
        return {
            "overall": overall_health,
            "services": health_results,
            "healthy_services": healthy_services,
            "total_services": total_services
        }


# Global resilience manager instance
_global_resilience_manager: Optional[APIResilienceManager] = None


def get_global_resilience_manager() -> Optional[APIResilienceManager]:
    """Get global resilience manager"""
    return _global_resilience_manager


def setup_global_resilience_manager(config: Dict[str, Any]) -> APIResilienceManager:
    """Setup global resilience manager"""
    global _global_resilience_manager
    _global_resilience_manager = APIResilienceManager(config)
    return _global_resilience_manager


# Decorator for automatic API resilience
def resilient_api_call(service: str):
    """Decorator to make API calls resilient"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            manager = get_global_resilience_manager()
            if manager:
                return await manager.make_resilient_api_call(service, func, *args, **kwargs)
            else:
                return await func(*args, **kwargs)
        return wrapper
    return decorator