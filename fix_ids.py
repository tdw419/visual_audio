import sqlite3

db = sqlite3.connect('db/wordbase.db')
db.execute("ATTACH 'voicebook/wordbase.db' AS vb")

db.execute("BEGIN TRANSACTION")

# Read all old words
old_words = db.execute("SELECT word, pronunciation, image_path, image_link, pos, definition, examples, frequency, created_at, updated_at, color_hex FROM words").fetchall()

# Read all VB ids
vb_ids = dict(db.execute("SELECT word, id FROM vb.words").fetchall())

db.execute("DROP TABLE words")
db.execute("""
CREATE TABLE words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL UNIQUE COLLATE NOCASE,
    pronunciation TEXT NOT NULL,
    image_path TEXT,
    image_link TEXT,
    pos TEXT NOT NULL,
    definition TEXT,
    examples TEXT,
    frequency INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    color_hex TEXT
)
""")

# Find max VB id
max_vb_id = max(vb_ids.values()) if vb_ids else 0
next_id = max_vb_id + 1

for row in old_words:
    word = row[0]
    if word in vb_ids:
        new_id = vb_ids[word]
    else:
        new_id = next_id
        next_id += 1
        
    db.execute(f"INSERT INTO words (id, word, pronunciation, image_path, image_link, pos, definition, examples, frequency, created_at, updated_at, color_hex) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (new_id,) + row)

db.execute("CREATE INDEX idx_word ON words(word)")
db.execute("CREATE INDEX idx_pos ON words(pos)")
db.execute("CREATE INDEX idx_frequency ON words(frequency DESC)")
db.execute("""
CREATE TRIGGER update_timestamp 
AFTER UPDATE ON words
BEGIN
    UPDATE words SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END
""")

db.execute("COMMIT")
print("Done fixing all IDs!")
