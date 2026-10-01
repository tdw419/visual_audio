# R3.3 Host Integration — Receipt (2026-09-21)

## Rung

PRODUCT_ROADMAP.md:69-71 (R3.3): "Host integration: the OS is reachable
from the host seat the way the current guest is (SSH/bridge), file
exchange verified both directions."

## What landed

`.builder_queue/probe_r33_hostbridge.py` — the BRIDGE leg of R3.3, built
entirely over LANDED substrate channels. Zero production lines changed.

- **host → machine**: `GlyphRunner.run_wgsl(input_ring=...)` — the SE022a
  host→shader input ring (tools/glyph_gpt/runner.py:140 seeds box_mmio
  INPUT_LEN/CURSOR/DATA; WGSL consumer tools/wgsl_glyph_isa_v2.py:742-757).
- **machine → host**: the guest program echoes received bytes to RAM
  (ST), the host reads them back from `receipt["ram"]`
  (runner.py:186 readback), plus `receipt["output"]` PRT markers.
- **guest program**: GlyphAssemblerV2-assembled SYSCALL 0x02 drain +
  copy loop; runs UNMODIFIED on both engines (WGSL shader path AND the
  Python reference engine GlyphCPUv2).

## Gate result (measured, this session)

Source: tests/fixtures/codec_test.py (262 B), pushed in 5×64-byte ring
chunks (INPUT_DATA_CAP=64, wgsl_glyph_isa_v2.py:193), one fresh machine
per chunk.

GREEN (exit 0):
```
R3.3 host-bridge probe: corrupt_verify=False corrupt_input=False src=codec_test.py (262 B)
R3.3 [wgsl] GREEN: 5 turns, 262 bytes round-tripped (sha256 a9428ae182e1…)
R3.3 [python] GREEN: 5 turns, 262 bytes round-tripped (sha256 a9428ae182e1…)
R3.3 HOST-BRIDGE: MATCH (file exchange verified both directions, both engines)
```
Reassembled-file sha256 equality is the both-directions check: the
bytes the host pushed came back byte-identical.

RED legs at landing (each exit 1, shown before green):

1. --corrupt-verify (verifier discrimination; exit 1 measured):
```
R3.3 corrupt-verify RED leg: verifier REJECTED a good echo under wrong
expectations (correct discrimination): echo mismatch at 23212f75…
!= 797b752f29…
```

2. --corrupt-input (loopback byte-faithfulness; exit 1 measured):
```
R3.3 [wgsl] RED correct: ring-corrupted payload does NOT round-trip
(sha 77c0c03ee38f… != source a9428ae182e1…)
R3.3 [python] RED correct: ring-corrupted payload does NOT round-trip
(sha 77c0c03ee38f… != source a9428ae182e1…)
R3.3 corrupt-input RED leg: both engines' honest echoes REJECTED the
corrupted payload (loopback byte-faithful)
```

## Defect found and fixed during implementation (in-probe, not production)

First green attempt echoed only byte 0 into echo[1] on every iteration
(echo count word overwritten). _dbg register trace showed the loop
counter r3 advancing while scratch r5 lagged by one — my original
program restored r5 = old-i AFTER the ST, so r5 never caught up; all 64
iterations stored dest[0] to echo[1]. Fix: the loop counter lives ONLY
in r5 (entering iteration i, r5=i; leaving, r5=i+1). No production
files touched; the defect was in the probe's guest program.

## What this PASS does NOT prove

- **SSH leg not claimed.** The substrate has no network stack; the
  rung's "(SSH/bridge)" is satisfied via the bridge mechanism only.
  An SSH-equivalent would need a network device + TCP/IP in-image —
  that is substrate work, not probe work, and is NOT faked here.
- **No persistent machine across chunks.** Each 64-byte chunk runs on
  a fresh runner (cursor 0); persistence is R3.2's GPX1 story, not
  re-claimed here.
- **Python engine leg is the reference twin**, not an independent
  implementation — cross-engine agreement is parity evidence, not
  replication.
- No rate/floor claims made (floors authority not engaged).

## Verdict

The machine is reachable from the host seat and file exchange works in
BOTH directions, host-verified, on the shader path. R3.3 bridge leg:
PASS. SSH leg: not claimed (blockage pre-registered above).
