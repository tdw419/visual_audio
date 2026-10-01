"""DEFECT-26 probe: does the failing test's verdict depend on PYTHONHASHSEED?
Runs the exact temp_wordbase fixture data through build_embeddings and
test_pixel_embeddings_feature_integration's assertion across seeds.
"""
import sys, os, tempfile, sqlite3, contextlib
sys.path.insert(0, 'src')
import numpy as np
from pixel_embeddings import PixelEmbeddings

WORDS = [
    ("embed_test", "T EH S T", "#508F6B", "noun", "A procedure", 1000),
    ("embed_best", "B EH S T", "#609F7B", "adjective", "Highest quality", 900),
    ("embed_rest", "R EH S T", "#70AF8B", "noun", "Repose", 800),
    ("embed_visual", "V IH ZH UH L", "#50FB6B", "adjective", "Relating to sight", 1000),
    ("embed_optical", "AA P T IH K AH L", "#40EA5A", "adjective", "Relating to vision", 900),
    ("embed_audio", "AO D IY OW", "#A5CA50", "noun", "Sound", 1000),
    ("embed_code", "K OW D", "#20B2AA", "noun", "Programming", 1000),
]

def make_db():
    fd, p = tempfile.mkstemp(suffix=".db")
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT NOT NULL UNIQUE COLLATE NOCASE,
        pronunciation TEXT NOT NULL,
        color_hex TEXT, pos TEXT NOT NULL,
        definition TEXT, frequency INTEGER DEFAULT 0)''')
    cur.executemany("INSERT INTO words (word, pronunciation, color_hex, pos, definition, frequency) VALUES (?,?,?,?,?,?)", WORDS)
    conn.commit()
    return p, conn

p, conn = make_db()
emb = PixelEmbeddings(p)
matrix = emb.build_embeddings(max_vocab=100)
center = np.mean(matrix, axis=0, keepdims=True)
distances = np.linalg.norm(matrix - center, axis=1)
std = float(np.std(distances))
print(f"PYTHONHASHSEED={os.environ.get('PYTHONHASHSEED','<random>')}: shape={matrix.shape} std(distances)={std!r} -> {'PASS' if std > 0 else 'FAIL'}")
conn.close()
os.unlink(p)
