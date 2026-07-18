import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from va_container import frame_to_chunk


def test_mkvpalace_bridge_roundtrip():
    """
    Test MKV to Memory Palace PNG bridge.
    Verifies that we can extract entries as Palace tiles and read them back
    losslessly using the coordinate manifest.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        mkv_path = tmp_path / "test.mkv"
        palace_path = tmp_path / "palace.png"
        manifest_path = tmp_path / "palace.png.manifest.json"
        
        # Tools paths
        tools_dir = Path(__file__).resolve().parent.parent / "tools"
        va_container = tools_dir / "va_container.py"
        mkv_to_palace = tools_dir / "mkv_to_palace.py"
        
        # 1. Initialize MKV
        subprocess.run([sys.executable, str(va_container), "init", str(mkv_path)], check=True)
        
        # 2. Add payloads
        payload1 = b"Visual Audio " * 6000  # ~78KB, spans 2 frames
        payload2 = b"Small payload for test."
        
        p1_path = tmp_path / "p1.bin"
        p2_path = tmp_path / "p2.bin"
        p1_path.write_bytes(payload1)
        p2_path.write_bytes(payload2)
        
        subprocess.run([sys.executable, str(va_container), "add", str(mkv_path), str(p1_path), "--name", "large_entry"], check=True)
        subprocess.run([sys.executable, str(va_container), "add", str(mkv_path), str(p2_path), "--name", "small_entry"], check=True)
        
        # 3. Generate Palace PNG with specific tile size
        tile_size = 512
        subprocess.run([
            sys.executable, str(mkv_to_palace), 
            str(mkv_path), 
            str(palace_path),
            "--tile-size", str(tile_size),
            "--manifest", str(manifest_path)
        ], check=True)
        
        assert palace_path.exists()
        assert manifest_path.exists()
        
        # 4. Read Manifest and PNG
        with open(manifest_path) as f:
            manifest = json.load(f)
            
        assert manifest["tile_size"] == tile_size
        img = Image.open(palace_path)
        assert img.mode == "RGBA"
        img_array = np.array(img)
        
        # 5. Verify and restore payloads
        for entry_name, original_payload in [("large_entry", payload1), ("small_entry", payload2)]:
            assert entry_name in manifest["entries"]
            entry_info = manifest["entries"][entry_name]
            
            # Sort chunks by index to reconstruct in order
            chunks_meta = sorted(entry_info["chunks"], key=lambda x: x["chunk_index"])
            
            reconstructed = b""
            for chunk_meta in chunks_meta:
                x1, y1, x2, y2 = chunk_meta["pixel_bounds"]
                
                # Extract tile
                tile = img_array[y1:y2, x1:x2]
                assert tile.shape == (tile_size, tile_size, 4)
                
                # Strip padding and alpha channel to get back 450x450x3 MKV frame
                # original frame is 450x450x3
                original_frame_size = 450
                frame_rgb = tile[:original_frame_size, :original_frame_size, :3]
                
                # Unpack chunk
                chunk_data = frame_to_chunk(frame_rgb)
                reconstructed += chunk_data
                
            # Truncate to exact length as MKV pads the last frame
            reconstructed = reconstructed[:entry_info["length"]]
            
            assert reconstructed == original_payload, f"Payload mismatch for {entry_name}"
