# Glass Box Demonstration (BK-14 / GH-26.5)

## Overview

The Glass Box Demonstration (`tools/glass_box_demo.py`) executes the end-to-end agent-in-the-loop lifecycle within the Glyph OS from a clean state. It demonstrates that an AI session operating through the Glyph OS is governed, auditable, and replayable:
- **Aperture constraint:** Agent write operations are strictly bounded to mailbox windows `{700..767}` via `tools.geos_emit` behind a human governance gate (`GEOS_EMIT_ACK`).
- **Preemptive scheduling:** The resident agent daemon executes as a real USER task under GH-16 hardware timer preemption.
- **Oracle admission:** Dynamically proposed capabilities cannot enter the kernel or execute without passing formal IR static verification and word-exact oracle evaluation.
- **Observable cockpit:** Every state transition manifests as spatial geometry on the Hilbert observation plane.
- **Canonical replay:** Every memory mutation resolves to a bit-identical cryptographic fixpoint.

---

## How to Run

### Standard Execution (Human-Gated)
```bash
GEOS_EMIT_ACK=1 python3 tools/glass_box_demo.py
```

### With ASCII Canvas Projections
```bash
GEOS_EMIT_ACK=1 python3 tools/glass_box_demo.py --show-canvases
```

### Human Gate Refusal Behavior (Unset Variable)
```bash
python3 tools/glass_box_demo.py
```
*Expected exit code:* `1` with message:
```
REFUSAL: GEOS_EMIT_ACK environment variable is unset.
The glass-box demo exercises the agent write path (tools.geos_emit),
which is human-gated under GH-26.2 / demo_wc008 governance rules.
To authorize execution, set GEOS_EMIT_ACK in your environment:
    export GEOS_EMIT_ACK=1
or pass inline:
    GEOS_EMIT_ACK=1 python3 tools/glass_box_demo.py
```

---

## What Each Stage Proves

| Stage | Name | Key Mechanics & What It Proves | Concrete Evidence |
|---|---|---|---|
| **0** | **Frame Geometry (Anchor 1)** | Proves the observation coordinate space ($N=128$ Hilbert projection) is intact, unrotated, and correctly scaled using 5 reference sentinels. | Sentinels: `origin`, `x_max`, `y_max`, `far`, `center` all match (5/5). Diagnosis: `mapping sound: all reference pixels match`. |
| **1** | **Intent Post** | Proves the agent write path obeys the GH-18 mailbox aperture `{700..767}`, encodes host-side GH-22 word format (`op=0x11, payload=0x2A`), and commits atomically to the observation image. | Mailbox word 750 = `0x3b00112a`. Hilbert coordinate `(27, 17)` lights marker `>`. |
| **2** | **Preemptive Servicing** | Proves real OS multitasking under GH-16 hardware timer preemption (`timer_quantum=12`). Resident daemon in BOX0 consumes argv @ 750, computes $3 \times 0\text{x}2\text{A} = 126$, and writes result @ 754. | Word 732 records `2` ticks serviced. Result word 754 = `126` (marker `@` at `(29, 17)`). Exit word 703 = `0xfeed0006` (marker `X` at `(31, 24)`). |
| **3** | **Capability Admission (Anchor 2)** | Proves no agent code executes on-die without formal proof. Proposed tile (triple verb for syscall 8) passes IR StaticVerifier and word-exact Oracle gate, is persisted to `tools/glyph_gpt/admitted/`, and table slot 1570 is stamped with the tile PC. | Table slot 1570 stamped PC `0x1e0004`. Tile text SHA256: `d29b29043f6dfa1e24c10db63fc7371c944b88140a9dd3527955769e5cdbdc33`. |
| **4** | **On-Die Re-Dispatch** | Proves dynamic capability execution: invoking syscall 8 on-die executes the admitted tile, yielding expected result 18 at word 754. | Syscall 8 result = `18`. Table slot 1570 manifests as marker `T` at Hilbert `(53, 21)`. |
| **5** | **Canonical Replay Fixpoint (Anchor 3)** | Proves determinism and replayability: an independent rerun from the same image yields 0 words of memory divergence across all 16,384 cells. | Replay divergence: `0` words. Memory state MD5: `0b22350df04841a768a8c714f0a33c4a`. |

