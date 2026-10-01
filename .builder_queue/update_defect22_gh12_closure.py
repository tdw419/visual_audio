import json, pathlib

p = pathlib.Path("/home/jericho/projects/zion/projects/visual_audio/.builder_queue/DEFECT-22_arc_legA_instability.json")
d = json.loads(p.read_text())
d["gh12_component_2026_09_13_0700"] = (
    "CLOSED (gh12 leg only). Ruling `.builder_queue/RULING_gh12_gate_determinism.md` OPTION 3 implemented this "
    "tick by cron af3e62239ce2 from `.builder_queue/brief_gh12_option3_split.md`: the gh12 arc leg is split into "
    "model-free deterministic legs (scripted candidate -> real admission/oracle/kernel -> byte-identical offline "
    "replay) + a non-blocking `@pytest.mark.live_smoke` smoke, with `tools/arc_lega.sh` ARGS gaining "
    "`-m \"not live_smoke\"`. Orchestrator-measured at head d64f509: RED before `output/gh12_prefix_red_d64f509.txt` "
    "(1 failed, 3 passed, :141 'no candidate verified in 6 attempts; last: no-halt: 5000 steps without HALT', "
    "36.76s) -> GREEN after `output/gh12_gate_postfix_full.txt` (6 passed, 11.33s) and "
    "`output/gh12_gate_postfix_arcargs.txt` (5 passed, 1 deselected, 1.11s); model-dead probe "
    "`output/gh12_orch_probe_model_dead.txt` 5 passed (no reachable model anywhere, all escalate identities at "
    "port 9); non-vacuity probe `output/gh12_orch_probe_candidate_mutated.txt` 2 failed (corrupted scripted "
    "candidate goes RED). Arc leg A at d64f509 with the change: rc=0, 325 passed / 1 skipped / 1 deselected, "
    "123.89s, seed 2671119501 (`output/arc_lega_seed2671119501_d64f509.txt`). Receipt "
    "`systems/RECEIPT_GH12_GATE_DETERMINISM.md`. MODEL-TAG NOTE (measured 2026-09-13 07:0x): `ollama list` shows "
    "qwen2.5-coder:14b IS resident (the tag escalate.py:32 requests), so the live leg's red is NOT a missing tag "
    "- the same head produced a GREEN smoke in the same tick (`output/gh12_live_smoke_d64f509.txt`: model "
    "qwen2.5-coder:14b, candidates_tried 2, rc 0, 10.21s) while the pre-fix gate run went RED with 6 failed "
    "attempts. That is the intermittent sampling red this leg no longer gates on. STILL OPEN for this ticket: the "
    "SIGSEGV inside GlyphCPUv2.step (tools/glyph_isa_v2.py:561, victim frame in "
    "tests/test_gh22_device_driver_abi.py:174); it did not reproduce in this tick's arc run (crashes=0)."
)
d["next_step"] = (
    "gh12 leg is closed (see gh12_component_2026_09_13_0700). Remaining work is the segfault leg only: reproduce "
    "under the arc's random-order context with the per-run record files now in place "
    "(`output/arc_lega_seed*_<head>.txt`), and treat `x % INSTR_WIDTH` in the victim frame as a symptom, not the "
    "cause."
)
p.write_text(json.dumps(d, indent=1) + "\n")
print("keys:", len(d))
print("gh12 key present:", "gh12_component_2026_09_13_0700" in d)
