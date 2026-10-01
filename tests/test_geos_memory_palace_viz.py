#!/usr/bin/env python3
"""
Test suite for TASK_V006: GeOS memory palace visualization

Tests the geos_memory_palace_viz.py tool for:
- Color band rendering (magenta/yellow/cyan)
- Metadata embedding in PNG
- Round-trip encode/decode
- Integration with V002 (dual-band) and V003 (ECC)
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tools.geos_memory_palace_viz import (
    GeOSMemoryPalaceVisualizer,
    PalaceTile,
    PalaceState,
    COLOR_MAGENTA,
    COLOR_YELLOW,
    COLOR_CYAN,
    TILE_SIZE,
    GRID_WIDTH,
    GRID_HEIGHT
)

def test_color_band_rendering():
    """Test that color bands render correctly for each modality."""
    print("TEST: Color band rendering")

    viz = GeOSMemoryPalaceVisualizer()

    # Create test state with one tile of each modality
    state = PalaceState()
    state.metadata = {'test': 'color_bands'}

    tiles = [
        PalaceTile(x=0, y=0, modality='audio', data_hash='a1', data={'test': 'audio'}, has_audio=True),
        PalaceTile(x=1, y=0, modality='ecc', data_hash='e1', data={'test': 'ecc'}, ecc_status='ok'),
        PalaceTile(x=2, y=0, modality='executable', data_hash='x1', data={'test': 'exec'}),
    ]
    state.tiles = tiles

    # Render to PNG
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        output_path = f.name

    try:
        viz.render_to_png(state, output_path)

        # Verify PNG exists and has correct dimensions
        from PIL import Image
        img = Image.open(output_path)
        assert img.width == GRID_WIDTH * TILE_SIZE, f"Width mismatch: {img.width} vs {GRID_WIDTH * TILE_SIZE}"
        assert img.height == GRID_HEIGHT * TILE_SIZE, f"Height mismatch: {img.height} vs {GRID_HEIGHT * TILE_SIZE}"

        # Sample interior of each tile to verify colors
        # Tile 0 (audio): magenta
        pixel = img.getpixel((2, 2))
        r, g, b = pixel[:3]
        assert r > 200 and g < 50 and b > 200, f"Tile 0 not magenta: RGB({r},{g},{b})"

        # Tile 1 (ECC): yellow
        pixel = img.getpixel((18, 2))
        r, g, b = pixel[:3]
        assert r > 200 and g > 200 and b < 50, f"Tile 1 not yellow: RGB({r},{g},{b})"

        # Tile 2 (executable): cyan
        pixel = img.getpixel((34, 2))
        r, g, b = pixel[:3]
        assert r < 50 and g > 200 and b > 200, f"Tile 2 not cyan: RGB({r},{g},{b})"

        print("  ✓ Color bands render correctly")
        return True

    finally:
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_metadata_embedding():
    """Test that metadata is embedded in PNG and can be retrieved."""
    print("TEST: Metadata embedding")

    viz = GeOSMemoryPalaceVisualizer()

    # Create state with metadata
    state = PalaceState()
    state.metadata = {
        'version': '1.0',
        'description': 'Test metadata',
        'custom_field': 'test_value'
    }
    state.tiles = []

    # Render
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        output_path = f.name

    try:
        viz.render_to_png(state, output_path)

        # Read PNG and verify metadata
        from PIL import Image, PngImagePlugin
        img = Image.open(output_path)
        pnginfo = img.info

        assert 'vamp_metadata' in pnginfo, "vamp_metadata not in PNG"
        assert 'generator' in pnginfo, "generator not in PNG"
        assert 'version' in pnginfo, "version not in PNG"

        # Parse embedded metadata
        metadata_json = pnginfo['vamp_metadata']
        metadata = json.loads(metadata_json)

        assert metadata['version'] == '1.0', f"Version mismatch: {metadata['version']}"
        assert metadata['metadata']['custom_field'] == 'test_value', "Custom field not preserved"

        print("  ✓ Metadata embedded and retrievable")
        return True

    finally:
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_roundtrip_encode_decode():
    """Test that encode/decode round-trip preserves tile modality."""
    print("TEST: Round-trip encode/decode")

    viz = GeOSMemoryPalaceVisualizer()

    # Create state with various tiles
    state = PalaceState()
    state.metadata = {'test': 'roundtrip'}

    tiles = [
        PalaceTile(x=0, y=0, modality='audio', data_hash='a1', data={}, has_audio=True),
        PalaceTile(x=1, y=0, modality='audio', data_hash='a2', data={}, has_audio=False),  # No audio
        PalaceTile(x=2, y=0, modality='ecc', data_hash='e1', data={}, ecc_status='corrupted'),
        PalaceTile(x=3, y=0, modality='ecc', data_hash='e2', data={}, ecc_status='ok'),
        PalaceTile(x=4, y=0, modality='executable', data_hash='x1', data={}),
    ]
    state.tiles = tiles

    # Render
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        png_path = f.name
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        json_path = f.name

    try:
        viz.render_to_png(state, png_path)

        # Decode
        decoded_state = viz.decode_png(png_path, json_path)

        # Verify tile count
        assert len(decoded_state.tiles) == 5, f"Tile count mismatch: {len(decoded_state.tiles)} vs 5"

        # Verify modality preservation
        modalities = [t.modality for t in decoded_state.tiles]
        assert modalities == ['audio', 'audio', 'ecc', 'ecc', 'executable'], \
            f"Modalities mismatch: {modalities}"

        # Verify audio status preservation
        audio_flags = [t.has_audio for t in decoded_state.tiles[:2]]
        assert audio_flags == [True, False], f"Audio flags mismatch: {audio_flags}"

        # Verify ECC status preservation
        ecc_statuses = [t.ecc_status for t in decoded_state.tiles[2:4]]
        assert ecc_statuses == ['corrupted', 'ok'], f"ECC statuses mismatch: {ecc_statuses}"

        print("  ✓ Round-trip encode/decode preserves state")
        return True

    finally:
        for path in [png_path, json_path]:
            if os.path.exists(path):
                os.unlink(path)


def test_v002_integration():
    """Test integration with TASK_V002 (dual-band audio export)."""
    print("TEST: V002 integration (dual-band audio tiles)")

    viz = GeOSMemoryPalaceVisualizer()

    # Create V002-style data
    vamp_data = {
        'version': '1.0',
        'metadata': {
            'source': 'vamp_audio_export.py',
            'description': 'Dual-band audio export'
        },
        'entries': [
            {
                'index': 0,
                'audio_path': '/tmp/batch_001.wav',
                'dual_band': True,
                'summary': 'Test summary'
            },
            {
                'index': 1,
                'audio_path': '/tmp/batch_002.wav',
                'dual_band': True,
                'summary': 'Another summary'
            }
        ]
    }

    # Create temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(vamp_data, f)
        vamp_json = f.name

    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        png_path = f.name

    try:
        # Load VAMP data and render
        state = viz.load_vamp_data(vamp_json)
        viz.render_to_png(state, png_path)

        # Decode and verify audio tiles
        decoded = viz.decode_png(png_path)

        audio_tiles = [t for t in decoded.tiles if t.modality == 'audio']
        assert len(audio_tiles) == 2, f"Expected 2 audio tiles, got {len(audio_tiles)}"

        # All V002 tiles should have audio indicator
        assert all(t.has_audio for t in audio_tiles), "V002 tiles missing audio indicator"

        print("  ✓ V002 integration works correctly")
        return True

    finally:
        for path in [vamp_json, png_path]:
            if os.path.exists(path):
                os.unlink(path)


def test_v003_integration():
    """Test integration with TASK_V003 (Reed-Solomon ECC tiles)."""
    print("TEST: V003 integration (ECC tiles)")

    viz = GeOSMemoryPalaceVisualizer()

    # Create V003-style data
    vamp_data = {
        'version': '1.0',
        'metadata': {
            'source': 'phoneme_ecc.py',
            'description': 'Reed-Solomon protected tiles'
        },
        'entries': [
            {
                'index': 0,
                'ecc_parity': 'parity_bytes_0',
                'rs_encoded': True,
                'data': {'original': 'test_data_0'}
            },
            {
                'index': 1,
                'ecc_parity': 'parity_bytes_1',
                'rs_encoded': True,
                'data': {'original': 'test_data_1'}
            }
        ]
    }

    # Create temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(vamp_data, f)
        vamp_json = f.name

    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        png_path = f.name

    try:
        # Load VAMP data and render
        state = viz.load_vamp_data(vamp_json)
        viz.render_to_png(state, png_path)

        # Decode and verify ECC tiles
        decoded = viz.decode_png(png_path)

        ecc_tiles = [t for t in decoded.tiles if t.modality == 'ecc']
        assert len(ecc_tiles) == 2, f"Expected 2 ECC tiles, got {len(ecc_tiles)}"

        # V003 tiles should be marked with ECC
        assert all(t.ecc_status == 'ok' for t in ecc_tiles), "ECC status not set correctly"

        print("  ✓ V003 integration works correctly")
        return True

    finally:
        for path in [vamp_json, png_path]:
            if os.path.exists(path):
                os.unlink(path)


def test_geos_cartridge_format():
    """Test that output is a valid dense PNG cartridge."""
    print("TEST: GeOS cartridge format")

    viz = GeOSMemoryPalaceVisualizer()

    # Create simple state
    state = PalaceState()
    state.tiles = [
        PalaceTile(x=0, y=0, modality='audio', data_hash='a1', data={}, has_audio=True),
    ]

    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        png_path = f.name

    try:
        viz.render_to_png(state, png_path)

        # Verify PNG format
        from PIL import Image
        img = Image.open(png_path)

        # Check dimensions (1024x1024 = 64x64 tiles @ 16px)
        assert img.width == 1024, f"Width not 1024: {img.width}"
        assert img.height == 1024, f"Height not 1024: {img.height}"

        # Check RGBA mode (required for dense cartridges)
        assert img.mode == 'RGBA', f"Mode not RGBA: {img.mode}"

        # Check file size is reasonable
        file_size = os.path.getsize(png_path)
        assert file_size < 50_000, f"File size too large: {file_size} bytes"

        print("  ✓ GeOS cartridge format valid")
        return True

    finally:
        if os.path.exists(png_path):
            os.unlink(png_path)


def main():
    """Run all tests."""
    print("=" * 60)
    print("TASK_V006: GeOS Memory Palace Visualization Tests")
    print("=" * 60)
    print()

    tests = [
        test_color_band_rendering,
        test_metadata_embedding,
        test_roundtrip_encode_decode,
        test_v002_integration,
        test_v003_integration,
        test_geos_cartridge_format,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
                print(f"  ✗ {test.__name__} FAILED")
        except Exception as e:
            failed += 1
            print(f"  ✗ {test.__name__} EXCEPTION: {e}")
            import traceback
            traceback.print_exc()

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())