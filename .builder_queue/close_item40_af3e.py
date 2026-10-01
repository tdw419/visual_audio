import json

p = '.builder_queue/QUEUE_STATE.json'
q = json.load(open(p))
for it in q['queue']:
    if it['id'] == 'item-40':
        it['status'] = 'landed'
q['active'] = None
json.dump(q, open(p, 'w'), indent=1)

t = {
    "ticket": "item-40",
    "title": "Desktop notification daemon & system tray ABI (asynchronous agent toast alerts, status bar reactive applets)",
    "status": "landed",
    "blocker": None,
    "defect_status": None,
    "worktree": "main tree (HEAD bef36c77 at claim; landed on this lineage)",
    "attempt": 2,
    "gate": "tests/test_item40_notify.py (10 legs: T1 toast-above-content z, T2 guest-emitted alert end-to-end + real consumption, T3 stack + expire collapse via move(), T4 level/magic contract loud refusals, T5 tray applet reactive repaint, T6 tray capacity refusal, T7 queue cap refusal without damage, T8 fence EXIT_FAULT + innocent survivors, N1 engine byte-guard, N2 non-vacuity)",
    "last_gate_result": "GREEN (own run, 2026-09-26 ~22:1x CDT): 10 passed in 0.08s, rc=0 (output/item40_green_final.txt). RED 1 (toast z pinned 0): T1 failed, rc=1 — discriminates. RED 2 (harvest consumption removed): T2 failed, rc=1 — discriminates. Both in output/item40_red1_red2.txt, module restored byte-exact (md5 d5cd0ed7b478e73954597d044ac7142f). Adjacent regression: item-38 + item-39 gates 18 passed. NOT proven: no GPU/WGSL exec (CPU oracle), no mid-run preemption (cooperative commit-between-runs), no text/fonts on toasts (solid color words).",
    "untrusted_probes": [],
    "notes": [
        "tools/glyph_notify.py NEW: GlyphNotifyDaemon over the item-38 GlyphCompositor — toast queue (cap 8, loud refusals), dispatch as real compositor windows (arrival-z above content), expire_top retires OLDEST + re-stacks via move(), agent request-word harvest (consume-then-judge, quarantine loud), tray applet ABI with respawn repaint",
        "brief: .builder_queue/BRIEF_item40_notify.md (check_brief PASS; self-test exit 0)",
        "receipt: .builder_queue/RECEIPT_item40_notify.md (tails pasted)",
        "pure consumer; zero new syscalls; N1 pins glyph_isa_v2.py md5 5a672d7d5a94a7b20f927f554b8a90c0",
        "gate-caught defects fixed in-scope: expire popped wrong end; close_window does not exist on compositor (records append-only -> set_visible False); repaint-before-open; T3 legs aligned to landed item-38 C4 word-anchored move doctrine"
    ]
}
json.dump(t, open('.builder_queue/CURRENT_TICKET.json', 'w'), indent=1)
print("queue+ticket updated")
