#!/bin/bash
rm -f /tmp/spatial_compositor.sock
export LIBGL_ALWAYS_SOFTWARE=1
export WGPU_BACKEND=gl
xvfb-run -a -s "-screen 0 1024x768x24" ./target/release/infinite_map_rs > comp.log 2>&1 &
COMP_PID=$!
sleep 5

python3 -c '
import socket, json, os
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
path = os.path.abspath("../../systems/glyph_os/patch_and_copy_demo.rts.png")
s.connect("/tmp/spatial_compositor.sock")
s.sendall(json.dumps({"action": "spawn_image_node", "id": "test_img", "x": 1.0, "y": 1.0, "path": path}).encode() + b"\n")
print("Response:", s.recv(1024).decode().strip())
' >> comp.log 2>&1

sleep 2
# take screenshot using import
DISPLAY=:99 import -window root screenshot.png
kill $COMP_PID
