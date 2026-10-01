#!/usr/bin/env python3
import socket
import struct
from PIL import Image
import numpy as np
from agent_bridge import SpatialCompositorClient

def stream_first_frame(host="127.0.0.1", port=5901, node_id="ubuntu_vnc"):
    print(f"[*] Connecting to {host}:{port}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)

    try:
        sock.connect((host, port))

        # Phase 1: Protocol version
        sock.sendall(b'RFB 003.008\n')
        version = sock.recv(12)
        print(f"[+] Version: {version!r}")

        # Phase 2: Security
        sec_count = sock.recv(1)[0]
        sec_types = sock.recv(sec_count)
        sock.sendall(bytes([1]))
        auth = sock.recv(4)
        if auth != b"\x00\x00\x00\x00":
            print(f"[!] Auth failed: {auth!r}")
            return

        print("[+] Auth successful")

        # Phase 3: ClientInit (non-shared)
        sock.sendall(bytes([0]))

        # Phase 4: ServerInit (16 bytes FB info + 4 bytes name length + name)
        fb_info = sock.recv(16)
        width, height, bpp, depth = struct.unpack("!HHBB", fb_info[0:6])
        name_len = struct.unpack("!I", sock.recv(4))[0]
        name = sock.recv(name_len).decode()
        print(f"[+] Framebuffer: {width}x{height}, bpp={bpp}, name={name!r}")

        # Phase 5: SetPixelFormat (32bpp RGBA)
        print("[+] Setting pixel format...")
        # Format: message-type(1) padding(1) bpp(2) depth(2) big-end(1) true-color(1)
        #         red-max(2) green-max(2) blue-max(2) red-shift(1) green-shift(1) blue-shift(1) padding(3)
        fmt = struct.pack("!BHBBBHHHHBBBxxx",
            0,   # message-type (SetPixelFormat)
            0,   # padding
            32,  # bits-per-pixel
            24,  # depth
            0,   # big-endian-flag
            1,   # true-color-flag
            255, 255, 255,  # red/green/blue max
            16, 8, 0         # red/green/blue shift
        )
        msg = struct.pack("!BH", 0, len(fmt)) + fmt
        sock.sendall(msg)

        # Phase 6: SetEncodings (Raw only)
        print("[+] Setting encodings...")
        encodings = [0]
        msg = struct.pack("!BH", 2, len(encodings))
        for enc in encodings:
            msg += struct.pack("!I", enc)
        sock.sendall(msg)

        # Request initial frame (non-incremental)
        print(f"[*] Requesting framebuffer ({width}x{height})...")
        # FramebufferUpdateRequest: B (type) B (padding) B (incremental) H H (x,y) H H (w,h)
        msg = struct.pack("!BBHHHH", 3, 0, 0, 0, 0, width, height)
        sock.sendall(msg)

        # Read FramebufferUpdate
        print("[*] Waiting for FramebufferUpdate...")
        header = sock.recv(4)
        msg_type, padding, n_rects = struct.unpack("!BBH", header)
        print(f"[+] Got update: type={msg_type}, rects={n_rects}")

        if msg_type != 0:
            print(f"[!] Unexpected message type: {msg_type}")
            return

        framebuffer = np.zeros((height, width, 3), dtype=np.uint8)
        total_pixels = 0

        for i in range(n_rects):
            rect_header = sock.recv(12)
            x, y, w, h, enc = struct.unpack("!HHHHi", rect_header)
            print(f"    Rect {i+1}: ({x},{y}) {w}x{h}, enc={enc}")

            if enc == 0:  # Raw encoding
                pixels = bytearray()
                remaining = w * h * 4
                while remaining > 0:
                    chunk = sock.recv(min(remaining, 8192))
                    if not chunk:
                        break
                    pixels.extend(chunk)
                    remaining -= len(chunk)

                # RGBA to RGB, composite into framebuffer
                arr = np.frombuffer(pixels, dtype=np.uint8).reshape(h, w, 4)
                rgb = arr[:, :, [2, 1, 0]]  # BGR to RGB

                if y + h <= height and x + w <= width:
                    framebuffer[y:y+h, x:x+w] = rgb
                    total_pixels += w * h
            else:
                # Skip unsupported encodings
                skip_bytes = w * h * 4
                while skip_bytes > 0:
                    chunk = sock.recv(min(skip_bytes, 8192))
                    if not chunk:
                        break
                    skip_bytes -= len(chunk)

        print(f"[+] Received {total_pixels} pixels")

        # Save and send to compositor
        output_path = "/tmp/qemu_vnc_first_frame.png"
        img = Image.fromarray(framebuffer, 'RGB')
        img.save(output_path)
        print(f"[+] Saved to {output_path}")

        client = SpatialCompositorClient()
        result = client.spawn_image(node_id, 0.0, 0.0, output_path)
        print(f"[+] Compositor spawn result: {result}")

        return True

    except Exception as e:
        print(f"[!] Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        sock.close()

if __name__ == "__main__":
    import sys
    success = stream_first_frame()
    sys.exit(0 if success else 1)