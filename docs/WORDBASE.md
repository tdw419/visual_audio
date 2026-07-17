# Visual Audio Wordbase

Maps words to their visual audio representations (spectrograms, pronunciations, etc.).

## Database Schema

### Tables

#### `words` (Main word entries)
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

#### `phrases` (Multi-word collocations/idioms)
- `id`, `phrase`, `pronunciation`, `image_path`, `image_link`
- `definition`, `examples`, `frequency`
- `created_at`, `updated_at`

#### `spectrogram_cache` (Pre-generated spectrograms)
- `word_id` - Foreign key to words table
- `spectrogram_bytes` - BLOB of PNG spectrogram
- `codec_version` - Codec version identifier
- `created_at`, `updated_at` - Timestamps

### Indexes
- `idx_word` on words(word)
- `idx_pos` on words(pos)
- `idx_frequency` on words(frequency DESC)
- `idx_phrase` on phrases(phrase)

## Usage

### Initialize database
```bash
# Database already created at db/wordbase.db
python3 tools/wordbase.py init
```

### Import from CMUdict
```bash
# Import all words (~130k)
python3 tools/wordbase.py import --cmudict data/cmudict.dict

# Test with limited import
python3 tools/wordbase.py import --cmudict data/cmudict.dict --limit 1000
```

### Look up a word
```bash
python3 tools/wordbase.py lookup --word hello
```

### Batch process words from stdin
```bash
echo -e "hello\nworld\ntest" | python3 tools/wordbase.py batch
```

### Export wordlist
```bash
# TSV format
python3 tools/wordbase.py export --output wordlist.tsv --format tsv

# JSON format
python3 tools/wordbase.py export --output wordlist.json --format json
```

## Python API

```python
from tools.wordbase import WordbaseManager

# Connect to database
wb = WordbaseManager()

# Add a word manually
word_id = wb.add_word(
    word="hello",
    pronunciation="HH EH L OW",
    pos="interjection",
    definition="A greeting",
    examples=["Hello, world!"],
    frequency=5000
)

# Look up a word
result = wb.get_word("hello")
print(result['pronunciation'])  # "HH EH L OW"

# Get pronunciation only (fast)
pron = wb.get_pronunciation("hello")

# Add a multi-word phrase
wb.add_phrase(
    phrase="good morning",
    pronunciation="G UH D M AO R N IH NG",
    definition="A greeting used in the morning"
)

# Cache a spectrogram
with open('hello_spectrogram.png', 'rb') as f:
    wb.cache_spectrogram(word_id, f.read())

# Get cached spectrogram
spec_bytes = wb.get_cached_spectrogram(word_id)

# Import from CMUdict
wb.import_cmudict(limit=1000)  # Test with 1000 words
wb.import_cmudict()  # Import all

# Export
wb.export_wordlist(Path('output.tsv'), format='tsv')

wb.close()
```

## Integration with Visual Audio

### Convert text to visual audio
```python
# Split text into words
text = "hello world"
words = text.lower().split()

# Get pronunciations from wordbase
pronunciations = []
for word in words:
    pron = wb.get_pronunciation(word)
    if pron:
        pronunciations.append(pron)
    else:
        # Fallback to TTS or phoneme-to-grapheme
        pass

# Generate spectrograms using codec
# (TODO: integrate with existing spectrogram generation)
```

### Batch word processing
```python
# Process top 1000 most frequent words
cursor = wb.conn.execute("SELECT word FROM words ORDER BY frequency DESC LIMIT 1000")
for row in cursor:
    word = row[0]
    # Generate spectrogram and cache it
    # ...
```

## Future Enhancements

1. **Spectrogram generation**: Automatically generate spectrograms when words are added
2. **TTS fallback**: Use text-to-speech for words not in CMUdict
3. **Frequency ranking**: Import corpus frequency data (Google N-grams, etc.)
4. **Phrase collocations**: Detect and import common multi-word expressions
5. **API server**: Expose wordbase via HTTP for remote lookup
6. **Offline mode**: Pre-generate all spectrograms for offline use

## Database Location
`db/wordbase.db` (SQLite)