// V5 Phase 5: Glyph Program Execution on the WCB
//
// Phase 4 loaded a .glyph program + window manifest from the PDB into
// spatial memory. Phase 5 executes that program: the Rust glyph interpreter
// (`geos_pixel_v5::glyph`) runs the spatial coordinator supervisor loop, which
// CALLR-dispatches each active window's tick routine. The tick routines
// mutate the WCB rows (X drifts right, Y drifts down, counters increment)
// — the same `data_memory` words the GPU render shader composites, so the
// windows visibly move on screen.
//
// Flow:
//   1. Read spatial_coordinator.glyph, assemble it (labels -> packed addrs).
//   2. Build a Phase 5 manifest: each active window's tick_addr points at
//      its real tick routine (window_tick0/1/2 packed addresses).
//   3. Encode program + manifest to a tiled PDB (self-hosting storage).
//   4. Decode back + bootstrap the WCB (Phase 4 path).
//   5. Run GlyphCpu over the bootstrapped data_memory for N instructions.
//   6. Render on GPU: windows have drifted from their seed positions.
//
// Usage:
//   cargo run --example v5_glyph_exec --features gpu -- [pdb_dir] [glyph_file]

use std::path::PathBuf;

#[cfg(feature = "gpu")]
use geos_pixel_v5::window::{seed_wcb_state, WindowSystem, MEM_WORDS};
#[cfg(not(feature = "gpu"))]
use geos_pixel_v5::window::MEM_WORDS;

fn sha256_hex(data: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    let mut hasher = Sha256::new();
    hasher.update(data);
    let digest = hasher.finalize();
    digest.iter().map(|b| format!("{:02x}", b)).collect()
}

