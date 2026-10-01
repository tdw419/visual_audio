# RCA: test_pixel_boot_pipeline CLI drift (2026-09-10, cron builder loop)

## Symptom
`tests/test_pixel_boot.py::test_pixel_boot_pipeline` failed at HEAD 6730b02:
`dense_encoder.py: error: unrecognized arguments: -o` → CalledProcessError exit 2.
(Open defect carried from .builder_queue/resolved/pre-existing-regression-failures-RESOLVED.md,
which fixed the parallel_opcodes family 2026-09-10 via 087f29b but explicitly
left this leg "NOT fixed (separate defect, still open)".)

## Root cause
CLI drift, not a codec/pipeline defect. Commit 4ef67e2 rewrote
`tools/dense_encoder.py` argparse from `-o <out>` flag style to positional
`input output` subcommands. `tests/test_pixel_boot.py` (last touched 9cdc1b7,
pre-drift) still passed `-o`. The tool's current positional convention is the
landed one; the test was stale.

## Fix
Update both subprocess calls in the test to positional form (encode/decode).
RED output captured in cron transcript (exit 2, argparse usage error) before fix.

## Verification
`python3 -m pytest tests/test_pixel_boot.py -q` → 1 passed post-fix
(bit-identical round-trip + QEMU RISC-V boot leg green).
Glyph arc at HEAD re-verified same session: GH15–GH23 103 passed (venv),
GH24+GH26 15 passed (/usr/bin/python3 — mcp in py3.12 user site),
GH-18 invariant run_gate_gh18.sh 14/14 exit 0.
