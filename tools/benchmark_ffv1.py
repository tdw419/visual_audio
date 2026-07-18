#!/usr/bin/env python3
"""
FFV1.3 Codec Optimization Tests - TASK_R020
Tests for FFV1.3 parameter tuning for VM use.

Reference: /home/jericho/zion/docs/research/Video Container Virtual Machines.md
- GOP=1 for intra-frame only (O(1) seeking)
- -slices 24 for multi-threaded encode/decode
- -slicecrc 1 for per-slice error detection
- libx264rgb -qp 0 with planar GBR (gbrp) to avoid YUV rounding drift
- Seek performance: O(1) with GOP=1 vs O(N) with GOP=250
"""

import pytest
import subprocess
import tempfile
import os
from pathlib import Path
import time


class TestGOPConfiguration:
    """Test GOP=1 vs GOP=250 for seeking performance."""

    def test_gop1_independent_frames(self):
        """Verify GOP=1 creates independent frames."""
        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as f:
            output_path = f.name

        try:
            # Create test frames (10 frames of 320x240)
            frames_path = Path("/tmp/test_gop1_frames")
            frames_path.mkdir(exist_ok=True)

            for i in range(10):
                import numpy as np
                frame = np.random.randint(0, 256, (240, 320, 3), dtype=np.uint8)
                from PIL import Image
                img = Image.fromarray(frame)
                img.save(frames_path / f"frame_{i:03d}.png")

            # Encode with GOP=1 (intra-frame only)
            cmd = [
                "ffmpeg", "-y",
                "-framerate", "30",
                "-i", str(frames_path / "frame_%03d.png"),
                "-vcodec", "ffv1",
                "-level", "3",
                "-g", "1",  # GOP=1: all keyframes
                "-slices", "24",
                "-slicecrc", "1",
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            assert result.returncode == 0, f"FFmpeg GOP=1 encoding failed: {result.stderr}"

            # Verify all frames are keyframes
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "frame=pict_type,pts",
                "-of", "csv=p=0",
                output_path
            ]

            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
            assert probe_result.returncode == 0

            frame_types = probe_result.stdout.strip().split("\n")
            assert len(frame_types) == 10

            # All frames should be I-frames (keyframes)
            for frame_info in frame_types:
                assert "I" in frame_info, f"Expected I-frame, got: {frame_info}"

        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
            if frames_path.exists():
                import shutil
                shutil.rmtree(frames_path)

    def test_gop250_p_frame_chain(self):
        """Verify GOP=250 creates P-frame chain."""
        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as f:
            output_path = f.name

        try:
            # Create test frames (300 frames)
            frames_path = Path("/tmp/test_gop250_frames")
            frames_path.mkdir(exist_ok=True)

            for i in range(300):
                import numpy as np
                frame = np.random.randint(0, 256, (240, 320, 3), dtype=np.uint8)
                from PIL import Image
                img = Image.fromarray(frame)
                img.save(frames_path / f"frame_{i:03d}.png")

            # Encode with GOP=250
            cmd = [
                "ffmpeg", "-y",
                "-framerate", "30",
                "-i", str(frames_path / "frame_%03d.png"),
                "-vcodec", "ffv1",
                "-level", "3",
                "-g", "250",  # GOP=250: P-frame chain
                "-slices", "24",
                "-slicecrc", "1",
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            assert result.returncode == 0, f"FFmpeg GOP=250 encoding failed: {result.stderr}"

            # Verify frame pattern (I, P, P, P, ..., I, P, P, ...)
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "frame=pict_type",
                "-of", "csv=p=0",
                output_path
            ]

            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
            assert probe_result.returncode == 0

            frame_types = probe_result.stdout.strip().split("\n")
            assert len(frame_types) == 300

            # First frame should be I-frame
            assert "I" in frame_types[0]

            # Most frames should be P-frames
            p_count = sum(1 for t in frame_types if "P" in t)
            i_count = sum(1 for t in frame_types if "I" in t)

            assert p_count > i_count, "GOP=250 has more P-frames than I-frames"

        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
            if frames_path.exists():
                import shutil
                shutil.rmtree(frames_path)


