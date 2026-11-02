# Hackathon lane supply (Meta Global AI Developer Hackathon, Oct 26 - Nov 4)

Scoped subtree for the `hackathon` factory lane (see HACKATHON_BUILD_PLAN.md).
digest.watch_paths = ["hackathon"] — only commits touching this subtree wake the lane.

- tickets/    — h1..h10 drafts; Day 0: copy into .factory/tickets/ and `factory ticket add` as DRAFT
- tests/      — lane verify (pytest, /usr/bin/python3.12, no GPU, <60s)
- demo/freeze — frozen demo path: BOOT_SMOKE.sh + receipts; kernel_paths-guarded after h6

Companion docs (repo root): HACKATHON_META_APPLICATION.md (approved), HACKATHON_BUILD_PLAN.md,
HACKATHON_DEMO_PREVERIFY_2026-10-20.md.
