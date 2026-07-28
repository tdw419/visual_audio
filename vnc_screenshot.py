#!/usr/bin/env python3
import socket
import struct
import io
from PIL import Image
import numpy as np

def vnc_protocol_version(sock):
    version = sock.recv(12)
    sock.sendall(b"RFB 003.008\n")

def vnc_handshake(sock):
    sec_count = sock.recv(1)[0]
    sec_types = sock.recv(sec_count)

    if 1 in sec_types:
        sock.sendall(bytes([1]))
    else:
        return False

    result = sock.recv(4)
    return result == b"\x00\x00\x00\x00"

def vnc_client_init(sock):
    sock.sendall(bytes([1]))

    fb_info = sock.recv(24)
    width, height = struct.unpack("!HH", fb_info[0:4])
    bpp, depth = struct.unpack("BB", fb_info[4:6])
    big_endian = fb_info[6]
    true_color = fb_info[7]

    name_len = struct.unpack("!I", sock.recv(4))[0]
    name = sock.recv(name_len)

    return width, height, bpp

def vnc_request_framebuffer(sock, x, y, w, h, incremental=0):
    msg = struct.pack("!BxHHHH", 3, incremental, x, y, w, h)
    sock.sendall(msg)

def vnc_set_pixel_format(sock):
    fmt = struct.pack("!BxBBBBHHHBBBxxx",
                      0,      # pad
                      32,     # bits-per-pixel
                      24,     # depth
                      0,      # big-endian
                      1,      # true-color
                      255, 255, 255, 0,    # red max, shift
                      255, 255, 255, 8,    # green max, shift
                      255, 255, 255, 16,   # blue max, shift
                      255, 255, 255, 24    # alpha? max, shift
    )
    msg = struct.pack("!BH", 0, len(fmt)) + fmt
    sock.sendall(msg)

def vnc_set_encodings(sock):
    encodings = [0, 1]  # Raw and CopyRect
    msg = struct.pack("!BH", 2, len(encodings))
    for enc in encodings:
        msg += struct.pack("!I", enc)
    sock.sendall(msg)

def capture_screenshot(host="127.0.0.1", port=5901, output="vnc_screenshot.png"):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        print(f"Connected to VNC {host}:{port}")

        vnc_protocol_version(sock)
        if not vnc_handshake(sock):
            print("Auth failed")
            return False

        width, height, bpp = vnc_client_init(sock)
        print(f"Framebuffer: {width}x{height}, {bpp}bpp")

        vnc_set_pixel_format(sock)
        vnc_set_encodings(sock)

        # Request full framebuffer
        vnc_request_framebuffer(sock, 0, 0, width, height, incremental=0)

        # Read framebuffer update message
        header = sock.recv(4)
        msg_type, padding, n_rects = struct.unpack("!BBH", header)
        print(f"Update: msg_type={msg_type}, rects={n_rects}")

        # Read raw rectangle data
        rect_header = sock.recv(12)
        x, y, w, h, enc = struct.unpack("!HHHHi", rect_header)
        print(f"Rect: {x},{y} {w}x{h}, enc={enc}")

        # Read pixel data
        pixels = bytearray()
        remaining = w * h * 4  # 32bpp
        while remaining > 0:
            chunk = sock.recv(min(remaining, 4096))
            if not chunk:
                break
            pixels.extend(chunk)
            remaining -= len(chunk)

        print(f"Received {len(pixels)} bytes (expected {w*h*4})")

        # Convert to image
        arr = np.frombuffer(pixels, dtype=np.uint8).reshape(h, w, 4)
        # VNC sends BGR, convert to RGB
        rgb = arr[:, :, [2, 1, 0]]
        img = Image.fromarray(rgb, 'RGB')
        img.save(output)
        print(f"Screenshot saved to {output}")
        sock.close()
        return True

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    capture_screenshot()