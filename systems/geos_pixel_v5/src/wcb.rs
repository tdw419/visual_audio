//! WCB (Window Control Block) layout constants — the single Rust source of
//! truth for the spatial memory layout shared by the GPU window system
//! (`window.rs`), the self-hosting loader (`spatial_loader.rs`), and the
//! WGSL shaders (`shaders/glyph_render.wgsl`, `shaders/glyph_interact.wgsl`).
//!
//! These are std-only so PDB decode / WCB seeding can run without the GPU
//! feature (Phase 4 self-hosting must work headless on the CPU side too).

/// Base address of the WCB array in `data_memory` (words).
pub const WCB_BASE: usize = 100;
/// Stride between WCB rows in words (16 words = 64 bytes).
pub const WCB_STRIDE: usize = 16;
/// Maximum number of windows the coordinator supervises.
pub const MAX_WINDOWS: usize = 4;
/// Size of the spatial memory buffer in i32 words.
pub const MEM_WORDS: usize = 2048;

/// Seed `mem` with the canonical 3-window test layout used by the Python
/// incubator (WC006/WC007): RED Z=1 at (50,50), GREEN Z=2 at (100,100),
/// BLUE Z=0 at (20,20), WCB3 empty.
///
/// Lives here (std-only) so both the GPU window system and the self-hosting
/// loader can reference the same canonical seed without a GPU dependency.
pub fn seed_wcb_state(mem: &mut [i32]) {
    mem.fill(0);
    // WCB0: RED
    mem[WCB_BASE + 0] = 1;
    mem[WCB_BASE + 1] = 50;
    mem[WCB_BASE + 2] = 50;
    mem[WCB_BASE + 3] = 200;
    mem[WCB_BASE + 4] = 150;
    mem[WCB_BASE + 5] = 1;
    mem[WCB_BASE + 8] = 1;
    // WCB1: GREEN
    let b1 = WCB_BASE + WCB_STRIDE;
    mem[b1 + 0] = 1;
    mem[b1 + 1] = 100;
    mem[b1 + 2] = 100;
    mem[b1 + 3] = 200;
    mem[b1 + 4] = 150;
    mem[b1 + 5] = 2;
    mem[b1 + 8] = 1;
    // WCB2: BLUE
    let b2 = WCB_BASE + 2 * WCB_STRIDE;
    mem[b2 + 0] = 1;
    mem[b2 + 1] = 20;
    mem[b2 + 2] = 20;
    mem[b2 + 3] = 400;
    mem[b2 + 4] = 300;
    mem[b2 + 5] = 0;
    mem[b2 + 8] = 1;
    // WCB3: empty (STATE stays 0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_seed_layout() {
        let mut mem = vec![0i32; MEM_WORDS];
        seed_wcb_state(&mut mem);
        assert_eq!(mem[WCB_BASE + 0], 1);
        assert_eq!(mem[WCB_BASE + 5], 1); // RED Z
        let b1 = WCB_BASE + WCB_STRIDE;
        assert_eq!(mem[b1 + 5], 2); // GREEN Z
        let b2 = WCB_BASE + 2 * WCB_STRIDE;
        assert_eq!(mem[b2 + 5], 0); // BLUE Z
        let b3 = WCB_BASE + 3 * WCB_STRIDE;
        assert_eq!(mem[b3 + 0], 0); // WCB3 empty
    }
}
