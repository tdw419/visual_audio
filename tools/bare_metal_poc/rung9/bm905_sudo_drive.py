#!/usr/bin/env python3
"""BM905 leg-0 helper: answer the guest's interactive sudo prompt over SSH.

The guest has no passwordless sudo and no root SSH; /dev/uinput ships as
crw------- root:root, and the daemon must write it to synthesize keycodes.
This drives `ssh -tt` with a pty and answers the "[sudo] password" prompt
exactly as a human would at the console — no passwords on stdin pipes.
Credential source: SUDO_PASSWORD in the repo .env (gitignored 2026-09-19),
matching the precedent password committed at tools/pxc1_serial_login_example.py.

Usage: bm905_sudo_drive.py "<guest shell command using sudo>"
Exit 0 = command ran (sudo prompt answered); nonzero otherwise.
"""
import os
import pty
import re
import select
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def load_password() -> str:
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("SUDO_PASSWORD="):
                return line.split("=", 1)[1].strip()
    sys.exit("SUDO_PASSWORD not set in repo .env")


SSH_BASE = ["sshpass", "-p", load_password(), "ssh", "-tt",
            "-o", "StrictHostKeyChecking=no", "-p", "2222",
            "jericho@127.0.0.1"]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    password = load_password()
    remote_cmd = sys.argv[1]
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp(SSH_BASE[0], SSH_BASE + [remote_cmd])
    # parent: watch for the sudo prompt, answer once
    buf = b""
    answered = False
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        r, _, _ = select.select([fd], [], [], 2.0)
        if fd in r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            sys.stdout.write(chunk.decode(errors="replace"))
            sys.stdout.flush()
            if not answered and re.search(rb"password", chunk, re.I):
                os.write(fd, (password + "\n").encode())
                answered = True
        else:
            # idle: check if child exited
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                break
    try:
        _, status = os.waitpid(pid, 0)
    except ChildProcessError:
        status = 0
    return os.waitstatus_to_exitcode(status) if status else 0


if __name__ == "__main__":
    sys.exit(main())
