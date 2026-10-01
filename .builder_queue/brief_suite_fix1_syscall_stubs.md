# BRIEF — SUITE-FIX-1 cluster (2): real handlers for the GlyphCPUv2 file/audio/run syscalls (0x03, 0x04, 0x07, 0x08, 0x09)

Roadmap row: `systems/GLYPH_SELF_HOSTING_ROADMAP.md:355` → **SUITE-FIX-1**, cluster **(2) “Syscall stubs”**.
Spec to read first: that row (cluster 2 + its GATE clause), then the three named test files — **they are the ABI
specification** and nothing else defines these syscalls:

- `tests/test_glyph_file_io.py` (FILE_WRITE `0x03`, FILE_READ `0x04`)
- `tests/test_glyph_audio_io.py` (AUDIO_OUT `0x08`, AUDIO_IN `0x09`)
- `tests/test_glyph_orchestrator_speak_to_driver.py` (AUDIO_IN → FILE_WRITE → RUN `0x07`, chained inside the CPU)

## Measured problem (orchestrator's own runs, HEAD `9f62ee7`)

`GlyphCPUv2._handle_syscall` (`tools/glyph_isa_v2.py:1034`) declares 0x03/0x04 in its docstring but **both branches
are print-only stubs** (`:1072`, `:1080` — `print(... (stub))` then `return 0`), and `0x07`/`0x08`/`0x09` fall through
to `[SYSCALL] UNKNOWN` (`:1107`). Consequences measured this tick:

| command | verdict |
|---|---|
| `/usr/bin/python3 -m pytest tests/test_glyph_file_io.py -q` | **2 failed** — `File not created: …/spatial_test.txt`; `FILE_READ should return -1 for missing file (assert 0 == -1)` |
| `/usr/bin/python3 -m pytest tests/test_glyph_audio_io.py -q` | **1 failed** — `[SYSCALL] UNKNOWN: syscall_num=0x08`, `test_out.wav` never created |
| `/usr/bin/python3 -m pytest tests/test_glyph_orchestrator_speak_to_driver.py -q` | **1 failed** — `[SYSCALL] UNKNOWN: syscall_num=0x09`, then `FILE_WRITE: -1 bytes … (stub)`, then `UNKNOWN: 0x07` |

## Scope

**May change:** `tools/glyph_isa_v2.py` — only the `GlyphCPUv2._handle_syscall` body (and, if genuinely required,
module-level imports inside the new handlers must be **function-local**, not top-level).

**MUST NOT change:** any file under `tests/` (the tests are the gate, not a tuning knob); `src/codec/phy.py`;
`tools/glyph_gpt/**`; `tools/rv64i_to_glyph.py`; `glyph_dispatch/**`; any WGSL shader; `tools/suite_iso_harness.py`;
`systems/GLYPH_SELF_HOSTING_ROADMAP.md`. **No new file** may be added. Do not touch the existing branches
0x01 / 0x02 / 0x05 / 0x06 / 0x10–0xFF and do not change the `_handle_syscall` signature: `(self, syscall_num: int,
image: np.ndarray, imm: int = 0) -> int` is **LOCKED**, as is the calling convention at `tools/glyph_isa_v2.py:861`
(`syscall_num = imm`; the return value is written to `self.registers[rd]`) and the argument convention
r1/r2/r3 = arg1/arg2/arg3. Syscall numbers and argument order are **LOCKED** by the tests.

## Gate clause (what must be written, refused, returned)

Implement real semantics, exactly as the three test files observe them:

1. **`0x03` FILE_WRITE** — r1 = path address (NUL-terminated string in image memory), r2 = data address, r3 = length.
   Read exactly `r3` bytes from image memory at `r2` (`cpu._mem_read(image, addr + i) & 0xFF`) and write them to the
   **host** path named at `r1`. Return `0` on success, `-1` on any `OSError` (a refused write must return, never raise).
