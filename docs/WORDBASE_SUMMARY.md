# Wordbase Database - Summary

**Created:** 2026-07-15
**Purpose:** Map AI text output to visual audio representations

## What Was Built

### 1. SQLite Database (`db/wordbase.db`)
**Schema includes:**
- `words` table - Primary word entries with pronunciation, part of speech, definition, examples, frequency
- `phrases` table - Multi-word collocations/idioms
- `spectrogram_cache` table - Pre-generated spectrograms (BLOB storage)
- Indexes on word, pos, frequency for fast lookup
- Auto-updating timestamps

**Columns in `words`:**
- `id` - Primary key
- `word` - The word (case-insensitive unique)
- `pronunciation` - CMU ARPAbet format (e.g., "HH EH L OW")
- `image_path` - Local path to spectrogram PNG
- `image_link` - URL to remote image (fallback)
- `pos` - Part of speech (noun, verb, adjective, etc.)
- `definition` - Dictionary definition
- `examples` - JSON array of example sentences
- `frequency` - Corpus frequency (for prioritization)
- `created_at`, `updated_at` - Timestamps

### 2. Wordbase Manager (`tools/wordbase.py`)
**Features:**
- Add words with pronunciation, definition, part of speech
- Look up words (case-insensitive)
- Get pronunciation only (fast lookup)
- Add multi-word phrases
- Cache spectrograms for words
- Import from CMUdict (when available)
- Batch processing from stdin
- Export to TSV or JSON

**CLI Usage:**
```bash
# Initialize
python3 tools/wordbase.py init

# Import from CMUdict
python3 tools/wordbase.py import --cmudict data/cmudict.dict --limit 1000

# Look up a word
python3 tools/wordbase.py lookup --word hello

# Batch process from stdin
echo -e "hello\nworld\ntest" | python3 tools/wordbase.py batch

# Export
python3 tools/wordbase.py export --output wordlist.tsv --format tsv
```

### 3. Text-to-Visual-Audio Integration (`tools/text_to_visual_audio.py`)
**Features:**
- Convert text to visual audio using Wordbase
- Fallback to CMUdict for missing words
- Use existing word_compiler pipeline for audio generation
- Concatenate word audio segments
- Save as WAV file

**CLI Usage:**
```bash
# Convert text
python3 tools/text_to_visual_audio.py "hello world test visual audio"

# From stdin
echo "visual audio code" | python3 tools/text_to_visual_audio.py --stdin

# Custom output
python3 tools/text_to_visual_audio.py "test" --output my_output.wav

# Skip Wordbase (use CMUdict only)
python3 tools/text_to_visual_audio.py "test" --no-wordbase
```

### 4. Test Suite (`test_wordbase.py`)
**Tests:**
- Add sample words to Wordbase
- Verify word lookup works
- Test case-insensitive lookup
- Test pronunciation-only lookup

**Run:**
```bash
python3 test_wordbase.py
```

## How It Works

### Pipeline: AI Text → Visual Audio
1. **Parse text into words**
2. **Lookup pronunciation in Wordbase** (fast, local SQLite)
3. **Fallback to CMUdict** if Wordbase doesn't have the word
4. **Convert phonemes to audio** using existing word_compiler
5. **Concatenate word segments** into full audio
6. **Save as WAV** (visual audio representation)

### Example Output
```
Input: hello world test visual audio

Processing 5 words...
  ✓ hello (HH EH L OW) [Wordbase]
  ✓ world (W ER L D) [Wordbase]
  ✓ test (T EH S T) [Wordbase]
  ✓ visual (V IH ZH UH L) [Wordbase]
  ✓ audio (AO D IY OW) [Wordbase]

Generating audio...

✓ Saved to: output_demo.wav
  Duration: 0.51s
```

## Database Status
- **Location:** `/home/jericho/projects/zion/projects/visual_audio/db/wordbase.db`
- **Sample words added:** 6 (hello, world, test, visual, audio, code)
- **Tables:** words, phrases, spectrogram_cache
- **Indexes:** word, pos, frequency

## Next Steps

1. **Import full CMUdict:** `python3 tools/wordbase.py import --cmudict data/cmudict.dict` (when CMUdict is available)
2. **Add definitions/examples:** Enhance with dictionary data
3. **Frequency ranking:** Import corpus frequency for prioritization
4. **Spectrogram caching:** Pre-generate and cache spectrograms for common words
5. **Phrase support:** Add common multi-word expressions
6. **API server:** Expose Wordbase via HTTP for remote lookup

## Files Created
- `db/wordbase.db` - SQLite database
- `tools/wordbase.py` - Database manager
- `tools/text_to_visual_audio.py` - Text-to-audio converter
- `test_wordbase.py` - Test suite
- `docs/WORDBASE.md` - Documentation

## Verified Working
- ✓ Database initialization
- ✓ Add/lookup words
- ✓ Case-insensitive lookup
- ✓ Text-to-visual-audio conversion
- ✓ Wordbase → CMUdict fallback
- ✓ WAV generation using word_compiler