
#!/usr/bin/env python3
"""
Enhanced Webhook Server for Trading Signal Processing
Handles incoming signals and forwards to the enhanced bot
"""

from flask import Flask, request, jsonify
import asyncio
import logging
import json
from datetime import datetime
from threading import Thread
import os

from enhanced_perfect_scalping_bot_v2 import EnhancedPerfectScalpingBotV2

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global bot instance
trading_bot = None
bot_loop = None

def run_bot_in_background():
    """Run the trading bot in background asyncio loop"""
    global trading_bot, bot_loop
    
    try:
        bot_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(bot_loop)
        
        trading_bot = EnhancedPerfectScalpingBotV2()
        bot_loop.run_until_complete(trading_bot.start())
        
    except Exception as e:
        logger.error(f"Bot background error: {e}")

@app.route('/webhook', methods=['POST'])
async def handle_webhook():
    """Handle incoming webhook signals"""
    try:
        data = request.get_json()
        logger.info(f"Received webhook: {data}")
        
        if not trading_bot:
            return jsonify({'error': 'Bot not initialized'}), 500
        
        # Process signal asynchronously
        if bot_loop:
            asyncio.run_coroutine_threadsafe(
                trading_bot.process_signal(data),
                bot_loop
            )
        
        return jsonify({
            'status': 'success',
            'message': 'Signal received and processing',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/signal', methods=['POST'])
async def handle_manual_signal():
    """Handle manual signal input"""
    try:
        data = request.get_json()
        signal_text = data.get('signal', '')
        
        if not signal_text:
            return jsonify({'error': 'No signal provided'}), 400
        
        logger.info(f"Manual signal: {signal_text}")
        
        if trading_bot and bot_loop:
            asyncio.run_coroutine_threadsafe(
                trading_bot.process_signal(signal_text),
                bot_loop
            )
        
        return jsonify({
            'status': 'success',
            'message': 'Manual signal processed',
            'signal': signal_text
        })
        
    except Exception as e:
        logger.error(f"Manual signal error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/status', methods=['GET'])
async def get_status():
    """Get bot status"""
    try:
        if not trading_bot:
            return jsonify({'status': 'bot_not_initialized'})
        
        # Get status from bot
        if bot_loop:
            future = asyncio.run_coroutine_threadsafe(
                trading_bot.get_status_report(),
                bot_loop
            )
            status = future.result(timeout=5.0)
        else:
            status = {'status': 'loop_not_running'}
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Status error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'bot_running': trading_bot is not None and trading_bot.running
    })

@app.route('/', methods=['GET'])
def index():
    """Root endpoint"""
    return jsonify({
        'name': 'Enhanced Perfect Scalping Bot V2',
        'version': '2.0',
        'status': 'running',
        'endpoints': {
            '/webhook': 'POST - Receive trading signals',
            '/signal': 'POST - Manual signal input',
            '/status': 'GET - Bot status',
            '/health': 'GET - Health check'
        }
    })

def initialize_app():
    """Initialize the Flask app and bot"""
    # Start bot in background thread
    bot_thread = Thread(target=run_bot_in_background, daemon=True)
    bot_thread.start()
    
    logger.info("🚀 Enhanced webhook server initialized")

if __name__ == '__main__':
    initialize_app()
    
    # Run Flask app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
#!/usr/bin/env python3
"""
Enhanced Webhook Server for Perfect Scalping Bot V2
Handles incoming signals and provides health check endpoints
"""

import asyncio
import logging
import json
import aiohttp
from aiohttp import web, ClientSession
from datetime import datetime
import sys
import os
import signal
from typing import Dict, Any, Optional

# Add SignalMaestro to path
sys.path.append(os.path.dirname(__file__))

try:
    from enhanced_perfect_scalping_bot_v2 import EnhancedPerfectScalpingBotV2
    from config import Config
except ImportError as e:
    print(f"Import error: {e}")
    # Create minimal config if import fails
    class Config:
        TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
        TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
        LOG_LEVEL = 'INFO'

class EnhancedWebhookServer:
    """Enhanced webhook server with health monitoring"""
    
    def __init__(self):
        self.config = Config()
        self.logger = self._setup_logging()
        self.app = web.Application()
        self.trading_bot = None
        self.server_start_time = datetime.now()
        self.running = False
        
        # Setup routes
        self._setup_routes()
        
        # Initialize trading bot
        try:
            self.trading_bot = EnhancedPerfectScalpingBotV2()
        except Exception as e:
            self.logger.warning(f"Could not initialize trading bot: {e}")
    
    def _setup_logging(self) -> logging.Logger:
        """Setup server logging"""
        logger = logging.getLogger('WebhookServer')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            formatter = logging.Formatter(
                '%(asctime)s | WEBHOOK | %(levelname)s | %(message)s'
            )
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def _setup_routes(self):
        """Setup webhook and health check routes"""
        self.app.router.add_post('/webhook', self.handle_webhook)
        self.app.router.add_post('/signal', self.handle_signal)
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/status', self.get_status)
        self.app.router.add_get('/', self.index)
    
    async def index(self, request):
        """Index endpoint"""
        return web.json_response({
            'service': 'Enhanced Perfect Scalping Bot V2',
            'status': 'running' if self.running else 'starting',
            'uptime': str(datetime.now() - self.server_start_time),
            'endpoints': {
                'webhook': '/webhook',
                'signal': '/signal', 
                'health': '/health',
                'status': '/status'
            }
        })
    
    async def health_check(self, request):
        """Health check endpoint for deployment manager"""
        try:
            health_data = {
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'uptime_seconds': (datetime.now() - self.server_start_time).total_seconds(),
                'server_running': True,
                'bot_running': self.trading_bot is not None and getattr(self.trading_bot, 'running', False),
                'endpoints_active': True
            }
            
            return web.json_response(health_data)
            
        except Exception as e:
            self.logger.error(f"Health check error: {e}")
            return web.json_response({
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }, status=500)
    
    async def get_status(self, request):
        """Detailed status endpoint"""
        try:
            status = {
                'server': {
                    'running': self.running,
                    'start_time': self.server_start_time.isoformat(),
                    'uptime_seconds': (datetime.now() - self.server_start_time).total_seconds()
                },
                'trading_bot': {
                    'initialized': self.trading_bot is not None,
                    'running': self.trading_bot is not None and getattr(self.trading_bot, 'running', False)
                },
                'endpoints': ['/webhook', '/signal', '/health', '/status', '/']
            }
            
            # Add trading bot status if available
            if self.trading_bot:
                try:
                    bot_status = await self.trading_bot.get_status_report()
                    status['trading_bot'].update(bot_status)
                except Exception as e:
                    status['trading_bot']['error'] = str(e)
            
            return web.json_response(status)
            
        except Exception as e:
            self.logger.error(f"Status error: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def handle_webhook(self, request):
        """Handle incoming webhook requests"""
        try:
            # Parse request data
            if request.content_type == 'application/json':
                data = await request.json()
            else:
                text = await request.text()
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    data = {'message': text}
            
            self.logger.info(f"📨 Webhook received: {data}")
            
            # Process signal if trading bot is available
            if self.trading_bot:
                try:
                    await self.trading_bot.process_signal(data)
                    response = {
                        'status': 'success',
                        'message': 'Signal processed successfully',
                        'timestamp': datetime.now().isoformat()
                    }
                except Exception as e:
                    self.logger.error(f"Signal processing error: {e}")
                    response = {
                        'status': 'error',
                        'message': f'Signal processing failed: {str(e)}',
                        'timestamp': datetime.now().isoformat()
                    }
            else:
                response = {
                    'status': 'warning',
                    'message': 'Signal received but trading bot not initialized',
                    'timestamp': datetime.now().isoformat()
                }
            
            return web.json_response(response)
            
        except Exception as e:
            self.logger.error(f"Webhook error: {e}")
            return web.json_response({
                'status': 'error',
                'message': str(e),
                'timestamp': datetime.now().isoformat()
            }, status=500)
    
    async def handle_signal(self, request):
        """Handle direct signal requests"""
        return await self.handle_webhook(request)
    
    async def start_server(self, host='0.0.0.0', port=5000):
        """Start the webhook server"""
        try:
            self.logger.info(f"🚀 Starting Enhanced Webhook Server on {host}:{port}")
            
            # Start trading bot if available
            if self.trading_bot:
                try:
                    self.logger.info("🤖 Starting trading bot...")
                    asyncio.create_task(self.trading_bot.start())
                except Exception as e:
                    self.logger.warning(f"Trading bot start error: {e}")
            
            # Setup signal handlers
            self._setup_signal_handlers()
            
            # Start web server
            runner = web.AppRunner(self.app)
            await runner.setup()
            
            site = web.TCPSite(runner, host, port)
            await site.start()
            
            self.running = True
            self.logger.info(f"✅ Enhanced Webhook Server running on http://{host}:{port}")
            self.logger.info("🌐 Endpoints available:")
            self.logger.info(f"  - Health: http://{host}:{port}/health")
            self.logger.info(f"  - Status: http://{host}:{port}/status") 
            self.logger.info(f"  - Webhook: http://{host}:{port}/webhook")
            self.logger.info(f"  - Signal: http://{host}:{port}/signal")
            
            # Keep server running
            try:
                while self.running:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass
            finally:
                await runner.cleanup()
                
        except Exception as e:
            self.logger.error(f"❌ Server start error: {e}")
            raise
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, shutting down...")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def shutdown(self):
        """Graceful shutdown"""
        self.logger.info("🛑 Shutting down Enhanced Webhook Server...")
        
        self.running = False
        
        # Stop trading bot
        if self.trading_bot and hasattr(self.trading_bot, 'stop'):
            try:
                await self.trading_bot.stop()
            except Exception as e:
                self.logger.error(f"Error stopping trading bot: {e}")
        
        self.logger.info("✅ Server shutdown complete")

async def main():
    """Main server function"""
    server = EnhancedWebhookServer()
    
    try:
        await server.start_server()
    except KeyboardInterrupt:
        await server.shutdown()
    except Exception as e:
        server.logger.error(f"Fatal server error: {e}")
        await server.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ Server failed to start: {e}")
        sys.exit(1)
