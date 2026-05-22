"""
Logging configuration for the trading bot
Provides structured logging with file rotation and formatting
"""

import logging
import logging.handlers
import sys
import os
from datetime import datetime
from typing import Optional

from config import Config

def setup_logging(log_level: Optional[str] = None, log_file: Optional[str] = None) -> logging.Logger:
    """
    Setup comprehensive logging configuration
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Log file path
        
    Returns:
        Configured logger instance
    """
    config = Config()
    
    # Use config values if not provided
    if log_level is None:
        log_level = config.LOG_LEVEL
    if log_file is None:
        log_file = config.LOG_FILE
    
    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(log_file) if os.path.dirname(log_file) else 'logs'
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # Create custom formatter
    formatter = CustomFormatter()
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Error file handler for errors and above
    error_file = log_file.replace('.log', '_errors.log')
    error_handler = logging.handlers.RotatingFileHandler(
        error_file,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)
    
    # Suppress some noisy third-party loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('ccxt').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    # Get main logger for the application
    logger = logging.getLogger('trading_bot')
    
    # Log initialization
    logger.info("="*50)
    logger.info("Trading Signal Bot - Logging Initialized")
    logger.info(f"Log Level: {log_level}")
    logger.info(f"Log File: {log_file}")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    logger.info("="*50)
    
    return logger

class CustomFormatter(logging.Formatter):
    """Custom formatter for colored and structured logging"""
    
    # Color codes for different log levels
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }
    
    def __init__(self):
        super().__init__()
        
        # Base format
        self.base_format = "[{asctime}] [{levelname:8}] [{name}] {message}"
        
        # Detailed format for errors
        self.error_format = "[{asctime}] [{levelname:8}] [{name}:{lineno}] {funcName}() - {message}"
        
        # Different formatters for different levels
        self.formatters = {
            logging.DEBUG: logging.Formatter(
                self.base_format, 
                style='{', 
                datefmt='%Y-%m-%d %H:%M:%S'
            ),
            logging.INFO: logging.Formatter(
                self.base_format, 
                style='{', 
                datefmt='%Y-%m-%d %H:%M:%S'
            ),
            logging.WARNING: logging.Formatter(
                self.error_format, 
                style='{', 
                datefmt='%Y-%m-%d %H:%M:%S'
            ),
            logging.ERROR: logging.Formatter(
                self.error_format, 
                style='{', 
                datefmt='%Y-%m-%d %H:%M:%S'
            ),
            logging.CRITICAL: logging.Formatter(
                self.error_format, 
                style='{', 
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        }
    
    def format(self, record):
        """Format log record with colors and appropriate format"""
        
        # Get appropriate formatter
        formatter = self.formatters.get(record.levelno, self.formatters[logging.INFO])
        
        # Format the record
        formatted = formatter.format(record)
        
        # Add colors for console output (check if output is a terminal)
        if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
            color = self.COLORS.get(record.levelname, '')
            reset = self.COLORS['RESET']
            formatted = f"{color}{formatted}{reset}"
        
        return formatted

class DatabaseLogHandler(logging.Handler):
    """Custom log handler that writes to database"""
    
    def __init__(self, database):
        super().__init__()
        self.database = database
        
    def emit(self, record):
        """Emit log record to database"""
        try:
            # Format the record
            message = self.format(record)
            
            # Extract module name
            module = record.name
            
            # Get user ID if available (from record context)
            user_id = getattr(record, 'user_id', None)
            
            # Save to database (async call needs to be handled properly)
            import asyncio
            try:
                asyncio.get_running_loop()
                # We're in an async context — schedule as a task
                asyncio.create_task(
                    self.database.save_system_log(
                        record.levelname,
                        message,
                        module,
                        user_id
                    )
                )
            except RuntimeError:
                # No event loop, skip database logging
                pass
                
        except Exception:
            # Don't let logging errors crash the application
            self.handleError(record)

def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name"""
    return logging.getLogger(name)

def log_trade_execution(logger: logging.Logger, trade_data: dict, user_id: int = None):
    """Log trade execution with structured data"""
    try:
        symbol = trade_data.get('symbol', 'UNKNOWN')
        side = trade_data.get('side', 'UNKNOWN')
        amount = trade_data.get('amount', 0)
        price = trade_data.get('price', 0)
        order_id = trade_data.get('order_id', 'UNKNOWN')
        
        message = f"Trade Executed: {side} {amount} {symbol} @ {price} (Order: {order_id})"
        
        # Add user context if provided
        if user_id:
            logger.info(message, extra={'user_id': user_id})
        else:
            logger.info(message)
            
    except Exception as e:
        logger.error(f"Error logging trade execution: {e}")

def log_signal_processing(logger: logging.Logger, signal_data: dict, result: dict, user_id: int = None):
    """Log signal processing with structured data"""
    try:
        symbol = signal_data.get('symbol', 'UNKNOWN')
        action = signal_data.get('action', 'UNKNOWN')
        status = result.get('status', 'UNKNOWN')
        
        message = f"Signal Processed: {action} {symbol} - Status: {status}"
        
        if user_id:
            logger.info(message, extra={'user_id': user_id})
        else:
            logger.info(message)
            
    except Exception as e:
        logger.error(f"Error logging signal processing: {e}")

def log_error_with_context(logger: logging.Logger, error: Exception, context: dict = None, user_id: int = None):
    """Log error with additional context"""
    try:
        error_message = f"Error: {type(error).__name__}: {str(error)}"
        
        if context:
            context_str = ", ".join([f"{k}={v}" for k, v in context.items()])
            error_message += f" | Context: {context_str}"
        
        extra = {}
        if user_id:
            extra['user_id'] = user_id
            
        logger.error(error_message, extra=extra, exc_info=True)
        
    except Exception as e:
        logger.error(f"Error logging error with context: {e}")

def log_performance_metric(logger: logging.Logger, metric_name: str, value: float, unit: str = "", user_id: int = None):
    """Log performance metrics"""
    try:
        message = f"Performance Metric: {metric_name} = {value} {unit}".strip()
        
        if user_id:
            logger.info(message, extra={'user_id': user_id})
        else:
            logger.info(message)
            
    except Exception as e:
        logger.error(f"Error logging performance metric: {e}")

def setup_database_logging(database):
    """Setup database logging handler"""
    try:
        # Create database log handler
        db_handler = DatabaseLogHandler(database)
        db_handler.setLevel(logging.INFO)
        
        # Add to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(db_handler)
        
        logger = logging.getLogger('trading_bot')
        logger.info("Database logging enabled")
        
    except Exception as e:
        logger = logging.getLogger('trading_bot')
        logger.error(f"Failed to setup database logging: {e}")

# Context manager for logging with user context
class LogContext:
    """Context manager for adding user context to logs"""
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.old_factory = logging.getLogRecordFactory()
        
    def __enter__(self):
        def record_factory(*args, **kwargs):
            record = self.old_factory(*args, **kwargs)
            record.user_id = self.user_id
            return record
            
        logging.setLogRecordFactory(record_factory)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.setLogRecordFactory(self.old_factory)

def with_user_context(user_id: int):
    """Decorator for logging with user context"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with LogContext(user_id):
                return func(*args, **kwargs)
        return wrapper
    return decorator
