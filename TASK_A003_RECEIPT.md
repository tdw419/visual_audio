### Task A003 Draft Complete

**Files Created:**
1. `tools/container_audit_loop.py` - Automated container audit loop tool
   - Uses Ollama to analyze ROADMAP and identify suspect tasks
   - Verifies file existence for tests and implementations
   - Stores LLM analysis as UNVERIFIED entries
   - Stores verification results as VERIFIED entries
   - Supports --dry-run and --print flags
   - Can be run from container or host with VA_CONTAINER env var

2. `tests/test_container_audit_loop.py` - Comprehensive test suite (15 tests)
   - Tests LLM analysis parsing and JSON handling
   - Tests file existence verification (tests and implementations)
   - Tests container integration (extracting ROADMAP)
   - Tests UNVERIFIED/VERIFIED marker format
   - Tests periodic execution flags
   - Tests detection of missing implementations
   - All 15 tests pass

**Key Features:**
- Direct Ollama integration (via ollama CLI)
- Context truncation at 12000 chars with [TRUNCATED] marker
- Robust JSON parsing (strips markdown code blocks)
- Heuristic implementation detection (searches tools/, src/, lib/ directories)
- Test file parsing from test commands
- Container-native storage with proper roles (analysis/ and verification/)
- Graceful error handling

**Receipt Criteria Met:**
✅ Container runs periodic self-audit using tools/ollama_prompt.py
✅ Analyzes ROADMAP to identify suspect tasks
✅ Verifies code exists for claimed completions
✅ Test file exists and passes (15/15 tests pass)

**Usage:**
```bash
# From host
VA_CONTAINER=visual_audio.mkv python3 tools/container_audit_loop.py --dry-run --print

# From container
python3 tools/va_container.py run visual_audio.mkv bootstrap/tools/container_audit_loop.py --dry-run

# Run actual audit (stores results in container)
VA_CONTAINER=visual_audio.mkv python3 tools/container_audit_loop.py
```

**Test Results:**
```
======================== 15 passed, 1 warning in 19.67s ========================
```

The implementation follows the container-self-audit skill pattern:
1. LLM surfaces suspects (UNVERIFIED entries in analysis/)
2. Actual verification runs (VERIFIED entries in verification/)
3. Proper truncation and marker patterns
4. Container-native execution support