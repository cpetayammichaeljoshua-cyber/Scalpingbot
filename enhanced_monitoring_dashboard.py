
#!/usr/bin/env python3
"""
Enhanced Monitoring Dashboard
Dynamically perfectly advanced flexible adaptable comprehensive
Web-based monitoring dashboard with real-time status updates
"""

import asyncio
import aiohttp
from aiohttp import web
import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging

class EnhancedMonitoringDashboard:
    """Advanced monitoring dashboard with real-time updates"""
    
    def __init__(self, port: int = 8081):
        self.port = port
        self.app = None
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.repl_name = os.getenv('REPL_SLUG', 'workspace')
        self.repl_owner = os.getenv('REPL_OWNER', 'carlotayam18')
        self.base_url = f"https://{self.repl_name}.{self.repl_owner}.repl.co"
        
        # Monitoring endpoints
        self.endpoints = {
            'health': f"{self.base_url}/health",
            'ping': f"{self.base_url}/ping",
            'keepalive': f"{self.base_url}/keepalive", 
            'status': f"{self.base_url}/status",
            'uptime': f"{self.base_url}:8080"
        }
        
        # Monitoring services configuration
        self.services = {
            'kaffeine': {
                'name': 'Kaffeine',
                'url': 'https://kaffeine.herokuapp.com/',
                'endpoint': 'keepalive',
                'setup_url': 'https://kaffeine.herokuapp.com/',
                'difficulty': 'Easy',
                'features': ['Free', 'No signup', 'Simple setup'],
                'color': '#28a745'
            },
            'uptimerobot': {
                'name': 'UptimeRobot',
                'url': 'https://uptimerobot.com/', 
                'endpoint': 'health',
                'setup_url': 'https://uptimerobot.com/',
                'difficulty': 'Medium',
                'features': ['50 monitors free', 'Email alerts', 'API access'],
                'color': '#007bff'
            },
            'pingdom': {
                'name': 'Pingdom',
                'url': 'https://www.pingdom.com/',
                'endpoint': 'ping',
                'setup_url': 'https://www.pingdom.com/',
                'difficulty': 'Medium', 
                'features': ['Professional monitoring', 'Global locations', 'Reports'],
                'color': '#ffc107'
            },
            'freshping': {
                'name': 'Freshping',
                'url': 'https://www.freshworks.com/website-monitoring/',
                'endpoint': 'status',
                'setup_url': 'https://www.freshworks.com/website-monitoring/',
                'difficulty': 'Easy',
                'features': ['50 checks free', 'Status pages', 'Team collaboration'],
                'color': '#17a2b8'
            }
        }
        
        # Status tracking
        self.endpoint_status = {}
        self.last_check = None
        self.check_history = []
    
    def create_app(self):
        """Create the web application"""
        app = web.Application()
        
        # Routes
        app.router.add_get('/', self.dashboard_handler)
        app.router.add_get('/api/status', self.api_status_handler)
        app.router.add_get('/api/endpoints', self.api_endpoints_handler)
        app.router.add_get('/api/services', self.api_services_handler)
        app.router.add_get('/api/test/{endpoint}', self.api_test_endpoint_handler)
        app.router.add_post('/api/test/all', self.api_test_all_handler)
        
        return app
    
    async def dashboard_handler(self, request):
        """Main dashboard page"""
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Enhanced Monitoring Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            min-height: 100vh;
            padding: 20px;
        }}
        
        .dashboard-container {{
            max-width: 1400px;
            margin: 0 auto;
            background: rgba(255,255,255,0.1);
            border-radius: 20px;
            padding: 30px;
            backdrop-filter: blur(20px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 40px;
            border-bottom: 2px solid rgba(255,255,255,0.2);
            padding-bottom: 20px;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            background: linear-gradient(45deg, #fff, #f0f0f0);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 25px;
            margin-bottom: 30px;
        }}
        
        .card {{
            background: rgba(255,255,255,0.15);
            border-radius: 15px;
            padding: 25px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}
        
        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 12px 40px rgba(0,0,0,0.4);
        }}
        
        .card h3 {{
            margin-bottom: 15px;
            font-size: 1.3em;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .status-indicator {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
            animation: pulse 2s infinite;
        }}
        
        @keyframes pulse {{
            0% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
            100% {{ opacity: 1; }}
        }}
        
        .status-online {{ background: #28a745; }}
        .status-offline {{ background: #dc3545; }}
        .status-testing {{ background: #ffc107; }}
        .status-unknown {{ background: #6c757d; }}
        
        .endpoint-url {{
            font-family: 'Courier New', monospace;
            background: rgba(0,0,0,0.3);
            padding: 10px;
            border-radius: 8px;
            margin: 10px 0;
            word-break: break-all;
            font-size: 0.9em;
        }}
        
        .btn {{
            background: rgba(255,255,255,0.2);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            margin: 5px;
            font-size: 0.9em;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
            text-align: center;
        }}
        
        .btn:hover {{
            background: rgba(255,255,255,0.3);
            transform: translateY(-2px);
        }}
        
        .btn-primary {{ background: rgba(0,123,255,0.8); }}
        .btn-success {{ background: rgba(40,167,69,0.8); }}
        .btn-warning {{ background: rgba(255,193,7,0.8); }}
        .btn-danger {{ background: rgba(220,53,69,0.8); }}
        
        .service-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
        }}
        
        .service-card {{
            background: rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            border-left: 4px solid;
            transition: all 0.3s ease;
        }}
        
        .service-card:hover {{
            background: rgba(255,255,255,0.2);
        }}
        
        .difficulty-easy {{ border-left-color: #28a745; }}
        .difficulty-medium {{ border-left-color: #ffc107; }}
        .difficulty-hard {{ border-left-color: #dc3545; }}
        
        .feature-list {{
            list-style: none;
            margin: 15px 0;
        }}
        
        .feature-list li {{
            padding: 5px 0;
            position: relative;
            padding-left: 20px;
        }}
        
        .feature-list li:before {{
            content: "✓";
            position: absolute;
            left: 0;
            color: #28a745;
            font-weight: bold;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        
        .stat-item {{
            text-align: center;
            padding: 15px;
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
        }}
        
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            display: block;
        }}
        
        .stat-label {{
            font-size: 0.9em;
            opacity: 0.8;
        }}
        
        .loading {{
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 1s ease-in-out infinite;
        }}
        
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
        
        .timestamp {{
            text-align: center;
            opacity: 0.7;
            margin-top: 20px;
            font-size: 0.9em;
        }}
        
        .alert {{
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            border-left: 4px solid;
        }}
        
        .alert-info {{
            background: rgba(23,162,184,0.2);
            border-left-color: #17a2b8;
        }}
        
        .alert-success {{
            background: rgba(40,167,69,0.2);
            border-left-color: #28a745;
        }}
        
        .alert-warning {{
            background: rgba(255,193,7,0.2);
            border-left-color: #ffc107;
        }}
        
        @media (max-width: 768px) {{
            .dashboard-container {{
                padding: 15px;
                margin: 10px;
            }}
            
            .header h1 {{
                font-size: 2em;
            }}
            
            .grid {{
                grid-template-columns: 1fr;
                gap: 15px;
            }}
            
            .btn {{
                padding: 8px 16px;
                margin: 3px;
            }}
        }}
    </style>
    <script>
        let endpoints = {json.dumps(self.endpoints)};
        let services = {json.dumps(self.services)};
        let statusData = {{}};
        
        async function testEndpoint(endpointName) {{
            const statusElement = document.getElementById(endpointName + '-status');
            const indicatorElement = document.getElementById(endpointName + '-indicator');
            const responseElement = document.getElementById(endpointName + '-response');
            
            try {{
                statusElement.textContent = 'Testing...';
                indicatorElement.className = 'status-indicator status-testing';
                
                const startTime = Date.now();
                const response = await fetch(`/api/test/${{endpointName}}`);
                const endTime = Date.now();
                const responseTime = endTime - startTime;
                
                const data = await response.json();
                
                if (data.status === 'success') {{
                    statusElement.textContent = `Online (${{data.status_code}})`;
                    indicatorElement.className = 'status-indicator status-online';
                    responseElement.textContent = `Response: ${{responseTime}}ms`;
                }} else {{
                    statusElement.textContent = `Error: ${{data.error}}`;
                    indicatorElement.className = 'status-indicator status-offline';
                    responseElement.textContent = 'Failed';
                }}
                
                statusData[endpointName] = data;
                updateStats();
                
            }} catch (error) {{
                statusElement.textContent = `Failed: ${{error.message}}`;
                indicatorElement.className = 'status-indicator status-offline';
                responseElement.textContent = 'Error';
            }}
        }}
        
        async function testAllEndpoints() {{
            const button = document.getElementById('test-all-btn');
            button.disabled = true;
            button.innerHTML = '<span class="loading"></span> Testing...';
            
            try {{
                const promises = Object.keys(endpoints).map(endpoint => testEndpoint(endpoint));
                await Promise.all(promises);
            }} finally {{
                button.disabled = false;
                button.innerHTML = '🔄 Test All Endpoints';
            }}
        }}
        
        function updateStats() {{
            const onlineCount = Object.values(statusData).filter(s => s.status === 'success').length;
            const totalCount = Object.keys(statusData).length;
            const offlineCount = totalCount - onlineCount;
            
            document.getElementById('online-count').textContent = onlineCount;
            document.getElementById('offline-count').textContent = offlineCount;
            document.getElementById('total-count').textContent = totalCount;
            
            const uptime = totalCount > 0 ? ((onlineCount / totalCount) * 100).toFixed(1) : '0';
            document.getElementById('uptime-percent').textContent = uptime + '%';
        }}
        
        function openServiceSetup(serviceName) {{
            const service = services[serviceName];
            if (service && service.setup_url) {{
                window.open(service.setup_url, '_blank');
            }}
        }}
        
        function copyEndpointUrl(endpointName) {{
            const url = endpoints[endpointName];
            if (navigator.clipboard) {{
                navigator.clipboard.writeText(url).then(() => {{
                    alert(`Copied to clipboard: ${{url}}`);
                }});
            }} else {{
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = url;
                document.body.appendChild(textArea);
                textArea.select();
                document.execCommand('copy');
                document.body.removeChild(textArea);
                alert(`Copied to clipboard: ${{url}}`);
            }}
        }}
        
        // Auto-refresh functionality
        let autoRefreshInterval;
        
        function startAutoRefresh() {{
            stopAutoRefresh();
            autoRefreshInterval = setInterval(testAllEndpoints, 60000); // Every minute
            document.getElementById('auto-refresh-status').textContent = 'Auto-refresh: ON (60s)';
        }}
        
        function stopAutoRefresh() {{
            if (autoRefreshInterval) {{
                clearInterval(autoRefreshInterval);
                autoRefreshInterval = null;
            }}
            document.getElementById('auto-refresh-status').textContent = 'Auto-refresh: OFF';
        }}
        
        // Initialize dashboard
        window.addEventListener('load', function() {{
            testAllEndpoints();
            startAutoRefresh();
            
            // Update timestamp
            setInterval(() => {{
                document.getElementById('current-time').textContent = new Date().toLocaleString();
            }}, 1000);
        }});
        
        // Cleanup on page unload
        window.addEventListener('beforeunload', stopAutoRefresh);
    </script>
</head>
<body>
    <div class="dashboard-container">
        <div class="header">
            <h1>🚀 Enhanced Monitoring Dashboard</h1>
            <p>Dynamically Perfectly Advanced Flexible Adaptable Comprehensive</p>
            <div class="stats-grid">
                <div class="stat-item">
                    <span class="stat-value" id="online-count">-</span>
                    <span class="stat-label">Online</span>
                </div>
                <div class="stat-item">
                    <span class="stat-value" id="offline-count">-</span>
                    <span class="stat-label">Offline</span>
                </div>
                <div class="stat-item">
                    <span class="stat-value" id="uptime-percent">-</span>
                    <span class="stat-label">Uptime</span>
                </div>
                <div class="stat-item">
                    <span class="stat-value" id="total-count">-</span>
                    <span class="stat-label">Total Endpoints</span>
                </div>
            </div>
            <button id="test-all-btn" class="btn btn-primary" onclick="testAllEndpoints()">🔄 Test All Endpoints</button>
            <button class="btn btn-success" onclick="startAutoRefresh()">▶️ Start Auto-Refresh</button>
            <button class="btn btn-warning" onclick="stopAutoRefresh()">⏸️ Stop Auto-Refresh</button>
        </div>
        
        <div class="alert alert-info">
            <strong>🤖 Bot URL:</strong> {self.base_url}<br>
            <strong>⏰ Dashboard Port:</strong> {self.port}<br>
            <strong>🔄 Auto-refresh:</strong> <span id="auto-refresh-status">Loading...</span>
        </div>
        
        <div class="card">
            <h3>📊 Endpoint Status Monitor</h3>
            <div class="grid">
'''
        
        # Add endpoint monitoring cards
        for endpoint_name, endpoint_url in self.endpoints.items():
            html_content += f'''
                <div class="card">
                    <h3>
                        <span id="{endpoint_name}-indicator" class="status-indicator status-unknown"></span>
                        {endpoint_name.title()} Endpoint
                    </h3>
                    <div class="endpoint-url">{endpoint_url}</div>
                    <p><strong>Status:</strong> <span id="{endpoint_name}-status">Checking...</span></p>
                    <p><strong>Response:</strong> <span id="{endpoint_name}-response">-</span></p>
                    <button class="btn btn-primary" onclick="testEndpoint('{endpoint_name}')">🧪 Test</button>
                    <button class="btn btn-success" onclick="copyEndpointUrl('{endpoint_name}')">📋 Copy URL</button>
                    <a href="{endpoint_url}" target="_blank" class="btn btn-warning">🔗 Open</a>
                </div>
            '''
        
        html_content += '''
            </div>
        </div>
        
        <div class="card">
            <h3>🛠️ Monitoring Services Setup</h3>
            <div class="service-grid">
'''
        
        # Add service setup cards
        for service_key, service in self.services.items():
            difficulty_class = f"difficulty-{service['difficulty'].lower()}"
            endpoint_url = self.endpoints[service['endpoint']]
            
            html_content += f'''
                <div class="service-card {difficulty_class}">
                    <h4 style="color: {service['color']};">{service['name']}</h4>
                    <p><strong>Difficulty:</strong> {service['difficulty']}</p>
                    <p><strong>Endpoint:</strong> <code>/{service['endpoint']}</code></p>
                    <ul class="feature-list">
            '''
            
            for feature in service['features']:
                html_content += f'<li>{feature}</li>'
            
            html_content += f'''
                    </ul>
                    <button class="btn btn-primary" onclick="openServiceSetup('{service_key}')">🚀 Setup {service['name']}</button>
                    <button class="btn btn-success" onclick="copyEndpointUrl('{service['endpoint']}')">📋 Copy URL</button>
                </div>
            '''
        
        html_content += f'''
            </div>
        </div>
        
        <div class="card">
            <h3>📋 Quick Actions</h3>
            <div class="grid">
                <div>
                    <h4>🔗 Direct Links</h4>
                    <a href="{self.base_url}/health" target="_blank" class="btn btn-success">🏥 Health Check</a>
                    <a href="{self.base_url}/status" target="_blank" class="btn btn-primary">📊 Status Page</a>
                    <a href="{self.base_url}:8080" target="_blank" class="btn btn-warning">📈 Uptime Service</a>
                </div>
                <div>
                    <h4>⚙️ Setup Tools</h4>
                    <a href="https://kaffeine.herokuapp.com/" target="_blank" class="btn btn-success">☕ Kaffeine</a>
                    <a href="https://uptimerobot.com/" target="_blank" class="btn btn-primary">🤖 UptimeRobot</a>
                    <a href="https://www.pingdom.com/" target="_blank" class="btn btn-warning">📊 Pingdom</a>
                </div>
            </div>
        </div>
        
        <div class="alert alert-success">
            <h4>💡 Pro Tips for Maximum Uptime</h4>
            <ul>
                <li>Use multiple monitoring services for redundancy</li>
                <li>Set different check intervals (5-30 minutes)</li>
                <li>Configure email and SMS alerts</li>
                <li>Monitor from different geographic locations</li>
                <li>Test your setup regularly</li>
                <li>Keep service credentials secure</li>
            </ul>
        </div>
        
        <div class="timestamp">
            <strong>🕒 Current Time:</strong> <span id="current-time">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span><br>
            <strong>🔧 Generated:</strong> Enhanced Monitoring Dashboard v2.0<br>
            <strong>🎯 Status:</strong> Dynamically Perfectly Advanced Flexible Adaptable Comprehensive
        </div>
    </div>
</body>
</html>'''
        
        return web.Response(text=html_content, content_type='text/html')
    
    async def api_status_handler(self, request):
        """API endpoint for status data"""
        status_data = {
            'timestamp': datetime.now().isoformat(),
            'endpoints': self.endpoint_status,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'base_url': self.base_url,
            'total_endpoints': len(self.endpoints),
            'online_endpoints': len([s for s in self.endpoint_status.values() if s.get('status') == 'success']),
            'dashboard_port': self.port
        }
        
        return web.json_response(status_data)
    
    async def api_endpoints_handler(self, request):
        """API endpoint for endpoints list"""
        return web.json_response(self.endpoints)
    
    async def api_services_handler(self, request):
        """API endpoint for services configuration"""
        return web.json_response(self.services)
    
    async def api_test_endpoint_handler(self, request):
        """API endpoint to test a specific endpoint"""
        endpoint_name = request.match_info['endpoint']
        
        if endpoint_name not in self.endpoints:
            return web.json_response({'error': 'Endpoint not found'}, status=404)
        
        endpoint_url = self.endpoints[endpoint_name]
        
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                start_time = time.time()
                async with session.get(endpoint_url) as response:
                    end_time = time.time()
                    response_time = (end_time - start_time) * 1000
                    
                    result = {
                        'status': 'success',
                        'endpoint': endpoint_name,
                        'url': endpoint_url,
                        'status_code': response.status,
                        'response_time_ms': round(response_time, 2),
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    # Store status
                    self.endpoint_status[endpoint_name] = result
                    self.last_check = datetime.now()
                    
                    return web.json_response(result)
                    
        except Exception as e:
            result = {
                'status': 'error',
                'endpoint': endpoint_name,
                'url': endpoint_url,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
            
            self.endpoint_status[endpoint_name] = result
            return web.json_response(result)
    
    async def api_test_all_handler(self, request):
        """API endpoint to test all endpoints"""
        results = {}
        
        for endpoint_name in self.endpoints.keys():
            # Simulate the individual endpoint test
            result_response = await self.api_test_endpoint_handler(
                type('MockRequest', (), {'match_info': {'endpoint': endpoint_name}})()
            )
            
            if hasattr(result_response, 'json'):
                results[endpoint_name] = await result_response.json()
            else:
                results[endpoint_name] = result_response
        
        summary = {
            'timestamp': datetime.now().isoformat(),
            'total_tested': len(results),
            'successful': len([r for r in results.values() if r.get('status') == 'success']),
            'failed': len([r for r in results.values() if r.get('status') == 'error']),
            'results': results
        }
        
        return web.json_response(summary)
    
    async def start_server(self):
        """Start the monitoring dashboard server"""
        try:
            self.app = self.create_app()
            runner = web.AppRunner(self.app)
            await runner.setup()
            
            site = web.TCPSite(runner, '0.0.0.0', self.port)
            await site.start()
            
            self.logger.info(f"🚀 Enhanced Monitoring Dashboard started on port {self.port}")
            self.logger.info(f"📊 Dashboard URL: {self.base_url}:{self.port}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start dashboard server: {e}")
            return False

async def main():
    """Main function to run the monitoring dashboard"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    dashboard = EnhancedMonitoringDashboard(port=8081)
    
    print("🚀 ENHANCED MONITORING DASHBOARD")
    print("=" * 50)
    print("Dynamically Perfectly Advanced Flexible Adaptable Comprehensive")
    print(f"🌐 Starting dashboard on port {dashboard.port}...")
    
    if await dashboard.start_server():
        print(f"✅ Dashboard started successfully!")
        print(f"📊 Access at: {dashboard.base_url}:{dashboard.port}")
        print("🔄 Real-time endpoint monitoring active")
        print("⚡ Auto-refresh every 60 seconds")
        print()
        print("Press Ctrl+C to stop...")
        
        try:
            # Keep the server running
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Shutting down dashboard...")
    else:
        print("❌ Failed to start dashboard server")

if __name__ == "__main__":
    asyncio.run(main())
