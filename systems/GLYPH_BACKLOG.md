# Glyph OS Backlog — gated candidate items

NOT claimable by the builder loop. An item enters `GLYPH_SELF_HOSTING_ROADMAP.md`
(and only then becomes work) when ALL of:
1. its prerequisites are committed green,
2. the auditor has reviewed the spec (no mechanism-shortcut test clauses),
3. Jericho approves (or standing rule below is enabled),
4. the roadmap has fewer than 3 unclaimed items (bounded queue — no speculative pile-up).

Format mirrors the roadmap table so promotion is a copy-plus-status-cell.

| ID | Item | Gate spec | Prereq | Source |
|---|---|---|---|---|
| BK-1 | argv/env block: loader (GH-9) passes argc/argv/envp in the box data page; C `main(argc, argv)` transpiles and reads them | `tests/test_bk1_argv.py` — injected C prog prints argv[1]; byte-exact vs native run | GH-9 | Linux-likeness gap; GH-9 spec says "argv block" but has no gate clause — split out so GH-9 stays minimal |
| BK-2 | WGSL parity per syscall: every new SYS N (6/7/8, loader) runs byte-identical on GlyphCPUv2 ≡ WGSL | extend `tests/test_gh4_wgsl_parity.py` pattern — one parity leg per syscall, same receipt | GH-8b | GH-4 proved the method; new syscalls landed CPU-only. Keeps the GPU leg honest instead of drifting |
| BK-3 | Signals lite: kernel-delivered SIG_KILL/SIG_USR1 to a box via mailbox word; handler registration syscall | `tests/test_bk3_signals.py` — task A signals B mid-round-robin; B's handler runs; SIG_KILL halts B, A unaffected; box bounds still enforced | GH-9 | Process management needs termination + notification; GH-7 has spawn/round-robin but no kill path |
| BK-4 | waitpid/join: parent task blocks on child exit code via kernel syscall | `tests/test_bk4_join.py` — parent spawns, child exits 42, parent reads 42; join on already-dead child returns immediately | GH-9, BK-3 | Completes the process lifecycle; needed before GH-13 agents can mean "wait for worker" |
| BK-5 | Performance pass vs AGENTS.md baselines: decode ≤8ms/audio-sec, spatial routines benchmarked, WGSL fastpath on the FS path | benchmark receipt committed to `docs/` with measured numbers vs baseline table; no functional change | GH-10 | AGENTS.md performance table; the loop optimizes nothing today — needs an explicit measured-target item |
| BK-6 | Boot self-check: image carries a hash-of-code-region word baked at build; kernel verifies before dispatch (detects pixel corruption) | `tests/test_bk6_integrity.py` — flipping one code pixel → kernel faults with INTEGRITY_FAIL instead of executing garbage | GH-8b | Natural for a visual medium (pixels corrupt silently); pairs with the corruption probe methodology |
| BK-7 | FS grow: SYS append + file resize with FSTAB compaction (moves blocks, updates start/len) | `tests/test_bk7_fs_grow.py` — write, append 2×, read back whole; delete creates hole, new create reuses it | GH-8b | Fixed-size files are the FS's biggest gap once GH-10 shell does `cp` |
| BK-8 | glyphs_dispatch lane sync: GH-8b pixel-resident FS evaluated as SHA-256 working-set storage (replaces host-side buffers in the lockstep harness) | spec review + measured before/after on the 13/13 gate | GH-8b, BK-2 | Cross-lane reuse — the other session's SHA-256 work wants exactly in-image storage |

## Standing promotion rule (disabled until Jericho enables)

When the roadmap has <3 unclaimed ⏳ items, promote the highest-priority backlog
item whose prereqs are green — automatically, with the auditor's spec-review as
the gate — and log the promotion in the roadmap's status column footer. Manual
`status` audits catch drift. Any item needing design judgment (not mechanical
spec) is exempt from auto-promotion and waits for Jericho.
