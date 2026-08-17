#!/usr/bin/env python3
import socket
import json

SOCKET_PATH = "/tmp/spatial_compositor.sock"

class SpatialCompositorClient:
    def __init__(self, path=SOCKET_PATH):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path)
        self.reader = self.sock.makefile('r')

    def send(self, payload: dict) -> dict:
        req = json.dumps(payload) + "\n"
        self.sock.sendall(req.encode('utf-8'))
        resp = self.reader.readline()
        return json.loads(resp)

    def spawn(self, node_id: str, x: float, y: float, cmd: str = None):
        return self.send({"action": "spawn_node", "id": node_id, "x": x, "y": y, "cmd": cmd})

    def read(self, node_id: str):
        return self.send({"action": "read_node", "id": node_id})

    def write(self, node_id: str, text: str):
        return self.send({"action": "write_node", "id": node_id, "data": text})

    def focus(self, node_id: str, zoom: float = 1.2):
        return self.send({"action": "focus_node", "id": node_id, "zoom": zoom})

    def set_annotations(self, items: list):
        return self.send({"action": "set_annotations", "items": items})

    def layout_nodes(self, mode: str = "grid"):
        return self.send({"action": "layout_nodes", "mode": mode})

    def update_markdown(self, node_id: str, x: float, y: float, source: str):
        return self.send({"action": "update_markdown", "id": node_id, "x": x, "y": y, "source": source})

    def close_node(self, node_id: str):
        return self.send({"action": "close_node", "id": node_id})

if __name__ == "__main__":
    client = SpatialCompositorClient()
    
    # 1. Spawn a dedicated build monitor node in AI space
    client.spawn("user_sh", x=2.2, y=0.0, cmd="cargo watch -x check")
    
    # 2. Draw some annotations
    client.set_annotations([
        {
            "type": "box",
            "node_id": "user_sh",
            "line_start": 8,
            "line_count": 3,
            "color": [1.0, 0.6, 0.0, 0.85],
            "thickness": 0.008
        },
        {
            "type": "arrow",
            "from": [1.2, 0.0],
            "to": [-0.1, 0.15],
            "color": [0.0, 1.0, 0.8, 0.9],
            "thickness": 0.012
        }
    ])
