#!/usr/bin/env python3
"""R5.1 build step 1 — embed the payload into the installer.

Usage: python3 .builder_queue/embed_r51.py
Writes glyphos_installer.py at the repo root: ONE self-contained file with
the launcher head + base64 gzipped payload + base64 gzipped sha256 manifest.
"""
import base64
import gzip
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAYLOAD = REPO / ".builder_queue" / "payload_r51.tar.gz"
MANIFEST = REPO / ".builder_queue" / "payload_r51_manifest.json"
OUT = REPO / "glyphos_installer.py"

BOOT_SCRIPT = r'''
# ---- runs inside the extracted payload tree ----
import json, os, sys, time
from pathlib import Path

# The repo's modules import each other BOTH ways: `tools.glyph_gpt.x`
# (needs extract root on sys.path) and bare `glyph_gpt.x` / `glyph_isa_v2`
# (needs extract_root/tools on sys.path).
_ROOT = os.path.dirname(os.path.abspath(__file__))
for _p in (_ROOT, os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

def fail(msg, code=1):
    print(msg)
    sys.exit(code)

flags = [a for a in sys.argv[1:] if a.startswith("--")]
as_json = "--json" in flags
corrupt = "--corrupt-verify" in flags

t0 = time.perf_counter()
from tools.glyph_gpt.atlas import build_default_atlas
from tools.glyph_gpt.runner import GlyphRunner
from tools.glyph_gpt.agent_resident import (
    resident_image, RES_FLEET_RCPT, RES_DONE_WORD, RES_FLEET_DONE,
    RES_FLEET_EXPECT, RES_FAULT_WORD)
t_import = time.perf_counter() - t0

t0 = time.perf_counter()
atlas = build_default_atlas()
t_atlas = time.perf_counter() - t0

t0 = time.perf_counter()
img = resident_image(atlas, mode="fleet", timer_quantum=6)
t_bake = time.perf_counter() - t0

t0 = time.perf_counter()
runner = GlyphRunner(img, ram_words=16384)
rec = runner.run_wgsl(max_steps=5000)
t_run = time.perf_counter() - t0

ram = rec.get("ram")
if ram is None:
    fail("boot: no RAM in run_wgsl receipt", 1)
exp_rcpt = RES_FLEET_DONE ^ 0x5A5A if corrupt else RES_FLEET_DONE
exp_results = ({w: v ^ 0x5A5A for w, v in RES_FLEET_EXPECT.items()}
               if corrupt else RES_FLEET_EXPECT)

results = {w: ram[w] for w in RES_FLEET_EXPECT}
ok = (ram[RES_FLEET_RCPT] == exp_rcpt
      and ram[RES_DONE_WORD] == 0b1011
      and results == exp_results)

receipt = {
    "status": "fleet_ready_verified" if ok else "VERIFY_FAILED",
    "corrupt_verify_leg": corrupt,
    "halted": rec.get("halted"),
    "steps": rec.get("steps"),
    "timings_s": {"imports": round(t_import, 3), "atlas": round(t_atlas, 3),
                  "bake": round(t_bake, 3), "run_wgsl": round(t_run, 3)},
    "receipt_word": f"0x{ram[RES_FLEET_RCPT]:08x}",
    "done_word": f"0b{ram[RES_DONE_WORD]:b}",
    "results": {str(w): v for w, v in results.items()},
}
if rec.get("error"):
    receipt["engine_error"] = rec["error"]

if as_json:
    print(json.dumps(receipt, indent=2))
else:
    print("Glyph OS boot receipt")
    print(f"  status      : {receipt['status']}")
    print(f"  halted      : {rec.get('halted')}  steps: {rec.get('steps')}")
    print(f"  timings_s   : {receipt['timings_s']}")
    print(f"  receipt word: 0x{ram[RES_FLEET_RCPT]:08x}")
    print(f"  done bits   : 0b{ram[RES_DONE_WORD]:b}")
    for w in sorted(RES_FLEET_EXPECT):
        print(f"  result[{w}]  : {results[w]}")
    if rec.get("error"):
        print(f"  engine error: {rec['error']}")

sys.exit(0 if ok else 1)
'''

