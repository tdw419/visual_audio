# TICKET SUPPLY STATE — ADDENDUM 113 (builder cron af3e62239ce2, 2026-09-16 ~16:0x CDT)

**Head at work-start:** `e186c00` (addendum 112). Branch `defect-d-ram-scoped-handlers`.
**Head at work-end:** `48cf113` — **Pillar 2.1 syscall ABI spec + doc-rot guard LANDED this tick.**

## 1. Landed: Pillar 2.1 — the syscall ABI as a spec, not a Python function (GLYPH_ISA_ROADMAP.md §2.1)

Pickup: addendum 112 §3 named this rung ("Pillar 3 implementation …
now also owns the LD/ST storage-home asymmetry" vs "2.1 ABI spec —
independent, documentation-with-rot-guard"). 2.1 was picked over the
LD/ST fix because the storage-home change needs FULL-(A) scope (stack
migration / LD-ST view unification), which the 2026-09-16 ruling
explicitly did NOT rule — the pillar-3 text says "Full (A) … is NOT
ruled here". 2.1 is ruled-by-construction (documentation + extraction
gate, zero engine risk).

**Mechanism** (`48cf113`, 2 new files, +721, no engine file touched):
- `docs/SYSCALL_ABI_SPEC.md` — one section per syscall across the whole
  implemented surface 0x01..0x09 + 0x10..0x12 (the 0x0A..0x0F gap is
  documented as part of the ABI: no branch → unknown → -1).
  Machine-readable `<!--ABI 0xNN -->` claim blocks (name / args /
  storage / returns / twin) + prose conventions: storage homes
  (RAM vs PIXEL vs HOST, post-(d)), no-crash OOB rule, NO errno set
  (printed host-console reason + -1), GLYPH_RUN_ALLOW containment for
  0x07/0x12, reserved-bridge range, twin-status legend. Twin divergences
  are NAMED, not hidden: 0x03/0x04/0x06 STUB-return-0; 0x10/0x11 BRIDGED
  return-0 WITHOUT VAC2 validation / WITHOUT the pixel copy.
- `tests/test_pillar21_abi_spec_rotguard.py` — 20 legs in 4 layers:
  L1 registry coverage (doc blocks ≡ dispatch branches, both
  directions, exact expected set), L2 storage claims re-derived from
  handler bodies (RAM ⇒ `self.memory[` present; PIXEL ⇒ `_mem_read/
  _mem_write(image` present), L3 twin-status vs WGSL source structure
  (own branch / 3u-4u-6u stub group with `||`-join-aware standalone
  detection / 16u-255u bridge / no branch) + divergence-ledger equality,
  L4 live behavioral legs on the real Python engine (direct
  `_handle_syscall` drives, the test_defect_d pattern) incl. the
  0x07/0x12 allowlist-refusal leg on a REAL existing non-allowlisted
  file (cannot pass via the file-not-found branch) and OOB no-crash +
  no-RAM-growth, L5 non-vacuity (three in-memory doc mutations each
  turn the matching check RED; shipped files untouched — the
  test_pillar23 in-memory-mutation pattern).

## 2. Gate legs (own runs)

- RED first: doc absent → **20 errors in 0.19s** (fixture assertion
  "docs/SYSCALL_ABI_SPEC.md missing").
- GREEN: `tests/test_pillar21_abi_spec_rotguard.py` **20 passed in 0.08s**.
- Gate caught 4 real imprecisions in my own first-draft legs during
  bring-up (non-contiguous surface assumption — 0x0A..0x0F have no
  branches; STUB-group false positive on the `||`-joined WGSL
  expression; 0x03's returns string; 0x02 OOB-arg register choice).
  All four fixed to match MEASURED engine truth; the doc was never
  bent to save a test.
- Neighbour sweep: defect_d(25) + pillar23(8) + se022a(4) + se024 +
  bk2 + triple-sync + gh4 + syscall_handlers + gh6 = **61 passed 2.23s**.
- Pre-commit hooks executed during the commit: engine/codec fast-path
  stanzas all skip-path (no engine file staged); commit is 2 files, +721.

## 3. HONEST BOUNDARY (what the PASS does not prove)

- The guard proves **doc↔code agreement**, not engine correctness —
  engine semantics stay owned by their own gates (defect_d suite,
  pillar23 corpus, syscall_handlers).
- L4 exercises the **Python engine live**; twin behavior is pinned
  structurally (L3) + by the 2.3 corpus, not by per-handler GPU legs
  here (determinism rule: GPU legs never gate).
- `_read_path`'s view-merge is documented as the path-addressing rule;
  its internal merge ALGORITHM is deliberately not pinned (RUN2/GH-9
  in-flight work per the (d) final ledger).
- 0x08/0x09 codec round-trip is NOT re-proven here (Phy16Tone legs own
  it); the spec describes the contract, not the codec.
- No repo-wide sweep (exclusivity clause; arc leg A is the standing
  gate; sibling claude 3845928 was live at tick start — no engine-file
  contact by it during this tick per `git log --all --since` checks).

## 4. Remaining supply

- **LD/ST storage-home asymmetry** (Pillar 3 residual, per addendum 112
  §2): needs FULL-(A) scope → **BLOCKED-ON-DESIGN** (the (A)-scoped
  ruling explicitly excluded full (A)); Jericho triage required.
- Pillar 1.3 comparison flags — BLOCKED-ON-DESIGN (SE025 unruled).
- Pillar 5 (LLVM IR→Glyph) — design judgment, exempt from self-promotion.
- DEFECT-22E — reopen-on-evidence only.
- Next mechanical rung candidates for triage/scan: none currently
  concrete beyond the above; a fresh promotion scan next tick.

## 5. Not verified this tick

- No WGSL/GPU leg ran (this row changes no engine file; the corpus +
  triple-sync suites in the neighbour sweep own the standing pins).
- No repo-wide sweep (exclusivity clause).
