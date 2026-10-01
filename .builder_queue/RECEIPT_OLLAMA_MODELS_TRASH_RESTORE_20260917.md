# 2026-09-17 ~08:15 CDT — Ollama models trashed mid-tick; restored by orchestrator (cron af3e62239ce2)

## Symptom chain
1. Standing arc conjunction (arc_legA_rerun.sh) went RED this tick: RUN4/RUN5 rc=1,
   6 failed, 324 passed — previous tick (addendum 201, 07:56, output/arc_lega_seed42_6b677b3.txt)
   was GREEN 373p/1s/9d/2xf rc0. The delta was ~2 minutes of wall time, no repo change
   (dirty file set unchanged, 237 tracked-dirty).
2. All 6 failures shared ONE traceback: tools/glyph_gpt/escalate.py:345 → _ollama
   → HTTP 404 on http://localhost:11434/api/generate (tests/test_gh20_fs_v2.py × 5,
   tests/test_bk13_net.py::test_bk13_l3_admission_oracle_refusal_and_receipt × 1).
   Not a test defect, not contention — environment.
3. `curl /api/tags` → `{"error":"mkdir /home/jericho/.ollama/models: file exists..."}`.
   `/home/jericho/.ollama/models` is a symlink → `/home/jericho/ollama_models_moved`,
   and the target did not exist. `curl /api/generate qwen2.5-coder:14b` → "model not found".

## Root cause (measured, not inferred)
`.local/share/Trash/info/ollama_models_moved.trashinfo`:
    Path=/home/jericho/ollama_models_moved
    DeletionDate=2026-09-17T07:57:43
The 48G ollama_models_moved dir (blobs + manifests, incl. qwen2.5-coder:14b) was moved
to Trash at 07:57:43 CDT — 80 seconds after the last green arc finished (07:56:30 file
mtime) and ~1 min before this cron tick's red runs (07:58+). Trash is same-volume, so
the trash move freed 0 bytes; /home read 100% full before AND after the deletion.
Perp not identified (no journal record of the deleting process).

## Exposure
escalate.py (OLLAMA_MODEL qwen2.5-coder:14b) AND ~/.hermes/scripts/local_digest.sh both
call this server; the digest clause in the orchestrator prompt and several repo tools
go dark with it. If anything had emptied the trash, the only copy of the models was gone.

## Fix
    mv ~/.local/share/Trash/files/ollama_models_moved ~/ollama_models_moved   (rename, net-zero)
    rm ~/.local/share/Trash/info/ollama_models_moved.trashinfo
Symlink target restored → /api/generate returned "pong" (qwen2.5-coder:14b, ~10s load).
Arc re-run: RUN4 + RUN5 rc=0, 332 passed / 1 skipped, 0 crashes (SEED=42).
local_digest.sh re-verified on a real file. Trash/files now 4.0K (empty).

## What this does NOT prove
- Who/what issued the trash move (no attribution; deleted process untraced).
- That nothing else was trashed in the same sweep — Trash was empty when checked, so any
  sibling casualty already emptied is unrecoverable from here.
- Long-term: /home at 100% (5.9G free after restore) keeps generating cleanup pressure;
  the models dir will get swept again unless it is relocated or pinned.
