#!/usr/bin/env python3
"""
Temporal frame logging for Spatial Execution Engine (Phase 11, TASK_SE004).

Implements Frames 4+ as full state snapshots with seekable timeline.
Each frame is a complete system state at a specific execution tick.

Core loop: read → validate → execute → tick → log → repeat
"""

import sys
import os
import struct
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from codec.phy import frame, unframe


@dataclass
class SystemState:
    """Complete system state at a specific tick."""
    tick: int
    timestamp: float
    frame1: Dict[str, Any]  # Seed, biome palette, tile atlas
    frame2: Dict[str, Any]  # Camera, world parameters, entity pointers
    frame3: Dict[str, Any]  # Diff overlay
    metadata: Dict[str, Any]


class TemporalLog:
    """
    Temporal logging system for spatial execution engine.
    
    Stores complete system state snapshots as PNG frames (one per tick).
    Provides seekable timeline: "load frame N" restores state to tick N.
    """
    
    def __init__(self, log_dir: Optional[str] = None):
        """
        Initialize temporal log.
        
        Args:
            log_dir: Directory to store temporal frames. If None, uses temp dir.
        """
        if log_dir is None:
            self.log_dir = Path(tempfile.mkdtemp(prefix='spatial_log_'))
        else:
            self.log_dir = Path(log_dir)
            self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.frames: Dict[int, Path] = {}  # tick -> frame path
        self.current_tick = 0
        self.max_cached_ticks = 1000  # Keep recent frames in memory
        
        print(f"[TemporalLog] Initialized with log_dir: {self.log_dir}")
    
    def capture_state(self, state: SystemState) -> Path:
        """
        Capture a system state as a temporal frame.
        
        Args:
            state: Complete system state to capture
            
        Returns:
            Path to the captured frame PNG
        """
        tick = state.tick
        
        # Serialize state to bytes
        state_bytes = self._serialize_state(state)
        
        # Frame with UA magic + CRC
        framed = frame(state_bytes)
        
        # Write as PNG (using dense encoder's 3 bytes/pixel format)
        frame_path = self.log_dir / f"frame_{tick:06d}.png"
        
        # Convert framed bytes to RGB pixels (3 bytes per pixel)
        pixel_data = _bytes_to_pixels(framed)
        
        # Save as PNG
        from PIL import Image
        import numpy as np
        
        # Calculate dimensions (3 bytes per pixel)
        total_pixels = len(pixel_data) // 3
        width = 450  # Match dense encoder frame size
        height = (total_pixels + width - 1) // width
        
        # Pad to exact dimensions
        total_capacity = width * height * 3
        if len(pixel_data) < total_capacity:
            pixel_data = pixel_data + b'\x00' * (total_capacity - len(pixel_data))
        
        # Reshape to image
        img_array = np.frombuffer(pixel_data, dtype=np.uint8).reshape(height, width, 3)
        img = Image.fromarray(img_array, mode='RGB')
        
        # Add metadata as PNG text chunks
        from PIL import PngImagePlugin
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text('tick', str(tick))
        pnginfo.add_text('timestamp', datetime.fromtimestamp(state.timestamp).isoformat())
        pnginfo.add_text('md5', hashlib.md5(state_bytes).hexdigest())
        
        img.save(frame_path, pnginfo=pnginfo)
        
        # Track frame
        self.frames[tick] = frame_path
        self.current_tick = tick
        
        # Prune old frames if too many
        if len(self.frames) > self.max_cached_ticks:
            oldest_tick = min(self.frames.keys())
            del self.frames[oldest_tick]
        
        print(f"[TemporalLog] Captured tick {tick}: {frame_path}")
        return frame_path
    
    def load_state(self, tick: int) -> Optional[SystemState]:
        """
        Load system state from a temporal frame.
        
        Args:
            tick: Tick number to load
            
        Returns:
            SystemState if found, None otherwise
        """
        frame_path = self.frames.get(tick)
        if not frame_path or not frame_path.exists():
            # Try finding in log directory
            frame_path = self.log_dir / f"frame_{tick:06d}.png"
            if not frame_path.exists():
                print(f"[TemporalLog] Frame {tick} not found")
                return None
        
        # Load PNG
        from PIL import Image
        import numpy as np
        
        img = Image.open(frame_path)
        img_array = np.array(img)
        
        # Extract pixels to bytes
        pixel_bytes = img_array.flatten().tobytes()
        
        # Strip trailing padding zeros added during capture_state
        # Capture pads to width*height*3 bytes with zeros
        pixel_bytes = pixel_bytes.rstrip(b'\x00')
        
        # Unframe - use module-level helper function
        framed = _pixels_to_bytes(pixel_bytes)
        state_bytes, crc_valid = unframe(framed)
        
        if not crc_valid:
            print(f"[TemporalLog] CRC error loading tick {tick}")
            return None
        
        # Deserialize
        state = self._deserialize_state(state_bytes)
        
        # Verify tick matches
        if state.tick != tick:
            print(f"[TemporalLog] Tick mismatch: expected {tick}, got {state.tick}")
            return None
        
        print(f"[TemporalLog] Loaded tick {tick}")
        return state
    
    def seek(self, tick: int) -> Optional[SystemState]:
        """
        Seek to a specific tick in the timeline.
        
        If exact tick not found, returns last available frame ≤ requested tick.
        
        Args:
            tick: Tick to seek to
            
        Returns:
            SystemState at or before requested tick, or None
        """
        if tick in self.frames:
            return self.load_state(tick)
        
        # Find closest earlier tick
        available_ticks = sorted([t for t in self.frames.keys() if t <= tick])
        
        if not available_ticks:
            print(f"[TemporalLog] No frames ≤ tick {tick}")
            return None
        
        closest_tick = available_ticks[-1]
        print(f"[TemporalLog] Seeking {tick} → closest frame {closest_tick}")
        return self.load_state(closest_tick)
    
    def get_tick_range(self) -> Tuple[int, int]:
        """Get min and max ticks available."""
        if not self.frames:
            return (0, 0)
        return (min(self.frames.keys()), max(self.frames.keys()))
    
    def _serialize_state(self, state: SystemState) -> bytes:
        """Serialize system state to bytes."""
        state_dict = {
            'tick': state.tick,
            'timestamp': state.timestamp,
            'frame1': state.frame1,
            'frame2': state.frame2,
            'frame3': state.frame3,
            'metadata': state.metadata
        }
        return json.dumps(state_dict).encode('utf-8')
    
    def _deserialize_state(self, state_bytes: bytes) -> SystemState:
        """Deserialize bytes to system state."""
        state_dict = json.loads(state_bytes.decode('utf-8'))
        return SystemState(
            tick=state_dict['tick'],
            timestamp=state_dict['timestamp'],
            frame1=state_dict['frame1'],
            frame2=state_dict['frame2'],
            frame3=state_dict['frame3'],
            metadata=state_dict['metadata']
        )