HEAD = '''#!/usr/bin/env python3
"""Glyph OS installer/launcher — PRODUCT_ROADMAP.md R5.1.

ONE file. Verifies its payload against a sha256 manifest, extracts the
Glyph OS boot chain to a private temp directory, boots the agent fleet on
the WGSL shader path (GlyphRunner.run_wgsl), and host-verifies the frozen
fleet readiness words. No repo checkout needed.

Usage:
    python3 glyphos_installer.py                # boot to fleet-ready
    python3 glyphos_installer.py --json         # machine-readable receipt
    python3 glyphos_installer.py --corrupt-verify   # RED leg: a corrupted
        manifest must REJECT the good payload (exit 1)
    python3 glyphos_installer.py --skip-boot    # verify payload, no boot

Requirements: python3, numpy, wgpu (shader path), Pillow.

Exit codes:
    0  fleet-ready, frozen words host-verified (or --skip-boot verified)
    1  verification failure (payload/manifest mismatch, boot failure, or
       readiness words wrong)
    4  payload unreadable / extraction failure
"""
import argparse, base64, gzip, hashlib, io, json, subprocess, sys
import tarfile, tempfile, time
from pathlib import Path

PAYLOAD_B64 = "@@PAYLOAD_B64@@"
MANIFEST_GZ_B64 = "@@MANIFEST_B64@@"

BOOT_SCRIPT = @@BOOT_SCRIPT@@


def _fail(msg, code):
    print(msg)
    sys.exit(code)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Glyph OS one-file installer/launcher (R5.1)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--corrupt-verify", action="store_true",
                    help="RED leg: corrupt the manifest; the GOOD payload "
                         "must be REJECTED (exit 1)")
    ap.add_argument("--skip-boot", action="store_true",
                    help="verify payload integrity only")
    ns = ap.parse_args()

    t0 = time.perf_counter()
    try:
        gz = base64.b64decode(PAYLOAD_B64)
        manifest = json.loads(gzip.decompress(base64.b64decode(MANIFEST_GZ_B64)))
    except Exception as e:
        _fail(f"installer: embedded payload unreadable: {e}", 4)

    if ns.corrupt_verify:
        # Corrupt the manifest entry for the fleet-image module: the
        # installer must REFUSE the payload (exit 1), never boot it.
        key = "tools/glyph_gpt/agent_resident.py"
        if key not in manifest:
            _fail(f"installer: manifest lacks {key}", 1)
        manifest[key] = hashlib.sha256(b"corrupted-expectation").hexdigest()

    # --- integrity gate: verify every member BEFORE extraction ---
    try:
        tar = tarfile.open(fileobj=io.BytesIO(gz), mode="r:gz")
    except Exception as e:
        _fail(f"installer: payload tar unreadable: {e}", 1)
    bad = []
    names = set()
    for member in tar.getmembers():
        if not member.isfile():
            continue
        names.add(member.name)
        h = hashlib.sha256(tar.extractfile(member).read()).hexdigest()
        exp = manifest.get(member.name)
        if exp is None:
            bad.append((member.name, "not in manifest"))
        elif h != exp:
            bad.append((member.name, "sha256 mismatch"))
    missing = set(manifest) - names
    if bad or missing:
        lines = [f"installer: PAYLOAD REJECTED "
                 f"({len(bad)} bad, {len(missing)} missing)"]
        for name, why in (bad + [(m, "missing") for m in sorted(missing)])[:8]:
            lines.append(f"  {name}: {why}")
        _fail("\\n".join(lines), 1)
    t_verify = time.perf_counter() - t0

    if ns.skip_boot:
        print(f"payload verified: {len(manifest)} members, "
              f"{t_verify * 1000:.0f} ms, manifest OK")
        return 0

    # --- extract to a private temp dir (repo layout) ---
    extract_dir = tempfile.mkdtemp(prefix="glyphos_")
    try:
        tar.extractall(extract_dir, filter="data")
    except Exception as e:
        _fail(f"installer: extraction failed: {e}", 4)

    boot_path = Path(extract_dir) / "_boot_r51.py"
    boot_path.write_text(BOOT_SCRIPT)
    argv = [sys.executable, str(boot_path)]
    if ns.json:
        argv.append("--json")
    if ns.corrupt_verify:
        argv.append("--corrupt-verify")
    try:
        proc = subprocess.run(argv, capture_output=True, text=True)
    finally:
        import shutil
        shutil.rmtree(extract_dir, ignore_errors=True)
    sys.stdout.write(proc.stdout)
    if proc.returncode != 0 and proc.stderr.strip():
        sys.stderr.write(proc.stderr)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
'''

HEAD = HEAD.replace("@@BOOT_SCRIPT@@", repr(BOOT_SCRIPT))
HEAD = HEAD.replace("@@MANIFEST_B64@@",
                    base64.b64encode(MANIFEST.read_bytes()).decode())
HEAD = HEAD.replace("@@PAYLOAD_B64@@",
                    base64.b64encode(PAYLOAD.read_bytes()).decode())
OUT.write_text(HEAD)
print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")
