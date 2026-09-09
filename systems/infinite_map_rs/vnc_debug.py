#!/usr/bin/env python3
import socket
import struct
import time
import sys
from PIL import Image
import numpy as np
from agent_bridge import SpatialCompositorClient

def debug_log(msg):
    print(f"[DEBUG] {msg}")
    sys.stdout.flush()

def vnc_protocol_version(sock):
    debug_log("Sending protocol version...")
    sock.sendall(b"RFB 003.008\n")
    version = sock.recv(12)
    debug_log(f"Server version: {version!r}")

def vnc_handshake(sock):
    debug_log("Reading security count...")
    sec_count = sock.recv(1)[0]
    debug_log(f"Security types available: {sec_count}")

    debug_log("Reading security types...")
    sec_types = sock.recv(sec_count)
    debug_log(f"Security types: {sec_types!r}")

    if 1 in sec_types:
        debug_log("Requesting None auth...")
        sock.sendall(bytes([1]))
    else:
        debug_log("No supported auth!")
        return False

    debug_log("Reading auth result...")
    result = sock.recv(4)
    debug_log(f"Auth result: {result!r}")
    return result == b"\x00\x00\x00\x00"

def vnc_client_init(sock):
    debug_log("Sending ClientInit (non-shared)...")
    sock.sendall(bytes([0]))

    debug_log("Reading ServerInit...")
    fb_info = sock.recv(24)
    width, height = struct.unpack("!HH", fb_info[0:4])
    bpp, depth = struct.unpack("BB", fb_info[4:6])
    name_len = struct.unpack("!I", sock.recv(4))[0]
    name = sock.recv(name_len)

    debug_log(f"Framebuffer: {width}x{height}, {bpp}bpp, {depth}depth")
    debug_log(f"Desktop name: {name!r}")
    return width, height, bpp

def vnc_set_pixel_format(sock):
    debug_log("Setting pixel format (32bpp RGBA)...")
    fmt = struct.pack("!BxBBBBHHHBBBxxx", 0, 32, 24, 0, 1, 255, 255, 255, 0, 255, 255, 255, 8, 255, 255, 255, 16, 255, 255, 255, 24)
    msg = struct.pack("!BH", 0, len(fmt)) + fmt
    sock.sendall(msg)
    debug_log("Pixel format set")

def vnc_set_encodings(sock):
    debug_log("Setting encodings (Raw only)...")
    encodings = [0]
    msg = struct.pack("!BH", 2, len(encodings))
    for enc in encodings:
        msg += struct.pack("!I", enc)
    sock.sendall(msg)
    debug_log("Encodings set")

def vnc_request_framebuffer(sock, x, y, w, h, incremental=0):
    debug_log(f"Requesting framebuffer: incremental={incremental}, rect=({x},{y}) {w}x{h}")
    msg = struct.pack("!BxHHHH", 3, incremental, x, y, w, h)
    sock.sendall(msg)
    debug_log("Request sent")

def stream_vnc(host="127.0.0.1", port=5901, node_id="ubuntu_vnc"):
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        debug_log(f"Connecting to {host}:{port}...")
        sock.connect((host, port))
        debug_log("Connected!")

        vnc_protocol_version(sock)
        if not vnc_handshake(sock):
            debug_log("Auth failed!")
            return

        width, height, bpp = vnc_client_init(sock)
        debug_log(f"ClientInit complete: {width}x{height}, {bpp}bpp")

        vnc_set_pixel_format(sock)
        vnc_set_encodings(sock)

        client = SpatialCompositorClient()
        output_path = "/tmp/qemu_vnc_stream.png"

        # Initial full-frame request
        debug_log("Requesting initial frame (non-incremental)...")
        vnc_request_framebuffer(sock, 0, 0, width, height, incremental=0)

        # Wait for response with timeout
        debug_log("Waiting for FramebufferUpdate response...")
        header = sock.recv(4)
        debug_log(f"Got header: {header!r}")

        if not header or len(header) < 4:
            debug_log("No header received!")
            return

        msg_type, padding, n_rects = struct.unpack("!BBH", header)
        debug_log(f"Message type={msg_type}, n_rects={n_rects}")

        if msg_type != 0:
            debug_log(f"Unexpected message type: {msg_type}")
            return

        debug_log(f"Processing {n_rects} rectangles...")
        for i in range(n_rects):
            debug_log(f"Rect {i+1}/{n_rects}...")
            rect_header = sock.recv(12)
            x, y, w, h, enc = struct.unpack("!HHHHi", rect_header)
            debug_log(f"  Rect: ({x},{y}) {w}x{h}, enc={enc}")

            if enc == 0:  # Raw
                debug_log(f"  Reading {w*h*4} bytes...")
                pixels = bytearray()
                remaining = w * h * 4
                while remaining > 0:
                    chunk = sock.recv(min(remaining, 8192))
                    if not chunk:
                        debug_log("  Connection closed mid-rect!")
                        break
                    pixels.extend(chunk)
                    remaining -= len(chunk)
                debug_log(f"  Got {len(pixels)} bytes")

                arr = np.frombuffer(pixels, dtype=np.uint8).reshape(h, w, 4)
                rgb = arr[:, :, [2, 1, 0]]
                img = Image.fromarray(rgb, 'RGB')
                img.save(output_path)
                debug_log(f"  Saved to {output_path}")

                # Send to compositor
                result = client.spawn_image(node_id, 0.0, 0.0, output_path)
                debug_log(f"  Spawn result: {result}")
            else:
                debug_log(f"  Unsupported encoding {enc}, skipping")
                skip_bytes = w * h * 4
                while skip_bytes > 0:
                    chunk = sock.recv(min(skip_bytes, 8192))
                    if not chunk:
                        break
                    skip_bytes -= len(chunk)

        debug_log("First frame complete!")

    except socket.timeout:
        debug_log("Socket timeout!")
    except Exception as e:
        debug_log(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if sock:
            debug_log("Closing socket...")
            sock.close()

if __name__ == "__main__":
    stream_vnc()