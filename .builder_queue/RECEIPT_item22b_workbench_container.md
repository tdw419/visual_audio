# RECEIPT — item-22b: standalone workbench container (items 22+23, second context)

**Ticket:** CLAIM QUEUE item-22b (QUEUE_STATE.json claim_order 22, unblocked)
**Landed by:** builder cron af3e62239ce2, 2026-09-25 ~21:5x CDT
**Spec source:** PRODUCT_ROADMAP.md / PRODUCT_LANE_STATE.md ROUND 11 ADDENDUM
(items 22+23 = ONE staging mechanism, TWO verification contexts; format
decision "PNG-family or self-extracting .py — final call at landing").
Context 1 (dev, BK-25, tools/stage_workbench.py) was already landed; this
ticket lands context 2 (standalone).

## SPEC: adoption line

No Linux-sourced contract adopted (round-11 doctrine only); SPEC-citation
gate not triggered.

## What landed

- `tools/build_workbench_container.py` — `build_container(manifest)` emits
  a SINGLE self-extracting .py. Bootstrap is stdlib-only
  (base64/hashlib/json/os/shutil/sys/tempfile/pathlib) and:
  - verifies every payload file's sha256 BEFORE writing anything; loud
    `ERR:CHECKSUM` refusal (rc 3), no silent corruption, no partial root;
  - bakes PATH_CAP from `experiments.glyph_l1_shell` at BUILD time, so the
    container's layout constraint can never drift from the engine's;
    loud `ERR:PATHCAP` refusal (rc 2) on violation;
  - unpacks into the IDENTICAL session-root layout (w.dat + bin/ +
    scripts/ + tests/ + experiments/tools/src import-root contract) as
    BK-25's `stage_workbench`;
  - prints `WORKBENCH_ROOT=<path>` and exits 0.
  - FORMAT DECISION AT LANDING: self-extracting .py over PNG-family.
    Reasons: (a) zero host deps to unpack (PNG needs PIL host-side);
    (b) programs+data-in-one-file is exactly round-11 doctrine, the
    interpreter is NOT carried; (c) VFS-1 png_vfs.py already owns the PNG
    transport for DISKS — no second PNG format needed for the carrier.
- `tests/test_item22b_workbench_container.py` (force-added past the
  .gitignore test rule) — 7-leg gate.

## Gate legs and their evidence

- G1 stdlib-only: AST-walks the generated container; every import root
  must be in the stdlib allowlist. GREEN.
- G2 subprocess unpack: container run as a real subprocess (`--base`);
  WORKBENCH_ROOT printed once; layout asserted; `len(root+"/w.dat") <=
  PATH_CAP` re-checked against the REAL engine constant (baked-cap
  cannot drift). Content COPIES (no symlinks). GREEN.
- G3 in-shell pytest from the container-unpacked root: 13 passed
  (hermetic BK-22 + item-11 fixtures). GREEN.
- G4 context equivalence: same manifest through both contexts —
  container-unpacked files byte-identical to BK-25-staged files
  (w.dat, bin/README, both staged tests). GREEN.
- N1a corrupted checksum: one flipped sha256 hex digit → rc != 0 with
  `ERR:CHECKSUM` on stderr, nothing unpacked. Demonstrated in-gate GREEN
  (i.e. the container refuses) and the leg itself fails loudly if the
  refusal regresses.
- N1b over-PATH_CAP base → rc != 0, `ERR:PATHCAP` on stderr. GREEN.
- N1c truncated container file (cut mid-payload-literal) → rc != 0.
  GREEN.

## RED-first evidence

- Pre-landing (builder absent): `ModuleNotFoundError:
  tools.build_workbench_container` at collection — the gate could not
  pass before the deliverable existed.
- Module moved aside post-landing, re-run: same collection error;
  restored: `7 passed in 0.47s`. The gate re-discriminates against its
  own deliverable.

## Measured findings (this tick, receipts for items 22c+ / engine lanes)

1. **FS-window path budget is the BINDING constraint, not PATH_CAP.**
   G3 first ran RED: `ERR:PATH:path too long for the FS window` for
   `<root>/solo.txt` — root_name `glyph_workbench_c22b` under /tmp makes
   49-char file paths; dev-context roots land ~37 chars and fit.
   Constraint site: `_stamp_path` → `build_dispatch_shell` layout,
   `path_cap = audio_path_addr - path_addr - 2`
   (experiments/glyph_interactive_shell.py:805; enforced at
   experiments/glyph_l1_shell.py:262). Container default root_name
   shortened + documented on the builder CLI. OPEN engine question
   (not fixed here, engine-adjacent): whether the window budget should
   be raised or paths made session-relative at stamp time.
2. **pytest tmp_path can never satisfy PATH_CAP** (re-measured, matches
   BK-25's note): pytest tmp bases are >90 chars; both staging contexts
   must use short mkdtemp bases. Gate carries its own `_short_base()`.

## What the PASS does NOT prove

- No GPU-image execution: the container runs on host CPython (Phase-2
  doctrine); the interpreter is deliberately not carried.
- The PNG-family carrier alternative is NOT tested (deferred by the
  round-11 "both formats satisfy the gate" clause; the .py choice is
  the landing decision).
- No WGSL twin (nothing spatial landed).
- Engine files untouched: findings are flagged, not fixed.
-Protected assets untouched (voicebook/, .rts/, rs_fixtures.json).

## Files

- tools/build_workbench_container.py (new)
- tests/test_item22b_workbench_container.py (new, force-added)
- .builder_queue/QUEUE_STATE.json (item-22b → landed)
- .builder_queue/CURRENT_TICKET.json (reconciled to landed)
- .builder_queue/PRODUCT_LANE_STATE.md (ledger entry, this landing)
- Receipt: .builder_queue/RECEIPT_item22b_workbench_container.md (this file)

## Next

Claim queue has no unblocked items left (item-25 RESERVED pending
operator sign-off). Next tick per Phase-1c: research ticket IF no new
supply/RULING; else take the queue.
