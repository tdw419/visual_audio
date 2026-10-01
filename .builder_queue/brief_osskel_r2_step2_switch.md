# BRIEF — OS-SKEL-R2 Phase 3, STEP 2 of 7: `AddressSpace.switch`

**Target id:** OS-SKEL-R2 Phase 3 step 2 (`systems/GLYPH_OS_SKELETON.md` § 6 Phase 3 roadmap row 2, line 163;
round brief `.builder_queue/brief_osskel_r2_phase3.md`). Step 1 (`map`/`unmap`) landed at `e4cfa2c`.
**Spec is the skeleton — read it FIRST:** `systems/GLYPH_OS_SKELETON.md` lines 160-166 plus the module
invariant **I4** (`tools/geos_aspace.py:34-35`) and the class docstring (`tools/geos_aspace.py:206-216`).
**Interfaces are LOCKED** — signatures, dataclass fields, constants, `__post_init__`, `__all__` entries.
If one looks wrong, STOP and report; that is a skeleton-sign-off change, not a builder call.

**Files in scope (only these may change):**
- `tools/geos_aspace.py` — fill `switch()` (`:251-253`) and add the module-level MMIO sink helpers below ONLY.
- `tests/test_osskel_aspace_switch.py` — NEW gate file.
- `output/osskel_r2_step2_red.txt`, `output/osskel_r2_step2_green.txt` — evidence captures.

**Do NOT** touch `tests/test_osskel_aspace_map.py`, any other existing `tests/*.py`, `tools/geos_os_skel_verify.py`
(it is the structural harness — see the step-1 amendment note at `.builder_queue/brief_osskel_r2_phase3.md:29-35`),
`tools/geos_caps.py`, `tools/geos_proctab.py`, `tools/geos_devtab.py`, `tools/glyph_isa_v2.py`, WGSL,
`tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, `systems/**`, `.builder_queue/**`.
Stdlib only (`geos_os_skel_verify.py` AST-scans for third-party imports). **DO NOT COMMIT.**

## Injection mechanism — DECIDED by the orchestrator, do not redesign

Fields are LOCKED, so the sink cannot live on the instance. Bind it at module level in
`tools/geos_aspace.py` (stdlib `typing.Callable` only):

```python
MmioSink = Callable[[int, int], None]      # (addr, word) -> None
_mmio_sink: Optional[MmioSink] = None

def set_mmio_sink(sink: Optional[MmioSink]) -> None:
    """Bind the engine's single-word MMIO write path; None unbinds."""
    # raise TypeError when sink is neither None nor callable

def get_mmio_sink() -> Optional[MmioSink]:
    """Current sink (None when unbound) — for tests and teardown."""
```

`set_mmio_sink` / `get_mmio_sink` / `MmioSink` must **NOT** be appended to `__all__` (the declared surface
stays frozen); the gate imports them by name.

## Behaviour to implement (I4 — do not re-derive, do not add features)

`switch() -> int`
- With a sink bound: call it **exactly once** as `sink(PAGE_TABLE_ADDR, self.satp_word)` and then return
  `self.satp_word`. No other address, no other word, no second call, no buffer/rebuild (I4: "a switch that
  requires a rebuild is a design regression").
- With **no** sink bound: raise `RuntimeError` naming the condition (e.g. `"no MMIO sink bound: refusing to
  report a switch that wrote nothing"`). **Orchestrator decision, already made:** a switch that silently
  returns while writing nothing is the exact anti-pattern this project refuses elsewhere; do not soften this
  into a no-op and do not invent a default sink.
- If the injected sink itself raises, let the exception propagate — `switch()` must not swallow a failed write.
- Keep `PAGE_TABLE_ADDR` (`0x804C`) the only write target and `satp_word`'s existing encoding
  (`(pt_base_word << PFN_SHIFT) | (asid & 0xFF)`) untouched.
- No real hardware/box word may be written anywhere by this step. The sink is the only path.

You may add a short comment above the helpers and update the module docstring `PHASE STATUS` line — that is
documentation, not interface. Do not rewrite existing invariant text.

## Gate — `tests/test_osskel_aspace_switch.py`

Gate command (the orchestrator re-runs this exact one):
```
/usr/bin/python3 -m pytest tests/test_osskel_aspace_switch.py -q 2>&1 | tail -20
```

Legs (each must assert the committed behaviour, not a tautology):
- **L1** one write: bind a recording sink (list of `(addr, word)` tuples); `switch()` returns `satp_word` and
  the sink recorded **exactly one** entry `(PAGE_TABLE_ADDR, satp_word)`.
- **L2** idempotent value, repeatable call: switching **twice** records **two** writes, both to
  `PAGE_TABLE_ADDR` with the **same** word.
- **L3** refusal (non-vacuity vs the stub): with **no** sink bound, `switch()` raises `RuntimeError` — the
  current stub returns `satp_word` and passes nothing, so this leg is RED before the change and GREEN after.
- **L4** addressing: the recorded address equals `PAGE_TABLE_ADDR` (`0x8000 + 0x4C`) and the recorded word
  equals `(pt_base_word << 8) | (asid & 0xFF)` for a space built with a known asid/`pt_base_word` (proves the
  sink gets *this* space's word, not a constant); a second space with a different asid records its own word.
- **L5** failed write is not swallowed: bind a sink that raises `OSError`; `switch()` propagates it (no
  `return` on the failure path).
- Use a pytest fixture (or try/finally) that restores the previous sink via `get_mmio_sink()` /
  `set_mmio_sink(...)`, so the module global cannot leak into other tests — and add an assertion that the
  sink is unbound again after the test body.

## Evidence discipline

1. BEFORE implementing: create the gate file, run the gate command, save the literal output to
   `output/osskel_r2_step2_red.txt` (expect FAIL — the stub silently returns, writing nothing).
2. After implementing: re-run the same command, save to `output/osskel_r2_step2_green.txt`.
3. Structural harnesses must both stay PASS through the step:
   `python3 tools/geos_os_skel_verify.py` (85 legs, exit 0) and `python3 tools/geos_spine_verify.py` (exit 0).
4. Arc regression must stay green:
   `/usr/bin/python3 -m pytest tests/test_gh*.py tests/test_bk*.py tests/test_spine_r1_*.py -q` exit 0.
5. Report at the end: exact files changed, the literal gate tail, the two harness tails, the arc tail, and
   anything you could NOT do (state it; never approximate it).
