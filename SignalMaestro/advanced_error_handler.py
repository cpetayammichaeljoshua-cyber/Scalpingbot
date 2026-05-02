#!/usr/bin/env python3
"""
Advanced Error Handling System for Trading Bot
Provides comprehensive error handling with retry mechanisms, circuit breakers, and graceful degradation
"""

import asyncio
import logging
import time
import traceback
from typing import Dict, Any, Optional, Callable, Union, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
from functools import wraps
import aiohttp


class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for better classification"""
    NETWORK = "network"
    API = "api"
    TRADING = "trading"
    DATABASE = "database"
    AUTHENTICATION = "authentication"
    VALIDATION = "validation"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    MARKET_CLOSED = "market_closed"
    UNKNOWN = "unknown"


@dataclass
class ErrorDetails:
    """Detailed error information"""
    error_id: str
    timestamp: datetime
    error_type: str
    error_message: str
    category: ErrorCategory
    severity: ErrorSeverity
    source_function: str
    retry_count: int = 0
    context: Dict[str, Any] = field(default_factory=dict)
    stack_trace: Optional[str] = None
    recovery_attempted: bool = False
    recovery_successful: bool = False


@dataclass
class CircuitBreakerState:
    """Circuit breaker state management"""
    is_open: bool = False
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    success_count: int = 0
    total_requests: int = 0
    next_attempt_time: Optional[datetime] = None


class TradingBotException(Exception):
    """Base exception for trading bot errors"""
    def __init__(self, message: str, category: ErrorCategory = ErrorCategory.UNKNOWN, 
                 severity: ErrorSeverity = ErrorSeverity.MEDIUM, context: Dict[str, Any] = None):
        super().__init__(message)
        self.category = category
        self.severity = severity
        self.context = context or {}
        self.timestamp = datetime.now()


class NetworkException(TradingBotException):
    """Network-related errors"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, ErrorCategory.NETWORK, ErrorSeverity.MEDIUM, **kwargs)


class APIException(TradingBotException):
    """API-related errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, **kwargs):
        super().__init__(message, ErrorCategory.API, ErrorSeverity.HIGH, **kwargs)
        self.status_code = status_code


class TradingException(TradingBotException):
    """Trading operation errors"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, ErrorCategory.TRADING, ErrorSeverity.HIGH, **kwargs)


class InsufficientFundsException(TradingBotException):
    """Insufficient funds error"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, ErrorCategory.INSUFFICIENT_FUNDS, ErrorSeverity.HIGH, **kwargs)


class RateLimitException(TradingBotException):
    """Rate limit exceeded error"""
    def __init__(self, message: str, retry_after: Optional[int] = None, **kwargs):
        super().__init__(message, ErrorCategory.RATE_LIMIT, ErrorSeverity.MEDIUM, **kwargs)
        self.retry_after = retry_after


class AuthenticationException(TradingBotException):
    """Authentication/authorization errors"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, ErrorCategory.AUTHENTICATION, ErrorSeverity.CRITICAL, **kwargs)


class ValidationException(TradingBotException):
    """Data validation errors"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, ErrorCategory.VALIDATION, ErrorSeverity.MEDIUM, **kwargs)


class DatabaseException(TradingBotException):
    """Database operation errors"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, ErrorCategory.DATABASE, ErrorSeverity.HIGH, **kwargs)


