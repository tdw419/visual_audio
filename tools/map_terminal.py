#!/usr/bin/env python3
"""tools/map_terminal.py — First-class GPU OS Terminal Prompter & Controller for Geometry OS.

Allows AI agents (Hermes, Claude, Antigravity) and human operators to directly
drive, prompt, inspect, and verify commands inside terminal window particles
live on the RTX 5090 Infinite Map Compositor substrate.

Usage (CLI):
  python3 tools/map_terminal.py list
  python3 tools/map_terminal.py spawn [node_id] [--cmd <command>] [--x <x>] [--y <y>]
  python3 tools/map_terminal.py exec <command> [--node <node_id>] [--timeout <sec>]
  python3 tools/map_terminal.py read [--node <node_id>]
  python3 tools/map_terminal.py write <text> [--node <node_id>]
  python3 tools/map_terminal.py focus <node_id>
  python3 tools/map_terminal.py close <node_id>
  python3 tools/map_terminal.py send <from_node> <to_node> <payload...>
  python3 tools/map_terminal.py pipe <from_node> <to_node>

Usage (Python API):
  from tools.map_terminal import MapTerminalClient
  client = MapTerminalClient()
  output = client.exec_cmd("uname -a", node_id="hermes_term")
  print(output)
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_SOCKET_PATH = Path("/tmp/spatial_compositor.sock")


class MapTerminalClient:
    """IPC client interface for Geometry OS Infinite Map Compositor."""

    def __init__(self, socket_path: Path = _SOCKET_PATH, timeout: float = 30.0):
        self.socket_path = socket_path
        self.default_timeout = timeout

    def rpc(self, req: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
        """Send JSON-RPC request to compositor socket and receive response."""
        t = timeout or self.default_timeout
        if not self.socket_path.exists():
            raise FileNotFoundError(
                f"Compositor socket '{self.socket_path}' not found. Is infinite_map_rs running?"
            )
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(t)
        try:
            s.connect(str(self.socket_path))
            payload = json.dumps(req) + "\n"
            s.sendall(payload.encode("utf-8"))
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
            if not buf:
                raise ConnectionError(f"No response from compositor socket for request: {req}")
            line = buf.decode("utf-8").splitlines()[0]
            return json.loads(line)
        finally:
            s.close()

    def list_nodes(self) -> List[Dict[str, Any]]:
        """List active window particles on the canvas."""
        res = self.rpc({"action": "list_nodes"})
        nodes = res.get("nodes", [])
        return nodes

    def spawn(
        self,
        node_id: str = "operator_term",
        cmd: Optional[str] = None,
        x: float = 0.0,
        y: float = 0.0,
    ) -> Dict[str, Any]:
        """Spawn a new terminal window particle."""
        req: Dict[str, Any] = {"action": "spawn_node", "id": node_id, "x": x, "y": y}
        if cmd:
            req["cmd"] = cmd
        return self.rpc(req)

    def ensure_node(self, node_id: str = "operator_term", cmd: Optional[str] = None) -> str:
        """Ensure a terminal node exists, spawning it if absent."""
        existing = self.list_nodes()
        existing_ids = [n if isinstance(n, str) else n.get("id") for n in existing]
        if node_id not in existing_ids:
            self.spawn(node_id=node_id, cmd=cmd)
            time.sleep(0.3)
        return node_id

    def focus(self, node_id: str, zoom: Optional[float] = None) -> Dict[str, Any]:
        """Focus camera and input on node."""
        req: Dict[str, Any] = {"action": "focus_node", "id": node_id}
        if zoom is not None:
            req["zoom"] = zoom
        return self.rpc(req)

    def close(self, node_id: str) -> Dict[str, Any]:
        """Close and reap a spatial node particle."""
        return self.rpc({"action": "close_node", "id": node_id})

    def write(self, data: str, node_id: str = "") -> Dict[str, Any]:
        """Write raw keystroke/text bytes to node's PTY."""
        return self.rpc({"action": "write_node", "id": node_id, "data": data})

    def type_text(self, text: str, node_id: Optional[str] = None) -> Dict[str, Any]:
        """Route text directly to targeted or focused spatial node."""
        req: Dict[str, Any] = {"action": "type_node", "text": text}
        if node_id:
            req["id"] = node_id
        return self.rpc(req)

    def read(self, node_id: str = "") -> List[str]:
        """Read formatted screen lines from node (or currently focused node)."""
        res = self.rpc({"action": "read_node", "id": node_id})
        return res.get("lines", [])

    def exec_cmd(
        self,
        command: str,
        node_id: Optional[str] = None,
        timeout: float = 15.0,
        poll_interval: float = 0.2,
    ) -> str:
        """Prompt and execute a command in the GPU OS terminal, waiting for output."""
        target_id = node_id or "operator_term"
        self.ensure_node(target_id)
        self.focus(target_id)

        # Baseline snapshot
        before_lines = self.read(target_id)
        before_count = len(before_lines)

        # Send command with newline
        self.write(command.strip() + "\n", target_id)

        # Poll for output stabilization
        deadline = time.time() + timeout
        last_seen = before_lines
        stable_count = 0

        while time.time() < deadline:
            time.sleep(poll_interval)
            current = self.read(target_id)
            if current != last_seen:
                last_seen = current
                stable_count = 0
            else:
                stable_count += 1
                if stable_count >= 2 and len(current) > 0:
                    break

        # Extract output rows
        clean_lines = [l.rstrip() for l in last_seen if l.strip()]
        return "\n".join(clean_lines)

    def transmit_packet(
        self,
        from_node: str,
        to_node: str,
        payload: str,
        speed: float = 2.0,
        auto_exec: bool = True,
    ) -> Dict[str, Any]:
        """Transmit a discrete traveling data packet along an edge."""
        return self.rpc({
            "action": "transmit_packet",
            "from": from_node,
            "to": to_node,
            "payload": payload,
            "speed": speed,
            "auto_exec": auto_exec,
        })

    def pipe_data(self, from_node: str, to_node: str, speed: float = 2.0) -> Dict[str, Any]:
        """Pipe output of from_node into to_node."""
        return self.rpc({
            "action": "pipe_data",
            "from": from_node,
            "to": to_node,
            "speed": speed,
        })