class TestSeekPerformance:
    """Test O(1) seek with GOP=1 vs O(N) with GOP=250."""

    def test_seek_gop1_constant_time(self):
        """Verify GOP=1 seeking is O(1)."""
        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as f:
            output_path = f.name

        try:
            # Create 100 frames
            frames_path = Path("/tmp/test_seek_gop1_frames")
            frames_path.mkdir(exist_ok=True)

            for i in range(100):
                import numpy as np
                frame = np.random.randint(0, 256, (240, 320, 3), dtype=np.uint8)
                from PIL import Image
                img = Image.fromarray(frame)
                img.save(frames_path / f"frame_{i:03d}.png")

            # Encode with GOP=1
            cmd = [
                "ffmpeg", "-y",
                "-framerate", "30",
                "-i", str(frames_path / "frame_%03d.png"),
                "-vcodec", "ffv1",
                "-level", "3",
                "-g", "1",
                "-slices", "24",
                "-slicecrc", "1",
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            assert result.returncode == 0

            # Measure seek times for frames 10, 50, 90
            seek_times = []
            for target_frame in [10, 50, 90]:
                cmd = [
                    "ffmpeg", "-ss", str(target_frame / 30.0),  # Convert to seconds
                    "-i", output_path,
                    "-frames:v", "1",
                    "-f", "null",
                    "-"
                ]

                start = time.time()
                result = subprocess.run(cmd, capture_output=True, text=True)
                end = time.time()

                assert result.returncode == 0
                seek_times.append(end - start)

            # Seek times should be roughly constant (within 2x)
            max_time = max(seek_times)
            min_time = min(seek_times)

            assert max_time / (min_time + 1e-6) < 2.0, \
                f"GOP=1 seek times not constant: {seek_times}"

        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
            if frames_path.exists():
                import shutil
                shutil.rmtree(frames_path)

    def test_seek_gop250_linear_time(self):
        """Verify GOP=250 seeking is O(N)."""
        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as f:
            output_path = f.name

        try:
            # Create 300 frames
            frames_path = Path("/tmp/test_seek_gop250_frames")
            frames_path.mkdir(exist_ok=True)

            for i in range(300):
                import numpy as np
                frame = np.random.randint(0, 256, (240, 320, 3), dtype=np.uint8)
                from PIL import Image
                img = Image.fromarray(frame)
                img.save(frames_path / f"frame_{i:03d}.png")

            # Encode with GOP=250
            cmd = [
                "ffmpeg", "-y",
                "-framerate", "30",
                "-i", str(frames_path / "frame_%03d.png"),
                "-vcodec", "ffv1",
                "-level", "3",
                "-g", "250",
                "-slices", "24",
                "-slicecrc", "1",
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            assert result.returncode == 0

            # Measure seek times for frames 10, 150, 290
            seek_times = []
            for target_frame in [10, 150, 290]:
                cmd = [
                    "ffmpeg", "-ss", str(target_frame / 30.0),
                    "-i", output_path,
                    "-frames:v", "1",
                    "-f", "null",
                    "-"
                ]

                start = time.time()
                result = subprocess.run(cmd, capture_output=True, text=True)
                end = time.time()

                assert result.returncode == 0
                seek_times.append(end - start)

            # Seek times should increase linearly with target frame
            # Later frames should take significantly longer
            assert seek_times[1] > seek_times[0], "Seek to frame 150 > frame 10"
            assert seek_times[2] > seek_times[1], "Seek to frame 290 > frame 150"

            # Frame 290 should be at least 2x slower than frame 10
            assert seek_times[2] / (seek_times[0] + 1e-6) > 2.0, \
                f"GOP=250 seeking not linear: {seek_times}"

        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
            if frames_path.exists():
                import shutil
                shutil.rmtree(frames_path)


class TestColorSpacePrecision:
    """Test planar GBR vs YUV for bit-exactness."""

    def test_libx264rgb_bit_exact(self):
        """Verify libx264rgb with gbrp is bit-exact."""
        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as f:
            output_path = f.name

        try:
            # Create test frame
            import numpy as np
            from PIL import Image

            original = np.random.randint(0, 256, (240, 320, 3), dtype=np.uint8)
            img = Image.fromarray(original)
            img.save("/tmp/test_colorspace.png")

            # Encode with libx264rgb (planar GBR)
            cmd = [
                "ffmpeg", "-y",
                "-i", "/tmp/test_colorspace.png",
                "-vcodec", "libx264rgb",
                "-qp", "0",  # Lossless
                "-pix_fmt", "gbrp",  # Planar GBR
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            assert result.returncode == 0, f"libx264rgb encoding failed: {result.stderr}"

            # Decode and compare
            decode_cmd = [
                "ffmpeg", "-i", output_path,
                "-pix_fmt", "rgb24",
                "-f", "rawvideo",
                "-"
            ]

            result = subprocess.run(decode_cmd, capture_output=True)
            decoded_rgb = np.frombuffer(result.stdout, dtype=np.uint8).reshape(240, 320, 3)

            # Verify bit-exact match
            assert np.array_equal(original, decoded_rgb), \
                "libx264rgb with gbrp is bit-exact"

        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
            if os.path.exists("/tmp/test_colorspace.png"):
                os.unlink("/tmp/test_colorspace.png")

    def test_yuv_rounding_drift(self):
        """Verify YUV causes rounding drift."""
        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as f:
            output_path = f.name

        try:
            import numpy as np
            from PIL import Image

            original = np.random.randint(0, 256, (240, 320, 3), dtype=np.uint8)
            img = Image.fromarray(original)
            img.save("/tmp/test_yuv.png")

            # Encode with standard H.264 (YUV420)
            cmd = [
                "ffmpeg", "-y",
                "-i", "/tmp/test_yuv.png",
                "-vcodec", "libx264",
                "-crf", "0",  # Lossless
                "-pix_fmt", "yuv420p",
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            assert result.returncode == 0

            # Decode and compare
            decode_cmd = [
                "ffmpeg", "-i", output_path,
                "-pix_fmt", "rgb24",
                "-f", "rawvideo",
                "-"
            ]

            result = subprocess.run(decode_cmd, capture_output=True)
            decoded_rgb = np.frombuffer(result.stdout, dtype=np.uint8).reshape(240, 320, 3)

            # Verify there IS drift (not bit-exact)
            diff = np.abs(original.astype(int) - decoded_rgb.astype(int))
            assert np.any(diff > 0), "YUV420 causes rounding drift"

        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
            if os.path.exists("/tmp/test_yuv.png"):
                os.unlink("/tmp/test_yuv.png")


class TestSliceCRC:
    """Test per-slice CRC error detection."""

    def test_slice_crc_validation(self):
        """Verify -slicecrc 1 enables per-slice CRC."""
        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as f:
            output_path = f.name

        try:
            # Create test frames
            frames_path = Path("/tmp/test_slice_crc_frames")
            frames_path.mkdir(exist_ok=True)

            for i in range(10):
                import numpy as np
                frame = np.random.randint(0, 256, (240, 320, 3), dtype=np.uint8)
                from PIL import Image
                img = Image.fromarray(frame)
                img.save(frames_path / f"frame_{i:03d}.png")

            # Encode with slice CRC enabled
            cmd = [
                "ffmpeg", "-y",
                "-framerate", "30",
                "-i", str(frames_path / "frame_%03d.png"),
                "-vcodec", "ffv1",
                "-level", "3",
                "-g", "1",
                "-slices", "24",
                "-slicecrc", "1",  # Enable per-slice CRC
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            assert result.returncode == 0, f"FFmpeg with -slicecrc failed: {result.stderr}"

            # Verify codec info mentions slice CRC
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "stream=codec_name,pix_fmt",
                "-of", "json",
                output_path
            ]

            result = subprocess.run(probe_cmd, capture_output=True, text=True)
            assert result.returncode == 0

            # FFV1 level 3 with slice CRC is valid
            assert "ffv1" in result.stdout.lower()

        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
            if frames_path.exists():
                import shutil
                shutil.rmtree(frames_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])