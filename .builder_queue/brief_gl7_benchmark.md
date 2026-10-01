# BRIEF — GL7-BUILD (OSS GL-7): cold-boot-to-first-instruction benchmark + regeneration gate

**Row id:** GL7-BUILD (the OSS lane's GL-7, promoted as a row in `GLYPH_SELF_HOSTING_ROADMAP.md`, commit `7d39d75`).
**Repo:** `/home/jericho/zion/worktrees/glyph-isa` — the public OSS repo (`github.com/tdw419/glyph-isa`),
NOT `visual_audio`. All paths below are relative to THAT repo root. Work ONLY there. **Do NOT commit.**

**Binding conditions:** `.builder_queue/NEXT_TARGET_gl7.md` § BINDING GATE CONDITION (lives in the *builder*
repo, so it is NOT readable from the OSS repo) — summarized: (1) MEASUREMENT not authorship, (2) REGENERATION
TOLERANCE (committed numbers within 3× of a fresh re-measurement), (3) NEGATIVE LEG + BASELINE LIVENESS,
(4) DOC-CONSISTENCY + HONESTY section. The legs specified below are the complete, binding specification.
A green gate is not evidence until it can fail. Legs 1–4 below are binding; do not weaken,
reorder, or add a fifth test.

## Deliverable — EIGHT new files, no existing file modified

1. `tools/bench_wasm_module.py` — stdlib-only emitter of a minimal valid `.wasm`.
2. `tools/bench_wasm_runner.js` — node runner (no npm deps) that instantiates a `.wasm` and times phases.
3. `tools/bench_boot_sector.py` — stdlib-only emitter of a 512-byte x86 boot sector.
4. `tools/bench_glyph_child.py` — the glyph-side child harness (own process, prints phase JSON).
5. `tools/bench_cold_boot.py` — the harness: runs all three legs N reps, emits the JSON.
6. `docs/bench/cold_boot.json` — raw numbers, produced by RUNNING the harness (never hand-written).
7. `docs/BENCHMARK_COLD_BOOT.md` — methodology, the numbers, and the honesty section.
8. `tests/test_gl7_benchmark.py` — the gate.

Stdlib only for every `.py` (numpy/PIL are already repo deps and may be imported by the glyph child, which
loads a `.glyph.png`). The `.js` file must run under plain `node` with no packages.

## The measurement (identical method for all three legs — this is the whole point)

`tools/bench_cold_boot.py` measures, per rep:

- `t_spawn = time.perf_counter()` immediately before `subprocess.Popen(...)` of the leg's child;
- read the child's stdout (text mode, line-buffered) until the leg's MARKER line appears;
- `t_marker = time.perf_counter()`;
- **headline number = `(t_marker - t_spawn) * 1000.0` milliseconds** — process spawn → the child's own
  "first instruction" marker. Same method for all three legs, so the comparison is like-for-like;
- the child also prints its INTERNAL phase breakdown, timed with `perf_counter` in the child, reported
  relative to the child's own entry. Both are recorded; the doc must say the headline includes exec,
  runtime startup and pipe latency.

Legs:

- **glyph** — child = `sys.executable tools/bench_glyph_child.py <image.png>`. Marker line = its JSON line.
  Phases: `import_ms` (entry → after importing the toolchain), `boot_ms` (→ after `GlyphRunner(image)`
  construction, i.e. image read + PNG decode + boot), `first_instr_ms` (→ after ONE `cpu.step(runner.image)`
  call). Use the repo's own API: `from tools.glyph_gpt.runner import GlyphRunner`; `runner = GlyphRunner(path)`;
  `cpu = runner.get_cpu()`; `cpu.step(runner.image)`. Take `t_entry = time.perf_counter()` as the FIRST
  statement executed in the module (before the heavy imports) so `import_ms` is honest. The image is
  produced in a temp work dir by `tools/glyphc.py build examples/01_hello.glyph -o <workdir>/01_hello.glyph.png`
  (setup, NOT measured) and its sha256 + byte size recorded for provenance.
- **wasm** — child = `node tools/bench_wasm_runner.js <module.wasm>`; module emitted by
  `tools/bench_wasm_module.py --out <workdir>/bench.wasm --constant 42`. Marker = the runner's JSON line
  (it prints exactly one line). Phases reported by the runner via `process.hrtime.bigint()`:
  `read_ms`, `compile_ms`, `instantiate_ms`, `first_call_ms`, plus `ret`. The headline for this leg is the
  parent-side spawn→marker time (node startup dominates; report it, do not hide it).
- **qemu_vm** — child = `qemu-system-x86_64 -drive format=raw,file=<workdir>/boot.img -nographic -serial mon:stdio -no-reboot`
  with `stdin=DEVNULL`, image emitted by `tools/bench_boot_sector.py --out <workdir>/boot.img`. Marker =
  the two marker bytes `\xfe\xed` written to COM1 by the boot sector's first instructions. Read the child's
  **stdout as bytes** and stop as soon as the two-byte marker appears (`t_marker`), then `kill()` the child.
  This is verified to work on this host (see below). The qemu leg is a FULL VM (SeaBIOS included) — the doc
  must say it is not a microVM.

Every child must be bounded: per-rep timeout (30 s glyph/wasm, 60 s qemu) → on timeout, that leg's
`status` becomes `"error"` with the reason, and the harness exits non-zero (never a silent number).
Kill children in a `finally:` block; no orphan qemu may survive the harness.

## Verified reference encodings (from the orchestrator's own probes — reproduce these EXACTLY)

**`tools/bench_wasm_module.py`** must reproduce, for `--constant 42`, this 37-byte module (hex):
```
0061736d010000000105016000017f03020100070801046d61696e00000a06010400412a0b
```
Structure: magic+version; type sec `01 05 01 60 00 01 7f` ((func)->i32); func sec `03 02 01 00`;
export sec `07 08 01 04 6d61696e 00 00` ("main", kind 0, index 0); code sec `0a 06 01 04 00 41 2a 0b`
(count 1, body_size 4, locals 0, `i32.const 42`, `end`). CLI: `--out PATH` (required), `--constant INT`
(default 42). Encode section sizes and LEB128 lengths properly (do NOT hardcode the sizes — 42 vs 7 differ
in immediate only, but the code must be a real encoder). Print one line: `module=<path> bytes=<n> sha256=<hex>`.
Verified: `node tools/bench_wasm_runner.js <it>` printed
`{"read_ms":0.036,"compile_ms":0.113,"instantiate_ms":0.019,"first_call_ms":0.045,"ret":42}`.

**`tools/bench_wasm_runner.js`** — takes the `.wasm` path as `argv[2]`, times with `process.hrtime.bigint()`,
prints exactly ONE JSON line: `{"read_ms":…,"compile_ms":…,"instantiate_ms":…,"first_call_ms":…,"ret":<int>}`.
`ret` must be the value RETURNED BY the instantiated module's exported `main()` (`inst.exports.main()`), never
a constant in the JS. Exit non-zero with a message on stderr if the module fails to compile.

**`tools/bench_boot_sector.py`** — CLI `--out PATH`. Emits exactly 512 bytes:
```
B0 FE   mov al, 0xFE
BA F8 03   mov dx, 0x3F8
EE      out dx, al
B0 ED   mov al, 0xED
EE      out dx, al
FA      cli
F4      hlt
```
then zero-pad to offset 510 and append `55 AA`. Print `image=<path> bytes=512 sha256=<hex>`.
Verified on this host: with the same qemu invocation above, qemu printed the SeaBIOS banner followed by the
two marker bytes and then idled until killed.

**Harness JSON schema** (`tools/bench_cold_boot.py --reps N --json PATH`; also prints the JSON to stdout as
its LAST line):
```json
{"schema":"glyph-cold-boot-bench/1","harness_version":"1","measured_at":"<ISO8601>","reps":N,
 "host":{"cpu":"<model>","nproc":N,"python":"<ver>","node":"<ver or null>","qemu":"<ver line or null>","uname":"<...>"},
 "legs":{
   "glyph":{"status":"measured","unit":"ms",
     "spawn_to_first_instr":{"values":[…],"min":…,"median":…,"max":…},
     "phases":{"import":{"values":[…],"median":…},"boot":{…},"first_instr":{…}},
     "artifact":{"path":"…","bytes":…,"sha256":"…"}},
   "wasm":{…, "ret":42},
   "qemu_vm":{"status":"measured","unit":"ms","spawn_to_first_instr":{…},
     "artifact":{"path":"…","bytes":512,"sha256":"…"}}},
 "honesty_notes":["…"]}
```
A leg whose runtime is absent gets `{"status":"skipped","reason":"<named reason, e.g. node not found on PATH>"}`
and NO numbers at all. CLI must also accept `--legs glyph,wasm,qemu_vm` (subset) and `--reps`.
Use `shutil.which` for `node`/`qemu-system-x86_64`; never assume.

## `tests/test_gl7_benchmark.py` — the gate (exactly these four tests)

Run from the repo root as `/usr/bin/python3 -m pytest tests/test_gl7_benchmark.py -q`. Derive paths from
`Path(__file__).resolve().parent.parent`; use `sys.executable` for python subprocesses; never leave the repo
dirty (all work in `tempfile.mkdtemp()`), and never depend on `/tmp` state left by another test or on the network.

- `test_l1_measurement_not_authorship` — run the COMMITTED harness
  (`subprocess.run([sys.executable, "tools/bench_cold_boot.py", "--reps", "1"], cwd=repo_root, ...)`, timeout 300)
  and parse its last JSON line. Assert: exit 0; `schema == "glyph-cold-boot-bench/1"`; `reps == 1`; and for
  EVERY leg in `legs` either `status == "measured"` with a positive finite `spawn_to_first_instr.median` and
  its phase fields present (glyph phases: `import`, `boot`, `first_instr`, each finite and >= 0), or
  `status == "skipped"` with a non-empty `reason` and NO numeric fields. Also assert the wasm leg, if
  measured, reports `ret == 42`.
- `test_l2_regeneration_within_tolerance` — compare the COMMITTED `docs/bench/cold_boot.json` against the
  FRESH measurement from L1 using ONE shared helper `regeneration_red_reasons(committed, fresh, tol=3.0)`
  defined at module level. The helper returns a list of human-readable RED reasons: for each leg present and
  `measured` in both, if `fresh.median > tol * committed.median` OR `fresh.median * tol < committed.median`
  → a reason naming the leg, both numbers and the ratio; also a reason if a leg's status differs between the
  two. Assert `regeneration_red_reasons(...) == []`.
- `test_l3_negative_leg_and_baseline_liveness` — (a) load the committed JSON, copy it, multiply the glyph
  leg's `spawn_to_first_instr.median` by 10.0 and assert `regeneration_red_reasons(mutated, fresh) != []`
  (the SAME helper the real assertion uses — a bespoke re-implementation is a failure); (b) emit a module
  with `--constant 42` and with `--constant 7` via the committed emitter into a temp dir, run the committed
  node runner on each, and assert `ret == 42` and `ret == 7` respectively — proving the baseline number comes
  from executing the module, not from a print. Skip (b) with `pytest.skip("node not found on PATH")` ONLY if
  `shutil.which("node")` is None, and in that case still run (a).
- `test_l4_doc_consistency_and_honesty` — the doc `docs/BENCHMARK_COLD_BOOT.md` must carry a fenced block
  whose first line is exactly `BENCH-NUMBERS` and which then has one line per leg in exactly the form
  `leg=<name> status=<status> median_ms=<float|->` (e.g. `leg=glyph status=measured median_ms=0.123`), with
  the numbers EQUAL to the committed JSON's medians for that leg (float compare within 1e-9 relative) — the
  doc's numbers are therefore derived from the JSON, not typed. Mutating one such line in a temp copy of the
  doc MUST make the checker report RED (assert it, using the same parse/compare helper as the real assertion).
  Also assert the doc contains a heading matching (case-insensitive) `what this does not show` and that the
  text after it mentions each required caveat token: `page cache`, `microVM`, `pipe`, `single host`,
  `startup`. Do not assert on prose beyond these tokens.

## `docs/BENCHMARK_COLD_BOOT.md`

Must contain, in this order: what was measured and the exact command to regenerate it
(`/usr/bin/python3 tools/bench_cold_boot.py --reps 7 --json docs/bench/cold_boot.json`); the environment
(cpu/nproc/python/node/qemu); the method paragraph (spawn → first-instruction marker, same for all legs,
N reps, min/median/max, what "first instruction" means on each leg); the `BENCH-NUMBERS` block; then the
**"What this does not show"** section stating at minimum: no page cache drop (no root), the qemu leg is a full
VM with firmware and is not a microVM, pipe/spawn latency is inside every headline number, one host and one
run class only, interpreter/runtime startup dominates the headline so this is not a comparison of ISA
efficiency, and the glyph leg measures the repo's current Python implementation (not a GPU/WGSL path).
Do not claim a winner; report the numbers and the caveats. One line: publishing/hosting is the maintainer's step.

## Evidence to print when you finish (do NOT commit)

1. `/usr/bin/python3 tools/bench_cold_boot.py --reps 7 --json docs/bench/cold_boot.json` → the JSON tail.
2. `/usr/bin/python3 -m pytest tests/test_gl7_benchmark.py -q` → result line.
3. `/usr/bin/python3 -m pytest tests -q 2>&1 | tail -3` → the repo's own suite must stay green.
4. `git status --short` → ONLY the eight new files (plus untracked caches).

If a leg cannot be measured on this host, say so explicitly in your final message with the exact error —
do NOT invent a number, and do NOT weaken a gate leg to make it pass.
