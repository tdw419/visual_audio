#!/usr/bin/env python3
"""Static file server with COOP/COEP headers (required for OPFS sync access
handles / SharedArrayBuffer). Serves the given directory (default: cwd)."""
import http.server, sys, os

class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8088
    os.chdir(sys.argv[2] if len(sys.argv) > 2 else ".")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
