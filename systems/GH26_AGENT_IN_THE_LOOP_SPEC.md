# GH-26 SPEC — Agent-in-the-Loop: From Observer to Resident (Tier 1→3)

## Overview

Extend the landed GH-24 observation plane into a full agent presence in the
Glyph OS: every AI session that touches this repo gains the ability to SEE
machine state as geometry (Tier 1, live), ACT through mailbox words behind a
hardware aperture (Tier 2), and eventually RESIDE as a scheduled agent box
whose memory pages through the GH-25 Hilbert plane (Tier 3).

The thesis under test: an agent prompted from within the OS is *safer* than
one operating through unrestricted host shells — box bounds are hardware
enforcement, mailbox-only I/O is an auditable protocol, canonical replay
makes every agent action rewindable, and the oracle gate filters agent
emissions exactly like every other tile.

## Architecture

```
   HOST SIDE (untrusted, cross-compiler role)          GLYPH OS (resident pixels)
   ┌──────────────────────────────────────┐            ┌─────────────────────────────┐
   │ AI sessions (Hermes/Claude/builder)  │            │  KERNEL (read-only, proven) │
   │  └─ geo-obs MCP  ──── read_surface()─────────────▶│  BOX0..BOXn agent arenas    │
   │  └─ geo-emit    ──── emit(intent) ───aperture───▶│   └─ mailbox words only     │
   │  └─ glyph runner ── per-tick dump ───────────────▶│  GH-25 Hilbert page table   │
   │  └─ oracle/autoatlas (sole admission)◀──admit─────│  UART/status words          │
   └──────────────────────────────────────┘            └─────────────────────────────┘
```

Trust boundary stays where it is: the host is untrusted, admission is the
oracle, agent writes pass a hardware-shaped aperture BEFORE any gate, and
nothing agent-emitted executes without word-exact proof.

## Core Components

### 26.1 LIVE — per-tick state publication (Tier 1 completion)

- Location: `tools/glyph_gpt/runner.py` (+ gate `tests/test_gh26_live_surface.py`)
- Purpose: the observation plane reads a photograph today; make it a window.
- Implementation:
  - `drive()` gains opt-in `publish_dir=Path` — after each tick boundary
    (and at HALT/fault), dumps `kernel_memory.npy` + `surface.meta.json`
    (tick, source receipt md5) to the publish dir.
  - `GEOS_IMAGE_DIR` resolution order: newest live publish dir → stale
    snapshot (current behavior). Age of state is ALREADY in the sidecar
    meta; surface clients surface it.
  - Budget guard: runner stays ≤200 lines (dump is ~8 lines; use np.save
    only, no new imports beyond numpy already present).
- Gate legs: (1) publish produces npy+meta per tick, meta.tick increments;
  (2) geo-obs reads live dir preferentially and reports fresh age;
  (3) runner budget + zero-dev-import preserved; (4) full arc regression.
- Lines: ~40 (runner + tests). Time: 0.5 day.

### 26.2 APERTURE — geos_emit with mailbox-only write rule (Tier 2)

- Location: `tools/geos_emit.py` (+ gate `tests/test_gh26_emit_aperture.py`)
- Purpose: the first agent write path. NOT raw memory write — a constrained
  intent API whose only legal targets are mailbox words in writable boxes.
- Implementation:
  - `emit(intent)` where intent ∈ {post(box, op, payload), clear(box),
    claim_ticket(name), signal_done(box)}. Encodes GH-22 mailbox word
    format (cksum[31:24] | op[15:8] | payload[7:0]) — malformed intents
    rejected host-side before touching anything.
  - APERTURE RULE: target word MUST lie in {700..767} (BOX0..BOX2 mailbox
    windows per GH-18 ABI facts); anything else → E_APERTURE, no write.
  - Writes land on a SCRATCH COPY of the current image + bump tick; the
    mutated copy becomes the newest publish image only after a
    checksummed commit step. No in-place mutation of a proven image.
  - HUMAN GATE: first version refuses to run unless
    `GEOS_EMIT_ACK=2026-09-1x` env is set by an explicit user action —
    same pattern as demo_wc008_gui.sh governance.