def main():
    parser = argparse.ArgumentParser(
        description="Prompt and control the Geometry OS Infinite Map terminal particle."
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # list
    subparsers.add_parser("list", help="List all active spatial window particles.")

    # spawn
    p_spawn = subparsers.add_parser("spawn", help="Spawn a new terminal window particle.")
    p_spawn.add_argument("node_id", nargs="?", default="operator_term", help="ID for node.")
    p_spawn.add_argument("--cmd", default=None, help="Shell or binary command to run in PTY.")
    p_spawn.add_argument("--x", type=f32 if "f32" in globals() else float, default=0.0, help="Initial X coordinate.")
    p_spawn.add_argument("--y", type=float, default=0.0, help="Initial Y coordinate.")

    # exec
    p_exec = subparsers.add_parser("exec", help="Execute command inside in-map terminal and print output.")
    p_exec.add_argument("command", help="Shell command to run.")
    p_exec.add_argument("--node", default="operator_term", help="Target node ID.")
    p_exec.add_argument("--timeout", type=float, default=15.0, help="Execution timeout in seconds.")

    # read
    p_read = subparsers.add_parser("read", help="Read current screen lines from terminal node.")
    p_read.add_argument("--node", default="", help="Node ID (empty for focused node).")

    # write
    p_write = subparsers.add_parser("write", help="Write raw text to node PTY.")
    p_write.add_argument("text", help="Text/keystrokes to write.")
    p_write.add_argument("--node", default="", help="Node ID (empty for focused node).")

    # focus
    p_focus = subparsers.add_parser("focus", help="Focus camera and input on node.")
    p_focus.add_argument("node_id", help="Node ID to focus.")

    # close
    p_close = subparsers.add_parser("close", help="Close node particle.")
    p_close.add_argument("node_id", help="Node ID to close.")

    # send
    p_send = subparsers.add_parser("send", help="Transmit data packet along edge beam.")
    p_send.add_argument("from_node", help="Source node ID.")
    p_send.add_argument("to_node", help="Target node ID.")
    p_send.add_argument("payload", help="Payload string to transmit.")

    # pipe
    p_pipe = subparsers.add_parser("pipe", help="Pipe output of from_node to to_node.")
    p_pipe.add_argument("from_node", help="Source node ID.")
    p_pipe.add_argument("to_node", help="Target node ID.")

    args = parser.parse_args()
    client = MapTerminalClient()

    if args.subcommand == "list":
        nodes = client.list_nodes()
        print(f"Active spatial nodes ({len(nodes)}):")
        for n in nodes:
            print(f"  - {n}")

    elif args.subcommand == "spawn":
        res = client.spawn(node_id=args.node_id, cmd=args.cmd, x=args.x, y=args.y)
        print(f"Spawned: {res.get('message', res.get('status'))}")

    elif args.subcommand == "exec":
        output = client.exec_cmd(command=args.command, node_id=args.node, timeout=args.timeout)
        print(output)

    elif args.subcommand == "read":
        lines = client.read(node_id=args.node)
        print("\n".join(lines))

    elif args.subcommand == "write":
        res = client.write(data=args.text, node_id=args.node)
        print(f"Write result: {res.get('status')}")

    elif args.subcommand == "focus":
        res = client.focus(node_id=args.node_id)
        print(f"Focus result: {res.get('status')}")

    elif args.subcommand == "close":
        res = client.close(node_id=args.node_id)
        print(f"Close result: {res.get('status')}")

    elif args.subcommand == "send":
        res = client.transmit_packet(from_node=args.from_node, to_node=args.to_node, payload=args.payload)
        print(f"Transmit result: {res.get('status')} ({res.get('message')})")

    elif args.subcommand == "pipe":
        res = client.pipe_data(from_node=args.from_node, to_node=args.to_node)
        print(f"Pipe result: {res.get('status')} ({res.get('message')})")


if __name__ == "__main__":
    main()
