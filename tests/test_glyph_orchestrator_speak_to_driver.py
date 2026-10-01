"""
End-to-end: "speak a driver into existence."

A single spatial-CPU program (GlyphCPUv2), no host Python in the loop between
steps, chains: AUDIO_IN (decode MFSK wav -> bytes) -> FILE_WRITE (bytes -> script
on disk) -> RUN (execute it, explicitly granted). The byte count from AUDIO_IN is
threaded through r3 into FILE_WRITE's length argument entirely inside the CPU -
the host test only sets up the *inputs* (an audio file simulating what a
listener daemon would have captured) and checks the *side effect* (RUN'd script
having actually written a marker file).

What the host must supply since RULING_run_syscall_containment (4863635), both
operator grants and both asserted below: (1) the target path exists with its exec
bit already set - the guest may NOT chmod host files (ruling decision 4), and exec
of a non-executable file fails [Errno 13]; (2) `GLYPH_RUN_ALLOW` names that exact
path (ruling decisions 2/3, realpath equality). The guest still supplies every
content byte, and FILE_WRITE opens the existing path so the operator's mode
survives - asserted, so a resurrected guest chmod is caught.
"""
import stat

import numpy as np
import pytest

from src.codec.phy import Phy16Tone
from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2

WIDTH_INSTRS = 32
WIDTH_PX = WIDTH_INSTRS * 4  # 128

# Deliberately NOT 0o755: the operator provisions the run target's mode, and the
# guest must leave it alone (ruling decision 4). A returned guest chmod would
# rewrite this mode and the assertions in both legs would catch it.
OPERATOR_MODE = 0o741


def _write_null_terminated(image, row, s):
    b = s.encode("utf-8") + b"\x00"
    for i, byte_val in enumerate(b):
        image[row, i] = [byte_val, byte_val, byte_val]


def _run_speak_to_driver_pipeline(tmp_path):
    marker_path = tmp_path / "driver_ran.txt"
    driver_source = (
        "#!/usr/bin/env python3\n"
        f"open({str(marker_path)!r}, 'w').write('driver executed')\n"
    ).encode("utf-8")

    spoken_wav = tmp_path / "spoken_driver.wav"
    symbols = Phy16Tone.bytes_to_symbols(driver_source)
    audio = Phy16Tone.encode_symbols(symbols)
    import scipy.io.wavfile as wavfile
    wavfile.write(str(spoken_wav), Phy16Tone.SAMPLE_RATE, (audio * 32767).astype(np.int16))

    driver_script = tmp_path / "spoken_driver.py"
    # Operator grant #1: the target path exists and is executable BEFORE the run.
    # The guest may not chmod (ruling decision 4); FILE_WRITE opens this existing
    # path, so the content is all guest-derived while the mode is all operator-set.
    driver_script.touch()
    driver_script.chmod(OPERATOR_MODE)

    op_map = OpcodeMapV2()
    try:
        assembler = GlyphAssemblerV2(op_map)

        wav_path_addr = WIDTH_PX * 1       # row 1
        script_path_addr = WIDTH_PX * 2    # row 2
        data_buf_addr = WIDTH_PX * 3       # row 3+

        program = [
            f"LDI r1 {wav_path_addr}",
            f"LDI r2 {data_buf_addr}",
            f"LDI r3 {len(driver_source) + 64}",  # max_len, generous headroom
            "SYSCALL r3 9",                        # AUDIO_IN -> r3 = actual decoded byte count
            f"LDI r1 {script_path_addr}",          # switch r1 to the output script path;
                                                    # r2 (data addr) and r3 (length) carry over
            "SYSCALL r0 3",                        # FILE_WRITE
            "SYSCALL r0 7",                        # RUN
            "HALT",
        ]
        while len(program) < WIDTH_INSTRS:
            program.append("HALT")

        image = assembler.assemble(program, width_instrs=WIDTH_INSTRS)
        extra_rows = 3 + (len(driver_source) // WIDTH_PX) + 2
        if image.shape[0] < extra_rows:
            pad = np.zeros((extra_rows - image.shape[0], WIDTH_PX, 3), dtype=np.uint8)
            image = np.vstack([image, pad])

        _write_null_terminated(image, 1, str(spoken_wav))
        _write_null_terminated(image, 2, str(driver_script))

        cpu = GlyphCPUv2(op_map, cols_instrs=WIDTH_INSTRS)
        cpu.run(image, max_instructions=100)

        return cpu, driver_script, driver_source, marker_path
    finally:
        op_map.close()


# backlog(d) handler 5/5 (2026-09-16): these two legs carried strict
# xfails while AUDIO_IN (0x09) still wrote its dest to image space -
# the chain was broken by the intermediate 3/5 state. 5/5 landed, the
# xfails XPASSed as designed, and were removed (the tripwire 85922f8
# planted, now retired). The legs are plain live assertions again.
def test_speak_a_driver_end_to_end(tmp_path, monkeypatch):
    # Operator grant #2: this exact path is allowlisted, so RUN is permitted and
    # the whole chain is observed end to end.
    driver_script = tmp_path / "spoken_driver.py"
    monkeypatch.setenv("GLYPH_RUN_ALLOW", str(driver_script.resolve()))

    cpu, script_path, driver_source, marker_path = _run_speak_to_driver_pipeline(tmp_path)

    assert not cpu.running
    assert script_path.exists(), "AUDIO_IN -> FILE_WRITE chain did not produce the script"
    assert stat.S_IMODE(script_path.stat().st_mode) == OPERATOR_MODE, (
        "the guest changed host file permissions (ruling decision 4)"
    )
    assert script_path.read_bytes() == driver_source, "decoded bytes did not match spoken source"

    assert marker_path.exists(), "RUN did not actually execute the spatially-written driver"
    assert marker_path.read_text() == "driver executed"


def test_speak_a_driver_run_is_default_denied(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GLYPH_RUN_ALLOW", raising=False)

    capsys.readouterr()  # clear buffer
    cpu, script_path, driver_source, marker_path = _run_speak_to_driver_pipeline(tmp_path)

    assert not cpu.running
    assert script_path.exists(), "AUDIO_IN -> FILE_WRITE chain did not produce the script"
    assert stat.S_IMODE(script_path.stat().st_mode) == OPERATOR_MODE, (
        "the guest changed host file permissions (ruling decision 4)"
    )
    assert script_path.read_bytes() == driver_source, "decoded bytes did not match spoken source"

    assert not marker_path.exists(), "RUN executed driver despite default-deny"

    captured = capsys.readouterr()
    lines = [line.strip() for line in captured.out.strip().splitlines() if line.strip()]
    assert any("[SYSCALL] RUN denied" in line for line in lines), f"Expected RUN denied in output, got: {captured.out}"

