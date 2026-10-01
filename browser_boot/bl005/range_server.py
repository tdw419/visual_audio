#!/usr/bin/env python3
"""Static file server with real HTTP Range (206 Partial Content) support,
plus COOP/COEP headers. Python's stdlib http.server ignores Range headers
(always serves 200 + full file) — verified empirically before writing this,
not assumed — so BL004's per-sector fetches need this replacement."""
import http.server
import os
import re
import sys


class RangeHandler(http.server.BaseHTTPRequestHandler):
    def end_headers_common(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "bytes")

    def do_GET(self):
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            self.send_error(404)
            return
        size = os.path.getsize(path)
        range_header = self.headers.get("Range")
        ctype = self.guess_type(path)

        if range_header:
            m = re.match(r"bytes=(\d*)-(\d*)", range_header)
            start_s, end_s = m.group(1), m.group(2)
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else size - 1
            end = min(end, size - 1)
            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(length))
            self.end_headers_common()
            self.end_headers()
            with open(path, "rb") as f:
                f.seek(start)
                self.wfile.write(f.read(length))
        else:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(size))
            self.end_headers_common()
            self.end_headers()
            with open(path, "rb") as f:
                self.wfile.write(f.read())

    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        return os.path.join(self.directory, path.lstrip("/"))

    def guess_type(self, path):
        if path.endswith(".wav"):
            return "audio/wav"
        if path.endswith(".html"):
            return "text/html"
        if path.endswith(".js") or path.endswith(".mjs"):
            return "application/javascript"
        if path.endswith(".wasm"):
            return "application/wasm"
        if path.endswith(".gz"):
            return "application/gzip"
        return "application/octet-stream"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8089
    directory = sys.argv[2] if len(sys.argv) > 2 else "."
    RangeHandler.directory = os.path.abspath(directory)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), RangeHandler).serve_forever()
