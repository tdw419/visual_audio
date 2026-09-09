//! Phase 4: Self-Hosting File Execution — load `.glyph` programs and window
//! definitions from the V4 PDB (Pixel Database) into the WCB.
//!
//! V5 boot sequence step 5/6: `geos_pixel_v5` allocates the spatial WCB rows
//! on the GPU and dispatches the native `.glyph` window coordinator. This
//! module removes the final host-OS dependency from that path: instead of
//! `seed_wcb_state()` hardcoding the three test windows in Rust, the
//! coordinator decodes its program bytes and window manifest from tiled PDB
//! frames (V4.1 `TiledPdbDecoder`) — "reading from the pixel database using
//! spatial memory coordinates, entirely bypassing standard file systems".
//!
//! ## Two PDB tables
//!
//! | table           | contents                                              |
//! |-----------------|-------------------------------------------------------|
//! | `glyph_program` | raw `.glyph` assembly bytes (blob-table semantics)    |
//! | `windows`       | serialized [`WindowDef`] rows (16 i32 words each)     |
//!
//! [`WindowDef`] mirrors the WCB row layout in `window.rs` exactly, so the
//! decoded manifest can be written straight into spatial memory words
//! `WCB_BASE + i*WCB_STRIDE` with no reinterpretation.
//!
//! The program itself is placed in the free region of the same `data_memory`
//! buffer (after the last WCB row), and each window's `tick_addr` field
//! (WCB offset 6) is set to the packed word coordinate of the loaded program
//! entry — the dispatch target the GPU supervisor CALLR's on every tick.

use crate::pdb::tiled::{
    TileCoord, TileGridConfig, TiledPdbDecoder, TiledPdbEncoder, TiledPdbHeader,
};
use crate::wcb::{MAX_WINDOWS, WCB_BASE, WCB_STRIDE};

/// Start of the glyph-program region in `data_memory` (words).
/// Sits immediately after the MAX_WINDOWS WCB rows: 100 + 4*16 = 164.
pub const PROGRAM_BASE: usize = WCB_BASE + MAX_WINDOWS * WCB_STRIDE;

/// Name of the PDB table holding `.glyph` program bytes.
pub const TABLE_GLYPH_PROGRAM: &str = "glyph_program";

/// Name of the PDB table holding the window manifest.
pub const TABLE_WINDOWS: &str = "windows";

/// A window definition exactly matching the WCB row layout.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct WindowDef {
    /// STATE: 0 = empty, 1 = active.
    pub state: i32,
    /// X: window origin column.
    pub x: i32,
    /// Y: window origin row.
    pub y: i32,
    /// W: window width.
    pub w: i32,
    /// H: window height.
    pub h: i32,
    /// Z: z-order (higher = closer to viewer).
    pub z: i32,
    /// TICK_ADDR: packed word coordinate of this window's tick routine
    /// within the loaded glyph program region.
    pub tick_addr: i32,
    /// VISIBLE: 0 = hidden, 1 = visible.
    pub visible: i32,
}

impl WindowDef {
    /// Pack this definition into a 16-word WCB row (same layout as the
    /// shader's `data_memory` WCB rows).
    pub fn to_wcb_row(&self) -> [i32; 16] {
        let mut row = [0i32; 16];
        row[0] = self.state;
        row[1] = self.x;
        row[2] = self.y;
        row[3] = self.w;
        row[4] = self.h;
        row[5] = self.z;
        row[6] = self.tick_addr;
        row[7] = 0; // counter
        row[8] = self.visible;
        row
    }

    /// Unpack a 16-word WCB row into a [`WindowDef`].
    pub fn from_wcb_row(row: &[i32; 16]) -> Self {
        Self {
            state: row[0],
            x: row[1],
            y: row[2],
            w: row[3],
            h: row[4],
            z: row[5],
            tick_addr: row[6],
            visible: row[8],
        }
    }
}