class TimeoutException(TradingBotException):
    """Timeout errors"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, ErrorCategory.TIMEOUT, ErrorSeverity.MEDIUM, **kwargs)


class RetryConfig:
    """Configuration for retry mechanisms"""
    def __init__(self, 
                 max_retries: int = 3,
                 base_delay: float = 1.0,
                 max_delay: float = 60.0,
                 exponential_base: float = 2.0,
                 jitter: bool = True):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter


class CircuitBreaker:
    """Circuit breaker implementation for external service calls"""
    
    def __init__(self, 
                 failure_threshold: int = 5,
                 recovery_timeout: int = 60,
                 expected_exception: type = Exception):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.state = CircuitBreakerState()
        
    def call(self, func: Callable, *args, **kwargs):
        """Execute function through circuit breaker"""
        if self.state.is_open:
            if self._should_attempt_reset():
                return self._attempt_reset(func, *args, **kwargs)
            else:
                raise TradingBotException(
                    f"Circuit breaker is open. Next attempt at {self.state.next_attempt_time}",
                    ErrorCategory.API,
                    ErrorSeverity.HIGH
                )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
            
    async def async_call(self, func: Callable, *args, **kwargs):
        """Execute async function through circuit breaker"""
        if self.state.is_open:
            if self._should_attempt_reset():
                return await self._async_attempt_reset(func, *args, **kwargs)
            else:
                raise TradingBotException(
                    f"Circuit breaker is open. Next attempt at {self.state.next_attempt_time}",
                    ErrorCategory.API,
                    ErrorSeverity.HIGH
                )
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt reset"""
        return (self.state.next_attempt_time and 
                datetime.now() >= self.state.next_attempt_time)
    
    def _attempt_reset(self, func: Callable, *args, **kwargs):
        """Attempt to reset circuit breaker"""
        try:
            result = func(*args, **kwargs)
            self._on_success()
            self.state.is_open = False
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    async def _async_attempt_reset(self, func: Callable, *args, **kwargs):
        """Attempt to reset circuit breaker (async)"""
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            self.state.is_open = False
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        """Handle successful call"""
        self.state.failure_count = 0
        self.state.success_count += 1
        self.state.total_requests += 1
    
    def _on_failure(self):
        """Handle failed call"""
        self.state.failure_count += 1
        self.state.total_requests += 1
        self.state.last_failure_time = datetime.now()
        
        if self.state.failure_count >= self.failure_threshold:
            self.state.is_open = True
            self.state.next_attempt_time = datetime.now() + timedelta(seconds=self.recovery_timeout)


