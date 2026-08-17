# Spatial OS Daemon — Byte-Count Discrepancy Resolution

## Issue

The daemon reported "wrote 4235 bytes" but read-back only recovered 4234 bytes before hitting a null terminator.

## Root Cause

Address wrap-around combined with misleading output:

1. **Wrap-Around Bug**: The test program used RESULT_BASE=10000, which wrapped to pixel position 16 in a 64-pixel image. The daemon's output overwrote program code, and the read-back hit a null byte from the corrupted program.

2. **Misleading Output**: The daemon's `write_string_to_image()` function returned `len(bytes_data) + 1` (including null terminator), but the print statement only showed "wrote X bytes" without clarifying that this included the null.

## Fix

1. **Test Program**: Updated `daemon_test.glyph` to use a larger image (width_instrs=1280, 5120 pixels) and RESULT_BASE=256 (safely beyond the 132-pixel program).

2. **Daemon Output**: Modified `write_string_to_image()` to return a tuple `(data_bytes, total_bytes_with_null)` and updated the print statement to show both:
   ```
   [OS DAEMON] Wrote 4234 data bytes (4235 total with null terminator) to spatial address 256
   ```

## Verification

```bash
python3 demo_wrap_around.py
```

Output now shows:
- Daemon writes: 4234 data bytes (4235 total with null)
- Read-back recovers: 4234 bytes before null terminator
- **Counts match**

## Lessons

1. **Address Space Matters**: Spatial memory uses modulo arithmetic. Always ensure RESULT_BASE is beyond the program code and that the image is large enough for the output.

2. **Terminators Count**: When writing null-terminated strings, clarify whether byte counts include or exclude the terminator in logs and documentation.

## Test File Status

The original `verify_daemon_writeback.py` file referenced in the handoff no longer exists. The verification is now performed by `demo_wrap_around.py`, which demonstrates both the bug and the fix.