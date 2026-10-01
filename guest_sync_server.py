#!/usr/bin/env python3
"""
Quick sync server - simple HTTP server for transferring Hermes data
Run inside guest to receive files from host
"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import os
import sys

# Change to Hermes directory
os.chdir('/home/ubuntu/.hermes')

# Custom handler that allows PUT for uploads
class SyncHandler(SimpleHTTPRequestHandler):
    def do_PUT(self):
        path = self.translate_path(self.path)
        if path.endswith('/') or os.path.isdir(path):
            self.send_error(400, "Directory upload not supported")
            return
        
        directory = os.path.dirname(path)
        if not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        
        length = self.headers.get('content-length')
        if length:
            length = int(length)
            with open(path, 'wb') as f:
                f.write(self.rfile.read(length))
        
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass

if __name__ == '__main__':
    PORT = 8769
    server = HTTPServer(('0.0.0.0', PORT), SyncHandler)
    print(f"Sync server running on port {PORT}")
    print(f"Serving {os.getcwd()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()