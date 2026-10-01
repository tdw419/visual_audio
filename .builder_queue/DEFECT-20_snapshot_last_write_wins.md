# DEFECT-20 — snapshot identity: last write wins, so a witness can corroborate the WRONG write

**Found:** 2026-09-12, by the dual-channel re-verification experiment (BK-14 demo vs `geo-obs` reads).
**Status:** OPEN · **Severity:** evidence-chain (not a kernel bug)

## Evidence (code-level, confirmed)

`tools/geos_emit.py`:

```
line  40 : IMAGE_NAME = "kernel_memory.npy"
line 108 : np.save(fh, mem)                       # single write path, fixed name
line  88 : _load_state(): prefers publish_dir/kernel_memory.npy,
                          else newest *.npy by mtime
```

One fixed filename, one write call. In a multi-stage run (BK-14's demo publishes in several
stages, each constructing its own memory image) every stage overwrites the same file, so the
committed snapshot only ever represents the **last** writer. An earlier stage's words can be
silently replaced by an unrelated later publish.

Observed in the experiment: word 703 (exit code) matched across channels because no later
stage touched it; word 750 (argv, stage 1) and 754 (result) did **not** match, because later
stages rewrote those words for unrelated purposes. Sentinels were stamped into an in-memory
surface frame that this path never persists.

## Consequence

A snapshot cannot distinguish "this is stage 1's value" from "this is whatever wrote last".
That makes two things unsound:

1. **The substrate-witness rule (roadmap, 1c27856)** — a witness is currently identifier-free,
   so it can be a true statement about the wrong write. Amend the rule: a witness must carry
   the **writer identity** (stage/intent id) it corroborates, not just `age_seconds`.
2. **Any multi-stage row verified through the substrate path** — BK-14's stages cannot be
   corroborated after the fact from the current artifact.

This is not a BK-14 defect: the demo's own host-side checks are correct at the moment they run.
It is a limitation of the observation/publish path.

## Fix (precedent exists in-repo)

The resident daemon already writes **per-tick** images (`kernel_memory_tick*.npy`), which is
exactly the shape needed. Either:

- (a) unique image per write: `kernel_memory.<stage_or_intent_id>.npy`, and/or
- (b) embed a write counter + writer id in the image header/sidecar and surface it via
  `geos_surface_meta`.

(b) is preferred: it keeps a stable read path while making the write identity
machine-checkable, and it is what a witness needs to be falsifiable.

## Acceptance criteria

- Two consecutive publishes from one process produce two distinguishable artifacts (or one
  artifact with a monotonic write id visible in meta).
- `geos_surface_meta` reports the writer id / write counter for the image it serves.
- A witness taken after publish N names publish N; taking a witness for an earlier publish
  fails loudly instead of silently reading the later image.
- Reproduce the BK-14 dual-channel experiment. **"Agreeing" means attributably
  agreeing**: every substrate-read word must be traced to the stage that wrote it
  (stage id + write id), not merely match numerically. Numerical agreement
  alone does NOT satisfy this criterion....[truncated]
