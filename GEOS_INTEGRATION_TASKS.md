### TASK_C030
- **Priority**: 2
- **Type**: code_generation
- **Description**: Integrate visual audio codec into GeOS hypervisor. Port `tools/speak.py` to Rust, add to `geometry_os/src/spatial/audio_codec.rs`. Support: encode pixel regions to WAV, decode WAV to pixel regions, CRC verification, Reed-Solomon error correction.
- **Dependencies**: TASK_C011
- **Receipt Criteria**: `audio_codec.rs` exists, compiles, encodes 1KB pixel region to WAV, decodes byte-identical, tests pass.
- **Test Command**: `cd /home/jericho/projects/zion/projects/geometry_os/geometry_os && cargo test audio_codec --lib`
- **Created**: 2026-07-13T22:00:00.000000Z

### TASK_C031
- **Priority**: 2
- **Type**: code_generation
- **Description**: Implement audio boot loader for GeOS. Create `geometry_os/src/boot/audio_boot.rs` that reads WAV from stdin, decodes to kernel image, loads into spatial memory, and jumps to entry point. Enable `cargo run --bin spatial_audio_boot < kernel_audio.wav`.
- **Dependencies**: TASK_C030
- **Receipt Criteria**: Audio boot loads kernel, executes, prints "Booted from audio", tests pass.
- **Test Command**: `cd /home/jericho/projects/zion/projects/geometry_os/geometry_os && cargo test audio_boot --test '*'`
- **Created**: 2026-07-13T22:00:00.000000Z

### TASK_C032
- **Priority**: 2
- **Type**: code_generation
- **Description**: Add phoneme-based LLM input to spatial kernel. Port `phonemes.py` to Rust in `geometry_os/src/spatial/phoneme_input.rs`. LLM token stream → phoneme audio → decode → opcode dispatch. Enable autonomous OS development via speech.
- **Dependencies**: TASK_C031
- **Receipt Criteria**: Phoneme input works, LLM speaks "spawn hello_world", GeOS executes, hello_world prints, tests pass.
- **Test Command**: `cd /home/jericho/projects/zion/projects/geometry_os/geometry_os && cargo test phoneme_input --lib`
- **Created**: 2026-07-13T22:00:00.000000Z