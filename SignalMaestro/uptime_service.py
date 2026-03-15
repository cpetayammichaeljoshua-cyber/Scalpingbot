
#!/usr/bin/env python3
"""
Enhanced Uptime Service for Trading Bot
Includes a robust web server, external ping service integration, and health monitoring
"""

import asyncio
import logging
import aiohttp
from aiohttp import web
import time
import os
import subprocess
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import json
import threading
import signal
import sys
from pathlib import Path

class EnhancedUptimeService:
    """Enhanced uptime monitoring service with comprehensive health checks"""
    
    def __init__(self, port: int = 8080):
        self.port = port
        self.logger = logging.getLogger(__name__)
        self.app = None
        self.runner = None
        self.site = None
        self.start_time = datetime.now()
        self.ping_count = 0
        self.last_ping = None
        self.health_checks = {}
        self.external_pings_active = False
        
        # Replit configuration
        self.repl_name = os.getenv('REPL_SLUG', 'trading-bot')
        self.repl_owner = os.getenv('REPL_OWNER', 'user')
        self.replit_url = f"https://{self.repl_name}.{self.repl_owner}.repl.co"
        
        # External ping services
        self.ping_services = [
            {
                'name': 'Kaffeine',
                'url': 'https://kaffeine.herokuapp.com/',
                'endpoint': f"{self.replit_url}/keepalive",
                'interval': 5
            },
            {
                'name': 'UptimeRobot',
                'url': 'https://uptimerobot.com/',
                'endpoint': f"{self.replit_url}/health",
                'interval': 5
            }
        ]
        
        # Health status tracking
        self.component_health = {
            'web_server': False,
            'trading_bot': False,
            'database': False,
            'binance_api': False,
            'telegram_bot': False
        }
        
        # Setup graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"🛑 Received signal {signum}, shutting down...")
        asyncio.create_task(self.stop_server())
        sys.exit(0)
        
    def create_app(self):
        """Create the enhanced web application"""
        app = web.Application()
        
        # Core endpoints
        app.router.add_get('/', self.dashboard_handler)
        app.router.add_get('/ping', self.ping_handler)
        app.router.add_get('/health', self.health_check)
        app.router.add_get('/status', self.status_handler)
        app.router.add_get('/uptime', self.uptime_handler)
        app.router.add_get('/keepalive', self.keepalive_handler)
        
        # Enhanced monitoring endpoints
        app.router.add_get('/metrics', self.metrics_handler)
        app.router.add_get('/components', self.components_handler)
        app.router.add_get('/logs', self.logs_handler)
        app.router.add_get('/api/ping-services', self.ping_services_handler)
        
        # Setup external pings endpoint
        app.router.add_post('/api/setup-pings', self.setup_external_pings)
        
        return app
    
    async def dashboard_handler(self, request):
        """Enhanced dashboard with system overview"""
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        
        dashboard_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Trading Bot Uptime Dashboard</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
                .container {{ max-width: 1200px; margin: 0 auto; }}
                .card {{ background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .status-good {{ color: #28a745; }}
                .status-warning {{ color: #ffc107; }}
                .status-error {{ color: #dc3545; }}
                .metric {{ display: inline-block; margin: 10px 20px; }}
                .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
                h1 {{ color: #333; text-align: center; }}
                h2 {{ color: #666; }}
                .ping-url {{ font-family: monospace; background: #f8f9fa; padding: 10px; border-radius: 4px; }}
                button {{ background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }}
                button:hover {{ background: #0056b3; }}
            </style>
            <script>
                function refreshStatus() {{
                    fetch('/status')
                        .then(response => response.json())
                        .then(data => {{
                            document.getElementById('ping-count').textContent = data.ping_count;
                            document.getElementById('last-ping').textContent = data.last_ping || 'Never';
                        }});
                }}
                function setupPings() {{
                    fetch('/api/setup-pings', {{method: 'POST'}})
                        .then(response => response.json())
                        .then(data => alert(data.message || 'Setup initiated'));
                }}
                setInterval(refreshStatus, 30000);
            </script>
        </head>
        <body>
            <div class="container">
                <h1>🚀 Trading Bot Uptime Dashboard</h1>
                
                <div class="card">
                    <h2>📊 System Status</h2>
                    <div class="metric">
                        <strong>Uptime:</strong> <span class="status-good">{self._format_uptime(uptime_seconds)}</span>
                    </div>
                    <div class="metric">
                        <strong>Ping Count:</strong> <span id="ping-count">{self.ping_count}</span>
                    </div>
                    <div class="metric">
                        <strong>Last Ping:</strong> <span id="last-ping">{self.last_ping.isoformat() if self.last_ping else 'Never'}</span>
                    </div>
                </div>
                
                <div class="grid">
                    <div class="card">
                        <h2>🌐 Ping Endpoints</h2>
                        <p><strong>Health Check:</strong></p>
                        <div class="ping-url">{self.replit_url}/health</div>
                        <p><strong>Keep-Alive:</strong></p>
                        <div class="ping-url">{self.replit_url}/keepalive</div>
                        <p><strong>Simple Ping:</strong></p>
                        <div class="ping-url">{self.replit_url}/ping</div>
                        <br>
                        <button onclick="setupPings()">🔧 Auto-Setup External Pings</button>
                    </div>
                    
                    <div class="card">
                        <h2>📡 External Services</h2>
                        <p><strong>Kaffeine:</strong> <a href="https://kaffeine.herokuapp.com/" target="_blank">Setup Manually</a></p>
                        <p><strong>UptimeRobot:</strong> <a href="https://uptimerobot.com/" target="_blank">Setup Manually</a></p>
                        <p><strong>Pingdom:</strong> <a href="https://www.pingdom.com/" target="_blank">Setup Manually</a></p>
                        <p><strong>StatusCake:</strong> <a href="https://www.statuscake.com/" target="_blank">Setup Manually</a></p>
                    </div>
                </div>
                
                <div class="card">
                    <h2>🔧 Quick Actions</h2>
                    <button onclick="window.open('/health', '_blank')">View Health Check</button>
                    <button onclick="window.open('/metrics', '_blank')">View Metrics</button>
                    <button onclick="window.open('/components', '_blank')">Component Status</button>
                    <button onclick="refreshStatus()">Refresh Status</button>
                </div>
            </div>
        </body>
        </html>
        """
        
        return web.Response(text=dashboard_html, content_type='text/html')
    
    async def health_check(self, request):
        """Comprehensive health check endpoint"""
        health_status = await self._perform_health_checks()
        
        status_code = 200 if health_status['overall_healthy'] else 503
        
        response = {
            'status': 'healthy' if health_status['overall_healthy'] else 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'uptime_seconds': (datetime.now() - self.start_time).total_seconds(),
            'service': 'enhanced_trading_bot_uptime',
            'components': health_status['components'],
            'last_ping': self.last_ping.isoformat() if self.last_ping else None,
            'ping_count': self.ping_count
        }
        
        return web.json_response(response, status=status_code)
    
    async def ping_handler(self, request):
        """Enhanced ping response with additional info"""
        self.ping_count += 1
        self.last_ping = datetime.now()
        
        return web.json_response({
            'pong': True,
            'ping_count': self.ping_count,
            'timestamp': self.last_ping.isoformat(),
            'uptime_seconds': (self.last_ping - self.start_time).total_seconds(),
            'service': 'enhanced_trading_bot',
            'message': 'Bot is alive and responding'
        })
    
    async def status_handler(self, request):
        """Detailed status information"""
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        health_status = await self._perform_health_checks()
        
        status = {
            'service': 'Enhanced Trading Bot Uptime Service',
            'status': 'running',
            'start_time': self.start_time.isoformat(),
            'uptime_seconds': uptime_seconds,
            'uptime_human': self._format_uptime(uptime_seconds),
            'ping_count': self.ping_count,
            'last_ping': self.last_ping.isoformat() if self.last_ping else None,
            'replit_url': self.replit_url,
            'port': self.port,
            'external_pings_active': self.external_pings_active,
            'component_health': health_status['components'],
            'overall_healthy': health_status['overall_healthy']
        }
        
        return web.json_response(status)
    
    async def uptime_handler(self, request):
        """Simple uptime endpoint"""
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        return web.Response(text=f"Uptime: {self._format_uptime(uptime_seconds)}")
    
    async def keepalive_handler(self, request):
        """Keep-alive endpoint optimized for external monitoring services"""
        self.ping_count += 1
        self.last_ping = datetime.now()
        
        # Quick health check
        is_healthy = await self._quick_health_check()
        
        if is_healthy:
            return web.Response(text="OK", status=200)
        else:
            return web.Response(text="DEGRADED", status=200)  # Still return 200 for external services
    
    async def metrics_handler(self, request):
        """Prometheus-style metrics endpoint"""
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        
        metrics = f"""# HELP uptime_seconds Total uptime in seconds
# TYPE uptime_seconds counter
uptime_seconds {uptime_seconds}

# HELP ping_count_total Total number of pings received
# TYPE ping_count_total counter
ping_count_total {self.ping_count}

# HELP last_ping_timestamp_seconds Last ping timestamp
# TYPE last_ping_timestamp_seconds gauge
last_ping_timestamp_seconds {self.last_ping.timestamp() if self.last_ping else 0}

# HELP component_health Component health status (1=healthy, 0=unhealthy)
# TYPE component_health gauge
"""
        
        for component, healthy in self.component_health.items():
            metrics += f'component_health{{component="{component}"}} {1 if healthy else 0}\n'
        
        return web.Response(text=metrics, content_type='text/plain')
    
    async def components_handler(self, request):
        """Component health status"""
        health_status = await self._perform_health_checks()
        return web.json_response(health_status)
    
    async def logs_handler(self, request):
        """Recent log entries"""
        try:
            log_file = 'enhanced_scalping_bot.log'
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    recent_logs = lines[-100:]  # Last 100 lines
                return web.json_response({
                    'logs': recent_logs,
                    'count': len(recent_logs)
                })
            else:
                return web.json_response({'logs': [], 'count': 0})
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)
    
    async def ping_services_handler(self, request):
        """Information about ping services"""
        return web.json_response({
            'services': self.ping_services,
            'replit_url': self.replit_url,
            'setup_instructions': self._get_setup_instructions()
        })
    
    async def setup_external_pings(self, request):
        """Attempt to auto-setup external ping services"""
        try:
            results = []
            
            # Try Kaffeine auto-setup
            kaffeine_result = await self._setup_kaffeine()
            results.append(kaffeine_result)
            
            # Generate UptimeRobot curl command
            uptimerobot_cmd = self._generate_uptimerobot_setup()
            results.append({
                'service': 'UptimeRobot',
                'status': 'manual_setup_required',
                'command': uptimerobot_cmd
            })
            
            self.external_pings_active = any(r.get('status') == 'success' for r in results)
            
            return web.json_response({
                'message': 'External ping setup attempted',
                'results': results,
                'external_pings_active': self.external_pings_active
            })
            
        except Exception as e:
            return web.json_response({
                'error': str(e),
                'message': 'Auto-setup failed, manual setup required'
            }, status=500)
    
    async def _perform_health_checks(self) -> Dict[str, Any]:
        """Perform comprehensive health checks"""
        components = {}
        
        # Web server health
        components['web_server'] = True  # If we're responding, web server is healthy
        
        # Trading bot health (check for running processes or PID files)
        components['trading_bot'] = self._check_trading_bot_health()
        
        # Database health (check if database files exist and are accessible)
        components['database'] = self._check_database_health()
        
        # Binance API health (simple connectivity test)
        components['binance_api'] = await self._check_binance_health()
        
        # Telegram bot health (check if bot token is configured)
        components['telegram_bot'] = self._check_telegram_health()
        
        # Overall health
        overall_healthy = all(components.values())
        
        return {
            'components': components,
            'overall_healthy': overall_healthy,
            'timestamp': datetime.now().isoformat()
        }
    
    async def _quick_health_check(self) -> bool:
        """Quick health check for keep-alive endpoint"""
        try:
            # Just check if critical files exist
            return (
                os.path.exists('SignalMaestro/enhanced_perfect_scalping_bot.py') and
                os.path.exists('SignalMaestro/config.py')
            )
        except:
            return False
    
    def _check_trading_bot_health(self) -> bool:
        """Check if trading bot is running"""
        try:
            # Check for PID files
            pid_files = [
                'enhanced_perfect_scalping_bot.pid',
                'ml_enhanced_trading_bot.pid',
                'perfect_scalping_bot.pid'
            ]
            
            for pid_file in pid_files:
                if os.path.exists(pid_file):
                    try:
                        with open(pid_file, 'r') as f:
                            pid = int(f.read().strip())
                        # Check if process is running
                        os.kill(pid, 0)  # This will raise OSError if process doesn't exist
                        return True
                    except (OSError, ValueError):
                        continue
            
            return False
        except:
            return False
    
    def _check_database_health(self) -> bool:
        """Check database health"""
        try:
            db_files = [
                'SignalMaestro/trading_bot.db',
                'ml_trade_learning.db',
                'trade_learning.db'
            ]
            
            for db_file in db_files:
                if os.path.exists(db_file):
                    return True
            
            return False
        except:
            return False
    
    async def _check_binance_health(self) -> bool:
        """Check Binance API connectivity"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.binance.com/api/v3/ping', timeout=aiohttp.ClientTimeout(total=5)) as response:
                    return response.status == 200
        except:
            return False
    
    def _check_telegram_health(self) -> bool:
        """Check Telegram bot configuration"""
        try:
            return bool(os.getenv('TELEGRAM_BOT_TOKEN'))
        except:
            return False
    
    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    
    async def _setup_kaffeine(self) -> Dict[str, Any]:
        """Attempt to auto-setup Kaffeine"""
        try:
            # Kaffeine doesn't have a public API, so we'll just provide instructions
            return {
                'service': 'Kaffeine',
                'status': 'manual_setup_required',
                'url': 'https://kaffeine.herokuapp.com/',
                'endpoint': f"{self.replit_url}/keepalive",
                'instructions': f"Visit https://kaffeine.herokuapp.com/ and add: {self.replit_url}/keepalive"
            }
        except Exception as e:
            return {
                'service': 'Kaffeine',
                'status': 'error',
                'error': str(e)
            }
    
    def _generate_uptimerobot_setup(self) -> str:
        """Generate UptimeRobot setup command"""
        return f"""
curl -X POST https://api.uptimerobot.com/v2/newMonitor \\
  -d "api_key=YOUR_API_KEY" \\
  -d "format=json" \\
  -d "type=1" \\
  -d "url={self.replit_url}/health" \\
  -d "friendly_name=Trading Bot Health Check" \\
  -d "interval=300"
        """.strip()
    
    def _get_setup_instructions(self) -> List[Dict[str, str]]:
        """Get setup instructions for all ping services"""
        return [
            {
                'service': 'Kaffeine',
                'url': 'https://kaffeine.herokuapp.com/',
                'endpoint': f"{self.replit_url}/keepalive",
                'instructions': 'Visit Kaffeine and add your endpoint URL'
            },
            {
                'service': 'UptimeRobot',
                'url': 'https://uptimerobot.com/',
                'endpoint': f"{self.replit_url}/health",
                'instructions': 'Create free account and add HTTP(S) monitor'
            },
            {
                'service': 'Pingdom',
                'url': 'https://www.pingdom.com/',
                'endpoint': f"{self.replit_url}/ping",
                'instructions': 'Create free account and add uptime check'
            },
            {
                'service': 'StatusCake',
                'url': 'https://www.statuscake.com/',
                'endpoint': f"{self.replit_url}/health",
                'instructions': 'Create free account and add uptime test'
            }
        ]
    
    async def start_server(self):
        """Start the enhanced web server"""
        try:
            self.app = self.create_app()
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
            await self.site.start()
            
            self.logger.info(f"🌐 Enhanced uptime service started on port {self.port}")
            self.logger.info(f"📊 Dashboard: {self.replit_url}")
            self.logger.info(f"❤️ Health check: {self.replit_url}/health")
            self.logger.info(f"🏓 Ping endpoint: {self.replit_url}/ping")
            self.logger.info(f"⏰ Keep-alive: {self.replit_url}/keepalive")
            
            # Start self-monitoring
            asyncio.create_task(self.self_monitoring_loop())
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start enhanced uptime service: {e}")
            return False
    
    async def stop_server(self):
        """Stop the web server gracefully"""
        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            self.logger.info("🛑 Enhanced uptime service stopped gracefully")
        except Exception as e:
            self.logger.error(f"Error stopping uptime service: {e}")
    
    async def self_monitoring_loop(self):
        """Internal monitoring and self-ping loop"""
        while True:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                
                # Perform internal health checks
                health_status = await self._perform_health_checks()
                self.health_checks[datetime.now().isoformat()] = health_status
                
                # Keep only last 24 hours of health checks
                cutoff_time = datetime.now() - timedelta(hours=24)
                self.health_checks = {
                    k: v for k, v in self.health_checks.items()
                    if datetime.fromisoformat(k) > cutoff_time
                }
                
                # Log health status
                if health_status['overall_healthy']:
                    self.logger.debug("✅ System health check passed")
                else:
                    unhealthy_components = [
                        comp for comp, healthy in health_status['components'].items()
                        if not healthy
                    ]
                    self.logger.warning(f"⚠️ Unhealthy components: {unhealthy_components}")
                
            except Exception as e:
                self.logger.error(f"Error in self-monitoring loop: {e}")
    
    async def run(self):
        """Main run method"""
        try:
            # Start the web server
            if await self.start_server():
                self.logger.info("🚀 Enhanced uptime service fully operational")
                self.logger.info("📋 Setup external ping services at: /api/ping-services")
                
                # Keep running
                while True:
                    await asyncio.sleep(60)
                    
        except KeyboardInterrupt:
            self.logger.info("🛑 Enhanced uptime service shutdown requested")
        except Exception as e:
            self.logger.error(f"Error in uptime service: {e}")
        finally:
            await self.stop_server()

async def main():
    """Main function"""
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s - %(message)s'
    )
    
    # Use port 8080 to avoid conflicts with main bot
    uptime_service = EnhancedUptimeService(port=8080)
    await uptime_service.run()

if __name__ == "__main__":
    asyncio.run(main())
