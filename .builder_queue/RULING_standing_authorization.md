# RULING — standing authorization: mechanism-class vs policy-class

**Date:** 2026-09-13 · **Seat:** orchestrator · **Status:** AUTHORIZED (reviewer affirmed) · Jericho may override

## The standing rule

The lane DECIDES mechanism-class items and proceeds without holding. Anything policy-class still comes to the seat.

### AUTHORIZED — mechanism-class (lane decides, no hold)
- restoring self-documented behaviour
- missing fixtures and path unanchoring
- stub syscall completions
- environment skip-with-reason
- two-phase collect/run harness flow

### RESERVED — policy-class (seat decides, ticket + hold)
- changing ISA translation semantics
- setting global memory/pfn ceilings
- redefining fault vocabularies
- altering ABI register layout
- deleting tests to achieve green

## Ticket rulings (same date)

- **SUITE-FIX-1 wordbook drift → Option (a).** The ISA claim (GlyphCPUv2 reads pixel colours from texture memory, no host dictionary) is orthogonal to DB colour churn. Query the live colours for the test IDs, or build a synthetic fixture in tmp_path. Do not freeze historical hash constants.
- **Cluster 4 → environment-dependent.** Live-service tests (e.g. test_ollama_contextual_memory_simple) get `@pytest.mark.live_smoke` or `skipif(not _ollama_available(), reason="Ollama daemon offline")`. Offline service failures are NEVER code regressions and are NEVER papered over with empty mocks.
- **Allowlist budgets → approved, parallel-aware.** test_pixel_lm_train: 80s solo / ~240s at `-w 4`. xv6 + stval go in a dedicated heavy-emulation tier, not the 150s unit gate; the tier number is locked only after a completed run at a raised budget (in flight).

## Tickets answered by this ruling (so the seat-blocker sensor stops re-reporting them)

- REPAIR_PENDING_suite_fix1_wordbook_db_drift.md → Option (a): dynamic/scratch fixture, never frozen hashes
