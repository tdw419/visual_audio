# ROADMAP Update Summary - 2026-07-18

## Critical Blocking Issues Requiring Immediate Attention

### Phase 8 Blockers (Pixel LM Completion)

**TASK_M007: Pixel OS Input Channel** - BLOCKED
- Missing test file: `tests/test_pixel_os_lm_input.py`
- Impact: Blocks Phase 8 completion, which blocks TASK_SE006 (Phase 11 integration)
- Resolution: Create test file that verifies pixel-LM stream → word decoding → OS command dispatch

**TASK_SE006: Pixel-token LM Integration** - BLOCKED (needs status update)
- Currently blocked on TASK_M006/M007
- TASK_M006 is COMPLETE (verified 2026-07-17)
- Should only be blocked on TASK_M007
- Update: Remove TASK_M006 from blocking dependency

### VAMP Phase 10 Blockers (Inaccurate Status Claims)

The following tasks show "Status: COMPLETE" but lack verification files:

**TASK_V003: Reed-Solomon ECC for Memory Tiles** - CLAIMED COMPLETE, NOT VERIFIED
- Missing test file: `tests/test_vamp_ecc_tiles.py`
- Cannot auto-verify without test
- Receipt claims ECC recovery up to 5% tile loss
- Resolution: Create test file or change status to PENDING

**TASK_V004: Executable Knowledge Cartridges** - CLAIMED COMPLETE, NOT VERIFIED  
- Missing test file: `tests/test_vamp_executable_cartridges.py`
- Cannot auto-verify without test
- Receipt claims sandboxed execution with consistency checks
- Resolution: Create test file or change status to PENDING

**TASK_V005: Voice Query Interface** - CLAIMED COMPLETE, NOT VERIFIED
- Missing test file: `tests/test_vamp_voice_query.py`
- Cannot auto-verify without test
- Receipt claims >85% accuracy for phoneme queries
- Resolution: Create test file or change status to PENDING

### Phase 6 Research Blockers

**TASK_R003: Steganographic/Ambient Channel** - BLOCKED
- Missing tool: `tools/ambient_encoder.py`
- Cannot verify steganographic encoding without tool
- Resolution: Implement ambient encoder or mark as exploratory research

**TASK_W002: Token-Chord Codec** - BLOCKED
- Test command undefined (Option A vs Option B decision needed)
- Needs design decision on verification approach
- Resolution: Choose test approach and implement

## Proposed Resolution Tasks

### New Test Creation Tasks

**TASK_T001: Create pixel OS input channel test**
- Priority: CRITICAL
- Dependencies: TASK_M006
- Deliverable: `tests/test_pixel_os_lm_input.py`
- Scope: Verify pixel-LM stream → word decoding → OS command dispatch
- Test command: `python3 -m pytest tests/test_pixel_os_lm_input.py`

**TASK_T002: Create VAMP ECC tiles test**
- Priority: HIGH
- Dependencies: TASK_V001, TASK_E001
- Deliverable: `tests/test_vamp_ecc_tiles.py`
- Scope: Verify encode_ecc/decode_ecc round-trip, 5% corruption recovery
- Test command: `python3 -m pytest tests/test_vamp_ecc_tiles.py`

**TASK_T003: Create VAMP executable cartridges test**
- Priority: HIGH
- Dependencies: TASK_V001, TASK_X001
- Deliverable: `tests/test_vamp_executable_cartridges.py`
- Scope: Verify cartridge generation, sandboxed execution, consistency checks
- Test command: `python3 -m pytest tests/test_vamp_executable_cartridges.py`

**TASK_T004: Create VAMP voice query test**
- Priority: HIGH
- Dependencies: TASK_V002, TASK_W001
- Deliverable: `tests/test_vamp_voice_query.py`
- Scope: Verify phoneme query parsing, fuzzy match accuracy >85%
- Test command: `python3 -m pytest tests/test_vamp_voice_query.py`

**TASK_T005: Implement ambient encoder**
- Priority: LOW
- Dependencies: TASK_D001
- Deliverable: `tools/ambient_encoder.py` + `tests/test_ambient_encoder.py`
- Scope: Psychoacoustic masking, steganographic data encoding
- Test command: `python3 tools/ambient_encoder.py encode music.wav firmware.py -o carrier.wav`

## Current Project Metrics (2026-07-18)

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Phoneme throughput | ~7.6 words/sec | ≥8.0 words/sec | ⚠️ Near target |
| Byte throughput | ~24 bytes/sec | ≥25 bytes/sec | ⚠️ Near target |
| Pixel density | ~2.5 bytes/pixel | ~3 bytes/pixel (VAMP) | 🟡 Need VAMP |
| Test coverage | 50+ test files | >80% | 🟡 Improving |
| Task completion | 31/68 (46%) | 100% | 🔴 Need focus |

## Critical Path Updates

### Original Path
```
Phase 0 (DONE) → Phase 1 (ECC) → Phase 3 (Dual-Band) → Phase 8 (Pixel LM) → Phase 11 (Spatial Engine)
                                    ↓
                               Phase 4 (GeOS) → Phase 10 (VAMP) → Memory Palace extension
```

### Updated Path with Resolution Tasks
```
Phase 0 (DONE) → Phase 1 (ECC DONE) → Phase 3 (Dual-Band DONE) → Phase 8 (Pixel LM - BLOCKED)
                                                                          ↓
                                                                    TASK_M007 (needs TASK_T001)
                                                                          ↓
Phase 4 (GeOS - DONE) → Phase 10 (VAMP - CLAIMED DONE) → Memory Palace extension
                            ↓                       ↓
                        TASK_C035/036 pending    TASK_V003-005 (need TASK_T002-004)
```

## Immediate Action Items

1. **Unblock Phase 8**: Create TASK_T001 test file (pixel OS input channel)
2. **Resolve VAMP claims**: Either create test files (TASK_T002-004) or revert status to PENDING
3. **Update TASK_SE006**: Remove TASK_M006 from blocking dependencies
4. **Resolve TASK_W002**: Make Option A/B decision and implement test
5. **Consider TASK_R003**: Mark as exploratory research or implement ambient encoder

## Success Criteria for Unblocking

- [ ] All test files exist (TASK_T001-004)
- [ ] TASK_SE006 updated to only block on TASK_M007
- [ ] VAMP tasks V003-005 either verified via tests or marked PENDING
- [ ] TASK_W002 has defined test command
- [ ] Autonomous executor can verify all unblocked tasks

## Updated Task Count Estimate

After resolution:
- Total tasks: 68 + 5 (new test tasks) = 73
- Current complete: 31 - 3 (VAMP claims retracted) = 28
- New complete potential: 28 + 5 (test tasks) = 33
- New percentage: 33/73 = 45.2%

This reflects a more honest assessment of actual progress.