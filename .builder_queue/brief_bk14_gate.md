ROADMAP ROW: BK-14 (remaining leg only) — "Glass-box demo script ... dedicated gate".
Implemented leg 1 already exists and must NOT be re-implemented or edited:
  - runner: tools/glass_box_demo.py (committed at 1605e0c)
  - doc:    systems/DEMO_GLASS_BOX.md
Your job is ONLY to add the missing dedicated gate: tests/test_bk14_demo.py

FILES IN SCOPE (this is the entire scope):
  - tests/test_bk14_demo.py  (NEW file — create it)
Do NOT modify any other file. In particular do NOT touch tools/glass_box_demo.py,
systems/DEMO_GLASS_BOX.md, systems/RECEIPT_GH26_AGENT_LOOP.md, tools/gh26_glass_box_scenario.py,
or tests/test_gh26_glass_box.py. If you conclude the runner cannot be gated as specified,
STOP and report the blocker with evidence — do not fix the runner.

WHY A NEW FILE: tests/test_gh26_glass_box.py covers the underlying GH-26.5 scenario but IS NOT
BK-14's gate clause (the roadmap row and .builder_queue note pin BK-14's gate to this new file).

GATE COMMAND (must be green from a clean run, no network, CPU only):
  cd /home/jericho/projects/zion/projects/visual_audio
  python3 -m pytest tests/test_bk14_demo.py -q
Write it RED-first discipline style like the repo's other gates: include in the module docstring
the spec reference (BK-14 / GH-26.5) and each leg's intent.

LEGS THE GATE MUST CONTAIN (all must be real assertions, no tautologies/skips):

L1 — Refusal (human gate). Run the runner as a subprocess with GEOS_EMIT_ACK REMOVED from the
child env: `python3 tools/glass_box_demo.py` (cwd = repo root).
  assert returncode == 1
  assert "REFUSAL: GEOS_EMIT_ACK" in stderr
  assert no stage banner ("[Stage 0]") was printed to stdout (refusal happens before any work).

L2 — Full end-to-end run. Same subprocess with env GEOS_EMIT_ACK=1 and --work-dir pointing at a
tmp_path directory.
  assert returncode == 0
  assert "VERDICT: ALL THREE ANCHORS VERIFIED (exit 0)" in stdout
  assert all six stage banners [Stage 0]..[Stage 5] each report "PASS" (parse the actual printed
  status lines; do not just count banners).

L3 — The three anchors, cross-checked against the COMMITTED receipt (this is the provenance leg;
the values must be read from systems/RECEIPT_GH26_AGENT_LOOP.md at test time, not hardcoded twice):
  - Anchor 1 frame geometry: stdout must contain "mapping sound: all reference pixels match"
    AND 5/5 sentinel markers — drive tools.geos_hilbert.verify_reference_pixels yourself on a
    frame stamped by tools.geos_hilbert.stamp_reference_pixels(n=128) and assert ok is True.
  - Anchor 2 admitted capability: parse the tile SHA256 out of the receipt
    (`systems/RECEIPT_GH26_AGENT_LOOP.md`) and assert the demo's printed "Tile SHA256:" equals it,
    and that the artifact `tools/glyph_gpt/admitted/syscall_8_template_<sha[:12]>.glyph` exists in
    the tree.
  - Anchor 3 canonical replay: parse the receipt's "Final State MD5" value and assert the demo's
    printed "Final State MD5:" equals it, and that the printed divergence is exactly
    "Divergence:       0 words" (0 of 16,384 cells).

L4 — Non-mutation. The demonstration must leave the repository's tracked artifacts byte-identical.
  Snapshot before the L2 run: sha256 of every file under tools/glyph_gpt/admitted/ plus
  systems/RECEIPT_GH26_AGENT_LOOP.md. Re-snapshot after. Assert the (path → sha256) maps are equal
  (no file added, removed, or changed). Do NOT use git status for this leg (the repo may be dirty
  from other sessions; git state is not the claim being made).
  Also assert the run's artifacts went to the --work-dir tmp_path (kernel_memory.npy,
  gh26_resident.npy, gh26_admit.npy, admissions.jsonl exist there), i.e. the demo is self-contained.

HARD CONSTRAINTS:
  - Python 3.12, pytest. Use the same repo-root sys.path bootstrap pattern as the other tests in
    tests/ (see tests/test_bk12_wgsl_tier.py and tests/test_gh26_glass_box.py).
  - CPU only. Do not import or require WGSL/GPU for this gate (the runner is CPU).
  - No network. No writes outside tmp_path and tools/glyph_gpt/admitted/ (which must be unchanged).
  - The whole file must run in well under 30 s (the demo itself takes ~1 s).
  - Do NOT commit anything. Leave the file in the working tree.

REPORT BACK (DIFF SUMMARY): the file you created, the exact command you ran, and the literal last
lines of its output (pass/fail counts). If any leg needed an assumption, state it explicitly.
