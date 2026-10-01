#!/usr/bin/env python3
"""Gate for RULING_monitor_age_cadence (bdc084b), implemented 2026-09-14.

Channel-isolated legs against the live monitor fingerprint
(~/.hermes/scripts/glyph_build_chain_monitor.py):

  test_l1_mtime_not_in_fingerprint  touch-only change on a tracked ticket
                                    -> digest UNCHANGED
  test_l2_volatile_value_ignored    rewriting ONLY the clock-ish 'updated'
                                    value in an UNTRACKED scratch ticket
                                    -> digest UNCHANGED
  test_l3_status_edge_moves_digest  OPEN -> CLOSED on the scratch ticket
                                    -> digest CHANGES; removing the file
                                       restores the baseline

Raw-bytes discipline: every restore writes back the exact original bytes and
mtime (json round-tripping reformats the file and trips the tracked-dirty
channel, which is a different signal — first draft failed for exactly this).

Collection safety (2026-09-14): this file originally ran everything at module
level and raised SystemExit — pytest collection died with INTERNALERROR when
the sweep harness picked it up. All legs are real tests now; the standalone
entrypoint is a shim over pytest.
"""
import hashlib
import json
import os
import re
import subprocess

import pytest

REPO = "/home/jericho/projects/zion/projects/visual_audio"
MON = os.path.expanduser("~/.hermes/scripts/glyph_build_chain_monitor.py")
QDIR = os.path.join(REPO, ".builder_queue")
SCRATCH = os.path.join(QDIR, "ZZZ_gate_scratch_ticket.json")
TRACKED = os.path.join(QDIR, "DEFECT-22_arc_legA_instability.json")


