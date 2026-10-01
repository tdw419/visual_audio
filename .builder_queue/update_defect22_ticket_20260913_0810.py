#!/usr/bin/env python3
"""DEFECT-22 ticket update — builder cron af3e62239ce2, 2026-09-13 08:0x tick.

Adds this tick's INSTRUMENT (the ticket's own next_step made executable) and its ledger.
No claim of a rate, no causality: every entry is a command + its output.
"""
import json

P = ".builder_queue/DEFECT-22_arc_legA_instability.json"
d = json.load(open(P))

d["instrument_defect22_live_capture_2026_09_13_0810"] = (
    "BUILT and committed this tick (the ticket's own next_step, made executable): live SIGSEGV capture "
    "for arc leg A under GDB. Files: tools/gdb_segv_capture.gdb (handle SIGSEGV stop print nopass + a "
    "greppable DEFECT22_CAPTURE: marker block — signal, $pc, $_siginfo si_addr, faulting instruction, "
    "info symbol $pc, thread apply all bt 40, $_exitcode), tools/arc_lega_capture.sh (arc leg A under "
    "gdb, same 52-file selector and ARGS byte-identical mirrors of tools/arc_lega.sh:52-53 / :70-71, "
    "artifacts <OUTDIR>/arc_lega_capture_seed<SEED>_<HEAD>[_rerun<N>].{txt,json,gdb.txt}, exit 139 on a "
    "caught SIGSEGV), tools/gate_arc_lega_capture.sh (legs L1-L5), tests/fixtures/faulthandler_segv_fixture.py. "
    "WHY it beats the core route measured last tick: gdb's `stop` fires BEFORE the in-process handler, so the "
    "siginfo is intact — the recovered 05:18 core could not name the fault address precisely because "
    "faulthandler consumes siginfo when it re-raises. MEASURED discriminator (gate L1 vs L2, same fixture): "
    "live capture -> si_addr=(void *) 0x0, pc=0x7ffff7d8badd, "
    "pc_symbol='__strlen_avx2 + 29 in section .text of /lib/x86_64-linux-gnu/libc.so.6', instruction "
    "'vpcmpeqb (%rdi),%ymm0,%ymm1', exit 139; plain run -> 'Fatal Python error: Segmentation fault' with "
    "0 si_addr and 0 .so attribution. Gate rc=0 (5/5 legs) twice; two independent REDs observed: in-gate "
    "falsifier (stop clause neutralised -> si_addr=pc_symbol=none) and an orchestrator hold-out (instrument "
    "moved aside -> gate rc=2, 'L1 SETUP FAIL: no gdb transcript written'; instrument restored byte-identical "
    "md5 dbe0103e1c897d768ceaa8f9189b2ae3). Acceptance on the REAL 52 files: SEED=1914088745 at 5da0a63 -> "
    "rc=0, 325 passed / 1 skipped / 1 deselected, 123.58 s, segv=no (vs 120.8-121.3 s plain, so ~+3 s "
    "overhead). NOT yet established: the instrument has not caught the real defect (n=1 capture run, 0 "
    "disturbed); 'the next RED will yield si_addr' is proven only against a crash we caused on purpose. "
    "Receipt systems/RECEIPT_DEFECT22_LIVE_CAPTURE.md; gate evidence "
    "output/defect22_live_capture_gate_GREEN.txt + _RED_holdout.txt; run artifacts "
    "output/arc_lega_capture_seed1914088745_5da0a63.{txt,json,gdb.txt}. Warts found in review and stated in "
    "the receipt: the 'was it a signal stop' branch keys on $_thread != 0 (heuristic, both branches "
    "exercised); the sidecar's `crashes` counter sees 0 on a captured SIGSEGV because faulthandler never "
    "runs (capture.segv_caught is authoritative, the counter is not); the gate's L5 checks tracked-modified "
    "== 0 + presence, not a full untracked-file allowlist."
)

d["ledger_2026_09_13_0810"] = (
    "5da0a63: 0 PLAIN arc runs this tick (deliberate — post-194844c 12 runs / 0 disturbed means a 13th "
    "plain green is noise) + 1 CAPTURE-instrument arc run, recorded as its own series, not folded into the "
    "plain ledger: SEED=1914088745 -> rc=0 / 325 passed / 1 skipped / 1 deselected / 123.58 s / segv=no. "
    "Supply re-checked this tick: roadmap census 48 id rows / 0 open (the 7 marker-less rows are the known "
    "GH-18/20/21/22/23/24/25 `✅`-without-literal-'done' false positives); GLYPH_BACKLOG.md table re-read in "
    "full (BK-1..BK-14 + OBS-1, every one already promoted and landed); the two rulings the loop's standing "
    "prompt still listed as 'awaiting implementation' (DEFECT-18 option (a), DEFECT-17 option (d)) were "
    "ALREADY landed — checked, not assumed: 11fe1ac 'feat(defect18): engine snapshots/restores the USER "
    "regfile on tick (ruling option (a))' + 3e2bd8e closure, and 7a4208a 'feat(defect17): loud refusal gate "
    "for RV x31 (t6)' + 696115a closure, with tests/test_defect18_tick_regfile.py and "
    "tests/test_defect17_x31_refusal.py present and RECEIPT_DEFECT18_ENGINE_TICK_REGISTERS.md / "
    "RECEIPT_DEFECT17_X31_REFUSAL.md on disk. So the prompt's 'RULINGS awaiting implementation' list is "
    "STALE, and live supply remains THIS ticket only. The tick therefore went to the ticket's named "
    "next_step instead of inventing scope."
)

d["next_step"] = (
    "ARMED — the live capture instrument now exists (see instrument_defect22_live_capture_2026_09_13_0810), "
    "so the next RED does not need post-mortem archaeology: run `SEED=<seed> bash tools/arc_lega_capture.sh` "
    "(pinned seed is logged either way) and read the sidecar — `capture.segv_caught=true` + non-null "
    "`si_addr`/`pc_symbol`/faulting instruction + exit 139 IS the live evidence the 05:18 core could not "
    "give. Post-mortem core recovery (tools/apport_core_unpack.py) stays as the fallback for crashes that "
    "happen outside the instrument. Unchanged and Jericho's call: renew lane supply, or accept DEFECT-22 as "
    "a documented stability bound and release the level trigger. The gh12 half of this ticket is closed "
    "(RULING_gh12_gate_determinism.md OPTION 3, landed)."
)

json.dump(d, open(P, "w"), indent=2)
print("updated", P, "keys:", len(d))
