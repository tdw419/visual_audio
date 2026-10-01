# The OS Where You Can Prove What the Machine — and the AI — Did

**Status:** living document — describes mechanisms that are landed and verified, and
marks what is still aspirational.
**Positioning source:** Jericho, 2026-09-11.
**Companion docs:** `docs/GLASS_BOX_ARCHITECTURE.md` (why the state is visible),
`systems/GH26_AGENT_IN_THE_LOOP_SPEC.md` (the agent spec),
`systems/RECEIPT_GH26_AGENT_LOOP.md` (the end-to-end receipt).

---

## 1. The claim, stated precisely

Every operating system has logs. Logs are *testimony* — written by the same
software that may be lying, or buggy, or compromised. This OS is built so that
its claims about itself are **evidence** instead: artifacts that a third party
can re-execute and check without trusting anyone's word.

Concretely, three questions get mechanical answers:

| Question | Mechanism | Artifact |
|---|---|---|
| Did the machine execute what I think it executed? | Two independent engines must agree word-for-word; execution is deterministic and replayable | parity receipts, canonical-replay MD5 |
| Is the image I'm running the one that was built? | The image carries its own code-region hash, checked before dispatch | `INTEGRITY_FAIL` fault, not silent garbage |
| Did the AI do what it claims it did? | Every agent write crosses a hardware-shaped aperture and an admission oracle; every attempt is logged | `output/agent_admissions.jsonl`, admitted tiles, replay fixpoint |

The rest of this document explains how each of those works, and — importantly —
what they do *not* yet prove (§7).

---

## 2. Why a normal OS cannot make this claim

Three structural reasons, none of them fixable by adding logging:

1. **State is invisible by construction.** In a conventional OS, "what the machine
   did" lives in caches, registers and opaque allocations. You reconstruct it after
   the fact from indirect traces (GDB, ptrace, kernel logs), each of which is itself
   software you must trust to be observing faithfully.
2. **Execution is not required to be reproducible.** Floating point, scheduling,
   address-space randomisation, and nondeterministic allocators mean two runs of the
   same program legally differ. If the run isn't reproducible, the trace isn't
   evidence — it's an anecdote.
3. **The syscall interface predates the question.** `open()`, `write()`, `ioctl()`
   were designed to move bytes, not to preserve intent. Nothing in the interface
   records *what the process meant*, and nothing gates a process's actions on proof
   that the action is well-formed. A conventional OS cannot distinguish "a program
   did this" from "a program did this and can prove it".

This project's bet is that all three are architectural, not incremental — so the
answers are architectural too.

---

## 3. Proof substrate I — the machine

### 3.1 Two engines, one answer

The instruction set has **two independent implementations**:

- the reference engine, `GlyphCPUv2` (`glyph_dispatch/src/glyph/glyph_isa_v2.py`) — plain Python, readable, the normative definition;
- the GPU engine, WGSL compute shaders (`glyph_dispatch/src/riscv/RISCV_CPU_MMU*.wgsl`) — the same semantics written as a parallel kernel.

Every instruction and syscall must produce **byte-identical results on both**.
The parity check is not "looks right on both" — it is a word comparison:

```
cpu_word & 0xFFFFFF == wgsl_word
```

Gates: `tests/test_gh4_wgsl_parity.py`, `tests/test_bk2_wgsl_syscall_parity.py`.

Why this is evidence and not just testing: two implementations that were written
against the same specification but not against each other's code can only agree
word-for-word if the specification is being honoured. It is differential
evidence, in the same family as N-version programming. It also has a track record
of catching real defects the Python engine hid — BK-2's parity work found an
asymmetric load path (`walk_ld` not checking the box-MMIO range in unpaged mode,
while `walk_st` did).

### 3.2 Determinism as a first-class property

Execution is deterministic by design: an image plus an entry point yields a
state, and the same image yields the same state again — not approximately, but at
the MD5 level.

Gate: `tests/test_gh8c_canonical_replay.py` — the *canonical replay fixpoint*.
Run the workload twice from the same committed image and the resulting state
hash must be identical. This is the property that turns a trace into evidence:
if the replay hash matches, anyone can reproduce the run; if it doesn't, you
have caught real nondeterminism instead of arguing about it.