2. **`0x04` FILE_READ** — r1 = path address, r2 = destination address, r3 = max length. Read up to `r3` bytes from the
   host path and write them into image memory at `r2`. Return the **actual byte count**; a **missing file must return
   exactly `-1`** (the second file_io leg asserts `cpu.registers[0] == -1`).
3. **`0x08` AUDIO_OUT** — r1 = path, r2 = data address, r3 = length → the `r3` bytes become an MFSK/16-tone wav at
   `r1` (use the repo's own `src.codec.phy.Phy16Tone`: `bytes_to_symbols`/`encode_symbols` or `encode`, written with
   `scipy.io.wavfile.write` at `Phy16Tone.SAMPLE_RATE`, `int16` = `(audio * 32767)`). Return `0`, `-1` on error.
4. **`0x09` AUDIO_IN** — r1 = path, r2 = destination address, r3 = max length → decode the wav at `r1` back to bytes
   (`Phy16Tone.decode` on the int16 samples), truncate to `r3`, write into memory at `r2`, and return the **actual
   decoded byte count**. Missing file → `-1`. **Round-trip requirement:** `AUDIO_OUT` then `AUDIO_IN` on the same
   payload must be byte-exact — the orchestrator leg writes `b"\xDE\xAD\xBE\xEF"` and reads the same 4 bytes back,
   and `test_glyph_orchestrator_speak_to_driver.py` builds its fixture with the same `Phy16Tone` path, so encode and
   decode must be exact inverses at `int16` scale.
5. **`0x07` RUN** — r1 = path of an existing file. Mark it executable (`os.chmod(path, 0o755)`) and execute it with
   `subprocess.run([path], cwd=<its parent dir>, timeout=30, capture_output=True)` — **never `shell=True`**, never a
   string command line. Return the child's exit code; return `-1` if the path does not exist or is not a regular file.
   (This is the value the orchestrator test consumes: it asserts the executed script's marker file exists and that the
   target's mode is `0o755`.)

Every handler must be **non-raising**: wrap host I/O in `try/except OSError` (and `subprocess` failures) and return
`-1`, because a stub that raises would take down the caller’s CPU loop. Keep the existing `print(f"[SYSCALL] …")`
diagnostic style so the transcript stays greppable, and keep the docstring table at `:1039-1044` in sync with the code.

## Gate command

```
/usr/bin/python3 -m pytest tests/test_glyph_file_io.py tests/test_glyph_audio_io.py tests/test_glyph_orchestrator_speak_to_driver.py -q
```
Expected: **`4 passed`**, exit code **0** — and each file green **alone** too:
`tests/test_glyph_file_io.py` 2 passed · `tests/test_glyph_audio_io.py` 1 passed ·
`tests/test_glyph_orchestrator_speak_to_driver.py` 1 passed.

## Failure evidence (required)

The gate must be shown able to fail. RED before this change (orchestrator's run, paste it in your report):
`4 failed in 0.24s` with the three `[SYSCALL] UNKNOWN`/`(stub)` lines. Also show a **non-vacuity probe**: after your
change, temporarily neuter ONE handler (e.g. make `0x09` return `0` without decoding) and show the corresponding leg
goes RED, then restore the file byte-identical (record its md5 before and after) and re-run the gate green.

## Definition of done

Gate command `4 passed / exit 0`; `git status --short` shows **only** `tools/glyph_isa_v2.py` modified (no new files);
the non-vacuity probe pasted RED→restored; the RED-before tail and the GREEN-after tail pasted literally; a statement
of what the PASS does **not** prove. **Do NOT commit** — the orchestrator re-runs the gate, runs the arc, and commits.

## Interfaces are LOCKED

If a locked signature or convention above looks wrong, do **not** change it: file
`.builder_queue/REPAIR_PENDING_suite_fix1_syscall_stubs_<topic>.md` with 2–4 options cheapest-first, state that it is
a skeleton-sign-off change, and report the blocker instead of editing the interface. Never weaken a live guard to make
a step pass — if a test or guard blocks the step, the step is wrong, not the guard.
