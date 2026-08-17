import socket
import os

path = "/tmp/spatial_compositor.sock"
if os.path.exists(path): os.remove(path)

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.bind(path)
s.listen(1)

while True:
    conn, addr = s.accept()
    while True:
        data = conn.recv(4096)
        if not data:
            break
        conn.sendall(b'{"status":"ok"}\n')
    conn.close()
