# Cross-Lingual Synthesis in Visual Audio

Visual Audio now supports cross-lingual phoneme synthesis using the `phonemizer` package with the `espeak` backend, expanding support beyond the default CMUdict English pipeline.

## Pipeline Architecture

1. **Text Input**: User specifies language via `--lang` (e.g. `es`, `de`, `fr-fr`).
2. **Phonemization**: `phonemizer` (via `EspeakBackend`) converts the foreign text into standard IPA (International Phonetic Alphabet) phonemes.
3. **IPA to ARPAbet Mapping**: `tools/ipa_to_arpabet.py` maps the generated IPA characters to our supported ARPAbet templates.
4. **Synthesis**: The existing `build_word_project_with_crossfade` stitches the mapped ARPAbet phonemes together with 5ms neural crossfades.

## Supported Language Codes (Espeak)

The `--lang` flag accepts standard espeak language codes. Common supported languages include:
- `en-us`: English (US) — defaults to the high-fidelity CMUdict path
- `es`: Spanish
- `fr-fr`: French (France)
- `de`: German
- `pt-br`: Portuguese (Brazil)

## Coverage Gaps and Voicing Fallbacks

The synthesis engine is currently constrained by our ARPAbet envelope templates, which were designed for American English. When synthesizing foreign languages, several approximations are made:

- **Vowels**: Foreign vowels without direct English equivalents are mapped to the closest ARPAbet sound. For example, French nasal vowels (`ã`, `õ`) are mapped to their non-nasal equivalents (`AA`, `OW`). The Spanish trilled `r` maps to the English alveolar approximant `R`.
- **R-Colored Vowels**: Words with `ʁ` (French) or `ʀ` (German) are approximated using English `R` or `HH`, which can sound unnatural.
- **Tonal Languages**: Mandarin and other tonal languages are not yet supported, as our ARPAbet envelopes do not encode pitch contours dynamically.

## Usage

To use cross-lingual synthesis via the CLI:

```bash
# Spanish
python3 tools/speak.py say "hola mundo" --lang es

# French
python3 tools/speak.py say "bonjour" --lang fr-fr

# German
python3 tools/speak.py say "hallo welt" --lang de
```
