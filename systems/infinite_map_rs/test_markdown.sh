#!/bin/bash
rm -f /tmp/spatial_compositor.sock
LIBGL_ALWAYS_SOFTWARE=1 WGPU_BACKEND=gl xvfb-run -a ./target/release/infinite_map_rs > comp.log 2>&1 &
COMP_PID=$!
sleep 4

python3 -c '
import socket, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect("/tmp/spatial_compositor.sock")
s.sendall(json.dumps({"action": "update_markdown", "id": "test_md", "x": 1.0, "y": 1.0, "source": "## Hello from the test script"}).encode() + b"\n")
print("Response 1:", s.recv(1024).decode().strip())

# List nodes to verify the node was created
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect("/tmp/spatial_compositor.sock")
s.sendall(json.dumps({"action": "list_nodes"}).encode() + b"\n")
print("Response 2:", s.recv(1024).decode().strip())
'

kill $COMP_PID
cat comp.log
