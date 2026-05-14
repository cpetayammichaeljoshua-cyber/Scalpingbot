
import http.server
import socketserver
import json
from datetime import datetime

class UpdateHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/update':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            response = {
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "message": "Update handled successfully"
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

if __name__ == "__main__":
    PORT = 8082
    with socketserver.TCPServer(("0.0.0.0", PORT), UpdateHandler) as httpd:
        print(f"Update server running on port {PORT}")
        httpd.serve_forever()
