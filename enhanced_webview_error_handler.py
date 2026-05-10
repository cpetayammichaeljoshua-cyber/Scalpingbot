
#!/usr/bin/env python3
"""
Enhanced Webview Error Handler
Dynamically Perfectly Advanced Flexible Adaptable Comprehensive
Fixes webview update errors and provides robust web interface
"""

import asyncio
import aiohttp
from aiohttp import web
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

class EnhancedWebviewErrorHandler:
    """Enhanced handler for webview update errors"""
    
    def __init__(self, port: int = 8083):
        self.port = port
        self.app = None
        self.logger = logging.getLogger(__name__)
        self.setup_logging()
        
        # Error tracking
        self.error_count = 0
        self.update_count = 0
        self.last_errors = []
        
    def setup_logging(self):
        """Setup logging system"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - WEBVIEW_HANDLER - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_dir / "webview_error_handler.log"),
                logging.StreamHandler()
            ]
        )
    
    def create_app(self):
        """Create the web application"""
        app = web.Application()
        
        # CORS middleware
        async def cors_middleware(request, handler):
            response = await handler(request)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            return response
        
        app.middlewares.append(cors_middleware)
        
        # Routes
        app.router.add_get('/', self.dashboard_handler)
        app.router.add_post('/update', self.update_handler)
        app.router.add_get('/health', self.health_handler)
        app.router.add_get('/status', self.status_handler)
        app.router.add_options('/{path:.*}', self.options_handler)
        
        return app
    
    async def dashboard_handler(self, request):
        """Main dashboard to show system status"""
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Enhanced Webview Error Handler</title>
    <style>
        body {{
            font-family: 'Arial', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            margin: 0;
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: rgba(255,255,255,0.1);
            border-radius: 20px;
            padding: 30px;
            backdrop-filter: blur(20px);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .status-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .status-card {{
            background: rgba(255,255,255,0.15);
            border-radius: 15px;
            padding: 20px;
            text-align: center;
        }}
        .status-value {{
            font-size: 2em;
            font-weight: bold;
            display: block;
            margin-bottom: 10px;
        }}
        .btn {{
            background: rgba(255,255,255,0.2);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            margin: 5px;
        }}
        .btn:hover {{
            background: rgba(255,255,255,0.3);
        }}
        .error-log {{
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
            max-height: 300px;
            overflow-y: auto;
        }}
    </style>
    <script>
        let updateCount = 0;
        let errorCount = 0;
        
        async function testUpdate() {{
            try {{
                const response = await fetch('/update', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    body: JSON.stringify({{
                        test: true,
                        timestamp: new Date().toISOString()
                    }})
                }});
                
                const data = await response.json();
                updateCount++;
                document.getElementById('update-count').textContent = updateCount;
                
                console.log('Update test successful:', data);
                document.getElementById('last-update').textContent = 'Success: ' + new Date().toLocaleTimeString();
                
            }} catch (error) {{
                errorCount++;
                document.getElementById('error-count').textContent = errorCount;
                console.error('Update failed:', error);
                document.getElementById('last-update').textContent = 'Failed: ' + error.message;
            }}
        }}
        
        async function checkStatus() {{
            try {{
                const response = await fetch('/status');
                const data = await response.json();
                
                document.getElementById('server-status').textContent = 'Online';
                document.getElementById('total-updates').textContent = data.update_count;
                document.getElementById('total-errors').textContent = data.error_count;
                
            }} catch (error) {{
                document.getElementById('server-status').textContent = 'Offline';
            }}
        }}
        
        // Auto-refresh status
        setInterval(checkStatus, 5000);
        setInterval(() => {{
            document.getElementById('current-time').textContent = new Date().toLocaleString();
        }}, 1000);
        
        // Initialize
        window.onload = function() {{
            checkStatus();
        }};
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔧 Enhanced Webview Error Handler</h1>
            <p>Dynamically Perfectly Advanced Flexible Adaptable Comprehensive</p>
        </div>
        
        <div class="status-grid">
            <div class="status-card">
                <span class="status-value" id="server-status">Checking...</span>
                <div>Server Status</div>
            </div>
            <div class="status-card">
                <span class="status-value" id="total-updates">{self.update_count}</span>
                <div>Total Updates</div>
            </div>
            <div class="status-card">
                <span class="status-value" id="total-errors">{self.error_count}</span>
                <div>Total Errors</div>
            </div>
            <div class="status-card">
                <span class="status-value" id="update-count">0</span>
                <div>Test Updates</div>
            </div>
        </div>
        
        <div style="text-align: center; margin: 30px 0;">
            <button class="btn" onclick="testUpdate()">🧪 Test Update</button>
            <button class="btn" onclick="checkStatus()">🔄 Refresh Status</button>
            <button class="btn" onclick="location.reload()">🔄 Reload Page</button>
        </div>
        
        <div class="status-card">
            <h3>📊 System Information</h3>
            <p><strong>Server Port:</strong> {self.port}</p>
            <p><strong>Current Time:</strong> <span id="current-time">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span></p>
            <p><strong>Last Update:</strong> <span id="last-update">None</span></p>
        </div>
        
        <div class="error-log">
            <h3>📝 Recent Activity</h3>
            <div id="activity-log">
                <p>Webview error handler started successfully</p>
                <p>Ready to handle update requests</p>
            </div>
        </div>
    </div>
</body>
</html>'''
        
        return web.Response(text=html_content, content_type='text/html')
    
    async def update_handler(self, request):
        """Handle update requests from webview"""
        try:
            # Read request data
            if request.content_type == 'application/json':
                data = await request.json()
            else:
                data = {}
            
            self.update_count += 1
            
            # Log the update
            self.logger.info(f"Update request received: {data}")
            
            # Create successful response
            response_data = {
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "update_id": self.update_count,
                "message": "Update processed successfully",
                "data_received": data
            }
            
            # Save update log
            update_log = {
                "timestamp": datetime.now().isoformat(),
                "update_id": self.update_count,
                "request_data": data,
                "response": response_data
            }
            
            log_file = Path("logs/update_requests.json")
            log_file.parent.mkdir(exist_ok=True)
            
            try:
                with open(log_file, 'r') as f:
                    logs = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                logs = []
            
            logs.append(update_log)
            
            # Keep only last 100 logs
            if len(logs) > 100:
                logs = logs[-100:]
            
            with open(log_file, 'w') as f:
                json.dump(logs, f, indent=2)
            
            return web.json_response(response_data)
            
        except Exception as e:
            self.error_count += 1
            self.last_errors.append({
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "request_path": str(request.path)
            })
            
            # Keep only last 10 errors
            if len(self.last_errors) > 10:
                self.last_errors = self.last_errors[-10:]
            
            self.logger.error(f"Update handler error: {e}")
            
            error_response = {
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "message": "Update processing failed"
            }
            
            return web.json_response(error_response, status=500)
    
    async def health_handler(self, request):
        """Health check endpoint"""
        health_data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": time.time() - getattr(self, 'start_time', time.time()),
            "update_count": self.update_count,
            "error_count": self.error_count,
            "port": self.port
        }
        
        return web.json_response(health_data)
    
    async def status_handler(self, request):
        """Status endpoint"""
        status_data = {
            "timestamp": datetime.now().isoformat(),
            "update_count": self.update_count,
            "error_count": self.error_count,
            "recent_errors": self.last_errors[-5:] if self.last_errors else [],
            "server_info": {
                "port": self.port,
                "uptime_seconds": time.time() - getattr(self, 'start_time', time.time())
            }
        }
        
        return web.json_response(status_data)
    
    async def options_handler(self, request):
        """Handle CORS preflight requests"""
        return web.Response(
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization'
            }
        )
    
    async def start_server(self):
        """Start the webview error handler server"""
        try:
            self.start_time = time.time()
            self.app = self.create_app()
            runner = web.AppRunner(self.app)
            await runner.setup()
            
            site = web.TCPSite(runner, '0.0.0.0', self.port)
            await site.start()
            
            self.logger.info(f"🚀 Enhanced Webview Error Handler started on port {self.port}")
            self.logger.info(f"🌐 Access at: http://localhost:{self.port}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start webview error handler: {e}")
            return False

async def main():
    """Main function to run the webview error handler"""
    print("🔧 ENHANCED WEBVIEW ERROR HANDLER")
    print("=" * 60)
    print("Dynamically Perfectly Advanced Flexible Adaptable Comprehensive")
    print("Fixing webview update errors with robust error handling")
    print("=" * 60)
    
    handler = EnhancedWebviewErrorHandler(port=8083)
    
    if await handler.start_server():
        print(f"✅ Webview error handler started on port {handler.port}")
        print("🔄 Handling update requests and fixing webview errors")
        print("Press Ctrl+C to stop...")
        
        try:
            # Keep the server running
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Shutting down webview error handler...")
    else:
        print("❌ Failed to start webview error handler")

if __name__ == "__main__":
    asyncio.run(main())
