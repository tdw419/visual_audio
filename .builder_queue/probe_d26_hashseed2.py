"""DEFECT-26 probe 2: test_pixel_embeddings_neighbors assertions across PYTHONHASHSEED."""
import sys, os, tempfile, sqlite3
sys.path.insert(0, 'src')
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
emb.build_embeddings(max_vocab=100)

n1 = [n[0] for n in emb.get_neighbors("embed_test", k=3)]
a1 = any(w in ("embed_best", "embed_rest") for w in n1)
n2 = [n[0] for n in emb.get_neighbors("embed_visual", k=3)]
a2 = "embed_optical" in n2
print(f"PYTHONHASHSEED={os.environ.get('PYTHONHASHSEED','<random>')}: "
      f"test_neighbors(test)={n1} assert1={'PASS' if a1 else 'FAIL'} | "
      f"test_neighbors(visual)={n2} assert2={'PASS' if a2 else 'FAIL'} -> "
      f"{'PASS' if (a1 and a2) else 'FAIL'}")
conn.close()
os.unlink(p)
