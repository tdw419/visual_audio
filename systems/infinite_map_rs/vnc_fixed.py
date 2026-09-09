#!/usr/bin/env python3
import socket
import struct
import time
from PIL import Image
import numpy as np
from agent_bridge import SpatialCompositorClient

def stream_vnc(host="127.0.0.1", port=5901, node_id="ubuntu_vnc"):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)

    try:
        # Phase 1: Protocol version
        sock.sendall(b"RFB 003.008\n")
        version = sock.recv(12)
        print(f"[+] Version: {version!r}")

        # Phase 2: Security
        sec_count = sock.recv(1)[0]
        sec_types = sock.recv(sec_count)
        sock.sendall(bytes([1]))
        auth = sock.recv(4)
        if auth != b"\x00\x00\x00\x00":
            print("[!] Auth failed")
            return

        # Phase 3: ClientInit
        sock.sendall(bytes([0]))

        # Phase 4: ServerInit (16 bytes FB info + 4 bytes name length + name string)
        fb_info = sock.recv(16)
        width, height, bpp, depth = struct.unpack("!HHBB", fb_info[0:6])
        name_len = struct.unpack("!I", sock.recv(4))[0]
        name = sock.recv(name_len).decode()
        print(f"[+] Framebuffer: {width}x{height}, {bpp}bpp, name={name}")

        # Phase 5: SetPixelFormat (32bpp RGBA)
        fmt = struct.pack("!BxBBBBHHHBBBxxx", 0, 32, 24, 0, 1, 255, 255, 255, 0, 255, 255, 255, 8, 255, 255, 255, 16, 255, 255, 255, 24)
        msg = struct.pack("!BH", 0, len(fmt)) + fmt
        sock.sendall(msg)

        # Phase 6: SetEncodings (Raw only)
        encodings = [0]
        msg = struct.pack("!BH", 2, len(encodings))
        for enc in encodings:
            msg += struct.pack("!I", enc)
        sock.sendall(msg)

        client = SpatialCompositorClient()
        output_path = "/tmp/qemu_vnc_stream.png"

        # Request initial frame
        msg = struct.pack("!BxHHHH", 3, 0, 0, 0, width, height)  # Non-incremental
        sock.sendall(msg)

        # Read FramebufferUpdate
        header = sock.recv(4)
        msg_type, padding, n_rects = struct.unpack("!BBH", header)

        if msg_type != 0:
            print(f"[!] Unexpected message type: {msg_type}")
            return

        print(f"[+] Processing {n_rects} rectangles...")

        framebuffer = np.zeros((height, width, 3), dtype=np.uint8)

        for i in range(n_rects):
            rect_header = sock.recv(12)
            x, y, w, h, enc = struct.unpack("!HHHHi", rect_header)

            if enc == 0:  # Raw
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

        # Save and spawn
        img = Image.fromarray(framebuffer, 'RGB')
        img.save(output_path)

        result = client.spawn_image(node_id, 0.0, 0.0, output_path)
        print(f"[+] Spawn result: {result}")

        print("[+] First frame complete! Would enter streaming loop here...")

    except Exception as e:
        print(f"[!] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sock.close()

if __name__ == "__main__":
    stream_vnc()