### 3.3 The image proves itself

Because the machine's state *is* pixels, silent corruption is a real failure
mode: a flipped bit is a changed instruction, and there is no MMU table entry
that tells you it was an accident.

Boot self-check (`tools/glyph_gpt/integrity.py`, gate `tests/test_bk6_integrity.py`,
receipt `systems/RECEIPT_BK6_INTEGRITY.md`): the image carries a hash of its own
code region, baked at build time. Before dispatch, the kernel verifies it.
Flip a single code pixel and the machine faults with `INTEGRITY_FAIL` rather than
executing garbage. The gate is deliberately **non-vacuous** — it also proves the
hash covers real code (not a degenerate run of zeros that would pass trivially).

### 3.4 Gates assert state, not stories

The discipline throughout this repo is that a gate asserts **register- and
memory-level state** against a word-exact expectation — not that output text
"looks right". Every landing is RED→GREEN: the failing run is captured as a
receipt, then the fix, then the green run, and the receipts live in `systems/`
(e.g. `systems/RECEIPT_BK7_FS_GROW.md`, `systems/RECEIPT_BK10_PIPES.md`).

This is what makes the repo's claims auditable after the fact: "done" is defined
as "a committed gate passes on a clean tree", and anyone can re-run it.

---

## 4. Proof substrate II — the AI

An AI agent that can write to a machine is, in every current OS, an unbounded
process with the user's privileges. This OS instead treats the agent as a
**boxed citizen whose writes are auditable, oracle-gated and replayable**. The
thesis under test (from `systems/GH26_AGENT_IN_THE_LOOP_SPEC.md`):

> an agent prompted from within the OS is *safer* than one operating through
> unrestricted host shells — box bounds are hardware enforcement, mailbox-only
> I/O is an auditable protocol, canonical replay makes every agent action
> rewindable, and the oracle gate filters agent emissions exactly like every
> other tile.

### 4.1 The trust boundary is explicit

```
HOST (untrusted — the "cross-compiler" role)      GLYPH OS (resident)
  AI sessions (Hermes / Claude / builder)           KERNEL (read-only, proven)
    ├─ geo-obs MCP ── read_surface() ────────────▶  BOX0..BOXn agent arenas
    ├─ geo-emit    ── emit(intent) ──aperture───▶   mailbox words only
    └─ oracle (sole admission) ◀──admit──────────   GH-25 Hilbert page table
```

The host may *propose*. It cannot *write* kernel state, cannot register
capabilities, and cannot bypass the aperture. Inference stays host-side by
design (LLM weights are not in-image — an explicit non-goal of GH-26); what
crosses into the OS is a constrained intent and a candidate tile.

### 4.2 The aperture — the only legal write path

`tools/geos_emit.py` implements the first agent write path. It is not "raw
memory write with a check"; it is a narrow intent API whose only legal targets
are mailbox words:

- `emit(intent)` with `intent ∈ {post(box, op, payload), clear(box), claim_ticket(name), signal_done(box)}`;
- encoding uses the GH-22 mailbox word format `cksum[31:24] | op[15:8] | payload[7:0]`, so a malformed intent is rejected **host-side, before touching anything**;
- **aperture rule:** the target word must lie inside the mailbox windows `{700..767}`. A write anywhere else — kernel words, page table, tile rectangle, another agent's arena — returns `E_APERTURE` and performs no write;
- writes land on a **scratch copy** of the current image, which becomes the newest published image only after a checksummed commit step. A proven image is never mutated in place, and a failed commit leaves no torn state;
- an explicit human gate (`GEOS_EMIT_ACK`) refuses on the first version unless a human enabled it.

### 4.3 The oracle gates emissions — emit → admit

An agent can *draft* code. It cannot *register* it. The only route from draft to
resident capability is the same admission pipeline every other tile uses
(`tools/glyph_gpt/autoatlas.py` + `tools/glyph_gpt/oracle.py`):

