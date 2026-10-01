# BRIEF — SUITE-FIX-1 drift: `tests/test_ollama_contextual_memory_simple.py` ports to the canonical session API

**Roadmap row:** `SUITE-FIX-1` in `systems/GLYPH_SELF_HOSTING_ROADMAP.md` (line 355), cluster "(3) API/firmware drift".
**Spec pointer (read first, it is the contract):** the module's OWN usage docstring, `tools/ollama_memory_manager.py:20-25`
—
`manager.create_session(...)` → `session.add_message(role, content)` → `session.get_conversation_history()`.
The implementing methods: `ConversationSession.add_message` `:138`, `get_conversation_history` `:188`,
`OllamaMemoryManager.create_session` `:378`, `get_session` `:432`.
**Classification correction (measured this tick, do not re-litigate):** the roadmap lists this file under cluster (4) as
"fails on an unmocked/offline endpoint (ENVIRONMENT)". **That is refuted by measurement**: it fails in **0.17 s** with
`AttributeError: 'OllamaMemoryManager' object has no attribute 'add_message'` at
`tests/test_ollama_contextual_memory_simple.py:31` and `:76` — no socket is opened. It is API drift, and the fix is the
test, not a skip. Do NOT add a skip/xfail and do NOT mark it env-class.

## The drift in one paragraph

`OllamaMemoryManager` has **no** `add_message` method and never had one: the message API lives on the session object
(`ConversationSession.add_message(role, content)`), and history is read with
`session.get_conversation_history()` / `get_last_n_messages(n)`. The test calls the manager directly —
`manager.add_message(conv_id, role, content)` — and then reads an attribute that does not exist either,
`session_after_turn1.messages`. Both legs therefore die on `AttributeError` before touching SQLite. The test is the
drifted consumer; the module is the product.

## Files in scope

**Positive — the ONLY file you may modify:**
1. `tests/test_ollama_contextual_memory_simple.py` — port both legs to the canonical API (see "Required behaviour").

**Negative — do NOT touch:**
- `tools/ollama_memory_manager.py` — the API is **LOCKED**. Do not add a manager-level `add_message` convenience, do not
  add a `messages` attribute/property, do not rename anything. If you believe the module is the wrong side, STOP and
  report instead of editing it.
- `tests/verify_ollama_memory.py` (same drift, uncollected by pytest — out of scope, leave byte-identical).
- any other test file, `pytest.ini`, `tools/**`, `glyph_dispatch/**`.

If a leg is red for a reason **outside the single in-scope file**, STOP and report the literal output.

## Required behaviour (preserve every assertion; relax nothing)

Port both legs to the canonical API; the assertions must remain **equivalent, same numbers, same strings**:
- `session = manager.create_session(session_id=conv_id)`; `session.add_message(MessageRole.USER, "...")`.
- Read history back through the manager boundary, not from live Python state:
  `history = manager.get_session(conv_id).get_conversation_history()`.
- **`test_context_persists_across_multiple_queries`** keeps: 2 messages after turn 1, `"France"` present in
  `history[0].content`, then 4 messages with all four contents asserted **in order** (France Q/A, Germany Q/A).
- **`test_database_persistence_across_reopen`** keeps: a **second** `OllamaMemoryManager` instance on the same db path
  sees 1 message, content `"Persistent message"`, `role == MessageRole.USER`.
- The `__main__` block (`:95-119`) must stay consistent with the ported calls (it calls both legs directly).
- No `pytest.skip`, no `xfail`, no assertion deleted or weakened, no network call added.

## Gate — run this exact command; it must exit 0 with 2 passed

```
/usr/bin/python3 -m pytest tests/test_ollama_contextual_memory_simple.py -q
```

Gate clause (falsifiable):
- **PASS** ⇔ `2 passed`, exit code 0, and mirroring the live failure mode: the ported file must contain **no**
  `manager.add_message(` and **no** `.messages` attribute access, and must contain `get_conversation_history()`.
- **REFUSE**: any skip/xfail; any edit outside the one in-scope file; any assertion whose expected count/string changed.

Failure evidence (RED-first — already measured by the orchestrator on the unmodified tree, 2026-09-13):
- Pre-fix run: `2 failed in 0.17s`, both `AttributeError: 'OllamaMemoryManager' object has no attribute 'add_message'`
  at `:31` and `:76`. Save the pre-fix run of the **new** ported file, on the unmodified module, to
  `output/suite_fix1_ollama_memory_red.txt` (write the port, run it against the untouched module, capture the RED,
  then keep going — there is no module fix to make).
- Non-vacuity (the ported legs must be discriminating): neuter the `INSERT INTO messages` in
  `ConversationSession.add_message` (`tools/ollama_memory_manager.py:163-169`) in an **out-of-tree copy or a temporary
  edit that you restore byte-identical (md5 before == md5 after)** — both ported legs must go RED. Save it to
  `output/suite_fix1_ollama_memory_nonvacuity.txt` and print the md5 pair.
- Save the post-port green run to `output/suite_fix1_ollama_memory_green.txt`.

## Interfaces are LOCKED + definition of done

**Interfaces LOCKED:** `tools/ollama_memory_manager.py`'s public API (`OllamaMemoryManager`,
`ConversationSession`, `MessageRole`, their method names and signatures) is locked and must not change.
**Definition of done:** the gate command above exits 0 with `2 passed` on your uncommitted tree; every assertion of the
two legs preserved with identical counts/strings; only the one in-scope file modified; RED-first output,
non-vacuity md5 pair, and green output saved under `output/`; nothing committed.

## Do NOT commit

Do **NOT** `git commit`, `git add`, `git checkout`, `git stash` or `git reset`. Leave the tree dirty; the orchestrator
verifies and commits.

## Report back (literal, no paraphrase)

1. The literal gate command and its literal tail (pre-fix RED and post-port GREEN).
2. The md5 before/after pair from the non-vacuity probe.
3. A DIFF SUMMARY: files changed, line counts.
4. Anything you did **NOT** verify.