/// The canonical three-window manifest used by the Python incubator
/// (WC006/WC007) and `seed_wcb_state()`: RED Z=1 at (50,50),
/// GREEN Z=2 at (100,100), BLUE Z=0 at (20,20).
///
/// All tick routines point at the loaded program's entry (PROGRAM_BASE);
/// a real glyph interpreter (Phase 5) resolves the packed entry per window.
pub fn canonical_manifest() -> Vec<WindowDef> {
    vec![
        WindowDef {
            state: 1, x: 50, y: 50, w: 200, h: 150, z: 1,
            tick_addr: PROGRAM_BASE as i32, visible: 1,
        },
        WindowDef {
            state: 1, x: 100, y: 100, w: 200, h: 150, z: 2,
            tick_addr: PROGRAM_BASE as i32, visible: 1,
        },
        WindowDef {
            state: 1, x: 20, y: 20, w: 400, h: 300, z: 0,
            tick_addr: PROGRAM_BASE as i32, visible: 1,
        },
        WindowDef {
            state: 0, x: 0, y: 0, w: 0, h: 0, z: 0,
            tick_addr: 0, visible: 0,
        },
    ]
}

/// Serialize a window manifest to the PDB `windows` table byte format:
/// `u32 LE count` followed by `count * 16 * i32 LE` row words.
pub fn serialize_windows(defs: &[WindowDef]) -> Vec<u8> {
    let mut out = Vec::with_capacity(4 + defs.len() * 64);
    out.extend_from_slice(&(defs.len() as u32).to_le_bytes());
    for def in defs {
        for w in def.to_wcb_row() {
            out.extend_from_slice(&w.to_le_bytes());
        }
    }
    out
}

/// Parse a window manifest from the PDB `windows` table byte format.
pub fn deserialize_windows(bytes: &[u8]) -> Result<Vec<WindowDef>, String> {
    if bytes.len() < 4 {
        return Err("windows table too short (missing count)".into());
    }
    let count = u32::from_le_bytes(bytes[0..4].try_into().unwrap()) as usize;
    if count > MAX_WINDOWS {
        return Err(format!("window count {} exceeds MAX_WINDOWS {}", count, MAX_WINDOWS));
    }
    let expected = 4 + count * 64;
    if bytes.len() < expected {
        return Err(format!(
            "windows table truncated: need {} bytes, have {}",
            expected,
            bytes.len()
        ));
    }
    let mut defs = Vec::with_capacity(count);
    for i in 0..count {
        let mut row = [0i32; 16];
        for (j, w) in row.iter_mut().enumerate() {
            let off = 4 + i * 64 + j * 4;
            *w = i32::from_le_bytes(bytes[off..off + 4].try_into().unwrap());
        }
        defs.push(WindowDef::from_wcb_row(&row));
    }
    Ok(defs)
}

/// Write the WCB region of `mem` from a decoded window manifest.
/// Equivalent to `seed_wcb_state()` but driven by PDB-decoded data.
pub fn seed_wcb_from_manifest(mem: &mut [i32], defs: &[WindowDef]) {
    for i in 0..MAX_WINDOWS {
        let base = WCB_BASE + i * WCB_STRIDE;
        let row = if i < defs.len() { defs[i].to_wcb_row() } else { [0i32; 16] };
        for (j, w) in row.iter().enumerate() {
            mem[base + j] = *w;
        }
    }
}

/// Place glyph-program bytes into the free region of `data_memory`
/// (words `PROGRAM_BASE..`), packed little-endian 4 bytes per word.
///
/// Returns the number of words consumed.
pub fn load_program_into_memory(mem: &mut [i32], program: &[u8]) -> usize {
    let words = (program.len() + 3) / 4;
    let start = PROGRAM_BASE;
    assert!(
        start + words <= mem.len(),
        "program too large: {} bytes needs {} words, buffer has {}",
        program.len(),
        words,
        mem.len() - start
    );
    for (wi, chunk) in program.chunks_exact(4).enumerate() {
        let w = i32::from_le_bytes(chunk.try_into().unwrap());
        mem[start + wi] = w;
    }
    // Tail bytes (1-3 remaining) padded with zeros.
    let rem = program.len() % 4;
    if rem != 0 {
        let mut tail = [0u8; 4];
        tail[..rem].copy_from_slice(&program[program.len() - rem..]);
        mem[start + words - 1] = i32::from_le_bytes(tail);
    }
    words
}

/// Read back glyph-program bytes from `data_memory` (inverse of
/// [`load_program_into_memory`]). `words` must be the word count from the
/// load step; returns exactly `words * 4` bytes (zero-padded tail).
pub fn read_program_from_memory(mem: &[i32], words: usize) -> Vec<u8> {
    let start = PROGRAM_BASE;
    assert!(start + words <= mem.len(), "program region out of bounds");
    let mut out = Vec::with_capacity(words * 4);
    for w in &mem[start..start + words] {
        out.extend_from_slice(&w.to_le_bytes());
    }
    out
}

