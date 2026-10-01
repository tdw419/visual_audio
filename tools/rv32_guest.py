#!/usr/bin/env python3
"""
rv32_guest.py — persistent handle to a Linux guest booted on SpatialRV32ICore
(the GPU-resident RISC-V core, real WGSL compute, not a CPU simulator).

Extracted from tools/inside_the_pixels_demo.py so pixel_os_listener.py can
keep one guest warm across many ops instead of rebooting Linux (~35s) per
command.

write_uart_input() is a single-byte RX register on this core -- writes
overwrite each other with no queuing, so bytes fired back-to-back with no
stepping in between get silently dropped except the last. type_line() below
steps the core after each byte, like a real keyboard, to avoid that.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spatial_rv32i_cpu import SpatialRV32ICore

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_KERNEL = REPO_ROOT / "boot_images" / "rv32ima_nommu" / "Image"
DEFAULT_DTB = REPO_ROOT / "boot_images" / "rv32ima_nommu" / "sixtyfourmb.dtb"

RAM_BASE = 0x80000000
DTB_OFFSET = 0x00400000
MEMORY_SIZE = 64 * 1024 * 1024

LOGIN_PROMPT = b"buildroot login:"
SHELL_PROMPT = b"# "


class GuestBootError(RuntimeError):
    pass


class RV32Guest:
    """A booted, logged-in Linux guest you can run shell commands in.

    One instance == one running VM. Boot + login happen once, in __init__;
    exec() reuses the same live guest for every subsequent command.
    """

    def __init__(self, kernel_path: Path = DEFAULT_KERNEL, dtb_path: Path = DEFAULT_DTB,
                 boot_timeout_blocks: int = 4000, on_output=None):
        """on_output, if given, is called with each raw output chunk (bytes) as
        it arrives -- for live logging. Boots and logs in immediately; raises
        GuestBootError if either fails."""
        self.on_output = on_output
        self.core = SpatialRV32ICore(memory_size_bytes=MEMORY_SIZE)
        self.core.load_program(kernel_path.read_bytes(), entry_point=RAM_BASE, ram_base=RAM_BASE)
        self.core.write_mem_bytes(DTB_OFFSET, dtb_path.read_bytes())
        self.core.write_register(10, 0)
        self.core.write_register(11, RAM_BASE + DTB_OFFSET)

        buf = self._run_until(LOGIN_PROMPT, max_steps_blocks=boot_timeout_blocks)
        if LOGIN_PROMPT not in buf:
            raise GuestBootError("Linux never reached the login prompt")

        buf = self._type_line("root")
        if SHELL_PROMPT not in buf:
            buf += self._run_until(SHELL_PROMPT, max_steps_blocks=500)
        if SHELL_PROMPT not in buf:
            raise GuestBootError("login as root never reached a shell prompt")

        self.alive = True

    def _run_until(self, needle: bytes, max_steps_blocks: int, block: int = 20000) -> bytes:
        buf = b""
        for _ in range(max_steps_blocks):
            self.core.step(steps=block)
            out = self.core.read_uart_output()
            if out:
                if self.on_output:
                    self.on_output(out)
                buf += out
            if needle in buf:
                return buf
        return buf

    def _type_line(self, text: str, settle_blocks: int = 20, block: int = 20000) -> bytes:
        buf = b""
        for ch in (text + "\n").encode():
            self.core.write_uart_input(bytes([ch]))
            for _ in range(settle_blocks):
                self.core.step(steps=block)
                out = self.core.read_uart_output()
                if out:
                    if self.on_output:
                        self.on_output(out)
                    buf += out
        return buf

    def exec(self, command: str, timeout_blocks: int = 500) -> str:
        """Run a shell command in the already-booted guest and return its stdout.

        Uses a sentinel echoed after the command so we can tell "the guest's
        real output" apart from the terminal echoing our own keystrokes back.

        Gotcha: the sentinel substring shows up in the buffer twice for two
        different reasons -- once immediately, as the raw terminal echo of
        the keystrokes we just typed (the line "command; echo <sentinel>"),
        and once for real, on its own line, once the shell has actually run
        `echo <sentinel>` as a command. A plain "sentinel in buf" check fires
        on the first (fake) occurrence and returns before the guest has done
        anything -- fine for slow, chatty commands where real output happens
        to land within the typing-settle window by luck, silently wrong for
        fast/silent ones (e.g. `uname -a` returned '' this way). We must wait
        for the sentinel as a *standalone output line*, not just anywhere.
        """
        if not self.alive:
            raise GuestBootError("guest is no longer running (a previous exec() likely crashed it)")

        sentinel = f"__RV32_GUEST_DONE_{abs(hash(command)) % 10**8}__"

        def sentinel_line_seen(b: bytes) -> bool:
            return any(line.strip() == sentinel
                       for line in b.decode(errors="replace").splitlines())

        buf = self._type_line(f"{command}; echo {sentinel}")
        steps_left = timeout_blocks
        while not sentinel_line_seen(buf) and steps_left > 0:
            chunk = self._run_until(sentinel.encode(), max_steps_blocks=min(steps_left, 50))
            buf += chunk
            steps_left -= 50
        if not sentinel_line_seen(buf):
            raise GuestBootError(f"command {command!r} never returned (guest may have hung)")

        # Everything between the echoed command line and the standalone
        # sentinel line is the command's real stdout.
        lines = buf.decode(errors="replace").splitlines()
        out_lines = []
        seen_cmd_echo = False
        for line in lines:
            if not seen_cmd_echo:
                if command in line:
                    seen_cmd_echo = True
                continue
            if line.strip() == sentinel:
                break
            out_lines.append(line)
        return "\n".join(out_lines).strip()
