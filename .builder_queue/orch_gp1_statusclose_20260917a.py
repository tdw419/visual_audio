#!/usr/bin/env python3
"""2026-09-17 (cron af3e62239ce2): close the bookkeeping gap left by 26ff048.

The GP-1 receipt (.builder_queue/RECEIPT_GP1_CORPUS_BATCH1.md) claims the
roadmap GP-1 status line was updated with 'batch 1 DONE', but the file is
untouched since b5f8504 (pre-implementation) — so the census kept reading the
raw 'implement via builder cron' cell. Patch exactly that sentence.
"""
path = 'systems/GLYPH_SELF_HOSTING_ROADMAP.md'
s = open(path).read()
old = ("⏳ queued 2026-09-17 — supply filed with Jericho's in-channel authorization "
       "(\"can we get the builder to work on this roadmap?\"); implement via builder "
       "cron af3e62239ce2 from the brief; sequential captures, one bridge call at a "
       "time; guest channel owned by this row for its duration")
new = ("⏳ queued — ✅ batch 1 DONE 2026-09-16 (commit 26ff048, builder cron af3e62239ce2): "
       "5/5 varied-task captures (gzip 715, dir-watch 1236, ls|head 1642/502 unfinished, "
       "rename 784, env 584; batch total 4357 syscalls) pass all 4 schema gates + count "
       "identity + RED-first batch legs (tamper leg shown non-discriminating on count "
       "identity — discrimination lives in the sha verify + round-trip legs; "
       "empty-capture rejection enforced); receipt "
       ".builder_queue/RECEIPT_GP1_CORPUS_BATCH1.md. Remaining supply: batch 2+ "
       "(optional, additive), GP-3 / GP-4 (briefs to follow); no urgency. | row stays "
       "open for batch 2+ intake; guest channel released")
assert s.count(old) == 1, f'anchor count {s.count(old)} != 1'
open(path, 'w').write(s.replace(old, new))
print('patched: GP-1 status cell updated with batch-1 DONE note')
