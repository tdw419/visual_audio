# RECEIPT — Live campaign 2026-10-29 (Muse authoring + SAM segmentation)

Credits: $150 applied, $100 spend-limit notification set. All calls live via
api.meta.ai/v1 with MODEL_API_KEY from ~/.config/llm_api/keys.env.

## Muse leg — v1 (no reasoning_effort): 0/6 usable
6 descriptions x max_tokens=8192, NO reasoning control: every generation
returned EMPTY content — reasoning_tokens pinned at exactly 8190/8192
(cap-loop). ~8.5k tokens wasted per call, ~70s each. Fixtures preserved:
muse_gen_*_response.json (v1 superseded in place by v2 files).

## Muse leg — v2 (reasoning_effort="minimal"): 1/6 clean HALT, all content delivered
- Latency 5-17s (vs ~70s); reasoning 318-1377 tokens (vs 8190 cap)
- gen_5 full success: lint 0 issues, executed, HALT at 650 steps
- Gate catches (lint working as designed):
  * gen_3: "HALT r10 r10" — extra operands rejected (BK-315 class)
  * gen_4: "JZ r0 r0" — extra operands rejected
- Model convention slips at minimal effort:
  * gen_1: "JNZ loop" — label reference missing ":" prefix
  * gen_6: invented "JLT" opcode (not in glyph ISA v2); uninitialized r8
- OUR pipeline gap (h7 material): colon-less label refs crash
  place_on_canvas with a raw unpack error instead of a clean lint message.
  Robustness fix belongs in the lane, not the campaign.

## WIRE RULES (upgraded, campaign-proven)
1. Muse Spark authoring: ALWAYS send reasoning_effort="minimal". Deep
   reasoning is pure waste on this task (cap-loops at 8192, 10x cost, 7x
   latency, zero output).
2. "none" is HTTP 400 on Muse Spark (docs) — "minimal" is the floor.
3. Minimal-effort adherence is imperfect: plan a lint->repair loop
   (feed lint errors back for a fix pass) rather than single-shot trust.

## SAM leg — negative receipt (4 calls)
On the canonical glyph-grid poster (dense 8px cells), SAM 3.1 returns an
EMPTY stream (0 boxes) for: "dark glyph cell", "grid of black squares",
"small black squares on paper", "dark ink marks". Contrast: pixel-exact
boxes on coarse poster shapes (c05132cc probe). Architectural consequence:
SAM's role is poster-level segmentation; glyph-cell decode rides the h4
classical fallback. Fixtures: sam_*_response.json.

## Usage this campaign
v1 51,336 + v2 8,084 + SAM 4 small + morning authoring 7,076 ≈ 67k tokens
total. Dashboard-flat but receipted: 10 live generations, 4 segmentations,
1 end-to-end authoring success, 2 failure classes characterized.
