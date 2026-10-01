"""HOLD tick maildrop staleness check (cron af3e62239ce2)."""
from pathlib import Path
import hashlib, time

REPO = Path('/home/jericho/projects/zion/projects/visual_audio')
md = REPO / '.geos/maildrop'
img = md / 'kernel_memory.npy'
if img.exists():
    st = img.stat()
    age = time.time() - st.st_mtime
    md5 = hashlib.md5(img.read_bytes()).hexdigest()
    print("img md5", md5[:8], "mtime_age_s", round(age, 1))
else:
    print("img absent")
c = md / 'content'
if c.exists():
    files = sorted(c.glob('*'))
    print("content files:", len(files))
    for p in files:
        h = hashlib.md5(p.read_bytes()).hexdigest()
        print(h[:8], p.name, "age_s", round(time.time() - p.stat().st_mtime, 1))
else:
    print("content dir absent:", c)
