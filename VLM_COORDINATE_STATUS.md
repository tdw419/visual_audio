# VLM Coordinate Extraction Status

**Date:** 2026-07-19

## Issue
VLM (llava) generates patches with text targets instead of coordinates:
- **Bad:** `"target": "UNKNOWN opcode hot region (9)"`
- **Good:** `"target": "(16, 20, 0)"`

## Fix Attempted
Updated VLM prompt to:
1. Include Z coordinate in hot region output: `"(x, y, 0)"` instead of `"(x, y)"`
2. Add CRITICAL instruction: "Your 'target' field MUST use exact coordinates like '(x, y, z)'"
3. Change operation types from abstract (`COMPACTION|REALLOCATION|COALESCING`) to concrete (`FILL_RECT|CLEAR_REGION|COPY_BLOCK`)
4. Require concrete fields: `color`, `width`, `height`

## Current Status
**Partial Success:**
- ✅ Mock analysis works correctly with coordinates
- ✅ Spatial Compiler parses coordinate format correctly
- ✅ Patch payload generation includes color/width/height when present
- ❌ VLM JSON parsing fails with "Invalid \escape" and "Expecting value" errors

## Root Cause
Ollama's JSON output has formatting issues:
- Escaped characters in unexpected places
- Markdown code blocks wrapping JSON
- Inconsistent quote escaping

The prompt improvements are correct, but the LLM output parsing needs robustification.

## Verified Working Path
```python
# Mock analysis (OLLAMA_AVAILABLE=False) works perfectly:
{
  "opportunities": [
    {
      "type": "FILL_RECT",
      "target": "(16, 20, 0)",
      "color": [236, 80, 80],
      "width": 4,
      "height": 4,
      "rationale": "dense block should be compacted",
      "status": "PENDING"
    }
  ],
  "priority": "HIGH"
}
```

This generates 1 operation in Spatial Compiler: `{'op_type': 3, 'x': 16, 'y': 20, 'z': 0, 'r': 236, 'g': 80, 'b': 80, 'width': 4, 'height': 4}`

## Next Steps
1. **Immediate:** Robust JSON parsing with regex fallback (already partially implemented)
2. **Medium:** Test with different VLM models (llava, minicpm-v, bakllava)
3. **Long-term:** Fine-tune small model for coordinate extraction (few-shot learning)

## Test Script
`test_vlm_coords.py` - Tests VLM coordinate extraction end-to-end