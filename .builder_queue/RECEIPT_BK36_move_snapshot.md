# RECEIPT — BK-36: Snapshot-at-reap for moved compositor windows

**Defect:** BK-36 (filed in `systems/GLYPH_BACKLOG.md` following Phase 1c research tick `8510c811` / `RESEARCH_move_damage_blackout.md`).  
**Symptom:** Dragged reaped windows composited 100% black because `GlyphCompositor.move()` updated the WCB bounding box while `composite()` read `cpu.memory[rr*W_MEM + cc]` from the CURRENT rect, whereas the task's RAM retained painted words at the origin grid coordinates.  
**Resolution:** Implemented snapshot-at-reap. When a window's guest finishes (`run_all()`), its tile pixels are captured from the origin rect into an `(h, w, 3)` uint8 frozen snapshot. `composite()` renders this snapshot translated to the window's moved coordinates. Un-reaped live windows have no snapshot and continue reading dynamically from task RAM.

---

## 1. Code Changes

1. **`tools/glyph_compositor.py`**:
   - Added `self._snapshots: dict[int, np.ndarray] = {}` to `GlyphCompositor.__init__`.
   - Added `_snapshot_at_reap(wid, wcb)` capturing `(h, w, 3)` tile from task RAM upon reaping.
   - Updated `composite()`: if a window has a snapshot (reaped), render the snapshot at the current rect; otherwise, read directly from `cpu.memory` (live).
   - Preserved all spatial fence and containment guarantees (zero ambient memory access).

2. **`tests/test_item38_compositor.py`**:
   - Updated `test_c4_move_drag()`: asserted moved window retains its reap-time paint at the new rect rather than masking the defect by expecting black cells.

3. **`tests/test_item40_notify.py`**:
   - Updated `test_t3_stack_and_collapse()`: asserted that collapsed toast stack preserves payload colors at shifted rows rather than expecting black cells.

4. **`tests/test_bk36_move_snapshot.py`**:
   - New dedicated verification suite with 6 legs covering full-tile painters, origin painters, pre-reap move refusal, live RAM pass-through, and non-vacuity.

---

## 2. Verification Gates

### RED Leg Verification (`output/bk36_red1.txt`)
Mutated `tools/glyph_compositor.py` by disabling `self._snapshots[wid] = snap`:
```text
FAILED tests/test_bk36_move_snapshot.py::test_l2_origin_paint_follows_move
FAILED tests/test_bk36_move_snapshot.py::test_l1_full_tile_snapshot_follows_move
PASSED tests/test_bk36_move_snapshot.py::test_l3_move_before_reap_refused
PASSED tests/test_bk36_move_snapshot.py::test_l4_live_windows_render_from_ram
2 failed, 2 passed in 0.24s (Exit Code: 1)
```
Proves the gate cannot pass vacuously when snapshotting is disabled.

### GREEN Gate Verification (`output/bk36_green_final.txt`)
Full 42-leg battery across items 38–41 + BK-36:
```text
tests/test_bk36_move_snapshot.py . . . .
tests/test_item38_compositor.py . . . . . . . .
tests/test_item39_vt.py . . . . . . . . . .
tests/test_item40_notify.py . . . . . . . . . .
tests/test_item41_taskmgr.py . . . . . . . . . .

============================== 42 passed in 0.38s ==============================
```

---

## 3. Adjacent System Integrity
- Root filesystem headroom: **8.6 GB available** (76% used).
- Disk `/home`: **70.4 GB available**.
- Architectural guarantees: Zero kernel/ISA modifications, zero ambient memory leaks.