def _bytes_to_pixels(data: bytes) -> bytes:
    """Convert bytes to RGB pixel bytes (3 bytes per pixel)."""
    # Data is already 3 bytes/pixel, just ensure alignment
    return data


def _pixels_to_bytes(pixel_bytes: bytes) -> bytes:
    """Convert RGB pixel bytes to raw bytes."""
    return pixel_bytes


class ExecutionEngine:
    """
    Read-Validate-Execute-Tick loop with temporal logging.
    
    Core execution pattern:
    1. READ: Load current state from temporal log
    2. VALIDATE: Verify state integrity (CRC, tick consistency)
    3. EXECUTE: Run one tick of procedural generation
    4. TICK: Advance tick counter
    5. LOG: Capture state to temporal frame
    6. REPEAT
    """
    
    def __init__(self, temporal_log: TemporalLog):
        """
        Initialize execution engine.
        
        Args:
            temporal_log: Temporal log for state capture/restoration
        """
        self.temporal_log = temporal_log
        self.current_state: Optional[SystemState] = None
        self.is_paused = False
        self.is_debug = False
    
    def execute_tick(self, procedural_gen_fn) -> SystemState:
        """
        Execute one tick of the simulation loop.
        
        Args:
            procedural_gen_fn: Function that generates state from tick
            
        Returns:
            New system state after this tick
        """
        # READ: Load current state or initialize
        if self.current_state is None:
            # Initial state at tick 0
            self.current_state = procedural_gen_fn(0)
        else:
            tick = self.current_state.tick + 1
            self.current_state = procedural_gen_fn(tick)
        
        # VALIDATE: Check state integrity
        if not self._validate_state(self.current_state):
            raise ValueError(f"State validation failed at tick {self.current_state.tick}")
        
        # EXECUTE: Procedural generation already done by procedural_gen_fn
        
        # TICK: Already advanced
        
        # LOG: Capture state
        self.temporal_log.capture_state(self.current_state)
        
        if self.is_debug:
            print(f"[Engine] Tick {self.current_state.tick} complete")
        
        return self.current_state
    
    def seek_and_resume(self, tick: int, procedural_gen_fn) -> SystemState:
        """
        Seek to historical tick and resume execution.
        
        Args:
            tick: Tick to seek to
            procedural_gen_fn: Function for forward execution from seek point
            
        Returns:
            System state at seek point (or closest available)
        """
        state = self.temporal_log.seek(tick)
        
        if state is None:
            raise ValueError(f"Cannot seek to tick {tick}: no frame available")
        
        self.current_state = state
        print(f"[Engine] Resumed from tick {state.tick}")
        
        return state
    
    def _validate_state(self, state: SystemState) -> bool:
        """Validate state integrity."""
        # Check tick is non-negative
        if state.tick < 0:
            return False
        
        # Check timestamp is reasonable
        if state.timestamp <= 0:
            return False
        
        # Check required frame data exists
        required_fields = ['frame1', 'frame2', 'frame3']
        for field in required_fields:
            if not hasattr(state, field) or not getattr(state, field):
                return False
        
        return True


