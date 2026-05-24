
#!/usr/bin/env python3
"""
Bot Health Monitor - Advanced monitoring system for trading bot
Monitors bot performance, channel activity, and trade execution
"""

import asyncio
import aiohttp
import json
import logging
import os
import psutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
import sqlite3

class BotHealthMonitor:
    """Advanced health monitoring system for trading bot"""
    
    def __init__(self):
        self.setup_logging()
        
        # Configuration
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_channel_id = os.getenv('TELEGRAM_CHANNEL_ID')
        self.monitoring_interval = 60  # seconds
        
        # Health thresholds
        self.max_memory_mb = 800
        self.max_cpu_percent = 85
        self.min_uptime_seconds = 300  # 5 minutes
        self.max_restart_count = 10
        
        # Database for tracking
        self.db_path = "bot_health_monitoring.db"
        self.init_database()
        
        # Metrics tracking
        self.health_history = []
        self.last_trade_time = None
        self.trade_count_today = 0
        
    def setup_logging(self):
        """Setup logging system"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - BOT_HEALTH - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_dir / "bot_health_monitor.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def init_database(self):
        """Initialize health monitoring database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS health_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    bot_running BOOLEAN,
                    memory_mb REAL,
                    cpu_percent REAL,
                    uptime_seconds REAL,
                    restart_count INTEGER,
                    trade_count INTEGER,
                    channel_responsive BOOLEAN,
                    overall_healthy BOOLEAN,
                    issues TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    event_type TEXT,
                    description TEXT,
                    severity TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
    
    def get_bot_process_info(self) -> Optional[Dict[str, Any]]:
        """Get information about running bot processes"""
        try:
            bot_processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info', 'cpu_percent', 'create_time']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    
                    # Check if it's a trading bot process
                    if any(bot_file in cmdline for bot_file in [
                        'ultimate_trading_bot.py',
                        'enhanced_perfect_scalping_bot.py',
                        'perfect_scalping_bot.py',
                        'start_ultimate_bot.py',
                        'start_enhanced_bot_v2.py'
                    ]):
                        memory_mb = proc.info['memory_info'].rss / 1024 / 1024
                        uptime_seconds = time.time() - proc.info['create_time']
                        
                        bot_info = {
                            'pid': proc.info['pid'],
                            'name': proc.info['name'],
                            'cmdline': cmdline,
                            'memory_mb': round(memory_mb, 2),
                            'cpu_percent': proc.info['cpu_percent'],
                            'uptime_seconds': uptime_seconds,
                            'create_time': datetime.fromtimestamp(proc.info['create_time']).isoformat()
                        }
                        bot_processes.append(bot_info)
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if bot_processes:
                # Return the most recently started bot
                return max(bot_processes, key=lambda x: x['uptime_seconds'])
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting bot process info: {e}")
            return None
    
    def get_continuous_manager_status(self) -> Dict[str, Any]:
        """Get status from continuous bot manager"""
        try:
            status_file = Path("continuous_bot_status.json")
            if status_file.exists():
                with open(status_file, 'r') as f:
                    return json.load(f)
            return {'status': 'no_status_file'}
        except Exception as e:
            self.logger.error(f"Error reading continuous manager status: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def check_telegram_connectivity(self) -> bool:
        """Check if Telegram bot is responsive"""
        if not self.telegram_bot_token:
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/getMe"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('ok', False)
            
            return False
            
        except Exception as e:
            self.logger.error(f"Telegram connectivity check failed: {e}")
            return False
    
    async def check_channel_activity(self) -> Dict[str, Any]:
        """Check recent activity in the trading channel"""
        if not self.telegram_bot_token or not self.telegram_channel_id:
            return {'active': False, 'reason': 'missing_config'}
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/getUpdates"
            params = {'limit': 10, 'offset': -10}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data.get('ok') and data.get('result'):
                            recent_messages = len(data['result'])
                            return {
                                'active': recent_messages > 0,
                                'recent_messages': recent_messages,
                                'last_update': datetime.now().isoformat()
                            }
            
            return {'active': False, 'reason': 'no_updates'}
            
        except Exception as e:
            self.logger.error(f"Channel activity check failed: {e}")
            return {'active': False, 'reason': str(e)}
    
    def count_trades_today(self) -> int:
        """Count trades executed today"""
        try:
            # Check various trade databases
            trade_dbs = [
                "trading_bot.db",
                "SignalMaestro/trading_bot.db",
                "trade_learning.db",
                "SignalMaestro/trade_learning.db"
            ]
            
            today = datetime.now().date()
            total_trades = 0
            
            for db_path in trade_dbs:
                if Path(db_path).exists():
                    try:
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        
                        # Try common table names
                        for table in ['trades', 'trade_history', 'signals']:
                            try:
                                cursor.execute(f'''
                                    SELECT COUNT(*) FROM {table} 
                                    WHERE date(timestamp) = date('now', 'localtime')
                                    OR date(created_at) = date('now', 'localtime')
                                ''')
                                count = cursor.fetchone()[0]
                                total_trades += count
                                break
                            except sqlite3.OperationalError:
                                continue
                        
                        conn.close()
                        
                    except Exception as e:
                        self.logger.warning(f"Error checking trades in {db_path}: {e}")
                        continue
            
            return total_trades
            
        except Exception as e:
            self.logger.error(f"Error counting trades: {e}")
            return 0
    
    async def perform_comprehensive_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        health_report = {
            'timestamp': datetime.now().isoformat(),
            'overall_healthy': False,
            'components': {},
            'issues': [],
            'recommendations': []
        }
        
        try:
            # Check bot process
            bot_info = self.get_bot_process_info()
            if bot_info:
                health_report['components']['bot_process'] = {
                    'running': True,
                    'pid': bot_info['pid'],
                    'memory_mb': bot_info['memory_mb'],
                    'cpu_percent': bot_info['cpu_percent'],
                    'uptime_seconds': bot_info['uptime_seconds'],
                    'healthy': (
                        bot_info['memory_mb'] < self.max_memory_mb and
                        bot_info['cpu_percent'] < self.max_cpu_percent and
                        bot_info['uptime_seconds'] > self.min_uptime_seconds
                    )
                }
                
                # Check for issues
                if bot_info['memory_mb'] >= self.max_memory_mb:
                    health_report['issues'].append(f"High memory usage: {bot_info['memory_mb']:.1f}MB")
                    health_report['recommendations'].append("Consider restarting bot to free memory")
                
                if bot_info['cpu_percent'] >= self.max_cpu_percent:
                    health_report['issues'].append(f"High CPU usage: {bot_info['cpu_percent']:.1f}%")
                
                if bot_info['uptime_seconds'] < self.min_uptime_seconds:
                    health_report['issues'].append("Bot recently restarted")
                    
            else:
                health_report['components']['bot_process'] = {
                    'running': False,
                    'healthy': False
                }
                health_report['issues'].append("No trading bot process found")
                health_report['recommendations'].append("Start the trading bot")
            
            # Check continuous manager
            manager_status = self.get_continuous_manager_status()
            health_report['components']['continuous_manager'] = {
                'status': manager_status.get('status', 'unknown'),
                'restart_count': manager_status.get('restart_count', 0),
                'healthy': manager_status.get('status') == 'running'
            }
            
            if manager_status.get('restart_count', 0) > self.max_restart_count:
                health_report['issues'].append(f"High restart count: {manager_status.get('restart_count')}")
            
            # Check Telegram connectivity
            telegram_ok = await self.check_telegram_connectivity()
            health_report['components']['telegram'] = {
                'connected': telegram_ok,
                'healthy': telegram_ok
            }
            
            if not telegram_ok:
                health_report['issues'].append("Telegram bot not responsive")
                health_report['recommendations'].append("Check TELEGRAM_BOT_TOKEN")
            
            # Check channel activity
            channel_status = await self.check_channel_activity()
            health_report['components']['channel'] = {
                'active': channel_status.get('active', False),
                'recent_messages': channel_status.get('recent_messages', 0),
                'healthy': channel_status.get('active', False)
            }
            
            # Count today's trades
            trades_today = self.count_trades_today()
            health_report['components']['trading_activity'] = {
                'trades_today': trades_today,
                'healthy': trades_today >= 0  # Any trading activity is good
            }
            
            # Overall health assessment
            healthy_components = sum(1 for comp in health_report['components'].values() if comp.get('healthy', False))
            total_components = len(health_report['components'])
            health_percentage = (healthy_components / total_components * 100) if total_components > 0 else 0
            
            health_report['overall_healthy'] = health_percentage >= 80
            health_report['health_percentage'] = round(health_percentage, 1)
            health_report['healthy_components'] = healthy_components
            health_report['total_components'] = total_components
            
            # Add to history
            self.health_history.append(health_report)
            if len(self.health_history) > 100:  # Keep last 100 checks
                self.health_history.pop(0)
            
            # Log health status
            status_emoji = "✅" if health_report['overall_healthy'] else "⚠️"
            self.logger.info(f"{status_emoji} Health Check: {health_percentage:.1f}% ({healthy_components}/{total_components} components healthy)")
            
            if health_report['issues']:
                for issue in health_report['issues']:
                    self.logger.warning(f"🚨 Issue: {issue}")
            
            # Store in database
            self.store_health_check(health_report)
            
            return health_report
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            health_report['issues'].append(f"Health check error: {str(e)}")
            return health_report
    
    def store_health_check(self, health_report: Dict[str, Any]):
        """Store health check results in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            bot_component = health_report['components'].get('bot_process', {})
            channel_component = health_report['components'].get('channel', {})
            
            cursor.execute('''
                INSERT INTO health_checks (
                    bot_running, memory_mb, cpu_percent, uptime_seconds,
                    restart_count, trade_count, channel_responsive,
                    overall_healthy, issues
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                bot_component.get('running', False),
                bot_component.get('memory_mb', 0),
                bot_component.get('cpu_percent', 0),
                bot_component.get('uptime_seconds', 0),
                health_report['components'].get('continuous_manager', {}).get('restart_count', 0),
                health_report['components'].get('trading_activity', {}).get('trades_today', 0),
                channel_component.get('active', False),
                health_report['overall_healthy'],
                json.dumps(health_report['issues'])
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error storing health check: {e}")
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get health summary from recent checks"""
        try:
            if not self.health_history:
                return {'status': 'no_data'}
            
            recent_checks = self.health_history[-10:]  # Last 10 checks
            healthy_count = sum(1 for check in recent_checks if check['overall_healthy'])
            
            latest_check = self.health_history[-1]
            
            return {
                'current_status': 'healthy' if latest_check['overall_healthy'] else 'unhealthy',
                'health_percentage': latest_check.get('health_percentage', 0),
                'recent_healthy_rate': (healthy_count / len(recent_checks)) * 100,
                'current_issues': latest_check.get('issues', []),
                'recommendations': latest_check.get('recommendations', []),
                'last_check': latest_check['timestamp'],
                'components': latest_check['components']
            }
            
        except Exception as e:
            self.logger.error(f"Error getting health summary: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def run_continuous_monitoring(self):
        """Run continuous health monitoring"""
        self.logger.info("🏥 Starting continuous health monitoring...")
        
        try:
            while True:
                self.logger.info("🔍 Performing health check...")
                
                health_report = await self.perform_comprehensive_health_check()
                
                # Take action on critical issues
                if not health_report['overall_healthy']:
                    critical_issues = [
                        issue for issue in health_report['issues'] 
                        if any(keyword in issue.lower() for keyword in ['not found', 'not responsive', 'high cpu'])
                    ]
                    
                    if critical_issues:
                        self.logger.error("🚨 Critical health issues detected!")
                        for issue in critical_issues:
                            self.logger.error(f"   • {issue}")
                        
                        # Log critical event
                        self.log_event('critical_health_issue', f"Critical issues: {'; '.join(critical_issues)}", 'high')
                
                # Wait for next check
                await asyncio.sleep(self.monitoring_interval)
                
        except KeyboardInterrupt:
            self.logger.info("🛑 Health monitoring stopped by user")
        except Exception as e:
            self.logger.error(f"💥 Health monitoring error: {e}")
    
    def log_event(self, event_type: str, description: str, severity: str = 'info'):
        """Log significant events"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO bot_events (event_type, description, severity)
                VALUES (?, ?, ?)
            ''', (event_type, description, severity))
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"📝 Event logged: {event_type} - {description}")
            
        except Exception as e:
            self.logger.error(f"Error logging event: {e}")

async def main():
    """Main health monitoring function"""
    print("🏥 BOT HEALTH MONITOR")
    print("=" * 60)
    print("🔍 Advanced monitoring for trading bot health")
    print("📊 Process, memory, CPU, and channel monitoring")
    print("=" * 60)
    
    monitor = BotHealthMonitor()
    
    try:
        # Perform initial health check
        print("🔍 Performing initial health check...")
        initial_health = await monitor.perform_comprehensive_health_check()
        
        print(f"📊 Initial Health: {initial_health['health_percentage']:.1f}%")
        print(f"✅ Healthy Components: {initial_health['healthy_components']}/{initial_health['total_components']}")
        
        if initial_health['issues']:
            print("⚠️ Issues found:")
            for issue in initial_health['issues']:
                print(f"   • {issue}")
        
        print("\n🔄 Starting continuous monitoring...")
        await monitor.run_continuous_monitoring()
        
    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped by user")
    except Exception as e:
        print(f"💥 Monitoring error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