/// Encode a glyph program + window manifest into a tiled PDB directory.
///
/// # Arguments
/// * `base_path` — directory for the tile PNGs + `tiles.json`
/// * `program` — raw `.glyph` assembly bytes
/// * `defs` — window manifest
pub fn encode_manifest_to_pdb(
    base_path: &str,
    program: &[u8],
    defs: &[WindowDef],
) -> Result<(), String> {
    // The encoder writes tile PNGs directly into base_path; make sure it exists.
    std::fs::create_dir_all(base_path)
        .map_err(|e| format!("create pdb dir {base_path}: {e}"))?;

    // Small payloads: a single 256x256 tile (256-128 data rows * 256 cols * 3
    // bytes = 98,304 bytes capacity) is far more than either table needs.
    let tile_size = 256u32;
    let logical = TileGridConfig::new(tile_size, tile_size, tile_size)
        .map_err(|e| format!("tile config: {e}"))?;
    let header = TiledPdbHeader::new(logical);
    let mut encoder =
        TiledPdbEncoder::new(base_path, header).map_err(|e| format!("encoder: {e}"))?;
    encoder
        .encode_table(TABLE_GLYPH_PROGRAM, program)
        .map_err(|e| format!("encode glyph_program: {e}"))?;
    let windows_bytes = serialize_windows(defs);
    encoder
        .encode_table(TABLE_WINDOWS, &windows_bytes)
        .map_err(|e| format!("encode windows: {e}"))?;
    encoder.save_header().map_err(|e| format!("save header: {e}"))?;
    Ok(())
}

/// Decode a glyph program + window manifest back from a tiled PDB directory.
pub fn decode_manifest_from_pdb(
    base_path: &str,
) -> Result<(Vec<u8>, Vec<WindowDef>), String> {
    let mut decoder =
        TiledPdbDecoder::new(base_path).map_err(|e| format!("decoder: {e}"))?;
    decoder
        .manager
        .load_header()
        .map_err(|e| format!("load header: {e}"))?;
    let program = decoder
        .decode_table(TABLE_GLYPH_PROGRAM)
        .map_err(|e| format!("decode glyph_program: {e}"))?;
    let windows_bytes = decoder
        .decode_table(TABLE_WINDOWS)
        .map_err(|e| format!("decode windows: {e}"))?;
    let defs = deserialize_windows(&windows_bytes)?;
    Ok((program, defs))
}

