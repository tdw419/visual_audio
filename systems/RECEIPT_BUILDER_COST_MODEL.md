# RECEIPT — Builder-loop cost model, corrected by measurement (2026-09-12)

**Why:** two cost claims were made in this session and both were wrong. This records
what the log actually says, so the next session starts from numbers rather than from a
plausible-sounding model.

## Claim 1 (wrong): "the fixed prompt is ~56K tokens, so trim the skills index"

Measured per run instead of inferred from a session default:

```
real orchestrator runs today : 21
calls per run                : min 13, median 61, max 150   (1,443 calls total)
FIRST call input             : median 13,408 tokens   <- the actual fixed prompt cost
LAST call input              : median 136,958 tokens   <- growth during the run
total input today            : 155.2M
```

The cron path's fixed prompt is **~13K tokens, not 56K** (the 56K figure came from
`hermes prompt-size` on an interactive CLI session, which injects the whole skills index
and every tool schema — the cron job does not). So trimming the skills index would have
bought ~nothing. Corollary: `enabled_toolsets: [terminal, file]` was still worth doing,
but the "56K × 1,366 calls" arithmetic that motivated a context diet was fiction.

## Claim 2 (wrong): "widen the cadence 2min → 5min for a >60% spend cut"

```
today's cron output files        : 50
  of which no_change/suppressed  : 19   <- these make ZERO API calls
real runs (agent invoked)        : 21
API calls                        : 1,443   -> ~61 calls per real run
```

Suppressed ticks short-circuit before the model is invoked, so cadence governs how often
a cheap local check runs — not how often we pay. Widening the cadence would cut monitor
checks by 60% and API spend by roughly nothing, while slowing reaction to change events.
The "60%" figure assumed linear cost per fire; the cost is per real run.

## What the cost actually is

```
input     155.2M   of which CACHED 153.4M (98.8%)
uncached    1.8M   <- full input rate
output      0.9M   <- output rate
```

So the billable structure is dominated by **cache reads on a context that grows
monotonically within each run**. Every tool result is appended and re-sent on every
subsequent call, so a 61-call run that grows 13K → 137K costs the integral — the five
largest runs today account for ~83M of the 155M (~53%).

## The lever that follows from the measurement

**Bound the growth curve, not the fixed prompt.**

1. *Cheaper tool outputs* — read tails, not whole logs; targeted greps; no full-file
   dumps; no re-reading unchanged files. Directly flattens the curve.
2. *Bounded runs* — a run past ~40 tool calls that is still red should write its RED
   evidence, file the ticket and hand off, because the marginal call costs more than the
   first one and the loop's value is in landed work, not in finishing inside one session.

Both are now clauses in the orchestrator prompt (`CONTEXT ECONOMY`), and both are
measurable on the next runs by the same per-run first/last-call measurement above — the
metric to watch is **median last-call input**, currently 136,958.

## What was NOT claimed

- No dollar figure: the token structure is exact, but current provider rates could not be
  fetched (the session's web tools are misconfigured — `hermes tools` names a provider
  `starlette` with no registered backend). Compute the bill from the four numbers above
  once rates are available: 153.4M cache-read + 1.8M uncached + 0.9M output per day.
- No claim that the loop is wasteful: it closed BK-11, BK-12, BK-14 and several docs
  increments today while running on a quota-fallback provider. The point of this receipt
  is that the *shape* of the cost was misdescribed, not that the work was.
