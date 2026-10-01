#!/usr/bin/env python3
"""
Geometry OS Integration Demo: Code → Pixels → Hypervisor

This demonstrates the Visual Audio → Geometry OS integration path:
1. Code stored as pixels in visual_audio.mkv
2. Extract and convert to Geometry OS hypervisor format
3. Show how pixel-native software transmission works

Integration Tasks:
- TASK_C030: Port visual audio codec to GeOS hypervisor (audio_codec.rs)
- TASK_C031: Audio boot loader (audio_boot.rs)
- TASK_C032: Phoneme-based LLM input (phoneme_input.rs)

See: GEOS_INTEGRATION_TASKS.md for full task list.
"""

import subprocess
import sys
import json
from pathlib import Path


def extract_pixel_data(mkv_path: str, entry_name: str) -> bytes:
    """Extract raw pixel data from container entry."""
    result = subprocess.run(
        ["python3", "tools/va_container.py", "cat", mkv_path, entry_name],
        capture_output=True
    )
    
    if result.returncode == 0:
        return result.stdout
    else:
        error_msg = result.stderr.decode() if result.stderr else "Unknown error"
        raise RuntimeError(f"Failed to extract {entry_name}: {error_msg}")


def show_hex_dump(data: bytes, title: str = "Pixel Data", max_lines: int = 20):
    """Display hex dump of pixel data."""
    print(f"\n{title} ({len(data)} bytes):")
    print("=" * 60)
    
    for i in range(0, min(len(data), max_lines * 16), 16):
        chunk = data[i:i+16]
        
        # Hex values
        hex_str = " ".join(f"{b:02x}" for b in chunk)
        
        # ASCII representation
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        
        # Address
        addr = f"{i:04x}"
        
        print(f"{addr}: {hex_str:<48} |{ascii_str}|")
    
    if len(data) > max_lines * 16:
        print(f"... ({len(data) - max_lines * 16} more bytes)")
    print("=" * 60)


def convert_to_geos_format(data: bytes) -> dict:
    """
    Convert raw pixel data to Geometry OS hypervisor format.

    In GeOS, pixel regions are stored in spatial memory with:
    - Position (x, y, z) in spatial grid
    - RGB24 color values
    - Metadata for size and type
    """
    # Calculate spatial coordinates
    # Each RGB pixel = 3 bytes
    pixel_count = len(data) // 3
    remainder = len(data) % 3
    
    # Arrange in frame (450x450 visual_audio standard)
    frame_width = 450
    frame_height = (pixel_count + frame_width - 1) // frame_width
    
    # Generate GeOS format structure
    geos_format = {
        "version": "1.0",
        "format": "pixel_native_software",
        "encoding": "RGB24",
        "metadata": {
            "total_bytes": len(data),
            "pixel_count": pixel_count,
            "remainder_bytes": remainder,
            "frame_size": {
                "width": frame_width,
                "height": frame_height
            },
            "spatial_position": {
                "x": 0,
                "y": 0,
                "z": 0
            }
        },
        "data": data.hex()
    }
    
    return geos_format


def show_integration_path():
    """Display the complete integration path from code to GeOS execution."""
    print("\n" + "=" * 70)
    print("GEOMETRY OS INTEGRATION PATH")
    print("=" * 70)
    
    print("""
Step 1: Code → Dense Encoding (visual_audio)
    Code: print("hello world")
    ↓ tools/dense_encoder.py
    Pixels: RGB24 (3 bytes/pixel)
    ↓ visual_audio.mkv storage
    MKV Frame: CRC32 + payload + SHA256

Step 2: Pixel → Hypervisor Format (GeOS integration)
    Extract pixels from MKV
    ↓ geometry_os/src/spatial/audio_codec.rs
    Spatial Memory: RGBA32 with position metadata
    ↓
    Region ID: allocated in GeOS spatial grid

Step 3: Pixel → Audio (for transmission)
    Spectral Codec: 16-tone MFSK (800-3050 Hz)
    ↓ tools/speak.py encode
    Audio: ~24 bytes/sec throughput
    ↓
    Transmission: speaker → microphone or wire

Step 4: Audio → Pixel (reception)
    Audio received
    ↓ tools/speak.py decode
    Pixels: RGB24 recovered
    ↓ Reed-Solomon ECC (5% error correction)

Step 5: Pixel → Execute (GeOS hypervisor)
    Spatial memory access
    ↓ geometry_os/src/boot/audio_boot.rs
    Software loaded into hypervisor
    ↓
    Execution: pixel-native software runs

Integration Points:
  - audio_codec.rs: Pixel region encode/decode (TASK_C030)
  - audio_boot.rs: Audio boot loader (TASK_C031)
  - phoneme_input.rs: LLM speech → software (TASK_C032)
    """)
    
    print("=" * 70)
    print("CURRENT STATUS")
    print("=" * 70)
    print("""
✓ Visual Audio:
  - Dense encoding (3 bytes/pixel) - COMPLETE
  - MKV container storage - COMPLETE
  - Direct execution from container - COMPLETE
  - Byte-perfect round-trip - VERIFIED

🔴 Geometry OS (needs implementation):
  - TASK_C030: audio_codec.rs - TODO
  - TASK_C031: audio_boot.rs - TODO
  - TASK_C032: phoneme_input.rs - TODO

Documentation:
  - GEOS_INTEGRATION_TASKS.md - task definitions
  - docs/CODE_TO_PIXEL_WORKFLOW.md - workflow guide
    """)
    
    print("=" * 70)


