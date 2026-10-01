# Syscall Corpus Schema (GP-1) — `va-syscall-corpus/1`

Contract for GP-1 captures so corpus lands analysis-ready, not prose.
Destined consumer: GlyphIR differential tests (GH-15 infra) + POSIX-shim
ground truth. Captures are made **inside the guest**, wrapping the target
workload (not hermes itself) in strace.

## Directory layout

```
corpus/<UTC-stamp>_<slug>/
  task.json      # dispatch metadata (schema below)
  trace.log      # raw strace output — GROUND TRUTH, never edited
  trace.json     # converted per this schema
  effects.json   # guest-side artifacts + sha256s (+ optional pixel addr)
```

Naming: `<YYYYMMDDTHHMMSSZ>_<slug>` e.g. `20260917T024500Z_gzip_1mb`.

## Capture recipe (guest-side, hermes task wording)

Task prompt template — the trace target is a plain command, strace wraps IT:

```
Run exactly: strace -f -ttt -T -s 256 -o <DIR>/trace.log <WORKLOAD>
Then: sha256sum <every file created/modified by the workload> > <DIR>/effects.sha256
```

Flags are load-bearing:
- `-f` follow forks (children get their own pid field)
- `-ttt` epoch-microsecond timestamps → `ts_rel_us`
- `-T` per-call duration → `duration_us`
- `-s 256` string args up to 256 bytes (paths, buffers)
- Full syscall set (no `-e` filter) — consumers filter, capture never does.

## task.json

```json
{"schema": "va-syscall-corpus/1",
 "captured_utc": "2026-09-17T02:45:00Z",
 "slug": "gzip_1mb",
 "task_prompt": "<verbatim hermes_run prompt>",
 "dispatch": "guest_bridge.py hermes_run",
 "guest": {"kernel": "6.8.0-136-generic", "strace": "6.8"},
 "hermes_reply": "<verbatim reply>"}
```

## trace.json

```json
{"schema": "va-syscall-corpus/1",
 "source": "trace.log",
 "counts": {"total": 1234, "converted": 1220, "skipped_unfinished": 14},
 "syscalls": [
   {"n": 0, "pid": 1234,
    "ts_rel_us": 512.0, "duration_us": 12.4,
    "name": "openat",
    "args_raw": ["AT_FDCWD", "\"/var/tmp/x\"", "O_WRONLY|O_CREAT", "0644"],
    "path": "/var/tmp/x",
    "ret": 3, "ret_raw": "3", "errno": null}
 ]}
```

Field rules:
- `args_raw`: lossless raw strings exactly as strace decoded them. No
  re-interpretation at capture time — consumers decode (wrong "pretty"
  parsing corrupts ground truth silently).
- `path`: extracted only when a quoted path argument is present; `null`
  otherwise. This is the field shim tests key on.
- `ret`/`errno`: on failure ret=-1 and errno is the bare mnemonic
  (`"ENOENT"`), message text dropped.
- `ts_rel_us`: relative to first converted line, microseconds, float.
- Unfinished/resumed call pairs (strace `<unfinished ...>`): v1 excludes
  both halves and counts them in `skipped_unfinished`. They are signal
  (signal delivery, multithread contention) — do not silently drop counts.
- `errno` is `null` on success; `ret` is the raw integer fd/bytes/code.
- `ret_raw` is the verbatim return token. Hex addresses (`0x7f57…`,
  mmap/brk returns) keep `ret: null` + `ret_raw` set — never truncate
  hex to int (real converter bug caught by the round-trip gate).

## effects.json

```json
{"schema": "va-syscall-corpus/1",
 "effects": [{"path": "/var/tmp/x.gz", "bytes": 1042,
              "sha256": "ab12...", "pixel_addr": "frame 3, (x,y) 12,40"}]}
```

`sha256` computed **guest-side** (authoritative) and re-verified host-side
after pull. `pixel_addr` is optional: when the container is live, map the
file through `tools/pixel_container/locate_in_container.py locate` so each
artifact carries its substrate address — this is what ties the corpus to
the pixel-debug chain.

## Acceptance gate for every capture

1. `trace.json` parses; `counts.converted + skipped_unfinished == counts.total`.
2. Every `effects[].sha256` re-verifies host-side after pull.
3. Round-trip spot check: pick 5 random converted lines, diff against
   trace.log raw — args_raw must be byte-identical substrings.
4. A capture whose workload did not run (empty trace, hermes error) is
   NOT a capture — delete the directory, do not commit.

Converter: `tools/corpus/strace_to_json.py` (stdlib only).
