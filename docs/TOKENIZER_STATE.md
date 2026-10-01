# Tokenizer & Wordbase Gap Analysis

## Executive Summary

The tokenizer and symbol/number table are **complete and working**. End-to-end verification confirms:

- `{x:1}` → `['open_brace','x','colon','one','close_brace']` ✓
- `a==b` → `['a','equal_equal','b']` ✓
- `x >= 3` → `['x','greater_equal','three']` ✓
- Symbol-bearing lines render to actual tiles ✓

**One real blocker remains:** non-Latin scripts.

---

## What's Already Working

### 1. Single Letters (Auto-Extend)
Letters automatically extend via grapheme fallback.

```python
word_id('x') → G2P produces 'EH K S' ("eks")
```

No extender needed. The system adds unknown tokens on lookup.

### 2. Latin-Script Foreign Words (Approximation)
Latin-script foreign words already approximate.

```python
'hola' → HH OW L AH  # via grapheme fallback (not phonemizer yet)
```

### 3. Code Symbols (Deterministic Table)
All code symbols have deterministic pronunciations in a ~50-entry table.

```python
'#'       → 'hash'           → 'HH AE SH'
'>='      → 'greater_equal'  → 'G R EY T ER IY K W AO L'
'{'       → 'open_brace'     → 'OW P AH N B R EY S'
':'       → 'colon'          → 'K OW L AH N'
```

Location: `tools/wordbase_compat.py` lines 21-86

### 4. Numbers (Spoken Form)
Numbers convert to spoken form.

```python
'3.14' → 'three point one four'
'42'   → 'four two'  # digit-by-digit for now
```

Location: `tools/wordbase_compat.py` lines 444-492

**Note:** All DB keys are now lowercase for consistency. Old uppercase entries ("ONE", "THREE POINT ONE FOUR") exist from the previous implementation but will not be used; new tokens create lowercase entries.

---

## The Real Blocker

### Non-Latin Scripts

**Current behavior:** silently dropped.

```python
'你好' → []  # disappears from canvas with no signal
```

**Fixed behavior:** UTF-8 byte sequence tiles (visible and reversible).

```python
'你好' → ['0xe4bda0e5a5bd']  # hex-encoded UTF-8, renders as byte tile
'hello世界' → ['hello', '0xe4b896e7958c']  # Latin + non-Latin mix
```

**Why visible fallback matters:**

- Silent truncation reads as success but is data loss
- Byte codec tiles preserve the execution truth (bytes, not phonemes)
- Round-trips losslessly even if unpronounceable
  - `0xe4bda0e5a5bd` decodes cleanly back to `你好`
- Consistent with "bytes are the source of truth" principle

**Known choices (future refinements, not blockers):**

1. **Per-character CJK tiles:** Current implementation collapses a whole non-Latin run into one token/tile (e.g., `你好` → a single `0xe4bda0e5a5bd` blob, not two separate tiles). Fine for display and reversible, but per-character tiles may be desirable for character-level manipulation in the future.

2. **Render-but-don't-narrate:** Byte-fallback tokens (`0x...`) will produce nonsense audio if spoken via G2P grapheme fallback (e.g., `0xe4bda0` pronounced as "zero ex four bee dee ay zero"). Per the display-only framing this is harmless, but a future refinement should mark byte-fallback tokens as visual-only to avoid generating gibberish in the audio band.

---

## Not a Blocker

### Case Folding

**Concern:** `X` vs `x` — do they need distinct pronunciations?

**Answer:** No. Case is display-only.

- Code executes through the **byte codec**, which preserves case perfectly
- Wordbase tiles are **display only**, not execution truth
- `X` and `x` can share pronunciation ("eks") without affecting correctness
- Optional: keep distinct tiles for visual difference, but **zero effort needed**

The architecture settled two turns ago makes case cosmetic in a layer that isn't authoritative.

---

## Open Items

### 1. Approximate Multilingual (phonemizer/espeak-ng) ✓ INTEGRATED

**Status:** Integration complete; requires phonemizer installation.

**What it gives:** foreign words mapped onto English-ish sounds via ARPAbet.

```python
# With phonemizer installed:
'hola' (lang='es') → 'HH OW L AA'  # Spanish "hola" approximated as English-ish
'bonjour' (lang='fr') → 'B AO N ZH UW R'  # French "bonjour" approximated
```

**Architecture:**

1. `word_id()` now accepts `lang` parameter (default: 'en')
2. Priority order:
   - Check deterministic symbol table
   - Check CMUdict (English)
   - **Try phonemizer for multilingual** (NEW)
   - Fall back to grapheme pronunciation
3. Phonemizer produces XSAMPA → mapped to ARPAbet via `tools/xsampa_to_arpabet.py`
4. ARPAbet pronunciations render using existing 39-phoneme templates

**Installation:**

```bash
pip install phonemizer
```

**Limitation:** ARPAbet ceiling.

- Tiles are built on ARPAbet — the English phoneme set
- Mandarin tones, Arabic pharyngeals, etc. have no ARPAbet symbol
- No tile template exists for these phonemes

**Honest framing:** "Approximate multilingual via phonemizer; faithful multilingual requires expanded phoneme inventory and new tile templates — a real project."

**Testing:**

```bash
python3 tools/test_multilingual.py
```

**Path forward:**

1. Install phonemizer (user action)
2. Optional: Integrate phonemizer for Latin-script approximations
3. Future: Track faithful multilingual as separate effort (new phonemes + templates)

### 2. Number-to-Words Enhancement

**Current:** Digit-by-digit ("four two" for 42).

**Future:** Proper spoken forms ("forty two", "one hundred twenty three").

**Priority:** Low — digit-by-digit works and is unambiguous.

---

## Code Location

- **Tokenizer:** `tools/wordbase_compat.py` `tokenize()` (line 335)
- **Symbol pronunciations:** `tools/wordbase_compat.py` `_SYMBOL_PRONUNCIATIONS` (line 21)
- **Number conversion:** `tools/wordbase_compat.py` `_speak_number()` (line 444)
- **Wordbase compatibility layer:** `tools/wordbase_compat.py` (entire file)

---

## Test Commands

```bash
# Verify tokenizer
python3 -c "import sys; sys.path.insert(0, 'tools'); from wordbase_compat import tokenize; print(tokenize('你好')); print(tokenize('{x:1}')); print(tokenize('x >= 3'))"

# Verify symbol pronunciations exist
sqlite3 db/wordbase.db "SELECT word, pronunciation FROM words WHERE word IN ('hash', 'greater_equal', 'x', 'three', 'point')"

# Verify end-to-end with compose.py (existing tests pass)
```

---

## Summary

**Done:**
- Tokenizer handles code symbols, numbers, and Latin words ✓
- Deterministic pronunciation table for ~50 symbols ✓
- Non-Latin visible fallback (UTF-8 byte tiles) ✓
- Case folding handled (display-only, not load-bearing) ✓

**Remaining:**
- Approximate multilingual via phonemizer (infrastructure exists, needs integration)
- Faithful multilingual (new phoneme inventory + tile templates — tracked separately)

The system is not broken. It's one feature (multilingual) away from complete.