def main():
    """Run the Geometry OS integration demo."""
    MKV_PATH = "visual_audio.mkv"
    TEST_ENTRY = "demo_code_system.py"
    
    print("=" * 70)
    print("GEOMETRY OS INTEGRATION: Visual Audio → Hypervisor")
    print("=" * 70)
    
    # Show integration path
    show_integration_path()
    
    # Extract pixel data from container
    print(f"\nExtracting pixel data from {TEST_ENTRY}...")
    try:
        pixel_data = extract_pixel_data(MKV_PATH, TEST_ENTRY)
    except RuntimeError as e:
        print(f"\n✗ {e}")
        print("\nMake sure the entry exists in the container:")
        print(f"  python3 tools/va_container.py ls {MKV_PATH}")
        return 1
    
    # Show hex dump
    show_hex_dump(pixel_data, f"Pixel Data: {TEST_ENTRY}", max_lines=10)
    
    # Convert to GeOS format
    print("\nConverting to Geometry OS hypervisor format...")
    geos_format = convert_to_geos_format(pixel_data)
    
    print(f"✓ GeOS format generated")
    print(f"  Total bytes: {geos_format['metadata']['total_bytes']}")
    print(f"  Pixel count: {geos_format['metadata']['pixel_count']}")
    print(f"  Frame size: {geos_format['metadata']['frame_size']['width']}x{geos_format['metadata']['frame_size']['height']}")
    print(f"  Spatial position: ({geos_format['metadata']['spatial_position']['x']}, {geos_format['metadata']['spatial_position']['y']}, {geos_format['metadata']['spatial_position']['z']})")
    
    # Save GeOS format
    output_path = Path("geos_pixel_software.json")
    output_path.write_text(json.dumps(geos_format, indent=2))
    print(f"\n✓ GeOS format saved to {output_path}")
    
    # Show example of how this would be used in GeOS
    print("\n" + "=" * 70)
    print("USAGE IN GEOMETRY OS (PSEUDOCODE)")
    print("=" * 70)
    print("""
// In geometry_os/src/spatial/audio_codec.rs

pub fn decode_pixel_region(
    spatial_memory: &SpatialMemory,
    region_id: RegionId,
) -> Result<Vec<u8>, AudioCodecError> {
    // Read pixel data from spatial memory
    let pixel_data = spatial_memory.read_region(region_id)?;
    
    // Decode RGB24 to bytes
    let mut bytes = Vec::new();
    for chunk in pixel_data.chunks(3) {
        if chunk.len() == 3 {
            let byte = (chunk[0] as u32) << 16 
                     | (chunk[1] as u32) << 8 
                     | (chunk[2] as u32);
            bytes.push(byte as u8);
        }
    }
    
    Ok(bytes)
}

// In geometry_os/src/boot/audio_boot.rs

pub fn boot_from_audio(audio_stream: &mut dyn AudioStream) -> Result<(), BootError> {
    // Decode audio to pixels
    let pixel_data = audio_codec::decode_audio_to_pixels(audio_stream)?;
    
    // Store in spatial memory
    let region_id = spatial_memory.allocate_region(pixel_data.len())?;
    spatial_memory.write_region(region_id, &pixel_data)?;
    
    // Decode pixels to kernel image
    let kernel_bytes = audio_codec::decode_pixel_region(&spatial_memory, region_id)?;
    
    // Load kernel into hypervisor
    hypervisor::load_kernel(&kernel_bytes)?;
    
    // Jump to entry point
    hypervisor::jump_to_entry();
    
    Ok(())
}
    """)
    
    print("=" * 70)
    print("✓ INTEGRATION DEMO COMPLETE")
    print("=" * 70)
    print("\nNext steps for full integration:")
    print("1. Implement TASK_C030: audio_codec.rs in GeOS")
    print("2. Implement TASK_C031: audio_boot.rs in GeOS")
    print("3. Implement TASK_C032: phoneme_input.rs in GeOS")
    print("4. Test end-to-end: code → audio → hypervisor → execute")
    print("\nSee GEOS_INTEGRATION_TASKS.md for full task definitions.")
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())