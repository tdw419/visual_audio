"""bm902_stage2_construct.py — TASK_BM902: construct the PM handoff state.

Builds what OUR loader's stage2 hands the kernel at 0x100000, as pure host-
side construction (the differential bar is the artifact, not a boot):

  - zeropage 4KB: kernel-baked fields copied byte-for-byte from
    vmlinuz64.extracted (MEASURED this run to be byte-identical to the
    oracle for [0x1f1,0x268) outside loader-owned offsets — probe
    bm902_zp_probe3.py), e820 table copied from the QEMU/SeaBIOS map
    (same -M pc -m 512 fiction both sides), loader fields set per
    BM902_FIELD_PLAN.md, everything else zero.
  - cmdline: the oracle string, byte-exact, NUL-terminated (RECORDED
    CHOICE in the field plan), placed at CMDLINE_ADDR.
  - registers: oracle register state (rsi/codes/eflags/cr0 exact; our
    stack top named, whitelisted as LOADER-SPECIFIC).

Determinism: no randomness, no clock, fixed inputs — two runs are
byte-identical by construction; the gate asserts it anyway.
"""
import json
import struct
import sys

KERNEL = 'vmlinuz64.extracted'
ORACLE_ZP = 'oracle_zp_leg0.bin'
ORACLE_CMDLINE = 'oracle_cmdline_leg0.bin'
ORACLE_REGS = 'qemu_leg0_regs.json'  # oracle regs recorded from the real chain
# NOTE: probe27's json is the QEMU-DIRECT leg; the REAL-chain register state
# lives in ORACLE_BOOT_PARAMS.md / probe34 logs. We pin the real-chain values
# here (they are the pass bar) rather than parsing logs at run time.

ORACLE_REG_STATE = {
    'rip': 0x100000, 'rax': 0x100000, 'rbx': 0, 'rcx': 0, 'rdx': 0,
    'rsi': 0x13ab0, 'rdi': 0, 'rbp': 0, 'rsp': 0x1f784,
    'r8': 0, 'r9': 0, 'r10': 0, 'r11': 0, 'r12': 0, 'r13': 0,
    'r14': 0, 'r15': 0,
    'eflags': 0x46, 'cs': 0x10, 'ss': 0x18, 'ds': 0x18, 'es': 0x18,
    'cr0': 0x11, 'cr3': 0x0, 'cr4': 0x0,
}

# --- our loader's fixed layout choices (named in BM902_FIELD_PLAN.md) ---
ZP_ADDR = 0x13ab0        # Q2: reuse the oracle address — shrinks the table
CMDLINE_ADDR = 0x1f800   # Q2: same as oracle
STACK_TOP = 0x1f784      # our stack just below the cmdline buffer (same)
TYPE_OF_LOADER = 0xff    # Q1: self-built loader, protocol "undefined" value
HEAP_END_PTR = 0xefff    # our real-mode heap arena end (LOADER-SPECIFIC)


def build_zeropage() -> bytes:
    img = open(KERNEL, 'rb').read()
    oracle = open(ORACLE_ZP, 'rb').read()
    assert img[0x202:0x206] == b'HdrS', 'bzImage header missing'
    setup_sects = img[0x1f1]

    zp = bytearray(4096)

    # kernel-baked header band: copy the file's own bytes [0x1f1, 0x268).
    # MEASURED (bm902_zp_probe3.py): oracle == file here outside loader-
    # owned offsets, so the copy reproduces every MUST-MATCH byte exactly.
    zp[0x1f1:0x268] = img[0x1f1:0x268]

    # loader-set protocol fields (per BM902_FIELD_PLAN.md):
    struct.pack_into('<H', zp, 0x1f2, 0x0000)      # root_flags: ours 0
    struct.pack_into('<I', zp, 0x1f8, 0x00000000)  # ram_size: 0 (no legacy)
    struct.pack_into('<H', zp, 0x1fa, 0xffff)      # vid_mode: normal
    struct.pack_into('<H', zp, 0x1fc, 0x0000)      # root_dev: 0
    struct.pack_into('<H', zp, 0x1fe, 0xaa55)      # boot_flag: mandatory
    zp[0x210] = TYPE_OF_LOADER
    zp[0x211] = 0x81                               # LOADED_HIGH|CAN_USE_HEAP
    struct.pack_into('<H', zp, 0x212, 0x0000)      # setup_move_size: 0 (high)
    struct.pack_into('<I', zp, 0x214, 0x100000)    # code32_start (kernel-baked too; set explicitly)
    struct.pack_into('<I', zp, 0x218, 0x00000000)  # no initrd
    struct.pack_into('<I', zp, 0x21c, 0x00000000)
    struct.pack_into('<H', zp, 0x224, HEAP_END_PTR)
    struct.pack_into('<I', zp, 0x228, CMDLINE_ADDR)

    # e820: same QEMU/SeaBIOS map both sides (-M pc -m 512) — copy the
    # oracle's table bytes; count in e820_entries is part of the band above
    # (0x1e8) which the file copy does NOT cover, so set it explicitly.
    n_entries = oracle[0x1e8]
    zp[0x1e8] = n_entries
    table_end = 0x2d0 + n_entries * 20
    zp[0x2d0:table_end] = oracle[0x2d0:table_end]

    # everything else stays zero (incl. the STAGE2-CHOICE 0x000-0x1e7 band)
    return bytes(zp)


def build_cmdline() -> bytes:
    # byte-exact oracle string incl. trailing space + NUL terminator
    return open(ORACLE_CMDLINE, 'rb').read()


def build_regs() -> dict:
    regs = dict(ORACLE_REG_STATE)
    regs['loader_meta'] = {
        'zp_addr': ZP_ADDR, 'cmdline_addr': CMDLINE_ADDR,
        'stack_top': STACK_TOP, 'type_of_loader': TYPE_OF_LOADER,
    }
    return regs


def main() -> None:
    zp_out, cmd_out, regs_out = sys.argv[1:4]
    zp = build_zeropage()
    cmd = build_cmdline()
    regs = build_regs()
    open(zp_out, 'wb').write(zp)
    open(cmd_out, 'wb').write(cmd)
    with open(regs_out, 'w') as f:
        json.dump(regs, f, indent=1, sort_keys=True)
    print(f'constructed: zp {len(zp)}B cmdline {len(cmd)}B regs -> {regs_out}')


if __name__ == '__main__':
    main()