1. candidate glyph text enters the **IR static verifier**;
2. surviving candidates are **executed** and compared word-exactly by the oracle;
3. only then is a table slot stamped.

Failed candidates return the exact oracle error to the agent and leave the
atlas and table **byte-unchanged** (diff-proven in the gate). Nothing partial
lands. Drafting is grammar-guided from the ABI-baked template library, with
GlyphGPT best-of-N as one source — measured, honestly, at ~9% first-try
acceptance, which is why grammar guidance carries the load.

Every attempt, pass or reject, appends a line to `output/agent_admissions.jsonl`.
The agent's emission history is itself replayable provenance.

### 4.4 The resident box — AI work as scheduled OS work

`tools/glyph_gpt/agent_resident.py` (gate `tests/test_gh26_resident.py`, 8/8)
runs the agent's *program* as a real USER task in its own box: preempted by the
GH-16 timer, bounded by hardware box limits, receiving work through its mailbox
and publishing results the same way, with working memory larger than the box
paged through the GH-25 Hilbert page table.

The division of labour matters: the box is the agent's **deterministic hands**;
the LLM session is the **mind**, outside, driving through Tier-2 emit. So the
part that acts is fully auditable, and the part that reasons is replaceable.

### 4.5 The observation plane — the machine reports its own state

The `geo-obs` MCP server (`tools/geos_observation_server.py`) reads a live
surface: per-tick memory dumps published by the runner, freshness in the
sidecar metadata, plus sentinel/reference-pixel verification
(`verify_reference_pixels` in `tools/geos_hilbert.py`) so a reader can tell a
correct frame from a plausible-looking wrong one. `geos_read_cell` /
`geos_verify_sentinels` are how an agent *sees* rather than assumes.

---

## 5. The composite: the three-hash provenance chain

The end-to-end scenario (GH-26.5, `systems/RECEIPT_GH26_AGENT_LOOP.md`) chains
the whole lifecycle into three anchors:

| Anchor | Mechanism | Value in the receipt |
|---|---|---|
| Frame geometry | sentinel / reference pixels over the Hilbert mapping | `mapping sound: all reference pixels match` |
| Admitted capability | SHA-256 of the admitted tile text | `d29b29043f6d…` (`admitted/syscall_8_template_d29b29043f6d.glyph`) |
| Execution | canonical replay fixpoint (MD5 of replayed state) | `0b22350df04841a768a8c714f0a33c4a` |

Worked example, one surface read telling the whole story:

1. the agent session posts an intent — mailbox word **750** lights with `0x3B00112A`, which renders as a `>` marker at Hilbert coordinates **(27, 17)**;
2. the resident box services it under preemption — the tick counter advances, proving it ran as *scheduled work*, not a simulation;
3. the result lands in word **754** (syscall 8 → result 18);
4. a new capability is admitted through the oracle — table slot **1570** lit, tile hash recorded;
5. the whole state replays to the same MD5 — so the sequence is rewindable and re-checkable by anyone.

Read that as a sentence: *this specific AI, through a bounded channel, caused
this specific instruction to be admitted and executed, and here is the arithmetic
that proves it.*

---

## 6. Verify it yourself

The claim is only as good as your ability to falsify it. All of these run from
the repo root; add `PYTHONPATH=tools:.` if your environment needs it.

```bash
# two engines agree, word for word
python3 -m pytest tests/test_gh4_wgsl_parity.py tests/test_bk2_wgsl_syscall_parity.py -q

# execution is deterministic and replayable
python3 -m pytest tests/test_gh8c_canonical_replay.py -q

# a corrupted image faults instead of executing garbage
python3 -m pytest tests/test_bk6_integrity.py -q

# an agent lives in a box, preempted, paged, mailbox-only
python3 -m pytest tests/test_gh26_resident.py -q

# the agent's emission history (passes and rejections)
wc -l output/agent_admissions.jsonl

# the end-to-end receipt, with the three anchors
sed -n '1,40p' systems/RECEIPT_GH26_AGENT_LOOP.md
```

Last verified on this tree: parity 3/3 and 4/4, replay 4/4, integrity 6/6,
resident 8/8.

