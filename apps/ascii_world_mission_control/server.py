import http.server
import socketserver
import subprocess
import os
import tempfile

PORT = 8080
INDEX_FILE = "index.html"
SOCKET_PATH = "/tmp/qemu-monitor.sock"

class MissionControlHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            with open(INDEX_FILE, 'rb') as f:
                self.wfile.write(f.read())
        elif self.path.startswith('/api/frame'):
            self.serve_frame()
        else:
            super().do_GET()

    def serve_frame(self):
        # 1. Check if QEMU socket exists
        if not os.path.exists(SOCKET_PATH):
            self.send_error(404, "QEMU Monitor socket not found")
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            ppm_path = os.path.join(tmpdir, "screen.ppm")
            png_path = os.path.join(tmpdir, "screen.png")

            # 2. Grab screendump via socat
            try:
                # Use socat to send command and ignore output
                cmd = f'echo "screendump {ppm_path}" | socat - UNIX-CONNECT:{SOCKET_PATH}'
                subprocess.run(cmd, shell=True, check=True, timeout=5)
                
                # 3. Convert to PNG
                subprocess.run(['convert', ppm_path, png_path], check=True, timeout=5)
                
                # 4. Serve the PNG
                with open(png_path, 'rb') as f:
                    png_data = f.read()
                
                self.send_response(200)
                self.send_header('Content-type', 'image/png')
                self.send_header('Content-length', str(len(png_data)))
                self.end_headers()
                self.wfile.write(png_data)
            
            except Exception as e:
                print(f"Error capturing frame: {e}")
                self.send_error(500, f"Error capturing frame: {e}")

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), MissionControlHandler) as httpd:
        print(f"ASCII World Mission Control running on http://localhost:{PORT}")
        httpd.serve_forever()