/// Build a Phase 5 manifest: seed geometry + real tick_addr per window.
fn phase5_manifest(prog: &geos_pixel_v5::glyph::GlyphProgram) -> Vec<geos_pixel_v5::spatial_loader::WindowDef> {
    use geos_pixel_v5::spatial_loader::WindowDef;
    let tick = |name: &str| -> i32 {
        prog.label_packed(name)
            .expect("tick label exists")
            as i32
    };
    vec![
        WindowDef {
            state: 1, x: 50, y: 50, w: 200, h: 150, z: 1,
            tick_addr: tick("window_tick0"), visible: 1,
        },
        WindowDef {
            state: 1, x: 100, y: 100, w: 200, h: 150, z: 2,
            tick_addr: tick("window_tick1"), visible: 1,
        },
        WindowDef {
            state: 1, x: 20, y: 20, w: 400, h: 300, z: 0,
            tick_addr: tick("window_tick2"), visible: 1,
        },
        WindowDef {
            state: 0, x: 0, y: 0, w: 0, h: 0, z: 0,
            tick_addr: 0, visible: 0,
        },
    ]
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let default_pdb = "/tmp/pdb_self_host_p5".to_string();
    let default_glyph = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../spatial_coordinator.glyph"
    );

    let mut args = std::env::args().skip(1);
    let pdb_dir = args.next().unwrap_or(default_pdb);
    let glyph_path = args.next().unwrap_or_else(|| default_glyph.to_string());

    println!("=== V5 Phase 5: Glyph Program Execution on the WCB ===");
    println!("PDB dir:      {}", pdb_dir);
    println!("Glyph source: {}", glyph_path);

    // 1. Load + assemble the .glyph program.
    let src = std::fs::read_to_string(&glyph_path)
        .map_err(|e| format!("read {}: {e}", glyph_path))?;
    let prog = geos_pixel_v5::glyph::GlyphProgram::assemble(&src, 8)
        .map_err(|e| format!("assemble: {e}"))?;
    println!("\n[1] Assembled {} instructions, {} labels (width 8)",
             prog.instrs.len(), prog.labels.len());
    for name in ["init", "main_loop", "window_tick0", "window_tick2"] {
        if let Some(packed) = prog.label_packed(name) {
            println!("    :{} -> index {}, packed 0x{:05x}", name,
                     prog.labels.get(name).copied().unwrap_or(0), packed);
        }
    }

    // 2. Build the Phase 5 manifest (real tick addresses).
    let defs = phase5_manifest(&prog);

    // 3. Encode program + manifest into tiled PDB.
    geos_pixel_v5::spatial_loader::encode_manifest_to_pdb(&pdb_dir, src.as_bytes(), &defs)?;
    println!("\n[2] Encoded {} windows + glyph program into PDB at {}", defs.len(), pdb_dir);
    let pdb_path = PathBuf::from(&pdb_dir);
    let mut png_count = 0;
    if let Ok(entries) = std::fs::read_dir(&pdb_path) {
        for entry in entries.flatten() {
            let p = entry.path();
            if p.extension().map_or(false, |e| e == "png") {
                png_count += 1;
            }
        }
    }
    println!("    total tile PNGs: {}", png_count);

    // 4. Decode back + bootstrap the WCB (Phase 4 self-hosting read).
    let (decoded_program, decoded_defs) =
        geos_pixel_v5::spatial_loader::decode_manifest_from_pdb(&pdb_dir)?;
    assert_eq!(decoded_program, src.as_bytes(), "program byte-identical");
    assert_eq!(decoded_defs, defs, "manifest byte-identical");
    println!("\n[3] Decoded from PDB: program {} bytes, {} windows (byte-identical)",
             decoded_program.len(), decoded_defs.len());

    let mut mem = vec![0i32; MEM_WORDS];
    let (_, _, prog_words) = geos_pixel_v5::spatial_loader::bootstrap_from_pdb(&mut mem, &pdb_dir)?;
    println!("\n[4] Bootstrapped WCB from PDB: program at word {} ({} words)",
             geos_pixel_v5::spatial_loader::PROGRAM_BASE, prog_words);

    // Snapshot the pre-execution WCB state.
    let snapshot = |m: &[i32]| -> Vec<(i32, i32, i32, i32)> {
        (0..geos_pixel_v5::window::MAX_WINDOWS)
            .map(|i| {
                let b = geos_pixel_v5::window::WCB_BASE + i * geos_pixel_v5::window::WCB_STRIDE;
                (m[b], m[b + 1], m[b + 2], m[b + 7]) // state, x, y, counter
            })
            .collect()
    };
    let before = snapshot(&mem);

    // 5. Execute the loaded program against the WCB data_memory.
    let mut cpu = geos_pixel_v5::glyph::GlyphCpu::new();
    let budget = 20_000usize;
    let steps = cpu.run(&prog, &mut mem, budget);
    println!("\n[5] Executed {} instructions of the spatial coordinator on the WCB", steps);

    let after = snapshot(&mem);
    let names = ["WCB0 (RED)", "WCB1 (GREEN)", "WCB2 (BLUE)", "WCB3"];
    for i in 0..geos_pixel_v5::window::MAX_WINDOWS {
        let (bs, bx, by, bc) = before[i];
        let (as_, ax, ay, ac) = after[i];
        let _ = as_; // state unchanged by execution (supervisor only mutates X/Y/counter)
        println!("    {}: state {} x {}->{} y {}->{} counter {}->{}",
                 names[i], bs, bx, ax, by, ay, bc, ac);
    }

    // Verify the drift invariants hold.
    let b0 = geos_pixel_v5::window::WCB_BASE;
    let b2 = geos_pixel_v5::window::WCB_BASE + 2 * geos_pixel_v5::window::WCB_STRIDE;
    assert_eq!(mem[b0 + 1], 50 + mem[b0 + 7], "WCB0 X = 50 + passes");
    assert_eq!(mem[b2 + 2], 20 + mem[b2 + 7], "WCB2 Y = 20 + passes");
    assert!(mem[b0 + 7] >= 1 && mem[b2 + 7] >= 1, "at least one pass");
    println!("    ✓ drift invariants hold: WCB0.X = 50+passes, WCB2.Y = 20+passes");
    println!("    ✓ program bytes in spatial memory match source: {}",
             if &geos_pixel_v5::spatial_loader::read_program_from_memory(&mem, prog_words)[..src.len()] == src.as_bytes() { "YES" } else { "NO" });

    // 6. GPU render: windows must have moved vs the canonical seed.
    #[cfg(feature = "gpu")]
    {
        println!("\n[6] GPU render (Vulkan)...");
        let ws = WindowSystem::new().expect("WindowSystem init failed");
        println!("    adapter: {}", ws.adapter_name());

        // Render the executed (drifted) state.
        ws.write_memory(&mem);
        let drifted_img = ws.render();

        // Render the canonical seed (pre-execution layout).
        let mut seed_mem = vec![0i32; MEM_WORDS];
        seed_wcb_state(&mut seed_mem);
        ws.write_memory(&seed_mem);
        let seed_img = ws.render();

        let diff = drifted_img
            .iter()
            .zip(seed_img.iter())
            .filter(|(a, b)| a != b)
            .count();
        println!("    pixel bytes changed vs seed render: {}", diff);
        assert!(diff > 0, "windows must have moved on screen");

        // Probe: the top-left corner of RED at (50,50) — after drift it should
        // no longer be RED there (BLUE window covers it).
        let probe = |img: &[u8], x: u32, y: u32| -> [u8; 4] { ws.pixel(img, x, y) };
        let seed_p = probe(&seed_img, 60, 60);
        let drift_p = probe(&drifted_img, 60, 60);
        println!("    pixel(60,60): seed {:?} -> after exec {:?}", seed_p, drift_p);
        assert_ne!(seed_p, drift_p, "pixel at RED origin must change after drift");

        // Color histogram after execution.
        let mut hist = std::collections::HashMap::new();
        for c in drifted_img.chunks_exact(4) {
            *hist.entry((c[0], c[1], c[2])).or_insert(0u32) += 1;
        }
        let mut v: Vec<_> = hist.into_iter().collect();
        v.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
        for (color, n) in v.iter().take(5) {
            println!("    color {:?} x {}", color, n);
        }
    }
    #[cfg(not(feature = "gpu"))]
    {
        println!("\n[6] GPU render skipped (run with --features gpu for pixel proof).");
    }

    println!("\n=== PHASE 5 GLYPH EXECUTION VERIFIED ===");
    Ok(())
}
