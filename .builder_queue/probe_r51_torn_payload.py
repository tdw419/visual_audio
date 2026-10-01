#!/usr/bin/env python3
"""R5.1 gate — RED leg for the PAYLOAD bytes (complements the installer's
own --corrupt-verify, which corrupts the manifest).

Build a one-off installer whose embedded payload has ONE flipped byte, run
it, and require: exit 1 + PAYLOAD REJECTED, and NO boot (no receipt word).
The gate is discriminating: a broken integrity gate would boot the torn
payload and exit 0, failing this test.
"""
import base64
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTALLER = REPO / "glyphos_installer.py"


def _flip_payload_byte(text: str) -> str:
    m = re.search(r'PAYLOAD_B64 = "([A-Za-z0-9+/=]+)"', text)
    assert m, "payload line not found"
    raw = bytearray(base64.b64decode(m.group(1)))
    raw[len(raw) // 2] ^= 0x01  # flip one bit mid-payload
    torn = base64.b64encode(bytes(raw)).decode()
    return text[:m.start(1)] + torn + text[m.end(1):]


def main() -> int:
    text = INSTALLER.read_text()
    torn_path = Path("/tmp/glyphos_installer_torn.py")
    torn_path.write_text(_flip_payload_byte(text))

    proc = subprocess.run([sys.executable, str(torn_path)],
                          capture_output=True, text=True, timeout=300)
    out = proc.stdout + proc.stderr
    ok = (proc.returncode == 1
          and "PAYLOAD REJECTED" in out
          and "fleet_ready_verified" not in out)
    print(out.strip()[:600])
    print(f"\nRED-leg(payload tear): exit={proc.returncode} "
          f"rejected={'PAYLOAD REJECTED' in out} "
          f"no_boot={'fleet_ready_verified' not in out} "
          f"=> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
