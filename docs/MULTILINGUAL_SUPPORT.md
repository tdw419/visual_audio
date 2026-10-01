# Approximate Multilingual Support

## Overview

Visual Audio now supports approximate multilingual pronunciation via the [phonemizer](https://github.com/bootphon/phonemizer) library and XSAMPA→ARPAbet mapping.

## How It Works

1. **Phonemizer** generates XSAMPA phonemes for foreign words
2. **XSAMPA→ARPAbet** mapping converts to our 39-phoneme template set
3. **ARPAbet tiles** render the word using existing phoneme envelopes

This gives English-ish approximations for foreign words (Spanish, French, German, etc.).

## Installation

```bash
pip install phonemizer
```

## Usage

### In Python Code

```python
import sys
sys.path.insert(0, 'tools')
from wordbase_compat import connect, word_id

db = connect()

# Spanish word
hola_id = word_id(db, 'hola', {}, lang='es')

# French word
bonjour_id = word_id(db, 'bonjour', {}, lang='fr')

# German word
hallo_id = word_id(db, 'hallo', {}, lang='de')
```

### From Command Line

```bash
# Speak Spanish text
python3 tools/speak.py say "hola mundo" --lang es

# Speak French text
python3 tools/speak.py say "bonjour le monde" --lang fr

# Speak German text
python3 tools/speak.py say "hallo welt" --lang de
```

## Example Pronunciations

| Word | Language | XSAMPA | ARPAbet | Notes |
|------|----------|--------|---------|-------|
| hola | Spanish | oU l A | OW L AA | /o/ → OW (approx), /a/ → AA |
| mundo | Spanish | m u n d o | M UW N D OW | Standard mapping |
| bonjour | French | b o~ Z u r | B AO N ZH UW R | /o~/ → AO (approx), nasal /~/ → NG (approx) |
| merci | French | m E R s i | M EH R S IY | /ɛ/ → EH, /i/ → IY |

## Limitations

### ARPAbet Ceiling

Our tile system is built on ARPAbet (English phonemes). Some foreign sounds don't have direct ARPAbet equivalents:

- **Mandarin tones:** No ARPAbet mapping (tone information lost)
- **Arabic pharyngeals:** No ARPAbet mapping (approximated as similar consonants)
- **French nasals:** Approximated (e.g., /ɔ̃/ → AO NG)

This is **approximate** multilingual, not faithful. For faithful multilingual, you'd need:

1. Expanded phoneme inventory beyond ARPAbet
2. New tile templates for each phoneme
3. Larger UPIC envelope collection

### Silent Fallback

If phonemizer is not installed, the system silently falls back to grapheme pronunciation (uppercase letters). This preserves functionality but loses multilingual support.

## Testing

```bash
# Run multilingual tests
python3 tools/test_multilingual.py

# Verify XSAMPA→ARPAbet mapping
python3 tools/xsampa_to_arpabet.py
```

## Priority Order

`word_id()` checks in this order:

1. **Deterministic symbol table** (operators, numbers)
2. **CMUdict** (English words)
3. **Phonemizer** (foreign words, lang parameter)
4. **Grapheme fallback** (last resort)

## Future Work

1. **Faithful multilingual:** New phoneme inventory + tile templates for non-English sounds
2. **Tone preservation:** Mechanism to encode tone information (e.g., Mandarin)
3. **Language detection:** Auto-detect language from text context
4. **Translations table:** Link words across languages (concept-based, not per-column)

## Files Modified

- `tools/wordbase_compat.py` — Added `_try_phonemizer()` and `lang` parameter
- `tools/xsampa_to_arpabet.py` — NEW: XSAMPA→ARPAbet mapping table
- `tools/test_multilingual.py` — NEW: Multilingual integration tests
- `docs/TOKENIZER_STATE.md` — Updated with multilingual integration status

## Related

- [TASK_G2P002 Report](../.hermes/TASK_G2P002_report.md) — Original phonemizer infrastructure
- [Phoneme Architecture](./PHONEME_ARCHITECTURE.md) — ARPAbet template definitions
- [TOKENIZER_STATE.md](./TOKENIZER_STATE.md) — Overall tokenizer and wordbase status