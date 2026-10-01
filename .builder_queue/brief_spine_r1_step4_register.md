# BRIEF — SPINE-R1 Phase 3 · STEP 4 of 6: `WriteRegistry.register` + persistence

**Row id:** SPINE-R1 step 4 of 6 (authority: `.builder_queue/RULING_lane_supply_20260912.md` § Reserved item 3;
parent plan `.builder_queue/brief_spine_r1_phase3.md`; spec of record `systems/GLYPH_SPINE_SKELETON.md`
§7 item 4 / §4 interface contracts, **LOCKED**).

**Steps 1–3 are landed** (commits `531bfaa`, `2e10286`, `0bc756a`; gates `tests/test_spine_r1_plan.py` 9/9,
`tests/test_spine_r1_compact.py` 7/7, `tests/test_spine_r1_refuse.py` 7/7). You implement **step 4 only**.
Prior partial work is NOT a precedent to copy — read the current file state first (`tools/geos_registry.py`
and `tools/geos_archive.py` at HEAD are the authority).

**Files in scope (only these two):**
- EDIT `tools/geos_registry.py` — implement `WriteRegistry.register()` (plus ONE private module-level helper
  if you need it). Do **not** implement `lookup()`, `conflicts()`, or `scan()` (they are step-5/6 work and
  stay stubs). Do **not** touch `registry_key`, `entry_line`, `index_digest`, `line_sha_for`, the
  `RegistryEntry` / `ArchiveRecord` dataclasses or their fields, `__all__`, or the `__main__` smoke block.
  Do **not** touch `tools/geos_archive.py`, `tools/geos_emit.py`, `tools/geos_observation_server.py`,
  `tools/geos_witness.py`, `tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, any WGSL,
  `systems/GLYPH_SPINE_SKELETON.md`, or `.builder_queue/**`.
- NEW `tests/test_spine_r1_register.py` — the gate.

**Stdlib only** in `tools/geos_registry.py` (`json`, `os`, `hashlib` already/obviously fine);
`tools/geos_spine_verify.py` AST-scans for third-party imports and must stay PASS.

## The rule (decided by the orchestrator — implement EXACTLY this)

`register(record, origin_id) -> RegistryEntry` appends one canonical line to the append-only index and
returns the persisted entry. Five clauses, all load-bearing:

**R1 — build the entry exactly as the stub already does.** `key = registry_key(origin_id, record.write_id)`
(this raises `ValueError` on an empty/whitespace `origin_id` and `TypeError` on a non-int `write_id` — keep
both), `origin_id=key[0]`, `write_id=key[1]`, `writer=record.writer`, `image_path=record.image_path`,
`line_sha=line_sha_for(record)`, `written_at=record.written_at`. The returned object is the SAME object
appended to `self.entries`.

**R2 — duplicate-key refusal happens BEFORE any byte is written.** The key must be absent from (a)
`self.entries` and (b) the log already on disk at `self.index_path`. On-disk check = read-only scan of the
existing file, one `json.loads(line)` per line, skipping blank/whitespace-only lines; an absent file means
an empty index (no error). If the key is already present, raise:

```
refusing to register: duplicate registry key {key!r} already present at line {n} of {index_path} (append-only index: history is never rewritten)
```

where `n` is the **1-based line number on disk**, or `0` when the duplicate is only in `self.entries`.
The message must contain the literal substring `duplicate registry key` and the `repr()` of the key tuple.
**Any** duplicate key is refused, regardless of `line_sha`: a key is a publish identity, so a second
registration is never legitimate (I1/I2). This is deliberately stricter than `conflicts()`'s
">1 distinct `line_sha`" rule — state that difference in the `register()` docstring.
A refusal must not create, truncate, or modify the index file.

**R3 — append semantics.** Create the parent directory first (`os.makedirs(os.path.dirname(...), exist_ok=True)`
guarded for the empty-dirname case), then open `index_path` in mode `"a"`, encoding `utf-8`, write
`entry_line(entry) + "\n"` as **one** `write()` (never a partial line), `flush()`, `os.fsync(fileno)`.
fsync-or-refuse: an `OSError` from makedirs/open/write/flush/fsync propagates as `OSError` (unchanged type
or wrapped with `from`, but it must remain an `OSError`), and in that failure path `self.entries` must be
**unchanged** (no in-memory success for a failed append).

**R4 — persistence/identity.** After a successful register on a fresh path, the file's lines and the
instance's in-memory lines agree byte-for-byte and in order:
`self.digest() == index_digest(open(index_path, encoding="utf-8").read().splitlines())`.
The index never rehydrates the whole log into `self.entries` — `self.entries` means "entries this instance
registered" — so for a **re-opened** instance (new object, non-empty log) the guarantee is
**prefix preservation**, not in-memory equality: appending a new key must leave every pre-existing byte
untouched and grow the file by exactly `len(entry_line(new_entry)) + 1` bytes.

**R5 — return value.** Return the appended `RegistryEntry` (same object as in `self.entries`).

## Gate: `tests/test_spine_r1_register.py`

Command: `/usr/bin/python3 -m pytest tests/test_spine_r1_register.py -q`

Every leg uses `tmp_path`; no test may touch a real repo path or `/tmp/glyph_spine_index.jsonl`.
Build records with `ArchiveRecord(...)` from `tools.geos_archive` — **distinct** `write_id` per key, and
distinct `image_path` values where a leg needs them. Legs (8):

- **L1 append basics** — fresh path: `register()` returns an entry whose `key`, `writer`, `image_path`,
  `written_at` match the record and whose `line_sha == line_sha_for(record)`; the file exists with exactly
  one newline-terminated line and that line `== entry_line(returned_entry)`; `json.loads(line)["write_id"]`
  is the record's `write_id`.
- **L2 append-only growth** — a second register with a *new* key appends exactly one more line; the first
  line's bytes are unchanged (prefix preserved); parsed key order == registration order.
- **L3 digest/persistence** — on a fresh path, `index_digest([])` for the empty log; after the registers
  `reg.digest() == index_digest(file_lines)` (the R4 equality) and equals `reg.lines()` digested; a second
  instance reading the file independently reproduces the same key sequence.
- **L4 duplicate refusal (in-memory)** — same instance, same key twice → `ValueError` containing
  `duplicate registry key` and `repr(key)`; line count still 1 and file md5 identical before/after.
- **L5 duplicate refusal (across re-open)** — a **new** instance on the same non-empty path registers a key
  already on disk → `ValueError` (message names the on-disk 1-based line number, `n >= 1`), file md5
  unchanged, and the pre-existing line is byte-identical. History is never rewritten.
- **L6 re-open append + prefix preservation** — new instance appends a genuinely new key to the non-empty
  log: file grows by exactly `len(entry_line(new_entry)) + 1`; `file_bytes[:len(before)] == before`;
  parsed key set == old keys ∪ new key. (This is the row's "digest stable across re-open" clause: the
  digest of the preserved prefix is identical before and after.)
- **L7 failure path is live** — `index_path` whose parent is a **regular file** (e.g.
  `str(tmp_path / "afile" / "index.jsonl")` after writing `tmp_path/"afile"`) → `pytest.raises(OSError)`;
  `reg.entries == []`; no file appears at the target path; a subsequent register on a valid path succeeds.
- **L8 no-write refusal + bad key** — empty/whitespace `origin_id` → `ValueError` **and no index file is
  created** (the path must not exist after the call); an empty (0-byte) or trailing-blank-line index is
  treated as "no entries" (no phantom duplicate, no crash).

Write the gate **first**, run it (expect RED: `register` is a stub), save that output, then implement, then
run it again for GREEN. Do not weaken a leg to make it pass; if a leg seems impossible under the frozen
interfaces, STOP and report the conflict instead of changing signatures.

## Hard constraints

- Interfaces frozen: no signature, dataclass-field, or `__all__` changes. If one seems wrong, STOP and report
  — that is a skeleton-sign-off change, not a builder call.
- Do not weaken the pure core (`registry_key` / `entry_line` / `index_digest` / `line_sha_for`) or the
  step-1/2/3 work in `tools/geos_archive.py` to make I/O easier.
- Wire-in (`geos_emit.publish()` → registry) and any registry compaction are **NOT** in this round.
- **Do NOT commit, do not `git add`.** Leave the tree for the orchestrator. Do not create extra files
  beyond `tests/test_spine_r1_register.py`.

## Evidence to leave behind (the orchestrator re-runs everything itself)

1. RED run before implementation, and GREEN run after — command + literal tail of both.
2. `/usr/bin/python3 -m pytest tests/test_spine_r1_plan.py tests/test_spine_r1_compact.py tests/test_spine_r1_refuse.py -q` still green.
3. `/usr/bin/python3 -m pytest tests/test_spine_r1_register.py -q` → all legs pass.
4. `/usr/bin/python3 tools/geos_spine_verify.py` → still PASS.
5. `git status --short` — only `tools/geos_registry.py` (modified) and `tests/test_spine_r1_register.py` (new).
