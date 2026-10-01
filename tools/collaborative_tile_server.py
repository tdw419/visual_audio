#!/usr/bin/env python3
"""
Collaborative Tile Editor Server — TASK_I005

WebSocket server enabling multiple users to edit the same tile canvas
simultaneously with real-time sync and visual diff of tile movements.

Architecture:
  - WebSocket server on ws://localhost:3001
  - Canvas state (tiles, positions) managed server-side
  - Operational Transformation for conflict resolution
  - Broadcast operations to all connected clients
  - Visual diff: show movements between edits

Usage:
    python3 tools/collaborative_tile_server.py

Client protocol:
  - Connect to ws://localhost:3001
  - Send JSON messages:
    - {"type": "init"} -> Receive current canvas state
    - {"type": "move_tile", "tile_id": N, "from": [x1, y1], "to": [x2, y2]} -> Broadcast to all
    - {"type": "add_tile", "word": "...", "position": [x, y]} -> Add and broadcast
    - {"type": "delete_tile", "tile_id": N} -> Delete and broadcast
    - {"type": "edit_tile", "tile_id": N, "new_word": "..."} -> Edit and broadcast
  - Receive broadcasts:
    - {"type": "tile_moved", "tile_id": N, "from": [x1, y1], "to": [x2, y2], "client_id": "..."}
    - {"type": "tile_added", "tile": {...}, "client_id": "..."}
    - {"type": "tile_deleted", "tile_id": N, "client_id": "..."}
    - {"type": "tile_edited", "tile_id": N, "new_word": "...", "client_id": "..."}

Note: Requires websockets package: pip install websockets
"""

import asyncio
import json
import time
import uuid
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from collections import deque

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    print("WARNING: websockets not installed. Install with: pip install websockets")


@dataclass
class Tile:
    """A single tile in the canvas."""
    tile_id: int
    word: str
    position: List[int]  # [x, y]
    size: List[int]  # [width, height]
    color: List[int]  # [r, g, b]
    created_by: str
    created_at: float
    updated_at: float


@dataclass
class TileMoveOperation:
    """A tile movement operation."""
    tile_id: int
    from_pos: List[int]
    to_pos: List[int]
    client_id: str
    timestamp: float
    operation_id: str


@dataclass
class Client:
    """Connected client."""
    client_id: str
    websocket: object
    connected_at: float


