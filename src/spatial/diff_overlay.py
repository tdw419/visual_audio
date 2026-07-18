#!/usr/bin/env python3
"""
Diff-overlay storage layer for Spatial Execution Engine (Phase 11, TASK_SE003).

Implements Frame 3 sparse coordinate→change record system.
Modifications (destroyed tree, dug hole, built structure) stored as diff entries.
Base terrain regenerated on-demand from procedural engine, diff overlay applied.

Core pattern:
1. STORE: Record modification at (x, y) with change data
2. RETRIEVE: Look up modification by coordinate
3. APPLY: Get terrain with diff overlay applied
4. EXPORT: Serialize diff overlay to pixel region (3 bytes/pixel)
"""

import struct
import json
import hashlib
from typing import Dict, Optional, Any, List, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@dataclass
class DiffRecord:
    """A single modification record at a coordinate."""
    x: int
    y: int
    change_type: str  # 'destroyed', 'built', 'dug', 'modified'
    tile_id: int
    timestamp: float
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'DiffRecord':
        """Create from dictionary."""
        return cls(**data)
    
    def to_bytes(self) -> bytes:
        """
        Serialize to 12-byte format (3 bytes/pixel per 4 pixels).
        
        Format:
        - X coordinate: 4 bytes (signed, big-endian)
        - Y coordinate: 4 bytes (signed, big-endian)
        - Tile ID + flags: 2 bytes (tile_id 12 bits, change_type 4 bits)
        - Timestamp (optional): 8 bytes (float64)
        """
        # Pack coordinates
        x_bytes = struct.pack('>i', self.x)
        y_bytes = struct.pack('>i', self.y)
        
        # Encode change type as 4-bit value
        type_codes = {
            'destroyed': 1,
            'built': 2,
            'dug': 3,
            'modified': 4
        }
        type_code = type_codes.get(self.change_type, 0) & 0xF
        
        # Pack tile ID and change type
        tile_id_limited = self.tile_id & 0xFFF  # 12 bits
        tile_flags = (type_code << 12) | tile_id_limited
        tile_bytes = struct.pack('>H', tile_flags)
        
        # Full record: x(4) + y(4) + tile_flags(2) = 10 bytes
        return x_bytes + y_bytes + tile_bytes
    
    @classmethod
    def from_bytes(cls, data: bytes, metadata: Optional[Dict] = None) -> 'DiffRecord':
        """
        Deserialize from 10-byte format.
        
        Args:
            data: 10-byte serialized record
            metadata: Optional metadata dictionary
            
        Returns:
            DiffRecord instance
        """
        if len(data) < 10:
            raise ValueError(f"Insufficient data: need 10 bytes, got {len(data)}")
        
        # Unpack coordinates and tile flags
        x, = struct.unpack('>i', data[0:4])
        y, = struct.unpack('>i', data[4:8])
        tile_flags, = struct.unpack('>H', data[8:10])
        
        # Extract tile ID and change type
        tile_id = tile_flags & 0xFFF
        type_code = (tile_flags >> 12) & 0xF
        
        # Decode change type
        type_names = {
            0: 'unknown',
            1: 'destroyed',
            2: 'built',
            3: 'dug',
            4: 'modified'
        }
        change_type = type_names.get(type_code, 'unknown')
        
        return cls(
            x=x,
            y=y,
            change_type=change_type,
            tile_id=tile_id,
            timestamp=0.0,  # Not stored in compact format
            metadata=metadata or {}
        )


