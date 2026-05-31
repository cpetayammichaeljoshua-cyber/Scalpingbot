#!/usr/bin/env python3
"""
Centralized Error Logging System
Provides comprehensive error logging with categorization, notifications, and analytics
"""

import logging
import asyncio
import json
import sqlite3
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path
import aiohttp
from advanced_error_handler import ErrorDetails, ErrorSeverity, ErrorCategory


@dataclass
class ErrorNotificationConfig:
    """Configuration for error notifications"""
    telegram_enabled: bool = True
    admin_chat_id: Optional[str] = None
    severity_threshold: ErrorSeverity = ErrorSeverity.HIGH
    cooldown_minutes: int = 5
    batch_notifications: bool = True
    max_batch_size: int = 5


class ErrorDatabase:
    """Database manager for error logging"""
    
    def __init__(self, db_path: str = "error_logs.db"):
        self.db_path = db_path
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize error logging database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Main error logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS error_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_id TEXT UNIQUE NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                source_function TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                context TEXT,
                stack_trace TEXT,
                recovery_attempted BOOLEAN DEFAULT 0,
                recovery_successful BOOLEAN DEFAULT 0,
                notification_sent BOOLEAN DEFAULT 0,
                resolved BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Error patterns table for analytics
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS error_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_name TEXT NOT NULL,
                pattern_description TEXT,
                error_count INTEGER DEFAULT 0,
                first_occurrence TIMESTAMP,
                last_occurrence TIMESTAMP,
                resolution_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Error metrics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS error_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                hour INTEGER NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                error_count INTEGER DEFAULT 0,
                recovery_rate REAL DEFAULT 0.0,
                avg_retry_count REAL DEFAULT 0.0,
                PRIMARY KEY (date, hour, category, severity)
            ) WITHOUT ROWID
        ''')
        
        conn.commit()
        conn.close()
    
    def log_error(self, error_details: ErrorDetails) -> bool:
        """Log error to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO error_logs (
                    error_id, timestamp, error_type, error_message, category, severity,
                    source_function, retry_count, context, stack_trace, recovery_attempted,
                    recovery_successful
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                error_details.error_id,
                error_details.timestamp,
                error_details.error_type,
                error_details.error_message,
                error_details.category.value,
                error_details.severity.value,
                error_details.source_function,
                error_details.retry_count,
                json.dumps(error_details.context),
                error_details.stack_trace,
                error_details.recovery_attempted,
                error_details.recovery_successful
            ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Failed to log error to database: {e}")
            return False
    
    def get_error_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """Get error statistics for the last N hours"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            # Total error count
            cursor.execute('''
                SELECT COUNT(*) FROM error_logs 
                WHERE timestamp >= ?
            ''', (cutoff_time,))
            total_errors = cursor.fetchone()[0]
            
            # Errors by category
            cursor.execute('''
                SELECT category, COUNT(*) FROM error_logs 
                WHERE timestamp >= ? 
                GROUP BY category
            ''', (cutoff_time,))
            category_breakdown = dict(cursor.fetchall())
            
            # Errors by severity
            cursor.execute('''
                SELECT severity, COUNT(*) FROM error_logs 
                WHERE timestamp >= ? 
                GROUP BY severity
            ''', (cutoff_time,))
            severity_breakdown = dict(cursor.fetchall())
            
            # Recovery rate
            cursor.execute('''
                SELECT 
                    COUNT(CASE WHEN recovery_successful = 1 THEN 1 END) * 1.0 / 
                    COUNT(CASE WHEN recovery_attempted = 1 THEN 1 END) as recovery_rate
                FROM error_logs 
                WHERE timestamp >= ? AND recovery_attempted = 1
            ''', (cutoff_time,))
            recovery_rate = cursor.fetchone()[0] or 0.0
            
            # Top error functions
            cursor.execute('''
                SELECT source_function, COUNT(*) as error_count 
                FROM error_logs 
                WHERE timestamp >= ? 
                GROUP BY source_function 
                ORDER BY error_count DESC 
                LIMIT 5
            ''', (cutoff_time,))
            top_error_functions = [
                {"function": row[0], "count": row[1]} 
                for row in cursor.fetchall()
            ]
            
            conn.close()
            
            return {
                "total_errors": total_errors,
                "error_rate": total_errors / hours,
                "category_breakdown": category_breakdown,
                "severity_breakdown": severity_breakdown,
                "recovery_rate": recovery_rate * 100,
                "top_error_functions": top_error_functions
            }
            
        except Exception as e:
            print(f"Failed to get error statistics: {e}")
            return {}
    
    def get_recent_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent errors"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT error_id, timestamp, error_type, error_message, 
                       category, severity, source_function, retry_count
                FROM error_logs 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [
                {
                    "error_id": row[0],
                    "timestamp": row[1],
                    "error_type": row[2],
                    "error_message": row[3],
                    "category": row[4],
                    "severity": row[5],
                    "source_function": row[6],
                    "retry_count": row[7]
                }
                for row in rows
            ]
            
        except Exception as e:
            print(f"Failed to get recent errors: {e}")
            return []


class CentralizedErrorLogger:
    """Centralized error logging system with notifications and analytics"""
    
    def __init__(self, 
                 notification_config: ErrorNotificationConfig = None,
                 db_path: str = "error_logs.db"):
        self.logger = logging.getLogger(__name__)
        self.notification_config = notification_config or ErrorNotificationConfig()
        self.error_db = ErrorDatabase(db_path)
        
        # Notification state
        self.pending_notifications: List[ErrorDetails] = []
        self.last_notification_time: Dict[str, datetime] = {}
        
        # Error pattern detection
        self.error_patterns: Dict[str, int] = {}
        
        # Setup file logging
        self._setup_file_logging()
    
    def _setup_file_logging(self):
        """Setup detailed file logging"""
        log_file = Path("logs/error_system.log")
        log_file.parent.mkdir(exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s'
        )
        file_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.setLevel(logging.INFO)
    
    async def log_error(self, error_details: ErrorDetails, 
                       send_notification: bool = True) -> bool:
        """Log error with full processing"""
        try:
            # Log to database
            db_success = self.error_db.log_error(error_details)
            
            # Log to file
            self._log_to_file(error_details)
            
            # Update error patterns
            self._update_error_patterns(error_details)
            
            # Handle notifications
            if send_notification and self._should_send_notification(error_details):
                await self._queue_notification(error_details)
            
            return db_success
            
        except Exception as e:
            self.logger.error(f"Failed to process error log: {e}")
            return False
    
    def _log_to_file(self, error_details: ErrorDetails):
        """Log error details to file"""
        log_level = self._get_log_level(error_details.severity)
        
        message = (
            f"[{error_details.error_id}] {error_details.source_function}: "
            f"{error_details.error_message} | "
            f"Category: {error_details.category.value} | "
            f"Severity: {error_details.severity.value} | "
            f"Retries: {error_details.retry_count}"
        )
        
        if error_details.context:
            message += f" | Context: {json.dumps(error_details.context)}"
        
        self.logger.log(log_level, message)
        
        # Log stack trace for high severity errors
        if error_details.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            if error_details.stack_trace:
                self.logger.debug(f"Stack trace for {error_details.error_id}:\n{error_details.stack_trace}")
    
    def _get_log_level(self, severity: ErrorSeverity) -> int:
        """Get logging level from error severity"""
        level_map = {
            ErrorSeverity.LOW: logging.INFO,
            ErrorSeverity.MEDIUM: logging.WARNING,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL
        }
        return level_map.get(severity, logging.WARNING)
    
    def _update_error_patterns(self, error_details: ErrorDetails):
        """Update error pattern detection"""
        pattern_key = f"{error_details.category.value}_{error_details.source_function}"
        self.error_patterns[pattern_key] = self.error_patterns.get(pattern_key, 0) + 1
        
        # Detect patterns (5+ occurrences of same type)
        if self.error_patterns[pattern_key] >= 5:
            self.logger.warning(
                f"Error pattern detected: {pattern_key} "
                f"(occurred {self.error_patterns[pattern_key]} times)"
            )
    
    def _should_send_notification(self, error_details: ErrorDetails) -> bool:
        """Determine if notification should be sent"""
        # Check severity threshold
        severity_levels = [ErrorSeverity.LOW, ErrorSeverity.MEDIUM, ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]
        if severity_levels.index(error_details.severity) < severity_levels.index(self.notification_config.severity_threshold):
            return False
        
        # Check cooldown
        cooldown_key = f"{error_details.category.value}_{error_details.severity.value}"
        last_notification = self.last_notification_time.get(cooldown_key)
        
        if last_notification:
            cooldown_delta = datetime.now() - last_notification
            if cooldown_delta.total_seconds() < (self.notification_config.cooldown_minutes * 60):
                return False
        
        return True
    
    async def _queue_notification(self, error_details: ErrorDetails):
        """Queue error notification"""
        self.pending_notifications.append(error_details)
        
        # Send immediately for critical errors or if batching is disabled
        if (error_details.severity == ErrorSeverity.CRITICAL or 
            not self.notification_config.batch_notifications):
            await self._send_pending_notifications()
        
        # Send if batch is full
        elif len(self.pending_notifications) >= self.notification_config.max_batch_size:
            await self._send_pending_notifications()
    
    async def _send_pending_notifications(self):
        """Send all pending notifications"""
        if not self.pending_notifications:
            return
        
        try:
            if self.notification_config.telegram_enabled and self.notification_config.admin_chat_id:
                await self._send_telegram_notifications()
            
            # Clear pending notifications after sending
            self.pending_notifications.clear()
            
        except Exception as e:
            self.logger.error(f"Failed to send notifications: {e}")
    
    async def _send_telegram_notifications(self):
        """Send notifications via Telegram"""
        if not self.pending_notifications:
            return
        
        # Group by severity for better presentation
        critical_errors = [e for e in self.pending_notifications if e.severity == ErrorSeverity.CRITICAL]
        high_errors = [e for e in self.pending_notifications if e.severity == ErrorSeverity.HIGH]
        other_errors = [e for e in self.pending_notifications if e.severity not in [ErrorSeverity.CRITICAL, ErrorSeverity.HIGH]]
        
        message_parts = []
        
        # Critical errors first
        if critical_errors:
            message_parts.append("🚨 **CRITICAL ERRORS:**")
            for error in critical_errors:
                message_parts.append(
                    f"• {error.source_function}: {error.error_message[:100]}..."
                )
        
        # High severity errors
        if high_errors:
            message_parts.append("\n⚠️ **HIGH SEVERITY ERRORS:**")
            for error in high_errors:
                message_parts.append(
                    f"• {error.source_function}: {error.error_message[:100]}..."
                )
        
        # Other errors summary
        if other_errors:
            message_parts.append(f"\n📊 **OTHER ERRORS:** {len(other_errors)} additional errors logged")
        
        if message_parts:
            message = "\n".join(message_parts)
            message += f"\n\n⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            # Note: Actual Telegram sending should be implemented by the bot
            self.logger.critical(f"NOTIFICATION TO SEND:\n{message}")
            
            # Update last notification times
            for error in self.pending_notifications:
                cooldown_key = f"{error.category.value}_{error.severity.value}"
                self.last_notification_time[cooldown_key] = datetime.now()
    
    async def force_send_notifications(self):
        """Force send all pending notifications"""
        await self._send_pending_notifications()
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get comprehensive error summary"""
        stats_24h = self.error_db.get_error_statistics(24)
        stats_1h = self.error_db.get_error_statistics(1)
        recent_errors = self.error_db.get_recent_errors(5)
        
        return {
            "statistics_24h": stats_24h,
            "statistics_1h": stats_1h,
            "recent_errors": recent_errors,
            "error_patterns": dict(list(self.error_patterns.items())[-10:]),  # Last 10 patterns
            "pending_notifications": len(self.pending_notifications)
        }
    
    def cleanup_old_logs(self, days: int = 7):
        """Clean up old error logs"""
        try:
            conn = sqlite3.connect(self.error_db.db_path)
            cursor = conn.cursor()
            
            cutoff_date = datetime.now() - timedelta(days=days)
            
            cursor.execute('''
                DELETE FROM error_logs WHERE timestamp < ?
            ''', (cutoff_date,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            self.logger.info(f"Cleaned up {deleted_count} old error logs (older than {days} days)")
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup old logs: {e}")
            return 0


# Global error logger instance
_global_error_logger: Optional[CentralizedErrorLogger] = None


def get_global_error_logger() -> CentralizedErrorLogger:
    """Get or create global error logger instance"""
    global _global_error_logger
    if _global_error_logger is None:
        _global_error_logger = CentralizedErrorLogger()
    return _global_error_logger


def setup_global_error_logger(notification_config: ErrorNotificationConfig = None,
                             db_path: str = "error_logs.db") -> CentralizedErrorLogger:
    """Setup global error logger with specific configuration"""
    global _global_error_logger
    _global_error_logger = CentralizedErrorLogger(notification_config, db_path)
    return _global_error_logger


async def log_error_globally(error_details: ErrorDetails, send_notification: bool = True):
    """Convenience function to log error using global logger"""
    logger = get_global_error_logger()
    return await logger.log_error(error_details, send_notification)