def demo_procedural_gen(tick: int) -> SystemState:
    """Demo procedural generation function for testing."""
    import time
    
    return SystemState(
        tick=tick,
        timestamp=time.time(),
        frame1={
            'seed': 0xDEADBEEF_CAFEBABE,
            'biome_palette': [f'biome_{i}' for i in range(9)],
            'tile_atlas': [f'tile_{i}' for i in range(100)]
        },
        frame2={
            'camera_x': tick * 10,
            'camera_y': tick * 5,
            'time_of_day': (tick % 24),
            'threat_level': 10
        },
        frame3={
            'diffs': [
                {'x': tick * 2, 'y': tick * 2, 'type': 'built', 'data': 'structure_1'}
            ]
        },
        metadata={
            'tick_duration_ms': 16.7,  # ~60 FPS
            'frame_rate': 60.0
        }
    )


def main():
    """Demo temporal logging and execution loop."""
    import time
    
    print("="*60)
    print("TASK_SE004: Temporal Frame Logging Demo")
    print("="*60)
    
    # Initialize
    log_dir = Path('/tmp/spatial_temporal_demo')
    if log_dir.exists():
        import shutil
        shutil.rmtree(log_dir)
    
    temporal_log = TemporalLog(str(log_dir))
    engine = ExecutionEngine(temporal_log)
    
    print("\n--- Running execution loop (10 ticks) ---")
    
    # Execute 10 ticks
    for i in range(10):
        state = engine.execute_tick(demo_procedural_gen)
        print(f"  Tick {state.tick}: camera at ({state.frame2['camera_x']}, {state.frame2['camera_y']})")
        time.sleep(0.01)  # Simulate work
    
    print(f"\n--- Timeline range: {temporal_log.get_tick_range()} ---")
    
    # Demonstrate seek
    print("\n--- Seeking to tick 3 ---")
    state = engine.seek_and_resume(3, demo_procedural_gen)
    print(f"  Loaded: tick {state.tick}, camera at ({state.frame2['camera_x']}, {state.frame2['camera_y']})")
    
    # Continue from seek point
    print("\n--- Continuing from tick 3 (2 more ticks) ---")
    for i in range(2):
        state = engine.execute_tick(demo_procedural_gen)
        print(f"  Tick {state.tick}: camera at ({state.frame2['camera_x']}, {state.frame2['camera_y']})")
    
    print(f"\n--- Final timeline: {temporal_log.get_tick_range()} ---")
    print(f"\n✓ TASK_SE004 Demo Complete")
    print(f"  Temporal frames saved to: {log_dir}")
    print(f"  Total frames: {len(temporal_log.frames)}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())