- Gate legs: (1) legal mailbox post appears in next surface read;
  (2) out-of-aperture targets rejected E_APERTURE (kernel words, table,
  tile rect, other agent's arena); (3) malformed mailbox word rejected;
  (4) commit step is atomic (no torn image on failure); (5) no-env refusal.
- Lines: ~200. Time: 1-2 days.

### 26.3 EMIT→ADMIT — agent proposes, oracle disposes (Tier 2 completion)

- Location: `tools/glyph_gpt/autoatlas.py` (extend) + `tools/geos_emit.py`
- Purpose: close the loop from agent intent to proven resident capability,
  reusing the entire GH-12/18 admission pipeline unchanged.
- Implementation:
  - `emit_admit(tile_text)` path: agent-drafted glyph text →
    `autoatlas.admit_syscall` (IR StaticVerifier → oracle word-exact →
    table stamp) — the agent has NO other registration route. Failed
    candidates return the oracle error to the agent; nothing partial lands.
  - Template/grammar-guided drafting per the S3 verdict: candidates come
    from the ABI-baked template library (grammar-guided), with GlyphGPT
    best-of-N as one drafting source at 9% first-try.
  - Every admission attempt (pass or reject) appends a receipt line to
    `output/agent_admissions.jsonl` — the agent's emission history is
    itself replayable provenance.
- Gate legs: (1) valid drafted tile admits and is callable in-image;
  (2) hostile/incorrect tile rejected, table+atlas byte-unchanged
  (diff-proven); (3) admission receipts complete; (4) GH-18 invariant
  14/14 unchanged.
- Lines: ~150. Time: 1-2 days.

### 26.4 RESIDENT — agent task as a box citizen (Tier 3, first cut)

- Location: `tools/glyph_gpt/agent_resident.py` (+ gate `tests/test_gh26_resident.py`)
- Purpose: an agent's *program* runs as a USER task in its own box on the
  preemptive timer (GH-16), receives work via mailbox, publishes results
  via mailbox. The AI session drives the box from outside (Tier 2 emit),
  but the box itself is real scheduled OS work, not a simulation.
- Implementation:
  - Bake a resident "agent daemon" kernel mode: box polls its mailbox,
    services simple verbs (echo/double/sum from the GH-19 tile set),
    signals done. This is NOT the LLM in the box — it is the box's
    deterministic hands. The LLM session is the box's mind over Tier 2.
  - Context handoff: session → box via argv block (GH-9 loader pattern);
    box → session via result word + uart receipt.
  - GH-25 integration: agent working memory > box size pages via
    PTE_HILB frames (first real resident-viewport consumer).
- Gate legs: (1) resident daemon completes verb under preemptive tick;
  (2) two agent boxes + one driver box coexist, zero violations;
  (3) paged working memory leg (box uses 2 Hilbert frames);
  (4) surface observation shows the full story live (26.1);
  (5) canonical replay fixpoint holds.
- Lines: ~350. Time: 3-5 days.

### 26.5 GLASS BOX — observation plane as the agent cockpit (integration)

- Location: geo-obs server (extend), `systems/RECEIPT_GH26_AGENT_LOOP.md`
- Purpose: the demonstration + receipt item. A single surface read shows:
  agent session posted intent (word 750 lit), resident box serviced it
  under preemption (tick advanced), result landed (754), new capability
  admitted via oracle (table slot lit), state replayable (md5 fixpoint).
- Gate legs: end-to-end scripted scenario runs from clean; receipt doc;
  surface canvases before/during/after archived as the receipt figures.
- Lines: ~100. Time: 1-2 days.

## Integration

- Reuses: GH-18 ABI facts (mailbox windows, table), GH-13/14 box+mailbox
  protocol, GH-16 preemption, GH-22 word format, GH-24 S1/S2 bridge+MCP,
  GH-25 PTE_HILB, GH-12/18 autoatlas admission, GH-8c canonical replay.
- Positioning guard compliance: every tier STRENGTHENS provenance — the
  agent gains capability only through the same oracle gate as everything
  else; the aperture is narrower than what userspace tasks already have.
- Non-goals: LLM weights resident in-image (host inference stays host-side);
  freehand memory writes; bypassing human gate on emit; PixiJS UI.

## Testing Strategy

- Each sub-item lands RED→GREEN with the failing run pasted in the commit
  (receipt discipline). Full-arc pytest from clean before each merge.
- Adversarial legs are first-class: aperture violations, malformed
  mailboxes, hostile tiles, tick-starvation attempts.
- 26.5 scenario is the standing end-to-end gate for the whole item.

## Estimated Total

~5 items, ~840 lines, 7-12 days of builder-loop time. 26.1 and 26.2 are
immediately actionable (no research risk); 26.3 rides landed pipelines;
26.4 is the first genuinely new mechanism; 26.5 is receipt+demo.
