import json

# QUEUE_STATE.json: item-20 queued -> landed
p = '.builder_queue/QUEUE_STATE.json'
d = json.load(open(p))
for q in d['queue']:
    if q['id'] == 'item-20':
        q['status'] = 'landed'
d['updated'] = '2026-09-25T20:45:00-05:00'
d['updated_by'] = 'builder af3e62239ce2 (item-20 shell-native swap landed)'
json.dump(d, open(p, 'w'), indent=2)
print('QUEUE_STATE: item-20 landed')

# CURRENT_TICKET.json
t = {
 "ticket": "item-20",
 "title": "Shell-native swap (Phase 2 to Phase 3 gradient)",
 "status": "landed",
 "blocker": None,
 "defect_status": None,
 "worktree": None,
 "attempt": 1,
 "gate": "tests/test_item20_shell_native_swap.py (9 legs)",
 "last_gate_result": "GREEN: 9 passed in 11.25s, exit 0. RED legs: stash-of-shell-change -> 3 failed/6 passed (L2 tr parity, L5b loud-refusal marker, L6 untouched verbs); in-gate L4b flips _SHELL_NATIVE proving distinct executors.",
 "untrusted_probes": [],
 "notes": [
  "grep+tr route through transpiled glyph binaries (rv32i -> _load_posix_program -> GlyphRunner), session bytes as generated C literal in seed .data",
  "Loud refusal: ERR:SHELLNATIVE:<verb> on missing toolchain/fault; ERR:NOENT before compile",
  "wc/head NOT swapped (17+/24B report shapes exceed 16-byte window) - disclosed",
  "tr added to L1_VERBS (which-table inconsistency fixed)",
  "Pipe producers stay host-side: BK-24 ring has NO saturation (faults at 25+ lines, measured) - open engine work, not this scope",
  "NOT proven: no WGSL twin leg; per-turn recompile ~1.7-4.65s (caching later); no in-guest exec; R1.4 convergence open",
  "Receipt: .builder_queue/RECEIPT_item20_shell_native_swap.md",
  "Cross-session note: work landed in tree 20:0x tick, commit deferred by timeout; this tick re-gated (GREEN 9 passed) + fresh RED (stash 3F/6P) before landing"
 ],
 "next_step": "Next claim by claim_order among unblocked: item-21; item-22b; item-25 reserved (operator sign-off)",
 "updated": "2026-09-25T20:45:00-05:00",
 "updated_by": "builder af3e62239ce2 (item-20 landing tick)"
}
json.dump(t, open('.builder_queue/CURRENT_TICKET.json', 'w'), indent=2)
print('CURRENT_TICKET: item-20 landed')
