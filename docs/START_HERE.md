# Glyph OS — Start Here

*R5.2 "Documentation a stranger can follow": what it is, what it's for, how to
run the anchor workload. Every command below was executed and its output
captured verbatim at landing time; the gate `tests/test_r52_stranger_doc.py`
re-executes every block and checks the promised lines actually appear.*

## What it is

Glyph OS is an experimental **GPU-native machine**. Programs are not stored as
bytes in a file system — they are compiled into **pixels**. A `.glyph` assembly
source becomes a baked PNG artifact; the artifact is executed by a RISC-V
(RV32IMA) core implemented in WGSL compute shaders (`GlyphRunner`), with the
machine's RAM mapped spatially along a Hilbert curve. Multiple agent programs
co-reside on one core under hardware-style fencing: task boxes are isolated by
the machine's own fault predicates (E-K1), not by host processes.

The full memory map, ABI words, and mailbox format are frozen in
`docs/BOX_ABI_v2.md`.

## What it's for

Agent workloads where **isolation between co-resident programs** is the point.
The project's preference measurement (P1.3) compared this substrate against
Ubuntu-sandboxed tenants running the same adversarial 4-agent fleet; the
measured chain, controls, and honesty caveats live in
`.builder_queue/RECEIPT_R13_preference.md` — read that receipt, not this doc,
for any performance claim. This is a research product for a **single known
machine** (the author's RTX 5090 host); it is not a general desktop OS and
makes no "OS replacement" claim (see `PRODUCT_ROADMAP.md` non-goals).

## How to run the anchor workload

Two entry points, both verified below.

### 1. The one-file installer (4-agent fleet, shader path)

`glyphos_installer.py` at the repo root is self-contained: integrity-verify,
extract to a private temp dir, boot atlas → fleet bake → WGSL run, and
host-verify the frozen result words.

Integrity check only (no boot):

```bash
python3 glyphos_installer.py --skip-boot
```

```text
~payload verified: 21 members, \d+ ms, manifest OK
exit: 0
```

Full boot to fleet-ready, machine-readable receipt:

```bash
python3 glyphos_installer.py --json
```

```text
"status": "fleet_ready_verified"
"halted": true
"steps": 458
"receipt_word": "0x5eed0005"
"results": {"714": 6, "728": 12, "748": 20, "763": 30}
exit: 0
```

The gate the run must satisfy: the fleet halts (458 steps), the supervisor
receipt word `0x5EED0005` is at address 765, the done mask `0b1011` at 717
(tenant C was reaped after an adversarial store was fault-suppressed), and the
four tenant results are `y = x·(x+1)` for seeds 2/3/4/5 → 6, 12, 20, 30.

Tamper leg — a corrupted manifest rejects the **good** payload before boot:

```bash
python3 glyphos_installer.py --corrupt-verify
```

```text
installer: PAYLOAD REJECTED (1 bad, 0 missing)
exit: 1
```

### 2. One command for a single program (`tools/glyph_run.py`)

Compile `.glyph` source to a pixel artifact and run it:

```bash
python3 tools/glyph_run.py examples/sum_1_to_5.glyph
```

```text
result   : HALT
steps    : 37
output   : 15
```

The artifact IS the program — re-run the baked PNG with no source present:

```bash
python3 tools/glyph_run.py examples/sum_1_to_5.glyph.png
```

```text
result   : HALT
output   : 15
```

Exit codes: 0 HALT · 1 fault · 2 assemble error · 3 budget exhausted ·
4 I/O error.

## Where to read next

- `PRODUCT_ROADMAP.md` — the product lane: rungs, gates, the P1.3 kill switch.
- `docs/BOX_ABI_v2.md` — frozen machine ABI (memory map, mailbox, receipts).
- `docs/ARCHITECTURE.md` — the wider Visual Audio system this grew out of.
- `.builder_queue/RECEIPT_R*.md` — one receipt per landed rung, RED legs
  included.

## Honesty (what is NOT claimed)

- This is a **GlyphRunner substrate boot**, not a kernel-image boot of the
  virtio-pixel Alpine guest.
- Everything above is measured on **this machine only** (RTX 5090, wgpu);
  no second-machine claim is made.
- The installer payload is the boot chain, not the whole repository.
- No performance numbers are quoted here on purpose: rates require fresh
  authoritative floors (`.builder_queue/floors_authoritative.json`, 12 h
  window) and a `check_regime` pass — see the receipts.