---

## Verbatim Demonstration Run

**Command:**
```bash
GEOS_EMIT_ACK=1 python3 tools/glass_box_demo.py
```

**Output:**
```
========================================================================
GLYPH OS GLASS BOX DEMONSTRATION (GH-26.5 / BK-14)
========================================================================

[Stage 0] Frame Geometry Self-Attestation (Anchor 1)
  Diagnosis:        mapping sound: all reference pixels match
  Markers matched:  origin, x_max, y_max, far, center (5/5)
  Anchor 1 Status:  PASS

[Stage 1] Intent Posted to Mailbox (tools.geos_emit)
  Mailbox word 750: 0x3b00112a (op=0x11, payload=0x2a, cksum=0x3b)
  Hilbert coord:    (27, 17) -> marker '>'
  Committed:        True (checksum 11fa4d1e68b2...)
  Stage 1 Status:   PASS

[Stage 2] Preemptive Servicing by Resident Daemon (GH-16 / Tier 3)
  Execution status: halted=True, faulted=False
  Ticks serviced:   2 (word 732, GH-16 timer quantum=12)
  Argv preserved:   0x3b00112a -> marker '>' @ (27, 17)
  Result computed:  126 (3 * 0x2a = 0x7e) -> marker '@' @ (29, 17)
  Exit word:        0xfeed0006 -> marker 'X' @ (31, 24)
  Stage 2 Status:   PASS

[Stage 3] Dynamic Capability Admission via Oracle (Anchor 2)
  Proposal:         syscall 8 (triple verb, expected=18 for argv=6)
  IR / Oracle Gate: ok=True (code=OK)
  Table slot 1570:  stamped PC 0x1e0004
  Persisted tile:   tools/glyph_gpt/admitted/syscall_8_template_d29b29043f6d.glyph
  Tile SHA256:      d29b29043f6dfa1e24c10db63fc7371c944b88140a9dd3527955769e5cdbdc33
  Anchor 2 Status:  PASS

[Stage 4] On-Die Re-Dispatch of Admitted Syscall 8
  Execution status: halted=True, faulted=False
  Syscall 8 result: 18 @ word 754 (expected 18)
  Table slot 1570:  marker 'T' @ (53, 21)
  Stage 4 Status:   PASS

[Stage 5] Canonical Replay Fixpoint (Anchor 3)
  Replay run:       halted=True, faulted=False
  Divergence:       0 words across 16,384 memory cells
  Final State MD5:  0b22350df04841a768a8c714f0a33c4a
  Anchor 3 Status:  PASS

========================================================================
THE THREE ANCHORS (GH-26 Provenance Chain)
========================================================================
  1. Frame Geometry:      mapping sound: all reference pixels match
     Status:              PASS
  2. Admitted Capability: SHA256: d29b29043f6dfa1e24c10db63fc7371c944b88140a9dd3527955769e5cdbdc33
     Artifact:            tools/glyph_gpt/admitted/syscall_8_template_d29b29043f6d.glyph
     Status:              PASS
  3. Execution Fixpoint:  MD5: 0b22350df04841a768a8c714f0a33c4a
     Status:              PASS
========================================================================
VERDICT: ALL THREE ANCHORS VERIFIED (exit 0)
```

---

## Anchor Value Comparison vs systems/RECEIPT_GH26_AGENT_LOOP.md

| Anchor | Value in RECEIPT_GH26_AGENT_LOOP.md | Value in DEMO_GLASS_BOX Run | Match? |
|---|---|---|---|
| **1. Frame Geometry** | `mapping sound: all reference pixels match` | `mapping sound: all reference pixels match` | ✅ Exact |
| **2. Admitted Capability** | `d29b29043f6dfa1e24c10db63fc7371c944b88140a9dd3527955769e5cdbdc33` | `d29b29043f6dfa1e24c10db63fc7371c944b88140a9dd3527955769e5cdbdc33` | ✅ Exact |
| **3. Canonical Replay Fixpoint** | `0b22350df04841a768a8c714f0a33c4a` | `0b22350df04841a768a8c714f0a33c4a` | ✅ Exact |

All three anchors reproduce bit-for-bit with zero drift or divergence.
