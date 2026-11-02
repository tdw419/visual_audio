#!/usr/bin/env python3
"""
Video-in-Video Architecture — Spatial Tensor Compositor

A true VAC3 compliant spatial compositor.
Instead of flattening MKV videos into a 2D sequence, this preserves
"The Screen is the Hard Drive" geometry by compositing across all
Z-layers simultaneously (Z=0 display, Z=1 RAM substrate, Z=2 diagnostics).

Key Features:
- Dual time vectors: system time vs media time
- Independent playheads per video zone
- Spatial VAC3 layer extraction & Z-aware compositing
- Inter-frame XOR delta reconstruction for true RAM state extraction
- Outputs a valid VAC3 master tensor containing embedded child tensors
"""

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from PIL import Image

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dense_encoder_video import decode_mkv, encode_mkv

class VideoZone:
    """A spatial tensor playback zone within a master VAC3 container."""
    
    def __init__(self, name: str, x: int, y: int, width: int, height: int,
                 video_path: str, start_frame: int = 0, loop: bool = True):
        self.name = name
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.video_path = video_path
        self.start_frame = start_frame
        self.loop = loop
        
        self.playhead = start_frame
        self.playing = True
        self.fps = 30.0
        self.total_frames = 0
        self.frame_duration_ms = 33
        
        # Manifest state
        self.vac3_metadata = None
        self.payload = None
        
        self.z0_size = 0
        self.z1_size = 0
        self.z2_size = 0
        self.bundle_size = 0
        self.tiles_per_capture = 1
        
        # We need to accumulate Z1 XOR deltas across time
        self.z1_accumulator = None
        self.cached_z1_playhead = -1
        
    def load_video(self):
        if not Path(self.video_path).exists():
            raise FileNotFoundError(f"Video not found: {self.video_path}")
            
        payload_bytes, manifest = decode_mkv(self.video_path)
        
        if "total_frames" not in manifest:
            raise ValueError("Invalid MKV manifest: missing total_frames")
            
        self.total_frames = manifest["total_frames"]
        self.payload = payload_bytes
        
        video_meta = manifest.get("metadata", {})
        self.fps = video_meta.get("fps", 30.0)
        self.frame_duration_ms = int(1000 / self.fps)
        
        self.tiles_per_capture = video_meta.get("tiles_per_capture", 1)
        pixel_width = video_meta.get("pixel_width", 256)
        pixel_height = video_meta.get("pixel_height", 256)
        
        # Calculate Layer Sizes
        self.z0_size = pixel_width * pixel_height * 3
        self.z1_size = self.z0_size * self.tiles_per_capture
        self.z2_size = self.z0_size
        self.bundle_size = self.z0_size + self.z1_size + self.z2_size
        
        if len(self.payload) < self.bundle_size * self.total_frames:
            # Fallback if it's not a full VAC3 bundle video (e.g. legacy mode)
            self.bundle_size = self.z1_size
            self.z0_size = 0
            self.z2_size = 0
            
        self.z1_accumulator = np.zeros(self.z1_size, dtype=np.uint8)
        self.cached_z1_playhead = -1
            
    def _reconstruct_z1_to(self, target_frame: int):
        """Reconstruct Z=1 XOR delta up to target_frame."""
        # If we went backward, reset
        if target_frame < self.cached_z1_playhead:
            self.z1_accumulator.fill(0)
            self.cached_z1_playhead = -1
            
        # Fast forward to target
        while self.cached_z1_playhead < target_frame:
            next_idx = self.cached_z1_playhead + 1
            offset = next_idx * self.bundle_size + self.z0_size
            delta_chunk = np.frombuffer(self.payload[offset:offset + self.z1_size], dtype=np.uint8)
            self.z1_accumulator = np.bitwise_xor(self.z1_accumulator, delta_chunk)
            self.cached_z1_playhead = next_idx

    def get_z_layer(self, layer_index: int, frame_idx: int) -> np.ndarray:
        """Extract a specific Z-layer (0, 1, or 2) at the given frame index."""
        if self.payload is None:
            self.load_video()
            
        if frame_idx < 0 or frame_idx >= self.total_frames:
            if not self.loop:
                return np.zeros((self.height, self.width, 3), dtype=np.uint8)
            frame_idx = frame_idx % self.total_frames
            
        bundle_offset = frame_idx * self.bundle_size
        
        if layer_index == 0:
            if self.z0_size == 0:
                return np.zeros((self.height, self.width, 3), dtype=np.uint8)
            data = self.payload[bundle_offset : bundle_offset + self.z0_size]
        elif layer_index == 1:
            self._reconstruct_z1_to(frame_idx)
            # Z=1 is composed of multiple tiles, for compositing we just treat it
            # as a flattened byte array we can render visually (first tile) or conceptually
            # To fit in a zone visually, we just grab the first tile
            data = self.z1_accumulator[:(self.z1_size // self.tiles_per_capture)].tobytes()
        elif layer_index == 2:
            if self.z2_size == 0:
                return np.zeros((self.height, self.width, 3), dtype=np.uint8)
            z2_offset = bundle_offset + self.z0_size + self.z1_size
            data = self.payload[z2_offset : z2_offset + self.z2_size]
        else:
            raise ValueError(f"Invalid layer index: {layer_index}")
            
        # We assume the source width/height is roughly sqrt(len/3) for resizing
        # Typically 256x256
        pixels = len(data) // 3
        src_w = int(math.sqrt(pixels))
        src_h = pixels // src_w
        
        frame = np.frombuffer(data, dtype=np.uint8).reshape((src_h, src_w, 3))
        return frame

    def advance(self, delta_ms: int):
        if not self.playing or self.total_frames == 0:
            return
        
        frames_to_advance = delta_ms / self.frame_duration_ms
        self.playhead += int(frames_to_advance)
        
        if self.loop:
            self.playhead = self.playhead % self.total_frames
        elif self.playhead >= self.total_frames:
            self.playhead = self.total_frames - 1
            self.playing = False
            
    def seek(self, frame_idx: int):
        """Seek to specific frame."""
        self.playhead = max(0, min(frame_idx, self.total_frames - 1))
        
    def get_current_frame(self) -> np.ndarray:
        return self.get_z_layer(0, self.playhead)

class VideoLayoutManager:
    """Manages layout of multiple video zones within a master frame."""
    def __init__(self, master_width: int = 1920, master_height: int = 1080):
        self.master_width = master_width
        self.master_height = master_height
        self.zones: Dict[str, VideoZone] = {}
        self.zone_order: List[str] = []
        
    def add_zone(self, zone: VideoZone):
        # Validate bounds
        if zone.x < 0 or zone.y < 0:
            raise ValueError(f"Zone {zone.name}: negative coordinates")
        if zone.x + zone.width > self.master_width:
            raise ValueError(f"Zone {zone.name}: exceeds master width")
        if zone.y + zone.height > self.master_height:
            raise ValueError(f"Zone {zone.name}: exceeds master height")
            
        self.zones[zone.name] = zone
        if zone.name not in self.zone_order:
            self.zone_order.append(zone.name)
            
    def remove_zone(self, name: str):
        if name in self.zones:
            del self.zones[name]
            if name in self.zone_order:
                self.zone_order.remove(name)
                
    def get_zone(self, name: str) -> Optional[VideoZone]:
        return self.zones.get(name)
        
    def check_overlap(self, name1: str, name2: str) -> bool:
        if name1 not in self.zones or name2 not in self.zones:
            return False
        z1 = self.zones[name1]
        z2 = self.zones[name2]
        separated_x = (z1.x + z1.width <= z2.x) or (z2.x + z2.width <= z1.x)
        separated_y = (z1.y + z1.height <= z2.y) or (z2.y + z2.height <= z1.y)
        return not (separated_x or separated_y)
            
    def layout_grid(self, rows: int, cols: int, video_paths: List[str]):
        cell_width = self.master_width // cols
        cell_height = self.master_height // rows
        zones = {}
        for i, path in enumerate(video_paths):
            if i >= rows * cols: break
            name = f"zone_{i}"
            zone = VideoZone(name, (i % cols) * cell_width, (i // cols) * cell_height,
                             cell_width, cell_height, path)
            self.add_zone(zone)
            zones[name] = zone
        return zones
            
    def layout_side_by_side(self, video_paths: List[str]):
        num = len(video_paths)
        zone_width = self.master_width // num
        zones = {}
        for i, path in enumerate(video_paths):
            name = f"zone_{i}"
            zone = VideoZone(name, i * zone_width, 0, zone_width, self.master_height, path)
            self.add_zone(zone)
            zones[name] = zone
        return zones

class VideoInVideoCompositor:
    """Composites multiple VAC3 video zones into a Master VAC3 Tensor."""
    
    def __init__(self, layout: VideoLayoutManager):
        self.layout = layout
        self.system_time_ms = 0
        self.background_color = [20, 20, 30]
    
    def composite_layer(self, layer_index: int) -> np.ndarray:
        """Create composite frame for a specific Z-layer."""
        master = np.full(
            (self.layout.master_height, self.layout.master_width, 3),
            self.background_color if layer_index == 0 else [0, 0, 0],
            dtype=np.uint8
        )
        
        for zone_name in self.layout.zone_order:
            zone = self.layout.zones[zone_name]
            try:
                frame = zone.get_z_layer(layer_index, zone.playhead)
                if frame.shape[:2] != (zone.height, zone.width):
                    frame = np.array(Image.fromarray(frame).resize(
                        (zone.width, zone.height), Image.NEAREST
                    ))
                master[zone.y:zone.y+zone.height, zone.x:zone.x+zone.width] = frame
            except Exception as e:
                print(f"Warning: Failed to composite zone {zone_name} layer {layer_index}: {e}")
                continue
                
        return master
        
    def composite_frame(self) -> np.ndarray:
        """Legacy 2D compositing helper for tests."""
        return self.composite_layer(0)
        
    def export_config(self) -> dict:
        config = {
            "master_width": self.layout.master_width,
            "master_height": self.layout.master_height,
            "system_time_ms": self.system_time_ms,
            "background_color": self.background_color,
            "zones": {}
        }
        for name, zone in self.layout.zones.items():
            config["zones"][name] = {
                "x": zone.x, "y": zone.y, "width": zone.width, "height": zone.height,
                "video_path": zone.video_path, "playhead": zone.playhead,
                "playing": zone.playing, "fps": zone.fps, "loop": zone.loop
            }
        return config
        
    def import_config(self, config: dict):
        self.layout.master_width = config["master_width"]
        self.layout.master_height = config["master_height"]
        self.system_time_ms = config["system_time_ms"]
        self.background_color = config["background_color"]
        for name, zc in config["zones"].items():
            zone = VideoZone(name, zc["x"], zc["y"], zc["width"], zc["height"],
                             zc["video_path"], loop=zc.get("loop", True))
            zone.playhead = zc["playhead"]
            zone.playing = zc["playing"]
            zone.fps = zc["fps"]
            self.layout.add_zone(zone)

    def tick(self, delta_ms: int):
        self.system_time_ms += delta_ms
        for zone in self.layout.zones.values():
            zone.advance(delta_ms)
            
    def render_vac3_timeline(self, duration_ms: int, frame_interval_ms: int = 33):
        """Render full VAC3 bundles (Z0+Z1+Z2) across the timeline."""
        frames_data = []
        timestamps = []
        
        t = 0
        last_z1_master = None
        
        while t < duration_ms:
            z0 = self.composite_layer(0)
            z1 = self.composite_layer(1)
            z2 = self.composite_layer(2)
            
            # Master Z=1 must be XOR compressed per VAC3 spec!
            if last_z1_master is not None:
                z1_delta = np.bitwise_xor(z1, last_z1_master)
            else:
                z1_delta = z1.copy()
            last_z1_master = z1.copy()
            
            bundle = z0.tobytes() + z1_delta.tobytes() + z2.tobytes()
            frames_data.append(bundle)
            timestamps.append(t)
            
            self.tick(frame_interval_ms)
            t += frame_interval_ms
            
        return frames_data, timestamps

def main():
    parser = argparse.ArgumentParser(description="VAC3 Spatial Tensor Compositor")
    parser.add_argument("--layout", "-l", choices=["grid", "side-by-side"], default="side-by-side")
    parser.add_argument("--videos", "-v", nargs="+", required=True)
    parser.add_argument("--output", "-o", default="/tmp/vac3_composite.mkv")
    parser.add_argument("--width", "-W", type=int, default=1024)
    parser.add_argument("--height", "-H", type=int, default=512)
    parser.add_argument("--duration", "-d", type=int, default=5000)
    args = parser.parse_args()
    
    layout = VideoLayoutManager(args.width, args.height)
    if args.layout == "grid":
        layout.layout_grid(2, 2, args.videos)
    else:
        layout.layout_side_by_side(args.videos)
        
    compositor = VideoInVideoCompositor(layout)
    
    for zone in layout.zones.values():
        zone.load_video()
        print(f"Loaded {zone.name}: {zone.total_frames} frames")
        
    print(f"\nCompositing {args.duration}ms VAC3 Spatial Tensor...")
    frames, timestamps = compositor.render_vac3_timeline(args.duration)
    
    metadata = {
        "format": "vac3_composite",
        "layout": args.layout,
        "pixel_width": args.width,
        "pixel_height": args.height,
        "total_frames": len(frames),
        "duration_ms": args.duration,
        "delta_encoding": "xor",
        "vac3_layers": [
            {"z_index": 0, "name": "display", "size": args.width * args.height * 3},
            {"z_index": 1, "name": "ram_substrate", "size": args.width * args.height * 3, "tiles": 1},
            {"z_index": 2, "name": "diagnostics", "size": args.width * args.height * 3}
        ]
    }
    
    mkv_path, _ = encode_mkv(b''.join(frames), args.output, metadata)
    print(f"\n✓ VAC3 Spatial Composite Generated: {mkv_path}")

if __name__ == "__main__":
    main()
