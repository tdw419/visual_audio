# HANDOFF — GL-6 demo artifact ready; publication is yours (2026-09-12, cron af3e62239ce2)

**Artifact commit:** `b5aa3f2` in `/home/jericho/zion/worktrees/glyph-isa` → `github.com/tdw419/glyph-isa`
(local, **unpushed**). Four new files, no existing file modified:

- `tools/record_cast.py` — stdlib-only pty recorder → asciinema v2 `.cast`
- `docs/demo/gl6_bake_and_run.cast` — the recorded demo (16 events, payload 606 B,
  `payload_sha256 18688ea8abc11bc4620691e8d084f592fc557ea7bbfdb34ff1e0d0f947b1ed16`)
- `tests/test_gl6_demo_cast.py` — the gate (4/4, junit 0 failures)
- `docs/DEMO.md` — regenerate/view instructions

Receipt: `systems/RECEIPT_GL6_DEMO_CAST.md` (builder repo).

## What only you can do (fenced to you by the lane ruling)

1. **Push** the glyph-isa commit (this also puts the new gate into GL-4's GitHub Actions matrix for the
   first time — it has not run in CI yet).
2. **Produce the shareable link**, which is GL-6's actual oracle:
   `asciinema upload docs/demo/gl6_bake_and_run.cast` (or host a page) → the URL.
3. **Flip the OSS row** `systems/GLYPH_OSS_ROADMAP.md:41` from `QUEUED` to `✅` once that URL exists, and
   optionally add one README line pointing at `docs/DEMO.md` (README was deliberately left untouched by the
   loop to avoid colliding with the OSS lane).

```diff
-| GL-6 | ... | A shareable URL or asciinema link that plays back the demo end to end | QUEUED |
+| GL-6 | ... | A shareable URL or asciinema link that plays back the demo end to end | ✅ DONE 2026-09-?? — <URL>, cast committed `b5aa3f2` |
```

## Verify it yourself in ~30 s

```bash
cd /home/jericho/zion/worktrees/glyph-isa
/usr/bin/python3 -m pytest tests/test_gl6_demo_cast.py -q     # 4 passed
python3 tools/record_cast.py --out /tmp/re.cast                # prints payload_sha256 + exit_code=0
```

## Honest limits

- `asciinema` was **not** used to record (absent on this host; `pip install --user` refused by PEP 668).
  The cast is the v2 format written by the committed recorder — asciinema.org accepts it as an upload, but
  playback in the real `asciinema` binary is unverified.
- The cast is bound to this tree: regenerating at a different commit changes the payload and L3 fails by
  design. Re-record when the demo's output changes (`DEMO_SESSION` in `tools/record_cast.py` is the demo's
  single definition).
