"""R5.1 payload builder — measure + pack the boot chain into glyphos.pyz."""
import gzip, hashlib, io, json, os, sys, tarfile

REPO = "/home/jericho/projects/zion/projects/visual_audio"
os.chdir(REPO)

MODS = [
    "tools/__init__.py",
    "tools/glyph_gpt/__init__.py",
    "tools/glyph_gpt/atlas.py",
    "tools/glyph_gpt/generate.py",
    "tools/glyph_gpt/model.py",
    "tools/glyph_gpt/tokenizer.py",
    "tools/glyph_gpt/agent_resident.py",
    "tools/glyph_gpt/baker.py",
    "tools/glyph_gpt/runner.py",
    "tools/glyph_gpt/fs_v2.py",
    "tools/glyph_gpt/posix_shim.py",
    "tools/glyph_gpt/gh22_driver_abi.py",
    "tools/glyph_gpt/libc_runtime.py",
    "tools/rv64i_to_glyph.py",
    "tools/rv64i_decode.py",
    "tools/glyph_isa_v2.py",
    "tools/glyph_ir.py",
    "tools/geos_aspace.py",
    "tools/wordbase.py",
    "tools/wgsl_glyph_isa_v2.py",
    "db/wordbase.db",
]

missing = [m for m in MODS if not os.path.exists(m)]
if missing:
    print("MISSING:", missing)
    sys.exit(2)

raw = sum(os.path.getsize(m) for m in MODS)
manifest = {}
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w") as tf:
    for m in MODS:
        data = open(m, "rb").read()
        manifest[m] = hashlib.sha256(data).hexdigest()
        info = tarfile.TarInfo(m)
        info.size = len(data)
        import time as _t
        info.mtime = int(_t.time())
        tf.addfile(info, io.BytesIO(data))
tar = buf.getvalue()
gz = gzip.compress(tar, 9)
mj = json.dumps(manifest, sort_keys=True).encode()
gzj = gzip.compress(mj, 9)

out = ".builder_queue/payload_r51.tar.gz"
with open(out, "wb") as f:
    f.write(gz)
with open(".builder_queue/payload_r51_manifest.json", "wb") as f:
    f.write(gzj)

print(f"modules={len(MODS)} raw={raw/1e6:.1f}MB tar={len(tar)/1e6:.1f}MB "
      f"gz={len(gz)/1e6:.2f}MB manifest_sha256={hashlib.sha256(gz).hexdigest()[:16]}")
print("wrote", out, "and payload_r51_manifest.json")
