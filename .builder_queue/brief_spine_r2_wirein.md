# BRIEF — SPINE-R2-WIREIN: publish-path registry append + operator retention CLI

**Roadmap row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md` → `SPINE-R2-WIREIN` (promoted `652e177`, queued 2026-09-13)
**Binding decision:** `.builder_queue/RULING_spine_wirein.md` — **OPTION 2**. Implement exactly that shape.
**Repo:** `/home/jericho/projects/zion/projects/visual_audio` (branch `glyph-transpiler-autoloop`, do NOT switch branches)

## Deliverables (three items — nothing wider)

### 1. `tools/geos_emit.py` — best-effort registry append in the publish path
The publish path is `GeosEmitter._commit(...)` (`tools/geos_emit.py:102`); it mints the DEFECT-20 write
identity (`write_id` monotonic at `:128-136`, `writer`) and writes `surface.meta.json` at `:153` (`:166` for
the archive meta). Today nothing writes a line to the `WriteRegistry`, so the publish identity is never
indexed at the moment it is minted.

Add: after the identity is established and the sidecar payload is built, append **exactly one** line to the
`WriteRegistry` (`tools/geos_registry.py`: `WriteRegistry`, `line_sha_for(record)` `:135`, `RegistryEntry`
`:69`, `entry_line` `:103`).

- The append is **best-effort**: on ANY failure (unwritable/missing registry path, OSError, `EmitError` from
  the registry, malformed payload) the publish MUST still succeed and return exactly what it returns today —
  no new exception path on the hot path.
- On append failure the sidecar carries `"unattributed": true` and `"unattributed_reason": "<why>"`.
  On success those fields are absent or false.
- Do NOT touch `write_id` minting semantics and do NOT add a lock to the DEFECT-20 counter — explicitly out of
  scope per the ruling (it would be its own ticket).

### 2. `tools/geos_retain.py` — NEW operator CLI over retention
Built on `tools/geos_archive.py` (`ArchiveRecord` `:79`, `RetentionPolicy` `:97`, `Eviction` `:115`,
`retention_plan(...)` `:177`, `ArchiveStore` `:248`).
Flags: `--plan`, `--apply`, `--keep-last N`, `--max-bytes B`, `--tag-exclude T`, plus the archive dir and
registry path arguments you need. Exit codes are the contract:

- `0` plan/apply succeeded
- `2` **refused** (a plan that would evict a registry-referenced archive, or an unknown writer) — the reason is
  written into the plan file AND stderr, and **nothing is deleted**
- `1` internal error
- **Default is inert**: `--apply` with no policy flag evicts nothing and says so. Retention is the only
  data-destroying operation in the project — the safe default does nothing.
- `--plan` writes a plan and deletes nothing. `--apply` is idempotent (a second `--apply` is a no-op, exit 0).

### 3. `tests/test_spine_r2_wirein.py` — NEW gate (six legs, verbatim from the ruling)
Use `tmp_path` fixtures only; no writes into the repo tree.

1. **Best-effort append, negative control.** Point the publish path at a read-only/unwritable registry path in
   a temp dir → publish **succeeds**, and the sidecar has `unattributed: true` with a non-empty reason.
2. **Happy path.** A successful publish appends **exactly one** line, and `line_sha` of that line equals
   `line_sha_for(entry)` — no drift between mint and index.
3. **`--plan` is non-destructive.** Fixture where one archive is registry-referenced: `--plan` writes a plan,
   exits 0, and **every file still exists** afterwards (assert by directory listing before/after).
4. **`--apply` is idempotent.** First `--apply` removes exactly the planned set; a second `--apply` is a no-op
   (exit 0, nothing further removed).
5. **Refusal.** A plan that would evict a registry-referenced archive exits **2**, writes the reason, and
   deletes nothing.
6. **Default is inert.** `--apply` with no policy flags evicts nothing and says so.

Each leg must be capable of failing — do not write a leg whose assertion cannot discriminate.

## Gates YOU must run and paste into your report (raw tail, no paraphrase)

```
/usr/bin/python3 -m pytest tests/test_spine_r2_wirein.py -q            # must be 6 passed, rc=0
/usr/bin/python3 -m pytest tests/test_spine_r1_*.py -q                 # must stay 50 passed, rc=0
/usr/bin/python3 tools/geos_spine_verify.py                            # must print PASS, rc=0
```
Also paste `git status --short` so the orchestrator can see the exact changed set.

## Scope fences

- Files you MAY touch: `tools/geos_emit.py`, `tools/geos_retain.py` (new), `tests/test_spine_r2_wirein.py` (new).
- Files you MUST NOT touch: `tools/geos_archive.py` (its API is the oracle here — if it cannot express a leg,
  STOP and report the missing API instead of editing it), `tools/geos_registry.py`, `tools/geos_spine_verify.py`,
  the roadmap, anything under `systems/`, any other test file, `pytest.ini`, and all GH/BK spinner core files
  (`tools/glyph_gpt/baker.py`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, WGSL shaders).
- Do **NOT** commit and do not run `git add`/`git commit`/`git stash`/`git checkout`. Leave the tree dirty for
  the orchestrator to verify and land.
- Prefer stdlib + the repo's own modules; no new third-party dependency (`tools/geos_spine_verify.py` leg 2
  AST-checks for third-party imports).

## Report back (concise)

Row id; the three gate commands with their raw tails and exit codes; `git status --short`; the exact
sidecar fields you added; anything you could not do and why; and an honest boundary section naming what this
gate does NOT prove (e.g. concurrency/atomicity of the append, behaviour under a hostile registry writer).
