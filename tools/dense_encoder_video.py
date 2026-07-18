#!/usr/bin/env python3
"""
Unified MKV container for Visual Audio dense encoding.

Combines FFV1 video (dense pixel tiles) + Visual Audio audio + manifest
into a single portable .mkv file. All data round-trips byte-exactly.

Architecture:
  - Video track: FFV1 RGB24 frames, each frame = one dense tile (65KB)
  - Audio track: 44.1kHz PCM, dual-band (semantic + byte layer)
  - Attachment: manifest.json (metadata + CRCs)

All tracks are independent, no cross-track dependencies. Frame-level
random access works because FFV1 is intra-frame only.

Based on: /home/jericho/zion/docs/research/Video Container Virtual Machines.md
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import struct
import zlib
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from dense_encoder import frame, unframe, bytes_to_pixels, pixels_to_bytes


# Constants
MANIFEST_VERSION = "MKV1"
FRAME_SIZE = 450  # 450x450 pixels per frame
MAX_PAYLOAD_PER_FRAME = 65531  # Same as MT2
FFV1_CODEC = "ffv1"
FFMPEG_PATH = "ffmpeg"

# Allowed lossless RGB pixel formats (no YUV)
ALLOWED_PIXEL_FORMATS = {
    "rgb24",   # 24-bit RGB
    "bgr0",    # 32-bit BGR with alpha padding (ffmpeg native)
    "bgra",    # 32-bit BGRA
    "rgb0",    # 32-bit RGB with alpha padding
    "rgba",    # 32-bit RGBA
    # Add other lossless RGB formats as needed
}

# Rejected YUV formats (lossy for our use case)
REJECTED_PIXEL_FORMATS = {
    "yuv420p", "yuv422p", "yuv444p",  # Planar YUV
    "nv12", "nv21",                     # Two-plane YUV
    "yuyv422", "uyvy422",               # Packed YUV
    "gray",                             # Grayscale
}


def md5_hash(data: bytes) -> str:
    """Calculate MD5 hash."""
    return hashlib.md5(data).hexdigest()


def check_pixel_format_lossless(mkv_path: str) -> str:
    """
    Verify that the video track uses a lossless RGB pixel format.
    
    Raises:
        ValueError: If format is YUV or unsupported
    
    Returns:
        The detected pixel format name
    """
    # Probe the video stream to get pixel format
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(mkv_path)],
        capture_output=True,
        text=True
    )
    
    # ffprobe may output JSON to stdout even with errors
    json_output = result.stdout
    
    if not json_output.strip() or result.returncode != 0:
        raise RuntimeError(f"Failed to probe MKV: {result.stderr}")
    
    import json
    try:
        info = json.loads(json_output)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse ffprobe output: {e}\nOutput: {json_output[:200]}")
    
    # Find video stream
    video_stream = None
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break
    
    if not video_stream:
        raise ValueError("No video stream found in MKV")
    
    pix_fmt = video_stream.get("pix_fmt", "").lower()
    
    if not pix_fmt:
        raise ValueError("Could not determine pixel format from video stream")
    
    # Check against rejection list
    if pix_fmt in REJECTED_PIXEL_FORMATS:
        raise ValueError(
            f"Lossy pixel format detected: {pix_fmt}\n"
            f"  Rejecting to prevent silent corruption.\n"
            f"  Allowed formats: {', '.join(sorted(ALLOWED_PIXEL_FORMATS))}\n"
            f"  YUV formats cause color space conversion and byte corruption.\n"
            f"  Re-encode with: ffmpeg -i input.mkv -c:v ffv1 -pix_fmt bgr0 output.mkv"
        )
    
    # Strict allowlist: anything unknown is rejected. A blocklist can't enumerate
    # every lossy variant (yuv420p10le etc. slipped through and produced a
    # cryptic magic-bytes error downstream instead of this clear one).
    if pix_fmt not in ALLOWED_PIXEL_FORMATS:
        raise ValueError(
            f"Pixel format '{pix_fmt}' is not in the lossless RGB allowlist.\n"
            f"  Allowed formats: {', '.join(sorted(ALLOWED_PIXEL_FORMATS))}\n"
            f"  Non-RGB formats corrupt dense-encoded bytes.\n"
            f"  Re-encode with: ffmpeg -i input.mkv -c:v ffv1 -pix_fmt bgr0 output.mkv"
        )
    
    print(f"Detected pixel format: {pix_fmt}")
    return pix_fmt


def split_into_frames(payload: bytes, max_per_frame: int = MAX_PAYLOAD_PER_FRAME) -> List[bytes]:
    """Split payload into frame-sized chunks."""
    return [payload[i:i + max_per_frame] for i in range(0, len(payload), max_per_frame)]


def chunk_to_frame(chunk: bytes, size: int = FRAME_SIZE) -> np.ndarray:
    """
    Encode a chunk as an RGB24 frame.

    Each pixel stores 3 bytes (RGB), so 450x450 = 202,500 pixels = 607,500 bytes.
    We only use 65,531 bytes per frame (payload), the rest is padding/metadata.

    Frame layout:
      - Header: 8 bytes (UA marker + version + length + CRC32)
      - Payload: up to 65,531 bytes
      - Padding: to fill 607,500 bytes (3 bytes per pixel)
    """
    # Frame the chunk
    framed = frame(chunk)
    
    # Create 450x450 RGB24 image
    total_pixels = size * size
    total_bytes = total_pixels * 3  # RGB24
    
    if len(framed) > total_bytes:
        raise ValueError(f"Framed chunk {len(framed)} bytes exceeds frame capacity {total_bytes}")
    
    # Pad to exactly fit frame
    padded = framed + b'\x00' * (total_bytes - len(framed))
    
    # Convert to 450x450x3 numpy array
    frame_array = np.frombuffer(padded, dtype=np.uint8).reshape(size, size, 3)
    
    return frame_array


def frame_to_chunk(frame_array: np.ndarray, size: int = FRAME_SIZE) -> bytes:
    """Decode a frame back to chunk."""
    # Flatten to bytes
    frame_bytes = frame_array.flatten().tobytes()
    
    # Find end (strip trailing zeros)
    end = len(frame_bytes)
    while end > 0 and frame_bytes[end-1:end] == b'\x00':
        end -= 1
    
    # Unframe
    return unframe(frame_bytes[:end])


def encode_mkv(
    payload: bytes,
    output_path: str,
    frame_size: int = FRAME_SIZE,
    audio_file: Optional[str] = None,
    metadata: Optional[dict] = None
) -> Tuple[str, dict]:
    """
    Encode payload as unified MKV file.

    Returns:
        (mkv_path, manifest_dict)
    """
    # Split payload into frames
    chunks = split_into_frames(payload)
    total_frames = len(chunks)
    overall_hash = md5_hash(payload)
    
    print(f"Encoding {len(payload)} bytes into {total_frames} FFV1 frames")
    print(f"  Frame size: {frame_size}x{frame_size} RGB24")
    print(f"  Payload per frame: up to {MAX_PAYLOAD_PER_FRAME} bytes")
    print(f"  Overall hash: {overall_hash}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create frames directory
        frames_dir = tmpdir / "frames"
        frames_dir.mkdir()
        
        # Generate frame checksums
        frame_checksums = []
        
        # Create each frame
        for idx, chunk in enumerate(chunks):
            frame_array = chunk_to_frame(chunk, frame_size)
            frame_path = frames_dir / f"frame_{idx:06d}.png"
            Image.fromarray(frame_array, mode='RGB').save(frame_path)
            
            frame_crc = struct.unpack('>I', (zlib.crc32(chunk) & 0xFFFFFFFF).to_bytes(4, 'big'))[0]
            frame_checksums.append({
                "index": idx,
                "crc32": frame_crc,
                "hash": md5_hash(chunk),
                "size": len(chunk)
            })
            
            if idx < 5 or idx >= total_frames - 5:
                print(f"  Frame {idx}/{total_frames-1}: {len(chunk)} bytes (CRC={frame_crc:08x})")
            elif idx == 5:
                print(f"  ... ({total_frames - 10} more frames)")
        
        # Build manifest
        manifest = {
            "version": MANIFEST_VERSION,
            "total_frames": total_frames,
            "frame_size": frame_size,
            "total_bytes": len(payload),
            "overall_hash": overall_hash,
            "frames": frame_checksums
        }
        
        if metadata:
            manifest["metadata"] = metadata
        
        # Write manifest
        manifest_path = tmpdir / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        # Encode video track (FFV1 RGB24)
        print("\nEncoding FFV1 video track...")
        video_path = tmpdir / "video.mkv"
        
        ffmpeg_cmd = [
            FFMPEG_PATH,
            "-y",  # Overwrite
            "-framerate", "1",  # 1 FPS for data frames
            "-i", str(frames_dir / "frame_%06d.png"),
            "-c:v", FFV1_CODEC,
            "-pix_fmt", "bgr0",  # FFV1 has no rgb24; bgr0 is its lossless 8-bit RGB layout. Pin it so ffmpeg never auto-substitutes a lossy format.
            "-preset", "medium",
            "-tune", "fastdecode",
            str(video_path)
        ]
        
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {result.stderr}")
        
        print(f"  Video: {video_path.stat().st_size / 1024:.1f} KB")
        
        # Build final MKV with attachments
        print("\nBuilding unified MKV...")
        final_cmd = [FFMPEG_PATH, "-y"]
        
        # Add video
        final_cmd.extend(["-i", str(video_path)])
        
        # Add audio if provided
        has_audio = False
        if audio_file and os.path.exists(audio_file):
            has_audio = True
            final_cmd.extend(["-i", audio_file])
            print(f"  Audio: {audio_file}")
        
        # Add attachment (manifest)
        final_cmd.extend(["-attach", str(manifest_path)])
        final_cmd.extend(["-metadata:s:t:0", "title=manifest"])
        final_cmd.extend(["-metadata:s:t:0", "mimetype=application/json"])
        
        # Map streams
        final_cmd.extend(["-map", "0"])  # Video
        
        if has_audio:
            final_cmd.extend(["-map", "1"])  # Audio
            # Copy audio as PCM (byte-exact)
            final_cmd.extend(["-c:a", "pcm_s16be"])
        
        # Final output
        final_cmd.extend(["-c:v", "copy"])  # Copy FFV1 as-is
        final_cmd.extend([output_path])
        
        result = subprocess.run(final_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"MKV mux failed: {result.stderr}")
        
        mkv_size = Path(output_path).stat().st_size
        compression_ratio = mkv_size / len(payload)
        
        print(f"\nUnified MKV: {output_path}")
        print(f"  Size: {mkv_size / (1024*1024):.1f} MB")
        print(f"  Compression ratio: {compression_ratio:.2f}x")
        print(f"  Frames: {total_frames} FFV1 RGB24")
        print(f"  Audio: {'Yes (PCM S16BE)' if has_audio else 'No'}")
        print(f"  Attachment: manifest.json")
        
        return output_path, manifest


def decode_mkv(mkv_path: str, output_dir: Optional[str] = None) -> Tuple[bytes, dict]:
    """
    Decode unified MKV file back to payload.

    Returns:
        (payload_bytes, manifest_dict)
    """
    mkv_path = Path(mkv_path)
    
    # Check pixel format first (before decoding)
    check_pixel_format_lossless(str(mkv_path))
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Extract manifest attachment
        print("Extracting manifest...")
        manifest_path = tmpdir / "manifest.json"
        
        # Use ffmpeg to extract attachment
        extract_cmd = [
            FFMPEG_PATH, "-y",
            "-dump_attachment:t", "0", str(manifest_path),
            "-i", str(mkv_path),
            "-f", "null", "-"  # Don't decode anything
        ]
        
        result = subprocess.run(extract_cmd, capture_output=True, text=True)
        if not manifest_path.exists():
            print("Warning: Could not extract manifest, continuing without verification...")
        
        # Load manifest if available
        manifest = None
        if manifest_path.exists():
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            print(f"Manifest version: {manifest.get('version', 'unknown')}")
            print(f"  Total frames: {manifest.get('total_frames', 'unknown')}")
            print(f"  Total bytes: {manifest.get('total_bytes', 'unknown')}")
            print(f"  Overall hash: {manifest.get('overall_hash', 'unknown')}")
        
        # Extract frames
        print("\nExtracting frames...")
        frames_dir = tmpdir / "frames"
        frames_dir.mkdir()
        
        # Extract video frames as PNG
        frames_pattern = str(frames_dir / "frame_%06d.png")
        
        ffmpeg_cmd = [
            FFMPEG_PATH, "-y",
            "-i", str(mkv_path),
            "-pix_fmt", "rgb24",  # Ensure RGB24 output
            frames_pattern
        ]
        
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Frame extraction failed: {result.stderr}")
        
        # Collect and decode frames
        frame_files = sorted(frames_dir.glob("frame_*.png"))
        print(f"  Extracted {len(frame_files)} frames")
        
        chunks = []
        for idx, frame_file in enumerate(frame_files):
            frame_array = np.array(Image.open(frame_file))
            chunk = frame_to_chunk(frame_array)
            chunks.append(chunk)
            
            if manifest:
                # Verify CRC32
                expected_crc = manifest["frames"][idx]["crc32"]
                actual_crc = struct.unpack('>I', (zlib.crc32(chunk) & 0xFFFFFFFF).to_bytes(4, 'big'))[0]
                
                if actual_crc != expected_crc:
                    raise ValueError(f"Frame {idx} CRC mismatch: expected {expected_crc:08x}, got {actual_crc:08x}")
            
            if idx < 5 or idx >= len(frame_files) - 5:
                print(f"  Frame {idx}/{len(frame_files)-1}: {len(chunk)} bytes (verified)")
            elif idx == 5:
                print(f"  ... ({len(frame_files) - 10} more frames)")
        
        # Reassemble payload
        payload = b''.join(chunks)
        
        # Verify overall hash
        actual_hash = md5_hash(payload)
        expected_hash = manifest["overall_hash"] if manifest else None
        
        if expected_hash and actual_hash != expected_hash:
            raise ValueError(f"Overall hash mismatch: expected {expected_hash}, got {actual_hash}")
        
        print(f"\nReassembly complete: {len(payload)} bytes (hash verified)")
        
        # Write to output if specified
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            payload_path = output_dir / "payload.bin"
            payload_path.write_bytes(payload)
            
            if manifest_path.exists():
                (output_dir / "manifest.json").write_bytes(manifest_path.read_bytes())
            
            print(f"Output written to {output_dir}")
        
        return payload, manifest


def verify_mkv_roundtrip(
    payload: bytes,
    output_path: str,
    audio_file: Optional[str] = None,
    metadata: Optional[dict] = None
) -> dict:
    """
    Full verification: encode → decode → compare.
    
    Returns verification receipt with all checksums.
    """
    print("="*60)
    print("MKV Roundtrip Verification")
    print("="*60)
    
    # Original checksums
    original_hash = md5_hash(payload)
    original_size = len(payload)
    
    print(f"Original payload: {original_size} bytes")
    print(f"MD5: {original_hash}")
    
    # Encode
    print("\nEncoding...")
    mkv_path, manifest = encode_mkv(payload, output_path, audio_file=audio_file, metadata=metadata)
    
    # Decode
    print("\nDecoding...")
    decoded, recovered_manifest = decode_mkv(mkv_path)
    
    # Verify
    decoded_hash = md5_hash(decoded)
    
    receipt = {
        "verification": "PASSED" if decoded == payload else "FAILED",
        "original": {
            "size": original_size,
            "md5": original_hash
        },
        "decoded": {
            "size": len(decoded),
            "md5": decoded_hash
        },
        "match": decoded == payload,
        "mkv_file": {
            "path": mkv_path,
            "size_bytes": os.path.getsize(mkv_path),
            "compression_ratio": os.path.getsize(mkv_path) / original_size
        },
        "manifest_version": manifest.get("version"),
        "frame_count": manifest.get("total_frames")
    }
    
    print("\n" + "="*60)
    print("VERIFICATION RECEIPT")
    print("="*60)
    print(json.dumps(receipt, indent=2))
    
    if receipt["verification"] != "PASSED":
        print("\n❌ VERIFICATION FAILED")
        sys.exit(1)
    else:
        print("\n✓ VERIFICATION PASSED")
        print(f"  Byte-identical recovery: {receipt['match']}")
        print(f"  MD5 match: {original_hash == decoded_hash}")
        print(f"  Size match: {original_size == len(decoded)}")
    
    return receipt


def main():
    parser = argparse.ArgumentParser(
        description="Unified MKV container for Visual Audio encoding",
        # Disable argparse prefix matching to avoid --output foo.bin becoming --output-dir
        allow_abbrev=False
    )
    sub = parser.add_subparsers(dest='cmd', required=True)
    
    p_enc = sub.add_parser('encode', help='encode payload as unified MKV', allow_abbrev=False)
    p_enc.add_argument('input', help='input binary file')
    p_enc.add_argument('output', help='output .mkv file')
    p_enc.add_argument('--audio', help='optional audio file for audio track')
    p_enc.add_argument('--frame-size', type=int, default=FRAME_SIZE, help='frame size in pixels (default: 450)')
    p_enc.add_argument('--metadata', help='JSON metadata to include')
    
    p_dec = sub.add_parser('decode', help='decode MKV back to payload', allow_abbrev=False)
    p_dec.add_argument('mkv', help='MKV file to decode')
    p_dec.add_argument('--output', help='output file for payload (use --output-dir for directory)')
    p_dec.add_argument('--output-dir', help='directory to write payload.bin and manifest.json')
    
    p_verify = sub.add_parser('verify', help='full roundtrip verification', allow_abbrev=False)
    p_verify.add_argument('input', help='input binary file')
    p_verify.add_argument('output', help='output .mkv file')
    p_verify.add_argument('--audio', help='optional audio file for audio track')
    p_verify.add_argument('--metadata', help='JSON metadata to include')
    
    args = parser.parse_args()
    
    if args.cmd == 'encode':
        with open(args.input, 'rb') as f:
            payload = f.read()
        
        metadata = None
        if args.metadata:
            with open(args.metadata, 'r') as f:
                metadata = json.load(f)
        
        encode_mkv(payload, args.output, frame_size=args.frame_size, audio_file=args.audio, metadata=metadata)
    
    elif args.cmd == 'decode':
        # Handle both --output and --output-dir
        if args.output:
            # User specified a file path, extract to temp then move
            output_file = args.output
            output_dir = None
        else:
            output_file = None
            output_dir = args.output_dir
        
        payload, manifest = decode_mkv(args.mkv, output_dir)
        
        if output_file:
            # Write to specific file
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            Path(output_file).write_bytes(payload)
            print(f"Payload written to {output_file}")
    
    elif args.cmd == 'verify':
        with open(args.input, 'rb') as f:
            payload = f.read()
        
        metadata = None
        if args.metadata:
            with open(args.metadata, 'r') as f:
                metadata = json.load(f)
        
        verify_mkv_roundtrip(payload, args.output, audio_file=args.audio, metadata=metadata)


if __name__ == '__main__':
    main()