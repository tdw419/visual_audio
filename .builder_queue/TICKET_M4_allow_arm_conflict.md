# TICKET — M4 vs landed `_l2_list` allow-arm design conflict

Filed: 2026-09-24 ~08:2x CDT (builder af3e62239ce2, L3 sub-step 1 tick)
Severity: gate-contract conflict, pre-existing at HEAD a47043dd

## Symptom

tests/test_l2_files_0x13_migration.py::test_m4_env_unset_refuses_not_falls_back
FAILS at clean HEAD a47043dd. Verified twice: git stash → run → FAIL →
stash pop → run → FAIL. NOT introduced by the L3 `>` redirect work.

## Root cause chain (measured, /tmp trace script)

1. M4 (tests/test_l2_files_0x13_migration.py:127-133) `delenv`s
   GLYPH_FS_ALLOW and expects `ls` to return ERR (deny-by-default
   propagating through the 0x13 arm's rc -1).
2. The landed sub-step-2 `_l2_list` (experiments/glyph_l1_shell.py,
   lines ~374-380 at HEAD) RE-ARMS the env var with the session root on
   EVERY listing call (append-only policy: "the shell NARROWS nothing
   it did not itself grant"), BEFORE the engine reads it
   (glyph_isa_v2.py:577-592 `_get_fs_allow_roots`).
3. Result: after delenv, `ls` still lists (FILE_LIST: 3 entries), M4's
   `out.startswith("ERR")` trips. The env var ends up re-set to the
   session root — matching the code comment's stated policy, and
   contradicting the test's expectation, simultaneously.

## The conflict, stated plainly

- Landed code policy: the SHELL is trusted to arm its own root
  (container model, sub-step-3's mkdir/rmdir share it —
  `_arm_fs_allow` at :529-541).
- Test policy: the ENV is the authority; unset must refuse even for
  the shell (host-fallback guard as written).
Both cannot hold. One is wrong. That is Jericho's call (or a ruling),
not a silent fix: option (a) re-scope M4 to poison the ROOTS FUNCTION
rather than the env var (keeps the deny-by-default proof, drops the
env-var expectation); option (b) stop re-arming in `_l2_list` (makes
delenv meaningful again, but then the shell must be launched with
GLYPH_FS_ALLOW pre-set — changes the landed UX contract and D-legs
depend on self-arming); option (c) split: keep re-arming for mkdir/
rmdir's containment but have the 0x13 listing honor "env ABSENT at
shell construction time" as a launch-time deny.

## Rule-4 note

The landed sub-step-2 receipt's GREEN was real — M4 passed then. What
changed: nothing in code; the test has been failing at HEAD since the
cwd/A6 work OR since a conftest/env ordering shift in how tests run
in-process (the re-arm persists for the process lifetime; pytest's
module ordering determines whether M4 sees a pre-armed env). That
ORDER-DEPENDENCE is itself part of the defect: M4 passes or fails
depending on which other tests ran first in the same process.

## Disposition

Not fixed in the L3 sub-step 1 commit (separate gate-able decision;
options above cheapest-first). Lane proceeds on L3; M4 stays RED and
named in every receipt until ruled.