class AdvancedErrorHandler:
    """Advanced error handling system with comprehensive features"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.error_history: List[ErrorDetails] = []
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.error_counts: Dict[str, int] = {}
        self.last_notification_time: Dict[str, datetime] = {}
        self.notification_cooldown = 300  # 5 minutes
        
        # Create default circuit breakers
        self.create_circuit_breaker("binance_api", failure_threshold=3, recovery_timeout=60)
        self.create_circuit_breaker("telegram_api", failure_threshold=5, recovery_timeout=30)
        self.create_circuit_breaker("cornix_api", failure_threshold=3, recovery_timeout=60)
        self.create_circuit_breaker("database", failure_threshold=2, recovery_timeout=30)
        
    def create_circuit_breaker(self, name: str, failure_threshold: int = 5, 
                             recovery_timeout: int = 60, expected_exception: type = Exception):
        """Create a named circuit breaker"""
        self.circuit_breakers[name] = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            expected_exception=expected_exception
        )
    
    def get_circuit_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name"""
        return self.circuit_breakers.get(name)
    
    async def execute_with_retry(self, 
                                func: Callable,
                                retry_config: RetryConfig = None,
                                circuit_breaker_name: Optional[str] = None,
                                context: Dict[str, Any] = None,
                                *args, **kwargs) -> Any:
        """Execute function with retry logic and optional circuit breaker"""
        retry_config = retry_config or RetryConfig()
        context = context or {}
        
        circuit_breaker = None
        if circuit_breaker_name:
            circuit_breaker = self.get_circuit_breaker(circuit_breaker_name)
        
        last_exception = None
        
        for attempt in range(retry_config.max_retries + 1):
            try:
                if circuit_breaker:
                    if asyncio.iscoroutinefunction(func):
                        return await circuit_breaker.async_call(func, *args, **kwargs)
                    else:
                        return circuit_breaker.call(func, *args, **kwargs)
                else:
                    if asyncio.iscoroutinefunction(func):
                        return await func(*args, **kwargs)
                    else:
                        return func(*args, **kwargs)
                        
            except Exception as e:
                last_exception = e
                error_details = self._create_error_details(e, func.__name__, attempt, context)
                self.error_history.append(error_details)
                
                # Check if we should retry
                if attempt >= retry_config.max_retries:
                    break
                
                # Calculate delay
                delay = self._calculate_retry_delay(attempt, retry_config, e)
                
                self.logger.warning(
                    f"Attempt {attempt + 1}/{retry_config.max_retries + 1} failed for {func.__name__}: {e}. "
                    f"Retrying in {delay:.2f} seconds..."
                )
                
                await asyncio.sleep(delay)
        
        # All retries exhausted
        final_error = self._create_error_details(last_exception, func.__name__, 
                                               retry_config.max_retries, context)
        final_error.recovery_attempted = True
        final_error.recovery_successful = False
        
        await self._handle_final_failure(final_error)
        raise last_exception
    
    def _create_error_details(self, error: Exception, function_name: str, 
                            retry_count: int, context: Dict[str, Any]) -> ErrorDetails:
        """Create detailed error information"""
        error_id = f"{function_name}_{int(time.time() * 1000)}"
        
        # Determine category and severity
        category, severity = self._classify_error(error)
        
        return ErrorDetails(
            error_id=error_id,
            timestamp=datetime.now(),
            error_type=type(error).__name__,
            error_message=str(error),
            category=category,
            severity=severity,
            source_function=function_name,
            retry_count=retry_count,
            context=context,
            stack_trace=traceback.format_exc()
        )
    
    def _classify_error(self, error: Exception) -> tuple[ErrorCategory, ErrorSeverity]:
        """Classify error by category and severity"""
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # Check for specific bot exceptions first
        if isinstance(error, TradingBotException):
            return error.category, error.severity
        
        # Network/connection errors
        if any(keyword in error_str for keyword in ['network', 'connection', 'dns', 'resolve']):
            return ErrorCategory.NETWORK, ErrorSeverity.MEDIUM
        
        # Timeout errors
        if any(keyword in error_str for keyword in ['timeout', 'timed out']):
            return ErrorCategory.TIMEOUT, ErrorSeverity.MEDIUM
        
        # API errors
        if any(keyword in error_str for keyword in ['api', 'http', 'status', '4', '5']):
            severity = ErrorSeverity.HIGH if any(code in error_str for code in ['500', '502', '503']) else ErrorSeverity.MEDIUM
            return ErrorCategory.API, severity
        
        # Authentication errors
        if any(keyword in error_str for keyword in ['auth', 'unauthorized', 'forbidden', 'invalid key']):
            return ErrorCategory.AUTHENTICATION, ErrorSeverity.CRITICAL
        
        # Rate limit errors
        if any(keyword in error_str for keyword in ['rate limit', 'too many requests', '429']):
            return ErrorCategory.RATE_LIMIT, ErrorSeverity.MEDIUM
        
        # Trading errors
        if any(keyword in error_str for keyword in ['insufficient', 'balance', 'margin', 'position']):
            return ErrorCategory.TRADING, ErrorSeverity.HIGH
        
        # Database errors
        if any(keyword in error_str for keyword in ['database', 'sql', 'sqlite', 'db']):
            return ErrorCategory.DATABASE, ErrorSeverity.HIGH
        
        # Default classification
        return ErrorCategory.UNKNOWN, ErrorSeverity.MEDIUM
    
    def _calculate_retry_delay(self, attempt: int, retry_config: RetryConfig, error: Exception) -> float:
        """Calculate delay for next retry attempt"""
        # Special handling for rate limit errors
        if isinstance(error, RateLimitException) and hasattr(error, 'retry_after'):
            return float(error.retry_after or retry_config.base_delay)
        
        # Exponential backoff
        delay = retry_config.base_delay * (retry_config.exponential_base ** attempt)
        delay = min(delay, retry_config.max_delay)
        
        # Add jitter if enabled
        if retry_config.jitter:
            import random
            delay *= (0.5 + random.random() * 0.5)
        
        return delay
    
    async def _handle_final_failure(self, error_details: ErrorDetails):
        """Handle final failure after all retries exhausted"""
        self.logger.error(
            f"Final failure in {error_details.source_function}: {error_details.error_message}\n"
            f"Error ID: {error_details.error_id}\n"
            f"Category: {error_details.category.value}\n"
            f"Severity: {error_details.severity.value}\n"
            f"Retries: {error_details.retry_count}"
        )
        
        # Update error counts
        error_key = f"{error_details.category.value}_{error_details.source_function}"
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
        
        # Send notification if needed
        await self._send_error_notification(error_details)
    
    async def _send_error_notification(self, error_details: ErrorDetails):
        """Send error notification if conditions are met"""
        # Check notification cooldown
        notification_key = f"{error_details.category.value}_{error_details.severity.value}"
        last_notification = self.last_notification_time.get(notification_key)
        
        if (last_notification and 
            (datetime.now() - last_notification).total_seconds() < self.notification_cooldown):
            return
        
        # Send notification for high severity errors
        if error_details.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            self.last_notification_time[notification_key] = datetime.now()
            # Note: Actual notification sending should be implemented by the bot
            self.logger.critical(
                f"🚨 Critical Error Notification:\n"
                f"Function: {error_details.source_function}\n"
                f"Error: {error_details.error_message}\n"
                f"Category: {error_details.category.value}\n"
                f"Severity: {error_details.severity.value}\n"
                f"Time: {error_details.timestamp}"
            )
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get comprehensive error statistics"""
        if not self.error_history:
            return {"total_errors": 0, "error_rate": 0.0}
        
        recent_errors = [e for e in self.error_history 
                        if (datetime.now() - e.timestamp).total_seconds() < 3600]
        
        category_counts = {}
        severity_counts = {}
        
        for error in recent_errors:
            category_counts[error.category.value] = category_counts.get(error.category.value, 0) + 1
            severity_counts[error.severity.value] = severity_counts.get(error.severity.value, 0) + 1
        
        circuit_breaker_status = {}
        for name, cb in self.circuit_breakers.items():
            circuit_breaker_status[name] = {
                "is_open": cb.state.is_open,
                "failure_count": cb.state.failure_count,
                "success_rate": (cb.state.success_count / max(cb.state.total_requests, 1)) * 100
            }
        
        return {
            "total_errors": len(self.error_history),
            "recent_errors_1h": len(recent_errors),
            "error_rate_1h": len(recent_errors) / 60.0,  # errors per minute
            "category_breakdown": category_counts,
            "severity_breakdown": severity_counts,
            "circuit_breaker_status": circuit_breaker_status,
            "top_error_functions": self._get_top_error_functions()
        }
    
    def _get_top_error_functions(self) -> List[Dict[str, Any]]:
        """Get functions with most errors"""
        function_errors = {}
        for error in self.error_history:
            func = error.source_function
            if func not in function_errors:
                function_errors[func] = {"count": 0, "latest": None}
            function_errors[func]["count"] += 1
            function_errors[func]["latest"] = error.timestamp
        
        return sorted(
            [{"function": func, **data} for func, data in function_errors.items()],
            key=lambda x: x["count"],
            reverse=True
        )[:5]
    
    def reset_error_history(self):
        """Reset error history (for maintenance)"""
        self.error_history.clear()
        self.error_counts.clear()
        self.last_notification_time.clear()
        self.logger.info("Error history reset")


# Decorator for automatic error handling
def handle_errors(retry_config: RetryConfig = None, 
                 circuit_breaker_name: Optional[str] = None,
                 context: Dict[str, Any] = None):
    """Decorator for automatic error handling with retry and circuit breaker"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Get error handler from instance if available
            error_handler = None
            if args and hasattr(args[0], 'error_handler'):
                error_handler = args[0].error_handler
            else:
                error_handler = AdvancedErrorHandler()
            
            return await error_handler.execute_with_retry(
                func, retry_config, circuit_breaker_name, context, *args, **kwargs
            )
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Quick access retry configurations
class RetryConfigs:
    """Predefined retry configurations for different scenarios"""
    
    NETWORK_RETRY = RetryConfig(max_retries=3, base_delay=2.0, max_delay=30.0)
    API_RETRY = RetryConfig(max_retries=2, base_delay=1.0, max_delay=15.0) 
    DATABASE_RETRY = RetryConfig(max_retries=2, base_delay=0.5, max_delay=5.0)
    CRITICAL_RETRY = RetryConfig(max_retries=5, base_delay=1.0, max_delay=60.0)
    QUICK_RETRY = RetryConfig(max_retries=1, base_delay=0.5, max_delay=2.0)