---

## 7. What this does NOT claim

Precision here is the whole point of the document, so the limits are stated as
plainly as the capabilities:

- **Not formal verification.** The oracle proves *execution equivalence*: the
  candidate behaves word-exactly as specified on the tested paths. It is not a
  theorem prover and does not prove absence of unspecified behaviour on untested
  input.
- **Coverage-bounded.** A property is proven only where a gate exists. Ungated
  paths are simply unproven — which is exactly why the standing rule is "the
  oracle gate applies to every tile, including the AI's".
- **The host is trusted for inference.** The LLM runs outside the box. What is
  proven is the effect of its emissions, not the soundness of its reasoning.
- **Throughput is tiered, and now measured.** Pixel-word execution is a
  correctness-and-auditability layer, not a speed layer, and two different
  paths carry two different numbers: the interpreter engine copying 64 words in
  a tight LD/ST loop runs at **~186 KB/s** (one engine instruction per word
  moved), while the per-step/readback lockstep harness is the "tens of bytes per
  second" path quoted in earlier revisions of this document. BK-12 (landed
  2026-09-12) adds the **WGSL throughput tier** beside the pixel tier: the same
  bytes in GPU compute buffers, proven byte-identical to the CPU reference (1KB
  copy, word-for-word + md5 + sha256) and round-tripped through the GH-8b pixel
  encoding, measured at **5.6 MB/s like-for-like (30× the pixel tier)** and
  19.8 MB/s → 47.4 MB/s for 1KB → 16KB blocks (one dispatch ≈52 µs, nearly all
  fixed submit cost). Honest bounds: it is a host-side service beside the
  substrate (no in-image GPU dispatch), it moves bytes without making execution
  faster, and 16KB is the largest block measured. Receipt:
  `docs/RECEIPT_BK12_WGSL_TIER.md`.
- **Not yet a standalone machine.** The substrate is GPU compute plus a host
  runner. Boot-from-image paths exist elsewhere in this repo; the provenance
  stack described here is currently exercised through the runner and gates.

---

## 8. What makes the claim stronger from here

The roadmap items are not a generic backlog — each one widens the class of
programs and actions the proof covers:

| Item | Why it matters to the claim |
|---|---|
| BK-9 hierarchical FS paths | Real programs expect paths; provenance must extend to real file semantics |
| BK-10 stdio as files + pipes | Composition (`prog1 \| prog2`) becomes auditable box-to-box handoff instead of opaque pipes |
| BK-11 coreutils volume port | A stranger's C program — compiled with riscv64-gcc, transpiled, run, byte-exact vs native — is the "it just runs, provably unmodified" milestone |
| BK-12 WGSL throughput tier | Removes the honest performance objection without giving up the provenance tier (landed 2026-09-12 — `docs/RECEIPT_BK12_WGSL_TIER.md`) |
| BK-13 oracle-audited networking | Every frame crosses admission — proof-gated I/O that no current OS offers |
| BK-14 glass-box demo | Turns this document into one reproducible command, ending in a replay hash instead of a marketing line |

The end state being aimed at: **the demo is a hash.** Anyone — a user, an
auditor, another agent — can re-run the sequence and get the same numbers back.

---

## 9. Why this is the competition worth picking

Windows and Linux will not lose on features, drivers or desktop share, and this
project should not try to beat them there. They are, however, structurally unable
to make this claim: their execution model is nondeterministic, their state is
opaque, and their interfaces were designed before "prove what the AI did" was a
question anyone asked. Retrofitting proof onto them means layering attestation
over a substrate that does not preserve it.

Here the substrate *is* the proof: pixels you can see, execution you can replay,
writes that must pass a gate, and agents that are boxed citizens with a recorded
emission history. That is a different product category — not a faster Unix, but
the operating layer for a world where machines act on their own and someone has
to be able to show, afterwards, exactly what happened.

*The machine reports; the arithmetic decides.*

---

*Last updated: 2026-09-12. Update this document when a mechanism it describes
changes, or when a limit in §7 is retired.*