def _fp():
    r = subprocess.run(["/usr/bin/python3", MON], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return hashlib.sha256(r.stdout.encode()).hexdigest()


@pytest.fixture(scope="module")
def baseline():
    return _fp()


@pytest.fixture
def tracked_mtime():
    """L1 helper: restore the tracked ticket's exact mtime afterwards."""
    st = os.stat(TRACKED)
    yield TRACKED
    os.utime(TRACKED, (st.st_atime, st.st_mtime))


@pytest.fixture
def scratch_ticket():
    """L2/L3 helper: untracked scratch ticket, always removed afterwards."""
    def _write(body: bytes):
        with open(SCRATCH, "wb") as f:
            f.write(body)
    yield _write
    if os.path.exists(SCRATCH):
        os.remove(SCRATCH)


def test_l1_mtime_not_in_fingerprint(baseline, tracked_mtime):
    h0 = baseline
    os.utime(TRACKED, (1, 1))  # epoch mtime: the extreme clock-state change
    assert _fp() == h0, "mtime-only change moved the digest — clock state leaked in"
    os.utime(TRACKED)  # back to now, bytes untouched throughout
    assert _fp() == h0, "digest did not return to baseline after mtime restore"


def test_l2_volatile_value_ignored(baseline, scratch_ticket):
    body_open = json.dumps({"id": "ZZZ-GATE", "status": "OPEN - gate probe",
                            "updated": "2000-01-01 00:00:00"}).encode()
    scratch_ticket(body_open)
    h2 = _fp()
    body_upd = body_open.replace(b"2000-01-01 00:00:00", b"2099-12-31 23:59:59")
    scratch_ticket(body_upd)
    assert _fp() == h2, "volatile 'updated' rewrite moved the digest"


def test_l3_status_edge_moves_digest(baseline, scratch_ticket):
    body_open = json.dumps({"id": "ZZZ-GATE", "status": "OPEN - gate probe",
                            "updated": "2000-01-01 00:00:00"}).encode()
    scratch_ticket(body_open)
    h_open = _fp()
    body_closed = body_open.replace(b"OPEN - gate probe",
                                    b"CLOSED 2026-09-14 gate probe done")
    scratch_ticket(body_closed)
    h_closed = _fp()
    assert h_closed != h_open, "OPEN->CLOSED did not move the digest"
    os.remove(SCRATCH)
    assert _fp() == baseline, "scratch removal did not restore the baseline digest"


def test_l5_statusless_data_artifact_not_a_ticket(baseline):
    """2026-09-21 incident (cron af3e62239ce2, HEAD 867e62f0):

    .builder_queue/floors.json is a tracked DATA artifact — GPU timing floors
    written by the R0 calibration lane (calibrate_floors.py:41, Jericho's
    2026-09-21 directive) and committed — with no 'status' field by design.
    The queue scan counted every status-less *.json as an OPEN ticket forever
    -> state=REPAIR_PENDING queue=1 phantom wake on a CLEAN tree. Same family
    as the 2026-09-14 'counting all *.json' fix (monitor :159) and
    foreign-lane dirt (REPAIR_PENDING_monitor_stall_signal_foreign_lanes.md):
    a repo-state channel ingesting non-ticket signal.

    Discriminating legs (untracked scratch files; tree-safe, unlike a
    rename — floors.json is TRACKED, so renaming it feeds the dirty channel
    and any digest delta is uninterpretable):
      a) a status-less scratch json (data-artifact shape) does NOT move the
         digest — before the fix it did (RED, live instrument);
      b) the SAME body plus '"status": "OPEN"' DOES move the digest — the
         queue channel is still live, so (a) cannot pass vacuously.
    """
    scratch = os.path.join(QDIR, "ZZZ_gate_scratch_data.json")
    body_nostatus = json.dumps({
        "floor_us": {"step": 243.4, "get_state": 26.4},
        "reps": 30,
        "measured_at": "2000-01-01T00:00:00+00:00",
    }).encode()
    body_open = json.dumps({
        "id": "ZZZ-GATE-DATA", "status": "OPEN - gate probe",
        "measured_at": "2000-01-01T00:00:00+00:00",
    }).encode()
    try:
        with open(scratch, "wb") as f:
            f.write(body_nostatus)
        h_nostatus = _fp()
        assert h_nostatus == baseline, (
            "status-less data artifact moved the fingerprint — the queue "
            "channel is still counting non-ticket *.json"
        )
        with open(scratch, "wb") as f:
            f.write(body_open)
        h_open = _fp()
        assert h_open != h_nostatus, (
            "an OPEN ticket did not move the digest — the queue channel is "
            "dead, so the status-less leg above proves nothing"
        )
    finally:
        if os.path.exists(scratch):
            os.remove(scratch)
    assert _fp() == baseline, "scratch removal did not restore the baseline digest"


def test_l4_runtime_churn_cannot_defeat_stall_breaker():
    """2026-09-19 incident (REPAIR_PENDING_monitor_newest_mtime_epoch.md):

    Live-guest runtime state (.hermes_guest_context/guest_state.json heartbeat,
    ubuntu_desktop_pxc1_v3_selfhost/ pixel journal + PNG writeback) is TRACKED
    and rewritten every ~2min by daemons. The freshness pool (max tracked-dirty
    mtime) could therefore never go stale -> FROZEN_STALLED was unreachable ->
    9h silent idle after the last brief was consumed, with stall_tier=0 the
    whole time. Fix under test: runtime paths are excluded from the dirty
    channel in tools/glyph_build_chain_monitor.py (live monitor is a shim).

    Legs (self-contained digests; no module-baseline dependency):
      a) touching a runtime file's mtime does NOT move the fingerprint;
      b) while runtime files ARE dirty, the monitor's dirty count is strictly
         smaller than the raw tracked-dirty count (exclusion is live);
      c) the exclusion table exists in the versioned twin (pin).
    """
    # (c) source pin — versioned twin must carry the exclusion tables.
    twin = os.path.join(REPO, "tools", "glyph_build_chain_monitor.py")
    src = open(twin, encoding="utf-8").read()
    assert "RUNTIME_EXEMPT_DIRS" in src, "twin lost the runtime exclusion table"
    assert ".hermes_guest_context/" in src and "ubuntu_desktop_pxc1_v3_selfhost/" in src

    runtime = os.path.join(REPO, ".hermes_guest_context", "guest_state.json")
    if os.path.exists(runtime):
        st = os.stat(runtime)
        try:
            h1 = _fp()
            os.utime(runtime, (1, 1))  # extreme clock-state change on a runtime file
            h2 = _fp()
            assert h2 == h1, (
                "runtime-file mtime moved the fingerprint — daemon churn still "
                "feeds the dirty channel; the stall breaker is dead again"
            )
        finally:
            os.utime(runtime, (st.st_atime, st.st_mtime))

    # (b) exclusion is live on the current tree, whenever a runtime file is
    # actually dirty (on a fully clean tree this leg is vacuously true).
    raw = subprocess.run(
        ["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    raw_dirty = [ln for ln in raw.splitlines() if not ln.startswith("??")]
    runtime_dirty = [ln for ln in raw_dirty
                     if any(ln[3:].strip().startswith(p) or ln[3:].strip() == ".pxc1_delta.jnl"
                            for p in (".hermes_guest_context/",
                                      "ubuntu_desktop_pxc1_v3_selfhost/"))]
    r = subprocess.run(["/usr/bin/python3", MON], capture_output=True, text=True, timeout=60)
    m = re.search(r"tracked_dirty=(\d+)", r.stdout)
    assert m, "monitor output missing tracked_dirty: %r" % r.stdout
    if runtime_dirty:
        assert int(m.group(1)) < len(raw_dirty), (
            "runtime files are dirty but NOT excluded from tracked_dirty (%d vs %d)"
            % (int(m.group(1)), len(raw_dirty))
        )


def test_l6_tracked_churn_files_excluded_from_dirty_channel():
    """2026-09-22 phantom-stall fix (af3e62239ce2):

    .update_proposals.log is .gitignore'd but still TRACKED (added before the
    ignore rule), and the live runtime appends llama3.1 proposal pings to it
    every ~5min. Its tracked-dirty mtime kept the monitor's freshness pool
    warm while the lane was idle -> FROZEN_STALLED was unreachable and a
    spurious T1/T2/T3 escalation (auto-stash circuit breaker) was armed on a
    cleanly-idling tree. Same class: .venv/bin/{normalizer,numba} carry
    shebang-flip churn from env-repair reinstalls (python3.11<->python3).

    Legs:
      a) source pin: the twin's RUNTIME_EXEMPT_FILES carries all three paths;
      b) with ONLY these files dirty (they are, on the idle tree), the live
         monitor reports tracked_dirty < raw tracked-dirty count — exclusion
         is live, and the fingerprint's dirty channel ignores them;
      c) DISCRIMINATING (RED-first proven 2026-09-22): reverting the twin's
         exemption table makes the same tree report the higher raw count
         (verified manually pre-fix: tracked_dirty=3 with the log+venv files
         dirty, monitor state frozen on their stale mtimes).
    """
    twin = os.path.join(REPO, "tools", "glyph_build_chain_monitor.py")
    src = open(twin, encoding="utf-8").read()

    # (a) source pin
    for path in (".update_proposals.log", ".venv/bin/normalizer", ".venv/bin/numba"):
        assert path in src, f"twin lost the churn-file exemption: {path}"

    # (b) exclusion is live on the current tree
    raw = subprocess.run(
        ["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    raw_dirty = [ln for ln in raw.splitlines() if not ln.startswith("??")]
    churn_dirty = [
        ln for ln in raw_dirty
        if ln[3:].strip() in (".update_proposals.log",
                              ".venv/bin/normalizer", ".venv/bin/numba")
    ]
    r = subprocess.run(["/usr/bin/python3", MON], capture_output=True, text=True, timeout=60)
    m = re.search(r"tracked_dirty=(\d+)", r.stdout)
    assert m, "monitor output missing tracked_dirty: %r" % r.stdout
    if churn_dirty and len(churn_dirty) == len(raw_dirty):
        # tree is dirty ONLY with churn files -> they must all be excluded
        assert int(m.group(1)) == 0, (
            "churn-only dirty tree reports tracked_dirty=%s — the exemption "
            "is not live; phantom-stall armament returns" % m.group(1)
        )
    elif churn_dirty:
        assert int(m.group(1)) < len(raw_dirty), (
            "churn files dirty but not excluded (%d vs %d)"
            % (int(m.group(1)), len(raw_dirty))
        )
    # (c) discrimination is demonstrated by the pre-fix probe on record in
    # PRODUCT_LANE_STATE.md (tracked_dirty=3 pre-fix vs 0 post-fix on the
    # identical tree); a revert-and-RED leg here is deliberately not executed
    # in-suite to avoid mutating the live instrument mid-run.


def test_l7_build_map_selfreference_churn_excluded():
    """2026-09-28 incident (cron af3e62239ce2, HEAD 7ed485e9, measured):

    build_map_data.json embeds the last-400-commit window, frontier_commit
    and generated_at (tools/spatial_build_map.py render()), and the BM000
    watchdog regenerates it every ~5min (glyph_builder_watchdog.py step 7).
    EVERY commit therefore makes the committed copy stale, and the next
    regen re-dirties the tree — measured: the map catch-up commit landed at
    19:32:40Z and the tree was DIRTY again at 19:32:51Z (11s later, window
    shifted by the commit itself). The committed copy can never converge; a
    fixpoint does not exist. Consequence: permanent DIRTY_ACTIVE on an
    otherwise-clean tree + a permanently warm freshness pool, so the stall
    breaker (FROZEN_STALLED, MAX_TIER=3 auto-stash) was unreachable — the
    exact phantom-freshness class exempted in 2026-09-22 (test_l6).

    Legs:
      a) source pin: the twin's RUNTIME_EXEMPT_FILES carries both map paths;
      b) LIVE instrument: with the map files dirty on the real tree (they
         are, whenever the watchdog has regenerated since the last commit),
         the live monitor must NOT count them in tracked_dirty;
      c) DISCRIMINATING (proven RED pre-fix): before the exemption the same
         tree reported tracked_dirty=1 state=DIRTY_ACTIVE with ONLY the map
         dirty (live probe on record in this incident's transcript,
         2026-09-28 ~14:33 CDT); reverting the exemption table reproduces
         that count, so (b) cannot pass vacuously.
    """
    twin = os.path.join(REPO, "tools", "glyph_build_chain_monitor.py")
    src = open(twin, encoding="utf-8").read()

    # (a) source pin
    for path in ("build_map_data.json", "build_map.png"):
        assert path in src, f"twin lost the build-map churn exemption: {path}"

    # (b) exclusion is live on the current tree, whenever the map is dirty
    raw = subprocess.run(
        ["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    raw_dirty = [ln for ln in raw.splitlines() if not ln.startswith("??")]
    map_dirty = [
        ln for ln in raw_dirty
        if ln[3:].strip() in ("build_map_data.json", "build_map.png")
    ]
    r = subprocess.run(["/usr/bin/python3", MON], capture_output=True, text=True, timeout=60)
    m = re.search(r"tracked_dirty=(\d+)", r.stdout)
    assert m, "monitor output missing tracked_dirty: %r" % r.stdout
    # 2026-09-30 scope amendment (worktree-blindness fix): tracked_dirty now
    # ALSO counts unlanded worktree dirt (wt: tokens), by design. The
    # exclusion claim this leg guards is scoped to the MAINLINE dirty pool —
    # compare mainline-only dirty (raw minus map churn) against
    # tracked_dirty minus the wt: FILE counts (token 'tag:4d' = 4 files,
    # not 1 — parse the digits, not the token count).
    wt_tokens = re.search(r" wt=(\S+)", r.stdout)
    wt_count = 0
    if wt_tokens:
        for tok in wt_tokens.group(1).split(","):
            tm = re.match(r"^[^:]+:(\d+)d$", tok)
            if tm:
                wt_count += int(tm.group(1))
    mainline_reported = int(m.group(1)) - wt_count
    if map_dirty and len(map_dirty) == len(raw_dirty):
        # tree is dirty ONLY with map churn -> all of it must be excluded
        assert mainline_reported == 0, (
            "map-only dirty tree reports tracked_dirty=%s — the self-reference "
            "exemption is not live; permanent-DIRTY_ACTIVE churn returns"
            % m.group(1)
        )
    elif map_dirty:
        # Exclusion identity (2026-09-30 tightening): the mainline-reported
        # count must equal raw mainline dirt minus exactly the map-churn
        # files — no more exemption drift possible in either direction.
        # (The old strict `<` held only when every non-map dirty file was
        # itself reported; the identity is the real invariant.)
        assert mainline_reported == len(raw_dirty) - len(map_dirty), (
            "map exclusion drifted: mainline_reported=%d, raw=%d, map=%d"
            % (mainline_reported, len(raw_dirty), len(map_dirty))
        )
    # (c) pre-fix RED on record: the identical tree read tracked_dirty=1
    # state=DIRTY_ACTIVE with only build_map_data.json modified (live probe,
    # 2026-09-28 14:33 CDT, pre-patch). No in-suite revert: the live
    # instrument must not be mutated mid-run (same reasoning as test_l6c).


def test_l8_nested_probe_leg_status_is_data_not_ticket(baseline):
    """2026-09-28 incident (cron af3e62239ce2, named in CURRENT_TICKET.json
    REPAIR_bk54_results_file_counts_as_ticket):

    .builder_queue/probe_bk54_blast_radius_af3e.results.json is UNTRACKED
    research DATA (a sibling session's BK-54 blast-radius probe, results md5
    5dcaf51b17d3495e4b4eeef39d04231a). Its probe LEGS carry nested
    '"status": "OK"' fields — and _ticket_status() regex-matched the FIRST
    '"status"' anywhere in the file, so the DATA file counted as an open
    ticket -> permanent REPAIR_PENDING queue=1 on a CLEAN tree (the monitor's
    own 2026-09-21 status-less fix at :195 can't catch it: this file HAS a
    status field, just not at ticket level).

    Fix under test: _ticket_status() honors only the TOP-LEVEL 'status' of a
    parsed-JSON ticket. Nested leg statuses are DATA, not ticket state.

    Discriminating legs (untracked scratch files, tree-safe):
      a) a probe-results-SHAPED json (statuses only NESTED, none top-level)
         does NOT move the digest — before the fix it did (RED, live
         instrument, shown at landing time);
      b) the same body PLUS a top-level '"status": "OPEN"' DOES move the
         digest — the queue channel is still live, so (a) cannot pass
         vacuously;
      c) scratch removal restores the baseline digest.
    """
    scratch = os.path.join(QDIR, "ZZZ_gate_scratch_probe_results.json")
    body_probe = json.dumps({
        "D1_overflow_401B": {"status": "OK", "delta_words": 401},
        "D2_overflow_4001B": {"status": "OK", "delta_words": 4001},
        "S1_static_map": {"known_words": {
            "status": {"value": 123, "word": 950}, "word": 950}},
    }).encode()
    body_open = json.dumps({
        "id": "ZZZ-GATE-PROBE", "status": "OPEN - gate probe",
    }).encode()
    try:
        with open(scratch, "wb") as f:
            f.write(body_probe)
        h_probe = _fp()
        assert h_probe == baseline, (
            "probe-results-shaped DATA (nested statuses only) moved the "
            "fingerprint — the queue scan still counts nested leg statuses "
            "as an open ticket: phantom REPAIR_PENDING returns"
        )
        with open(scratch, "wb") as f:
            f.write(body_open)
        h_open = _fp()
        assert h_open != h_probe, (
            "an OPEN ticket did not move the digest — the queue channel is "
            "dead, so the nested-status leg above proves nothing"
        )
    finally:
        if os.path.exists(scratch):
            os.remove(scratch)
    assert _fp() == baseline, "scratch removal did not restore the baseline digest"


def test_l9_stale_ledger_next_line_is_not_claim_supply():
    """2026-09-28 incident (cron af3e62239ce2, named in CURRENT_TICKET.json
    REPAIR_stale_NEXT_line_triggers_claim_pending):

    The ledger fallback (monitor :350-353, the 2026-09-24 split-brain fix)
    regex-matched the FIRST '^NEXT:' ANYWHERE in
    HEAD:.builder_queue/PRODUCT_LANE_STATE.md — no recency anchor. A stale
    2026-09-25 NEXT line (ledger :3913, 'round-9+ supply items 18-23') kept
    driving state=CLAIM_PENDING on a queue-empty tree (QUEUE_STATE.json: 25
    landed, 0 queued) long after every item it named was landed. Same
    phantom class as the two fixed the same day (build-map self-reference
    churn; nested probe-leg statuses): a supply channel ingesting stale /
    non-ticket signal. RED shown at landing time against the LIVE
    instrument: `git stash` of the fix -> 'state=CLAIM_PENDING queue=0
    supply=claim: (round-9+ supply items 18-23 from the seat lane';
    `stash pop` -> phantom gone (measured 2026-09-28 ~15:2x CDT).

    Fix under test: the NEXT scan is anchored to the MOST RECENT ledger
    entry (the first '### ' block); NEXT lines are per-entry state, so a
    NEXT in any older entry must never feed supply.

    Legs:
      a) source pin: the twin anchors the fallback scan to the newest
         entry boundary (_ledger.find("### ", 5));
      b) LIVE instrument: the stale 'round-9+' text never appears as the
         supply note (the phantom's literal fingerprint);
      c) mechanism, deterministic against HEAD's ledger at run time: with
         the OLD whole-file regex, if the first NEXT match sits OUTSIDE
         the newest entry (the observed defect shape), the NEW
         newest-entry-scoped scan must return no match — the fix changes
         the outcome for exactly the shape that fired the phantom.
    """
    twin = os.path.join(REPO, "tools", "glyph_build_chain_monitor.py")
    src = open(twin, encoding="utf-8").read()

    # (a) source pin: newest-entry anchor in the fallback branch
    assert '_ledger.find("### ", 5)' in src, (
        "twin lost the newest-entry anchor — the NEXT scan is back to "
        "whole-file-first-match and the stale-NEXT phantom returns"
    )

    # (b) live instrument: stale NEXT text must not be the supply note
    r = subprocess.run(
        ["/usr/bin/python3", MON], capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0, r.stderr
    assert "supply=claim: (round-9+" not in r.stdout, (
        "the stale 2026-09-25 NEXT line is still driving CLAIM_PENDING — "
        "the newest-entry anchor is not live on the instrument"
    )

    # (c) mechanism: old whole-file scan vs new newest-entry scope on the
    # same HEAD ledger. Conditional on the defect shape being present so
    # the leg stays valid once a future entry legitimately carries NEXT.
    ledger = subprocess.run(
        ["git", "-C", REPO, "show",
         "HEAD:.builder_queue/PRODUCT_LANE_STATE.md"],
        capture_output=True, text=True,
    ).stdout
    old = re.search(r"^NEXT: \*\*(.+?)\*\*", ledger, re.S | re.M)
    newest_end = ledger.find("### ", 5)
    if old and newest_end > 0 and old.start() > newest_end:
        scope = ledger[:newest_end]
        new = re.search(r"^NEXT: \*\*(.+?)\*\*", scope, re.S | re.M)
        assert new is None, (
            "defect shape present (whole-file first match in a STALE entry) "
            "but the newest-entry scope ALSO matches — the fix does not "
            "change the outcome, so leg (b) proves nothing"
        )


if __name__ == "__main__":  # standalone: same legs via pytest, exit code preserved
    raise SystemExit(pytest.main([__file__, "-q"]))
