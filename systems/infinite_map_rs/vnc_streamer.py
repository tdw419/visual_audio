#!/usr/bin/env python3
"""
VNC Frame Streamer - Live QEMU VNC to infinite_map_rs compositor bridge

Uses vncdotool library instead of hand-rolled RFB parser.
Captures full frames at ~30fps and updates compositor node.
"""
import time
import sys
import os
import signal
from PIL import Image
import numpy as np

# Import vncdotool with fallback
try:
    from vncdotool import api
except ImportError:
    print("[!] vncdotool not available, install with: pip install vncdotool")
    sys.exit(1)

from agent_bridge import SpatialCompositorClient

class VNCStreamer:
    def __init__(self, host="127.0.0.1", port=5901, node_id="ubuntu_vnc", fps=30):
        self.host = host
        self.port = port
        self.node_id = node_id
        self.fps = fps
        self.client = None
        self.compositor = None
        self.output_path = "/tmp/qemu_vnc_stream.png"
        self.running = False

    def connect(self):
        print(f"[*] Connecting to VNC at {self.host}:{self.port}...")
        try:
            self.client = api.connect(f"{self.host}:{self.port}", timeout=10)
            print(f"[+] Connected to VNC server")
            self.compositor = SpatialCompositorClient()
            return True
        except Exception as e:
            print(f"[!] VNC connection failed: {e}")
            return False

    def capture_and_send(self, first_frame=False):
        try:
            # Capture full frame
            img = self.client.captureScreen()
            if img is None:
                print("[!] captureScreen returned None")
                return False

            # Save to temp file
            img.save(self.output_path)

            # Send to compositor
            if first_frame:
                print(f"[*] Spawning image node: {self.node_id} ({img.width}x{img.height})")
                result = self.compositor.spawn_image(self.node_id, 0.0, 0.0, self.output_path)
                if result.get("status") != "ok":
                    print(f"[!] Spawn failed: {result}")
                    return False
            else:
                result = self.compositor.update_image(self.node_id, self.output_path)
                if result.get("status") != "ok":
                    print(f"[!] Update failed: {result}")
                    return False

            return True
        except Exception as e:
            print(f"[!] Capture error: {e}")
            return False

    def run(self):
        if not self.connect():
            return

        self.running = True
        first_frame = True
        frame_interval = 1.0 / self.fps

        print(f"[*] Starting stream at {self.fps} FPS...")
        print("[*] Press Ctrl-C to stop")

        # Set up graceful shutdown
        def signal_handler(sig, frame):
            print("\n[*] Stopping VNC streamer...")
            self.running = False
        signal.signal(signal.SIGINT, signal_handler)

        while self.running:
            start_time = time.time()

            if not self.capture_and_send(first_frame=first_frame):
                time.sleep(1)
                continue

            if first_frame:
                first_frame = False
                print("[+] Streaming frames...")

            # Maintain frame rate
            elapsed = time.time() - start_time
            sleep_time = max(0, frame_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

        print("[*] Disconnected")

if __name__ == "__main__":
    # Parse args: [host] [port] [node_id] [fps]
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5901
    node_id = sys.argv[3] if len(sys.argv) > 3 else "ubuntu_vnc"
    fps = int(sys.argv[4]) if len(sys.argv) > 4 else 30

    streamer = VNCStreamer(host, port, node_id, fps)
    streamer.run()