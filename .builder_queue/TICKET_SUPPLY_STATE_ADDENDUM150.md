# TICKET SUPPLY STATE — ADDENDUM 150

2026-09-17, builder cron af3e62239ce2.

Supply consumed this tick: **GP-1 batch 2** (the only open roadmap row's
remaining intake; optional/additive per the row text) — 5 new varied-task
captures (denied-access/EACCES, AF_UNIX sockets, mmap RW, tar.gz tree
roundtrip, dd block I/O), 3996 syscalls, all schema gates + tamper/empty
negative legs green, container verify match:true on 4/5 artifacts. Receipt
`.builder_queue/RECEIPT_GP1_CORPUS_BATCH2.md`.

New operational finding recorded: a host-side timed-out `hermes_run` prompt
still completes in the guest later and can overwrite same-named capture
paths — measured as a stale sha *pairing* (pixel chain stayed sound, recon
matched the guest's live bytes). Mitigation: unique paths per attempt;
documented in the batch-2 receipt for batch 3+.

Remaining supply after this tick: GP-1 stays open for batch 3+ intake only
(optional, additive, no urgency). GP-0..GP-4 all landed. Roadmap census
otherwise OPEN=0. SE021 maildrop stays Jericho's.