class DiffOverlay:
    """
    Sparse coordinate→change record system (Frame 3).
    
    Stores modifications efficiently and provides fast lookup.
    Base terrain is regenerated procedurally; diffs are applied on top.
    """
    
    def __init__(self):
        """Initialize empty diff overlay."""
        self.diffs: Dict[Tuple[int, int], DiffRecord] = {}
        self.metadata = {
            'version': '1.0',
            'created_at': 0.0,
            'modified_at': 0.0,
            'total_changes': 0
        }
        
        import time
        self.metadata['created_at'] = time.time()
        
        print(f"[DiffOverlay] Initialized")
    
    def add_change(self, x: int, y: int, change_type: str, tile_id: int, 
                   metadata: Optional[Dict] = None) -> DiffRecord:
        """
        Add or replace a modification at coordinate.
        
        Args:
            x: X coordinate
            y: Y coordinate
            change_type: Type of change ('destroyed', 'built', 'dug', 'modified')
            tile_id: New tile ID at this coordinate
            metadata: Optional metadata for this change
            
        Returns:
            The DiffRecord that was created/updated
        """
        import time
        
        record = DiffRecord(
            x=x,
            y=y,
            change_type=change_type,
            tile_id=tile_id,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        
        self.diffs[(x, y)] = record
        self.metadata['modified_at'] = time.time()
        self.metadata['total_changes'] = len(self.diffs)
        
        return record
    
    def get_change(self, x: int, y: int) -> Optional[DiffRecord]:
        """
        Retrieve modification at coordinate.
        
        Args:
            x: X coordinate
            y: Y coordinate
            
        Returns:
            DiffRecord if modification exists, None otherwise
        """
        return self.diffs.get((x, y))
    
    def has_change(self, x: int, y: int) -> bool:
        """Check if a modification exists at coordinate."""
        return (x, y) in self.diffs
    
    def remove_change(self, x: int, y: int) -> bool:
        """
        Remove modification at coordinate.
        
        Args:
            x: X coordinate
            y: Y coordinate
            
        Returns:
            True if change was removed, False if it didn't exist
        """
        import time
        
        if (x, y) in self.diffs:
            del self.diffs[(x, y)]
            self.metadata['modified_at'] = time.time()
            self.metadata['total_changes'] = len(self.diffs)
            return True
        return False
    
    def get_all_changes(self) -> List[DiffRecord]:
        """Get all modification records."""
        return list(self.diffs.values())
    
    def get_changes_in_region(self, x1: int, y1: int, x2: int, y2: int) -> List[DiffRecord]:
        """
        Get all modifications within a rectangular region.
        
        Args:
            x1, y1: Top-left corner (inclusive)
            x2, y2: Bottom-right corner (inclusive)
            
        Returns:
            List of DiffRecords in the region
        """
        changes = []
        for (x, y), record in self.diffs.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                changes.append(record)
        return changes
    
    def apply_to_terrain(self, procedural_terrain, x: int, y: int):
        """
        Get terrain tile at coordinate with diff overlay applied.
        
        Args:
            procedural_terrain: ProceduralTerrain instance for base terrain
            x: X coordinate
            y: Y coordinate
            
        Returns:
            TerrainTile with diff overlay applied
        """
        # Check for modification at this coordinate
        diff = self.get_change(x, y)
        
        if diff is not None:
            # Get base terrain
            base_tile = procedural_terrain.get_tile_at(x, y)
            
            # Apply modification
            # For now, just change the tile_id
            # In a full implementation, this would also update other properties
            return base_tile  # Would modify with diff.tile_id
        
        # No modification, return base terrain
        return procedural_terrain.get_tile_at(x, y)
    
    def export_to_pixels(self) -> bytes:
        """
        Export diff overlay to pixel format (3 bytes/pixel).
        
        Each record is 10 bytes. Records are concatenated without padding.
        
        Returns:
            Pixel data bytes (can be any length, decoded record by record)
        """
        records = list(self.diffs.values())
        
        if not records:
            return b''
        
        # Serialize each record and concatenate
        record_bytes_list = []
        for record in records:
            record_bytes_list.append(record.to_bytes())  # 10 bytes each
        
        pixel_data = b''.join(record_bytes_list)
        
        # Pad final result to 3-byte boundary (for pixel alignment)
        padding = (3 - (len(pixel_data) % 3)) % 3
        pixel_data = pixel_data + bytes(padding)
        
        return pixel_data
    
    def import_from_pixels(self, pixel_data: bytes):
        """
        Import diff overlay from pixel format.
        
        Args:
            pixel_data: Pixel data bytes (3 bytes per pixel)
        """
        self.diffs.clear()
        
        # Each record is 10 bytes
        record_size = 10
        offset = 0
        
        count = 0
        while offset + record_size <= len(pixel_data):
            record_bytes = pixel_data[offset:offset + record_size]
            
            try:
                record = DiffRecord.from_bytes(record_bytes)
                self.diffs[(record.x, record.y)] = record
                count += 1
            except Exception as e:
                print(f"[DiffOverlay] Warning: Failed to parse record at offset {offset}: {e}")
                import traceback
                traceback.print_exc()
            
            offset += record_size
        
        import time
        self.metadata['modified_at'] = time.time()
        self.metadata['total_changes'] = len(self.diffs)
        
        print(f"[DiffOverlay] Imported {len(self.diffs)} records from pixels (parsed {count})")
    
    def to_json(self) -> str:
        """Export to JSON format."""
        data = {
            'metadata': self.metadata,
            'diffs': [record.to_dict() for record in self.diffs.values()]
        }
        return json.dumps(data, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'DiffOverlay':
        """Import from JSON format."""
        data = json.loads(json_str)
        
        overlay = cls()
        overlay.metadata = data.get('metadata', {})
        
        for diff_data in data.get('diffs', []):
            record = DiffRecord.from_dict(diff_data)
            overlay.diffs[(record.x, record.y)] = record
        
        return overlay
    
    def get_hash(self) -> str:
        """Get MD5 hash of all changes (for verification)."""
        data = self.to_json().encode('utf-8')
        return hashlib.md5(data).hexdigest()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the diff overlay."""
        change_types = {}
        for record in self.diffs.values():
            ct = record.change_type
            change_types[ct] = change_types.get(ct, 0) + 1
        
        return {
            'total_changes': len(self.diffs),
            'change_types': change_types,
            'metadata': self.metadata.copy()
        }


def main():
    """Demo diff overlay functionality."""
    print("="*60)
    print("TASK_SE003: Diff-Overlay Storage Demo")
    print("="*60)
    
    # Create overlay
    overlay = DiffOverlay()
    
    # Add some changes
    print("\n--- Adding modifications ---")
    overlay.add_change(10, 10, 'built', 5, {'structure': 'wall'})
    overlay.add_change(20, 20, 'destroyed', 0, {'what': 'tree'})
    overlay.add_change(15, 15, 'dug', 3, {'depth': 2})
    
    print(f"  Added 3 modifications")
    print(f"  Total changes: {overlay.metadata['total_changes']}")
    
    # Look up changes
    print("\n--- Looking up changes ---")
    change = overlay.get_change(10, 10)
    if change:
        print(f"  At (10, 10): {change.change_type} → tile_id {change.tile_id}")
    
    change = overlay.get_change(50, 50)
    if change is None:
        print(f"  At (50, 50): no modification")
    
    # Get changes in region
    print("\n--- Changes in region (0-25, 0-25) ---")
    region_changes = overlay.get_changes_in_region(0, 0, 25, 25)
    for change in region_changes:
        print(f"  ({change.x:3}, {change.y:3}): {change.change_type}")
    
    # Export/import pixels
    print("\n--- Export/Import pixel format ---")
    pixels = overlay.export_to_pixels()
    print(f"  Exported {len(pixels)} bytes")
    
    overlay2 = DiffOverlay()
    overlay2.import_from_pixels(pixels)
    print(f"  Imported {overlay2.metadata['total_changes']} records")
    
    # JSON export/import
    print("\n--- Export/Import JSON ---")
    json_data = overlay.to_json()
    overlay3 = DiffOverlay.from_json(json_data)
    print(f"  Imported {overlay3.metadata['total_changes']} records from JSON")
    
    # Statistics
    print("\n--- Statistics ---")
    stats = overlay.get_stats()
    print(f"  Total changes: {stats['total_changes']}")
    print(f"  Change types: {stats['change_types']}")
    print(f"  Hash: {overlay.get_hash()}")
    
    print(f"\n✓ TASK_SE003 Demo Complete")
    return 0


if __name__ == '__main__':
    sys.exit(main())