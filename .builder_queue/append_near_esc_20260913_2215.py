from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
entry = """

## 2026-09-13 22:0x — SUITE-HEAVY-1 tick (builder cron `af3e62239ce2`)

**Almost asked:** the delegated harness change made a **live gate leg** fail on its *expected value* —
`test_l7_signal_death_is_oom_never_pass_or_fail` asserted `counts.observed_collected == 0` and the real record said
`1` (the SIGKILLed child *did* print its collection before it died). The forbidden-looking move was to "fix" the gate
by editing the expected number, which is the shape of weakening a live guard to reach green; the alternative was to
file a REPAIR_PENDING and hold the row.

**Decided instead:** measured what the guard is *for* before touching the number. L7's invariant is "a kill is
neither pass nor fail" — `passed == 0 and failed == 0` — and that is untouched by this change. The zero it also
pinned was on a field that did not exist before this row: the honest expectation for a child that collects one test
and then dies is `observed_collected == 1`, and `collected == 0` (no junitxml survives a kill). Re-pinned the number
**with the reason in a comment** and left every other part of the assertion (whole-dict equality, OOM verdict,
SIGKILL named, non-zero exit) intact.

**Reason:** "never weaken a live guard" forbids removing or loosening the *assertion of the property*; it does not
require pinning a NEW field to a value measurement contradicts. Distinguishing the two required reading what the leg
asserts, and the difference is exactly this row's subject (separating `collected` from `observed_collected`) — so a
leg that could not tell them apart would have been the vacuous one.

**Outcome:** gate `22 passed / rc 0 / 138.59 s`; RED-first on the pre-change harness (`PROBE_VERDICT=RED`:
vocabulary/validator absent, `counts={'collected':0,'passed':0,'failed':0}`, missing `['observed_collected','skipped']`);
non-vacuity my own run — neutering all 7 `observed_collected` emissions turns L4 RED and the harness is restored
md5-identical `95765cab…`. Tell for next time: **when a new field breaks an old exact-dict assertion, check whether
the pinned VALUE is part of the guard's invariant or merely the only value that existed before — re-pin the value
with the reason, do not loosen the shape.** Second tell, about cost: `git stash pop` in this tree prints ~62 K chars
of untracked-file listing — use `git stash pop -q` and never let a stash round-trip share a command with anything
whose output I need.
"""
path = REPO / "NEAR_ESCALATIONS.md"
with path.open("a") as fh:
    fh.write(entry)
print("appended", len(entry), "chars; file now", path.stat().st_size, "bytes")
