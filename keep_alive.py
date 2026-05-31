
#!/usr/bin/env python3
"""
Enhanced Keep-Alive Service for Replit
Optimized for continuous operation and external ping compatibility
"""

import asyncio
import logging
import json
import os
import time
import signal
import sys
from datetime import datetime, timedelta
from aiohttp import web
from typing import Dict, Any, Optional

class ReplatEnhancedKeepAlive:
    """Enhanced keep-alive service designed specifically for Replit"""
    
    def __init__(self, port: int = 3000):
        self.port = port
        self.logger = logging.getLogger(__name__)
        self.start_time = datetime.now()
        self.ping_count = 0
        self.last_ping = None
        self.app = None
        self.runner = None
        self.site = None
        
        # Replit specific configuration
        self.repl_name = os.getenv('REPL_SLUG', 'trading-bot')
        self.repl_owner = os.getenv('REPL_OWNER', 'user')
        self.replit_url = f"https://{self.repl_name}.{self.repl_owner}.repl.co"
        
        # Health tracking
        self.health_status = {
            'service': 'healthy',
            'main_bot': 'unknown',
            'uptime_service': 'unknown'
        }
        
        # Setup graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(self._shutdown())
        
    async def _shutdown(self):
        """Graceful shutdown"""
        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            self.logger.info("Keep-alive service stopped gracefully")
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
        finally:
            sys.exit(0)
    
    def create_app(self):
        """Create the web application"""
        app = web.Application()
        
        # Essential endpoints for external monitoring
        app.router.add_get('/', self.home_handler)
        app.router.add_get('/ping', self.ping_handler)
        app.router.add_get('/health', self.health_handler)
        app.router.add_get('/keepalive', self.keepalive_handler)
        app.router.add_get('/status', self.status_handler)
        
        # Replit specific endpoints
        app.router.add_get('/replit', self.replit_info_handler)
        app.router.add_get('/uptime', self.uptime_handler)
        app.router.add_get('/wake', self.wake_handler)
        
        return app
    
    async def home_handler(self, request):
        """Home page with service information"""
        uptime = self._format_uptime()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Trading Bot Keep-Alive Service</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background: #f0f8ff; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .status {{ padding: 15px; margin: 10px 0; border-radius: 5px; text-align: center; }}
                .online {{ background: #d4edda; color: #155724; border: 2px solid #c3e6cb; }}
                .info {{ background: #cce7ff; color: #004085; border: 2px solid #99d6ff; }}
                .endpoint {{ font-family: monospace; background: #f8f9fa; padding: 8px; border-radius: 4px; margin: 5px 0; }}
                h1 {{ color: #333; text-align: center; margin-bottom: 30px; }}
                .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }}
                .metric {{ text-align: center; padding: 10px; }}
                .metric-value {{ font-size: 2em; font-weight: bold; color: #007bff; }}
                .metric-label {{ color: #666; }}
            </style>
            <script>
                function updateStats() {{
                    fetch('/status')
                        .then(response => response.json())
                        .then(data => {{
                            document.getElementById('ping-count').textContent = data.ping_count;
                            document.getElementById('last-ping').textContent = data.last_ping || 'Never';
                            document.getElementById('uptime-display').textContent = data.uptime_human;
                        }})
                        .catch(error => console.log('Update failed:', error));
                }}
                setInterval(updateStats, 10000); // Update every 10 seconds
            </script>
        </head>
        <body>
            <div class="container">
                <h1>🚀 Trading Bot Keep-Alive Service</h1>
                
                <div class="status online">
                    ✅ Service is ONLINE and responding to pings
                </div>
                
                <div class="grid">
                    <div class="metric">
                        <div class="metric-value" id="uptime-display">{uptime}</div>
                        <div class="metric-label">Uptime</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value" id="ping-count">{self.ping_count}</div>
                        <div class="metric-label">Total Pings</div>
                    </div>
                </div>
                
                <div class="status info">
                    <h3>📡 Monitoring Endpoints</h3>
                    <div class="endpoint">GET {self.replit_url}/ping</div>
                    <div class="endpoint">GET {self.replit_url}/health</div>
                    <div class="endpoint">GET {self.replit_url}/keepalive</div>
                    <div class="endpoint">GET {self.replit_url}/wake</div>
                </div>
                
                <div class="status info">
                    <h3>🔧 Setup Instructions</h3>
                    <p><strong>Kaffeine:</strong> Add <code>{self.replit_url}/keepalive</code></p>
                    <p><strong>UptimeRobot:</strong> Monitor <code>{self.replit_url}/health</code></p>
                    <p><strong>Pingdom:</strong> Check <code>{self.replit_url}/ping</code></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return web.Response(text=html, content_type='text/html')
    
    async def ping_handler(self, request):
        """Simple ping response"""
        self.ping_count += 1
        self.last_ping = datetime.now()
        
        return web.json_response({
            'pong': True,
            'timestamp': self.last_ping.isoformat(),
            'service': 'trading_bot_keep_alive',
            'message': 'Service is alive'
        })
    
    async def health_handler(self, request):
        """Health check with component status"""
        self._update_health_status()
        
        health_data = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'uptime_seconds': (datetime.now() - self.start_time).total_seconds(),
            'ping_count': self.ping_count,
            'last_ping': self.last_ping.isoformat() if self.last_ping else None,
            'replit_url': self.replit_url,
            'components': self.health_status,
            'service': 'trading_bot_keep_alive'
        }
        
        return web.json_response(health_data)
    
    async def keepalive_handler(self, request):
        """Keep-alive endpoint optimized for external services"""
        self.ping_count += 1
        self.last_ping = datetime.now()
        
        # Simple text response for external monitoring services
        return web.Response(text="OK", status=200, headers={
            'Cache-Control': 'no-cache',
            'X-Service': 'trading-bot-keepalive',
            'X-Timestamp': self.last_ping.isoformat()
        })
    
    async def status_handler(self, request):
        """Detailed status information"""
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        self._update_health_status()
        
        status = {
            'service': 'Enhanced Trading Bot Keep-Alive',
            'status': 'running',
            'start_time': self.start_time.isoformat(),
            'current_time': datetime.now().isoformat(),
            'uptime_seconds': uptime_seconds,
            'uptime_human': self._format_uptime(),
            'ping_count': self.ping_count,
            'last_ping': self.last_ping.isoformat() if self.last_ping else None,
            'replit_info': {
                'repl_name': self.repl_name,
                'repl_owner': self.repl_owner,
                'replit_url': self.replit_url
            },
            'health_status': self.health_status,
            'endpoints': {
                'ping': f"{self.replit_url}/ping",
                'health': f"{self.replit_url}/health", 
                'keepalive': f"{self.replit_url}/keepalive",
                'wake': f"{self.replit_url}/wake"
            }
        }
        
        return web.json_response(status)
    
    async def replit_info_handler(self, request):
        """Replit specific information"""
        return web.json_response({
            'platform': 'replit',
            'repl_name': self.repl_name,
            'repl_owner': self.repl_owner,
            'replit_url': self.replit_url,
            'port': self.port,
            'service': 'keep_alive',
            'optimized_for': 'external_monitoring'
        })
    
    async def uptime_handler(self, request):
        """Simple uptime text response"""
        uptime = self._format_uptime()
        return web.Response(text=f"Uptime: {uptime}")
    
    async def wake_handler(self, request):
        """Wake endpoint to prevent sleeping"""
        self.ping_count += 1
        self.last_ping = datetime.now()
        
        return web.json_response({
            'status': 'awake',
            'message': 'Service is awake and running',
            'timestamp': self.last_ping.isoformat(),
            'ping_count': self.ping_count
        })
    
    def _update_health_status(self):
        """Update health status of components"""
        # Check if main bot files exist
        main_bot_files = [
            'SignalMaestro/enhanced_perfect_scalping_bot.py',
            'start_enhanced_perfect_bot.py',
            'SignalMaestro/config.py'
        ]
        
        self.health_status['main_bot'] = 'healthy' if all(os.path.exists(f) for f in main_bot_files) else 'unhealthy'
        
        # Check if uptime service is running (port 8080)
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', 8080))
            sock.close()
            self.health_status['uptime_service'] = 'healthy' if result == 0 else 'unknown'
        except:
            self.health_status['uptime_service'] = 'unknown'
    
    def _format_uptime(self) -> str:
        """Format uptime in human readable format"""
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    
    async def start_server(self):
        """Start the keep-alive server"""
        try:
            self.app = self.create_app()
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
            await self.site.start()
            
            self.logger.info(f"🌐 Enhanced keep-alive service started on port {self.port}")
            self.logger.info(f"📡 Available at: {self.replit_url}")
            self.logger.info(f"❤️ Health check: {self.replit_url}/health")
            self.logger.info(f"⏰ Keep-alive: {self.replit_url}/keepalive")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start keep-alive service: {e}")
            return False
    
    async def run(self):
        """Main run method"""
        try:
            if await self.start_server():
                self.logger.info("✅ Enhanced keep-alive service operational")
                
                # Keep running and perform periodic tasks
                while True:
                    await asyncio.sleep(300)  # 5 minutes
                    
                    # Log status periodically
                    self.logger.info(f"⏰ Keep-alive running - Uptime: {self._format_uptime()}, Pings: {self.ping_count}")
                    
        except KeyboardInterrupt:
            self.logger.info("🛑 Keep-alive service shutdown requested")
        except Exception as e:
            self.logger.error(f"Error in keep-alive service: {e}")
        finally:
            await self._shutdown()

async def main():
    """Main function"""
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s - %(message)s'
    )
    
    # Use port 3000 for keep-alive (separate from main bot and uptime service)
    keep_alive = ReplatEnhancedKeepAlive(port=3000)
    await keep_alive.run()

if __name__ == "__main__":
    asyncio.run(main())