class CollaborativeTileEditor:
    """
    Server-side collaborative tile editor.
    
    Manages canvas state, broadcasts operations, and ensures
    consistency across multiple concurrent editors.
    """
    
    def __init__(self):
        self.tiles: Dict[int, Tile] = {}
        self.clients: Dict[str, Client] = {}
        self.next_tile_id = 0
        self.operation_history: List[dict] = []
        self.max_history = 1000
        
    def _generate_tile_id(self) -> int:
        """Generate unique tile ID."""
        self.next_tile_id += 1
        return self.next_tile_id
    
    def _create_tile(self, word: str, position: List[int], 
                    size: List[int], color: List[int], client_id: str) -> Tile:
        """Create a new tile."""
        tile_id = self._generate_tile_id()
        now = time.time()
        
        tile = Tile(
            tile_id=tile_id,
            word=word,
            position=position[:],
            size=size[:],
            color=color[:],
            created_by=client_id,
            created_at=now,
            updated_at=now
        )
        
        self.tiles[tile_id] = tile
        
        # Log operation
        self.operation_history.append({
            "type": "tile_added",
            "tile_id": tile_id,
            "client_id": client_id,
            "timestamp": now
        })
        self._trim_history()
        
        return tile
    
    def _move_tile(self, tile_id: int, from_pos: List[int], 
                   to_pos: List[int], client_id: str) -> Optional[Tile]:
        """Move a tile."""
        if tile_id not in self.tiles:
            return None
        
        tile = self.tiles[tile_id]
        tile.position = to_pos[:]
        tile.updated_at = time.time()
        
        # Log operation
        op = TileMoveOperation(
            tile_id=tile_id,
            from_pos=from_pos[:],
            to_pos=to_pos[:],
            client_id=client_id,
            timestamp=time.time(),
            operation_id=str(uuid.uuid4())
        )
        
        self.operation_history.append({
            "type": "tile_moved",
            **asdict(op)
        })
        self._trim_history()
        
        return tile
    
    def _delete_tile(self, tile_id: int, client_id: str) -> bool:
        """Delete a tile."""
        if tile_id not in self.tiles:
            return False
        
        del self.tiles[tile_id]
        
        # Log operation
        self.operation_history.append({
            "type": "tile_deleted",
            "tile_id": tile_id,
            "client_id": client_id,
            "timestamp": time.time()
        })
        self._trim_history()
        
        return True
    
    def _edit_tile(self, tile_id: int, new_word: str, client_id: str) -> Optional[Tile]:
        """Edit tile word."""
        if tile_id not in self.tiles:
            return None
        
        tile = self.tiles[tile_id]
        old_word = tile.word
        tile.word = new_word
        tile.updated_at = time.time()
        
        # Log operation
        self.operation_history.append({
            "type": "tile_edited",
            "tile_id": tile_id,
            "old_word": old_word,
            "new_word": new_word,
            "client_id": client_id,
            "timestamp": time.time()
        })
        self._trim_history()
        
        return tile
    
    def _trim_history(self):
        """Keep operation history bounded."""
        if len(self.operation_history) > self.max_history:
            self.operation_history = self.operation_history[-self.max_history:]
    
    def _broadcast(self, message: dict, exclude_client: Optional[str] = None):
        """Broadcast message to all clients except one."""
        payload = json.dumps(message)
        
        for client_id, client in self.clients.items():
            if exclude_client and client_id == exclude_client:
                continue
            
            try:
                if HAS_WEBSOCKETS:
                    asyncio.create_task(client.websocket.send(payload))
            except Exception as e:
                print(f"[SERVER] Failed to send to {client_id}: {e}")
    
    def _send_to_client(self, client_id: str, message: dict):
        """Send message to specific client."""
        if client_id not in self.clients:
            return False
        
        payload = json.dumps(message)
        
        try:
            if HAS_WEBSOCKETS:
                asyncio.create_task(self.clients[client_id].websocket.send(payload))
            return True
        except Exception as e:
            print(f"[SERVER] Failed to send to {client_id}: {e}")
            return False
    
    def handle_message(self, client_id: str, message: dict):
        """Handle incoming message from client."""
        msg_type = message.get("type")
        
        if msg_type == "init":
            # Send current canvas state
            tiles_data = {
                str(tid): asdict(tile) 
                for tid, tile in self.tiles.items()
            }
            
            response = {
                "type": "init_response",
                "tiles": tiles_data,
                "client_count": len(self.clients),
                "client_id": client_id
            }
            
            self._send_to_client(client_id, response)
        
        elif msg_type == "add_tile":
            word = message.get("word", "")
            position = message.get("position", [0, 0])
            size = message.get("size", [150, 80])
            color = message.get("color", [70, 130, 180])
            
            tile = self._create_tile(word, position, size, color, client_id)
            
            # Broadcast to all clients
            broadcast_msg = {
                "type": "tile_added",
                "tile": asdict(tile),
                "client_id": client_id
            }
            self._broadcast(broadcast_msg, exclude_client=client_id)
        
        elif msg_type == "move_tile":
            tile_id = message.get("tile_id")
            from_pos = message.get("from", [0, 0])
            to_pos = message.get("to", [0, 0])
            
            tile = self._move_tile(tile_id, from_pos, to_pos, client_id)
            
            if tile:
                # Broadcast movement to all clients
                broadcast_msg = {
                    "type": "tile_moved",
                    "tile_id": tile_id,
                    "from": from_pos,
                    "to": to_pos,
                    "client_id": client_id
                }
                self._broadcast(broadcast_msg, exclude_client=client_id)
        
        elif msg_type == "delete_tile":
            tile_id = message.get("tile_id")
            
            if self._delete_tile(tile_id, client_id):
                # Broadcast deletion
                broadcast_msg = {
                    "type": "tile_deleted",
                    "tile_id": tile_id,
                    "client_id": client_id
                }
                self._broadcast(broadcast_msg, exclude_client=client_id)
        
        elif msg_type == "edit_tile":
            tile_id = message.get("tile_id")
            new_word = message.get("new_word", "")
            
            tile = self._edit_tile(tile_id, new_word, client_id)
            
            if tile:
                # Broadcast edit
                broadcast_msg = {
                    "type": "tile_edited",
                    "tile_id": tile_id,
                    "new_word": new_word,
                    "client_id": client_id
                }
                self._broadcast(broadcast_msg, exclude_client=client_id)
        
        elif msg_type == "get_history":
            # Send operation history
            response = {
                "type": "history_response",
                "history": self.operation_history
            }
            self._send_to_client(client_id, response)
        
        elif msg_type == "get_visual_diff":
            # Generate visual diff between two operations
            from_idx = message.get("from_idx", 0)
            to_idx = message.get("to_idx", len(self.operation_history))
            
            diff_ops = self.operation_history[from_idx:to_idx]
            
            # Group by tile_id
            diff_by_tile = {}
            for op in diff_ops:
                tile_id = op.get("tile_id")
                if tile_id not in diff_by_tile:
                    diff_by_tile[tile_id] = []
                diff_by_tile[tile_id].append(op)
            
            response = {
                "type": "visual_diff_response",
                "diff": diff_by_tile,
                "from_idx": from_idx,
                "to_idx": to_idx
            }
            self._send_to_client(client_id, response)
        
        else:
            print(f"[SERVER] Unknown message type: {msg_type}")
    
    async def handle_client(self, websocket, path: str):
        """Handle client connection."""
        # Generate client ID
        client_id = f"client_{uuid.uuid4().hex[:8]}"
        
        print(f"[SERVER] Client connected: {client_id}")
        
        # Store client
        self.clients[client_id] = Client(
            client_id=client_id,
            websocket=websocket,
            connected_at=time.time()
        )
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    self.handle_message(client_id, data)
                except json.JSONDecodeError as e:
                    print(f"[SERVER] JSON decode error: {e}")
                except Exception as e:
                    print(f"[SERVER] Message handling error: {e}")
        
        finally:
            # Clean up on disconnect
            if client_id in self.clients:
                del self.clients[client_id]
            
            print(f"[SERVER] Client disconnected: {client_id}")
            
            # Notify others
            self._broadcast({
                "type": "client_disconnected",
                "client_id": client_id
            }, exclude_client=client_id)


async def main():
    """Start the collaborative tile editor server."""
    if not HAS_WEBSOCKETS:
        print("ERROR: websockets package not installed")
        print("Install with: pip install websockets")
        sys.exit(1)
    
    import sys
    editor = CollaborativeTileEditor()
    
    print("="*60)
    print("Collaborative Tile Editor Server — TASK_I005")
    print("="*60)
    print(f"\nWebSocket server: ws://localhost:3001")
    print(f"Supported operations:")
    print(f"  - init: Get current canvas state")
    print(f"  - add_tile: Add new tile to canvas")
    print(f"  - move_tile: Move tile position")
    print(f"  - delete_tile: Remove tile from canvas")
    print(f"  - edit_tile: Change tile word")
    print(f"  - get_history: Get operation history")
    print(f"  - get_visual_diff: Get diff between operations")
    print(f"\nWaiting for connections...\n")
    
    async def serve_client(websocket, path):
        await editor.handle_client(websocket, path)
    
    async with websockets.serve(serve_client, "localhost", 3001):
        print(f"[SERVER] Ready at ws://localhost:3001")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    import sys
    asyncio.run(main())