# RECEIPT — SUITE-FIX-1 cluster (3) drift: `test_ollama_contextual_memory_simple.py` ports to the canonical session API

**Date:** 2026-09-13 · **Builder cron:** `af3e62239ce2` · **Branch:** `glyph-transpiler-autoloop`
**Roadmap row:** `SUITE-FIX-1` (`systems/GLYPH_SELF_HOSTING_ROADMAP.md:355`) — **row stays open** (cluster (4) tolerances + leg 1b)
**In-scope file (one):** `tests/test_ollama_contextual_memory_simple.py` · **Delegate:** `agy` (exit 0, 113 s, `output/agy/agy_impl_20260913_183631.log`)
**Brief:** `.builder_queue/brief_suite_fix1_ollama_memory_drift.md`

## 1. The row's classification is refuted by measurement

The roadmap lists this file under cluster (4) as *"fails on an unmocked/offline endpoint (ENVIRONMENT, not a code
defect)"* and directs that it *"must be marked skip-with-reason"*. Measured 2026-09-13 by the orchestrator:

```
tests/test_ollama_contextual_memory_simple.py:31: AttributeError: 'OllamaMemoryManager' object has no attribute 'add_message'
tests/test_ollama_contextual_memory_simple.py:76: AttributeError: 'OllamaMemoryManager' object has no attribute 'add_message'
2 failed in 0.18s
```

**0.18 s, no socket is opened** — an offline or unmocked endpoint cannot fail this way. The file is **API drift**
(cluster (3) class), and the prescribed skip would have masked a real product/consumer mismatch as an environment
condition. The step was therefore run as a drift fix, not a skip.

## 2. Root cause

`OllamaMemoryManager` (`tools/ollama_memory_manager.py:301`) has **no** `add_message` — the message API is session-scoped
by the module's own contract (`:20-25`):

```
manager = OllamaMemoryManager(db_path=...)
session = manager.create_session("user_alice")
session.add_message("user", "Hello")
history = session.get_conversation_history()
```

The test called `manager.add_message(conv_id, role, content)` and then read `session.messages`, an attribute that does
not exist either (`ConversationSession` exposes `get_conversation_history()` / `get_last_n_messages(n)`). Both legs died
on the first call. The test was the drifted consumer; the module is the product.

## 3. Gate (orchestrator's own re-run — never the delegate's claim)

| step | command | result |
|---|---|---|
| RED, pre-fix | `/usr/bin/python3 -m pytest tests/test_ollama_contextual_memory_simple.py -q` on the `4863635` blob | **2 failed in 0.18 s** (`output/suite_fix1_ollama_memory_red_orch.txt`) |
| GREEN, post-port | same command, ported file | **2 passed, 2 warnings in 0.16 s, rc=0** |
| standalone `__main__` | `/usr/bin/python3 tests/test_ollama_contextual_memory_simple.py` | all 4 turns + persistence printed, **rc=0** |
| forbidden tokens | `grep -n "skip\|xfail\|manager.add_message(\|\.messages"` on the ported file | **none** |
| row gate (sweep) | `PATH=/usr/bin:$PATH suite_sweep.sh -b 12G -w 4 -- /usr/bin/python3 tools/suite_iso_harness.py tests -t 150 -w 4` | 257 files / 1618 collected / **PASS 243 · FAIL 10 · TIMEOUT 4**, 467.38 s (`output/SUITE_FIX1_C34_SINK.jsonl`) |

Ported assertions are equivalent, not relaxed: 2 messages after turn 1, `"France"` in `history[0].content`, 4 messages
with all four contents **in order**, and the reopen leg still reads through **a second manager instance** (1 message,
content and `role == MessageRole.USER`).

## 4. Non-vacuity (the ported legs are discriminating)

Orchestrator's own probe, independent of the delegate's: neutered the `INSERT INTO messages` in
`ConversationSession.add_message` (`tools/ollama_memory_manager.py:163`) → **both ported legs RED**
(`2 failed in 0.18 s`); module restored, **md5 `28998c374c92acd817c61c998a5bdc9a` before == after**, `git diff` on the
module empty. The legs read from SQLite; they do not pass on live Python state.

## 5. Tree-sweep delta vs the previous sink — one regression found, NOT caused by this change

Per-file attribution against `output/SUITE_FIX1_C3B_SINK.jsonl` (256 files / 1610 collected / PASS 242 · FAIL 10 · TIMEOUT 4):

| file | C3B | C34 (this tick) |
|---|---|---|
| `tests/test_ollama_contextual_memory_simple.py` | FAIL (2/0/2) | **PASS (2/2/0)** ← this row's step |
| `tests/test_glyph_orchestrator_speak_to_driver.py` | PASS | **FAIL (1/0/1)** ← **regression, caused by `4863635`, not by this change** |
| `tests/test_run_containment.py` | (absent) | PASS (new file, `4863635`) |

The regression is a consumer of the 0x07 containment landing (`4863635`): its end-to-end leg never grants itself a
`GLYPH_RUN_ALLOW` entry, so RUN is now denied, and `:83` asserts the `0o755` chmod side effect that
`RULING_run_syscall_containment.md` decision 4 **deliberately removed**. **The ruling's enabling finding (`:29-35`,
"a default-deny allowlist breaks **zero existing tests**") is falsified** — it inspected only
`tests/test_glyph_run_program.py`; the arc selector does not collect this file, which is why the landing's arc run was
green. Repair brief: `.builder_queue/brief_run_containment_orchestrator_repair.md`; landing receipt:
`systems/RECEIPT_RUN_CONTAINMENT_ORCHESTRATOR_REPAIR.md`.

## 6. HONEST BOUNDARY — what this PASS does not prove

- The port is a **consumer-side** fix: it proves the *test* now exercises the module's shipped API, and says nothing
  about the module's own behaviour beyond the two paths exercised.
- `tests/verify_ollama_memory.py` carries the **same drift** and is still broken — out of scope (pytest does not collect
  it, it is named `verify_*.py`); it is left byte-identical, not fixed.
- The `project_root = Path(__file__).parent.parent` change (delegate's) was verified by running both the standalone
  `__main__` (rc=0) and the collected gate (2 passed); the file's import path under other invocations was not probed.
- The two `PytestReturnNotNoneWarning`s (`return True` from a test) are pre-existing and untouched.
- No WGSL leg, no arc leg for this change (test-only, not in the arc selector); the sweep above is the row gate.
- Cluster (4)'s tolerance files (`test_griffin_lim.py` 18/4, `test_vcc_validation.py` 6/3, `test_cross_modal.py` 2/6) and
  the 4 TIMEOUT files were **not** investigated this tick.
