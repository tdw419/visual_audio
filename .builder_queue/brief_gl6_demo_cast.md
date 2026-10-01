# BRIEF — GL6-BUILD (OSS GL-6): recorded demo cast + capture-authenticity gate

**Row id:** GL6-BUILD (the OSS lane's GL-6, promoted as a row in `GLYPH_SELF_HOSTING_ROADMAP.md`).
**Repo:** `/home/jericho/zion/worktrees/glyph-isa` — this is the public OSS repo (`github.com/tdw419/glyph-isa`),
NOT `visual_audio`. All paths below are relative to that repo root. Work ONLY there.

## Deliverable (FOUR new files; no existing file may be modified; do NOT commit)

1. `tools/record_cast.py` — stdlib-only recorder (see spec).
2. `docs/demo/gl6_bake_and_run.cast` — the committed artifact, produced by RUNNING the recorder (never hand-written).
3. `tests/test_gl6_demo_cast.py` — the gate.
4. `docs/DEMO.md` — short doc: what the demo shows, the exact regenerate command, how to view it, and the note
   that publishing the shareable link (asciinema.org upload / hosted page) is Jericho's step, not the repo's.

## Why this form (already decided — do not re-litigate)

`asciinema` is not installed on this host and `pip install --user` is refused under PEP 668, so a committed
stdlib pty recorder writing the asciinema v2 format is the artifact path. The cast must therefore be a REAL
capture: every event line comes from bytes read off a pty, never typed, templated, or synthesised.

## `tools/record_cast.py` — exact spec

- Stdlib only (`pty`, `os`, `sys`, `json`, `time`, `select`, `argparse`, `hashlib`, `pathlib`). No third-party imports.
- CLI: `python3 tools/record_cast.py --out <path-to.cast>` (only required arg). Repo root is derived from the script
  location (`Path(__file__).resolve().parent.parent`), never hardcoded, never `os.getcwd()`.
- The recorder runs ONE fixed demo session, defined as a module-level constant list `DEMO_SESSION`:
  ```
  mkdir -p /tmp/glyph_demo
  ./glyphc build examples/01_hello.glyph -o /tmp/glyph_demo/01_hello.glyph.png
  ./glyphc run /tmp/glyph_demo/01_hello.glyph.png
  ./glyphc build examples/03_fibonacci.glyph -o /tmp/glyph_demo/03_fibonacci.glyph.png
  ./glyphc run /tmp/glyph_demo/03_fibonacci.glyph.png
  exit
  ```
- Mechanism: `pty.fork()` a child running `/bin/sh` (NON-interactive — it reads the session from the pty's stdin)
  with `cwd` = repo root and env `PS1='$ '`, `LC_ALL=C`, `TERM=xterm-256color`, `NO_COLOR=1`. The parent writes
  each `DEMO_SESSION` line to the master fd (so the tty driver's own echo puts the command lines in the transcript)
  and reads all output with `select()` in chunks until EOF/`EIO`. Record each chunk as one event with its real
  elapsed time. `waitpid` the child and capture its exit status.
- The cast is asciinema v2 text: line 1 = JSON object `{"version": 2, "width": <int>, "height": <int>,
  "timestamp": <unix int>, "env": {"SHELL": "/bin/sh", "TERM": "xterm-256color"}, "title": "Glyph: bake a .glyph
  program to pixels and execute it", "exit_code": <int>}`; then one JSON array per line: `[<float seconds>, "o",
  "<captured chunk>"]`, times non-decreasing and starting at 0.0. `exit_code` is the recorded child status.
- After writing, print ONE line to stdout for provenance, e.g.
  `cast=<path> events=<n> bytes=<n> payload_sha256=<hex> exit_code=<n>`
  where `payload_sha256` is `sha256("".join(payloads).encode())` over the concatenated output payloads and `bytes`
  is the length of that concatenation.
- Exit non-zero with a clear stderr message if the pty cannot be created, if the child produces no output, or if
  the child's exit status is non-zero.

## Measured expectations (from the current tree — do not invent others)

- `./glyphc build examples/01_hello.glyph -o …` → `✓ Baked 'examples/01_hello.glyph' -> '…' (256x19 px, 64 cols)`
- `./glyphc run …/01_hello.glyph.png` → `OUTPUT: 42` then `[HALTED] in 3 steps | r0=0 r10=42`
- `./glyphc build examples/03_fibonacci.glyph -o …` → `✓ Baked … (256x19 px, 64 cols)`
- `./glyphc run …/03_fibonacci.glyph.png` → `OUTPUT: 13` then `[HALTED] in 513 steps | r0=1 r10=13`
- `tools/glyphc.py` emits no ANSI escape codes (verified: 0 matches for colour sequences), so a payload comparison
  needs no ANSI stripping — compare raw.

## `tests/test_gl6_demo_cast.py` — the gate (exactly these four tests)

Run from the repo root as `/usr/bin/python3 -m pytest tests/test_gl6_demo_cast.py -q`.
The committed cast path is `docs/demo/gl6_bake_and_run.cast`; derive it from `Path(__file__).resolve().parent.parent`
(never a hardcoded absolute path). Use `sys.executable` for any subprocess that must use the same interpreter.

- `test_l1_cast_structure` — the committed cast exists; line 1 parses as a JSON object with `version == 2`,
  `width`/`height` ints > 0, a numeric `timestamp`, and an integer `exit_code` **asserted equal to 0**; every
  remaining non-empty line parses as a 3-element JSON array `[t, "o", payload]` with numeric `t`, non-decreasing
  across events; the concatenated payload is non-empty and contains at least 5 newlines.
- `test_l2_replay_anchors_in_order` — concatenate the payloads and assert the following appear **in this order**
  (indexes strictly increasing): `./glyphc build examples/01_hello.glyph`, `✓ Baked`, `256x19 px, 64 cols`,
  `./glyphc run`, `OUTPUT: 42`, `[HALTED] in 3 steps`, `./glyphc build examples/03_fibonacci.glyph`,
  `OUTPUT: 13`, `[HALTED] in 513 steps`. The command lines must be present because the tty echoed them —
  assert the command lines too, not just the program output.
- `test_l3_reexecution_matches_committed_payloads` — re-run the COMMITTED recorder
  (`subprocess.run([sys.executable, "tools/record_cast.py", "--out", <tmpfile>], cwd=repo_root, check=True)`) and
  assert the fresh cast's concatenated payload is **byte-identical** to the committed cast's, and the fresh
  header's `exit_code` is 0. This is the anti-fabrication leg: a hand-written cast cannot match a fresh real run.
- `test_l4_negative_leg_red_on_mutation` — copy the committed cast to a tmp file, mutate exactly one character
  inside one output payload (e.g. the `42` in `OUTPUT: 42` → `43`), and assert the gate's own checker reports RED
  for that copy. Implement the checker as a helper so L1/L2 call it too (the mutation must trip the SAME code path
  the real assertions use, not a bespoke re-implementation). A mutated copy that still passes means the gate is
  vacuous — that must be an assertion failure with a clear message.

Do not add a fifth test, do not weaken a leg, and do not make any leg depend on network, GPU, or `/tmp` state left
by another test.

## `docs/DEMO.md`

State: what the demo shows (`.glyph` → baked pixels → execution, two programs: `01_hello` prints 42 in 3 steps,
`03_fibonacci` prints 13 in 513 steps); the exact regenerate command
(`python3 tools/record_cast.py --out docs/demo/gl6_bake_and_run.cast`); how a reader replays it
(`asciinema play docs/demo/gl6_bake_and_run.cast`, or paste it as a file on asciinema.org); the receipt values the
gate asserts (child exit code 0, and re-running the recorder reproduces the payload byte-for-byte); and one honest
line that publishing the shareable link is the maintainer's step.

## Evidence to print when you finish (do NOT commit)

1. `python3 tools/record_cast.py --out docs/demo/gl6_bake_and_run.cast` → its provenance line.
2. `/usr/bin/python3 -m pytest tests/test_gl6_demo_cast.py -q` → result line.
3. `/usr/bin/python3 -m pytest tests -q 2>&1 | tail -3` → the repo's own suite must stay green.
4. `git status --short` → must show ONLY the four new files (plus untracked caches).
