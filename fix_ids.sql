ATTACH 'voicebook/wordbase.db' AS vb;
PRAGMA foreign_keys=off;
BEGIN TRANSACTION;

CREATE TABLE words_new AS SELECT * FROM words WHERE 0;
INSERT INTO words_new SELECT * FROM words;

UPDATE words_new
SET id = (SELECT id FROM vb.words WHERE vb.words.word = words_new.word)
WHERE EXISTS (SELECT 1 FROM vb.words WHERE vb.words.word = words_new.word);

DROP TABLE words;
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
);
CREATE INDEX idx_word ON words(word);
CREATE INDEX idx_pos ON words(pos);
CREATE INDEX idx_frequency ON words(frequency DESC);
CREATE TRIGGER update_timestamp 
AFTER UPDATE ON words
BEGIN
    UPDATE words SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

INSERT INTO words SELECT * FROM words_new;
DROP TABLE words_new;

COMMIT;