/// Full self-hosting bootstrap: PDB directory → WCB-ready `data_memory`.
///
/// Decodes both tables, places the program at [`PROGRAM_BASE`], seeds the WCB
/// rows from the manifest, and returns the number of program words loaded.
pub fn bootstrap_from_pdb(mem: &mut [i32], base_path: &str) -> Result<(Vec<u8>, Vec<WindowDef>, usize), String> {
    let (program, defs) = decode_manifest_from_pdb(base_path)?;
    let words = load_program_into_memory(mem, &program);
    seed_wcb_from_manifest(mem, &defs);
    Ok((program, defs, words))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::wcb::{seed_wcb_state, MEM_WORDS};

    const TEST_GLYPH: &[u8] = b":init\nLDI r31 250\nLDI r29 0\nLDI r30 1\nHALT\n";

    fn make_mem() -> Vec<i32> {
        vec![0i32; MEM_WORDS]
    }

    #[test]
    fn test_window_def_row_roundtrip() {
        let def = WindowDef {
            state: 1, x: 50, y: 50, w: 200, h: 150, z: 1,
            tick_addr: 164, visible: 1,
        };
        let row = def.to_wcb_row();
        assert_eq!(row[0], 1);
        assert_eq!(row[1], 50);
        assert_eq!(row[6], 164);
        assert_eq!(row[8], 1);
        assert_eq!(WindowDef::from_wcb_row(&row), def);
    }

    #[test]
    fn test_serialize_deserialize_windows() {
        let defs = canonical_manifest();
        let bytes = serialize_windows(&defs);
        let parsed = deserialize_windows(&bytes).unwrap();
        assert_eq!(parsed, defs);
    }

    #[test]
    fn test_deserialize_rejects_oversize() {
        let mut bytes = vec![0u8; 4];
        bytes[0] = 99; // count = 99 > MAX_WINDOWS
        assert!(deserialize_windows(&bytes).is_err());
    }

    #[test]
    fn test_seed_from_manifest_matches_seed_wcb_state() {
        let mut a = make_mem();
        let mut b = make_mem();
        seed_wcb_state(&mut a);
        seed_wcb_from_manifest(&mut b, &canonical_manifest());
        // Geometry fields (0-5, 7-15) must match the canonical seed; tick_addr
        // (6) intentionally differs: the PDB-loaded manifest points windows at
        // the loaded program's entry (PROGRAM_BASE), which seed_wcb_state
        // leaves as 0 (no program loaded).
        for i in 0..MAX_WINDOWS {
            let base = WCB_BASE + i * WCB_STRIDE;
            for j in 0..16 {
                if j == 6 {
                    if b[base] != 0 {
                        // Active windows point their tick routine at the
                        // loaded program; empty windows leave it 0.
                        assert_eq!(
                            b[base + 6],
                            PROGRAM_BASE as i32,
                            "WCB{} tick_addr must point at program",
                            i
                        );
                    } else {
                        assert_eq!(b[base + 6], 0, "empty WCB{} must have tick_addr 0", i);
                    }
                } else {
                    assert_eq!(a[base + j], b[base + j], "WCB{} field {} mismatch", i, j);
                }
            }
        }
    }

    #[test]
    fn test_program_load_roundtrip() {
        let mut mem = make_mem();
        let words = load_program_into_memory(&mut mem, TEST_GLYPH);
        assert_eq!(words, (TEST_GLYPH.len() + 3) / 4);
        // Exact bytes must survive (compare against the true length, not the
        // zero-padded readback).
        let readback = read_program_from_memory(&mem, words);
        assert_eq!(&readback[..TEST_GLYPH.len()], TEST_GLYPH);
    }

    #[test]
    fn test_program_tail_padding() {
        // 5 bytes → 2 words: [4 bytes][1 byte + 3 zero pad]
        let data = [1u8, 2, 3, 4, 5];
        let mut mem = make_mem();
        let words = load_program_into_memory(&mut mem, &data);
        assert_eq!(words, 2);
        assert_eq!(mem[PROGRAM_BASE], i32::from_le_bytes([1, 2, 3, 4]));
        assert_eq!(mem[PROGRAM_BASE + 1], i32::from_le_bytes([5, 0, 0, 0]));
    }

    #[test]
    fn test_pdb_roundtrip_small() {
        let dir = std::env::temp_dir().join(format!("pdb_selfhost_test_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let defs = canonical_manifest();
        encode_manifest_to_pdb(dir.to_str().unwrap(), TEST_GLYPH, &defs).unwrap();
        let (program, parsed_defs) = decode_manifest_from_pdb(dir.to_str().unwrap()).unwrap();
        assert_eq!(program, TEST_GLYPH, "glyph program must round-trip byte-identical");
        assert_eq!(parsed_defs, defs, "window manifest must round-trip identical");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_bootstrap_end_to_end() {
        let dir = std::env::temp_dir().join(format!("pdb_selfhost_boot_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let defs = canonical_manifest();
        encode_manifest_to_pdb(dir.to_str().unwrap(), TEST_GLYPH, &defs).unwrap();

        let mut mem = make_mem();
        let (program, parsed_defs, words) = bootstrap_from_pdb(&mut mem, dir.to_str().unwrap()).unwrap();
        assert_eq!(program, TEST_GLYPH);
        assert_eq!(parsed_defs, defs);
        assert_eq!(words, (TEST_GLYPH.len() + 3) / 4);

        // WCB geometry must match the canonical seed byte-for-byte
        // (tick_addr excluded: manifest points it at PROGRAM_BASE).
        let mut reference = make_mem();
        seed_wcb_state(&mut reference);
        for i in 0..MAX_WINDOWS {
            let base = WCB_BASE + i * WCB_STRIDE;
            for j in 0..16 {
                if j != 6 {
                    assert_eq!(
                        mem[base + j], reference[base + j],
                        "bootstrapped WCB{} field {} must equal canonical seed",
                        i, j
                    );
                }
            }
        }

        // Program region must hold the glyph bytes.
        let readback = read_program_from_memory(&mem, words);
        assert_eq!(&readback[..TEST_GLYPH.len()], TEST_GLYPH);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn test_tilecoord_used() {
        // Ensure the tiled imports are wired (avoid dead-code churn).
        let c = TileCoord { tile_x: 1, tile_y: 0 };
        assert_eq!(c.to_index(2), 1);
    }
}
