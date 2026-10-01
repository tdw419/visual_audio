# RECEIPT — Can GlyphGPT be the builder? (measured, 2026-09-12)

**Question (Jericho):** could we use GlyphGPT as the builder?
**Method:** audit its training-data plumbing, measure what backfilling buys, and
re-run the acceptance measurement — instead of arguing from the model's size.
**Short answer:** No for the builder/orchestrator role; yes for the narrow
oracle-gated drafter seat it already holds. Details and corrections below.

---

## 1. The model, measured

| property | value |
|---|---|
| parameters | ~838K (`d_model=128`, 4 layers, 4 heads) |
| vocab / opcodes | 77 / 30 |
| output domain | glyph assembly tile text (longest training program 82 tokens) |
| decoding | FSM/grammar-constrained (`generate.GlyphFSM` masks illegal token classes per step) |
| measured standing (GH-24 S3) | **SAFE-ONLY** — best-of-N as one drafting source at **9% first-try** oracle acceptance |
| failure cost | zero — nothing it emits exists until IR verifier → word-exact oracle → table stamp |

It cannot read a roadmap, run git/pytest, call tools, plan multi-phase, or write
Python. Those are not prompt-away gaps; they are outside the architecture.

## 2. Backfill measurement — the corpus is NOT missing tiles

`tools/glyph_gpt/backfill_corpus.py` (written for this experiment; non-destructive —
keeps existing entries verbatim, dedupes by sha256, oracle-PASS only):

```
existing corpus entries: 69 (68 distinct sha256)
collected (repo *.glyph, oracle-verified): 49
  oracle status: pass 36 | syntax_error 4 | no_halt 5 | unknown_dialect 4
oracle-PASS usable tiles: 36
new (not already in corpus): 1        ← backfill buys +1 tile
merged entries: 70
```

**Correction to an earlier claim in this session:** "146 `.glyph` files vs 68
corpus tiles" was wrong — the 146 count included the (now removed) GH-19
worktree's copies. The collectible in-repo inventory is 49 files; the corpus is
already a superset of it, retaining tiles from earlier since-deleted sources.
Backfilling is a dead end.

## 3. The training set is ~1000 programs, and my "starved corpus" read was wrong

`pack_dataset.py` consumes **two** sources:

| source | entries |
|---|---|
| `synth_receipts.jsonl` (5 template families × 200, **all oracle-matched**) | 1000 |
| `corpus.jsonl` (real landed tiles) | 68 |
| total loaded at last pack | 1055 → 1000 packed sequences |

So the model already trains on ~1000 oracle-verified programs. Reading
`corpus.jsonl` alone (68 lines) and concluding "starved" was an over-conclusion on
my part; the synthetic generator (`synth.py`, Phase 3b) is the main data source and
it works (alu_chain / conditional / counted_loop / leaf_call / mem_pass, 200/200
match each).

**Therefore the constraint is capability, not data plumbing.**

## 4. Defect found and fixed while measuring

`python3 tools/glyph_gpt/corpus.py --summary` **crashed** with `KeyError: 'dialect'`:
`corpus.jsonl` mixes four key-shapes, including one metadata-only header line
written by the append-on-admit path (`record_admitted_tile`). Fixed in
`_summary()` — it now counts real tile rows and reports the metadata-only rows
instead of dying. (The collect path and the append path disagreeing on schema is
also part of why the corpus grows so slowly: only agent admissions append, and
there has been exactly one.)

## 5. Verdict and the roles it can actually hold

| role | verdict |
|---|---|
| orchestrator / builder | **No** — no tool use, planning, long context, or Python |
| implementer (the `agy` seat) | **No** — writes glyph tiles, not repo/Python work |
| **tile drafter in the admission pipeline** | **Yes — already does this** (GH-26.3 EMIT→ADMIT: grammar-guided drafting, GlyphGPT best-of-N as one source, oracle as the only door) |
| repair search over rejected tiles | **Yes, in principle** — `escalate.py` already implements the loop |

Levers that could move the acceptance number, cheapest first:
more synthetic families (`synth.py --n`), longer training, model scale
(838K → 10–50M), and keeping the FSM + best-of-N + repair scaffolding. **Acceptance
rate is the gate for granting more authority; commit authority is never on the
table** — that is what makes the drafter seat safe.
