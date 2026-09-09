// V5 Phase 4: Self-Hosting File Execution
//
// The Spatial Program Coordinator reads new .glyph programs and visual
// assets directly from the V4 PDB (Pixel Database) using spatial memory
// coordinates — entirely bypassing standard file systems.
//
// This example:
//   1. Encodes a .glyph program (spatial_coordinator.glyph) + a window
//      manifest into a tiled PDB directory (V4.1, PNG frames only).
//   2. Decodes both tables back from the PDB.
//   3. Bootstraps the WCB `data_memory`: program bytes at PROGRAM_BASE,
//      WCB rows seeded from the PDB-decoded manifest.
//   4. Renders on the GPU and verifies the PDB-loaded state produces the
//      same framebuffer as the canonical hardcoded seed (seed_wcb_state).
//
// Usage:
//   cargo run --example v5_self_host --features gpu -- [pdb_dir] [glyph_file]
//
// With no args, a default PDB is written to /tmp/pdb_self_host and the
// repo's spatial_coordinator.glyph is used.

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

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let default_pdb = "/tmp/pdb_self_host".to_string();
    let default_glyph = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../spatial_coordinator.glyph"
    );

    let mut args = std::env::args().skip(1);
    let pdb_dir = args.next().unwrap_or(default_pdb);
    let glyph_path = args.next().unwrap_or_else(|| default_glyph.to_string());

    println!("=== V5 Phase 4: Self-Hosting File Execution ===");
    println!("PDB dir:      {}", pdb_dir);
    println!("Glyph source: {}", glyph_path);

    // 1. Load the .glyph program bytes.
    let program = std::fs::read(&glyph_path)
        .map_err(|e| format!("read {}: {e}", glyph_path))?;
    println!("\n[1] Loaded .glyph program: {} bytes", program.len());
    println!("    sha256: {}", sha256_hex(&program));

    // 2. Encode program + manifest into tiled PDB (PNG frames).
    let defs = geos_pixel_v5::spatial_loader::canonical_manifest();
    geos_pixel_v5::spatial_loader::encode_manifest_to_pdb(&pdb_dir, &program, &defs)?;
    println!("\n[2] Encoded {} windows + glyph program into PDB at {}", defs.len(), pdb_dir);

    // List the produced tile PNGs.
    let pdb_path = PathBuf::from(&pdb_dir);
    let mut png_count = 0;
    if let Ok(entries) = std::fs::read_dir(&pdb_path) {
        for entry in entries.flatten() {
            let p = entry.path();
            if p.extension().map_or(false, |e| e == "png") {
                png_count += 1;
                println!("    tile: {}", p.file_name().unwrap().to_string_lossy());
            }
        }
    }
    println!("    total tile PNGs: {}", png_count);

    // 3. Decode back from the PDB — the "self-hosting read".
    let (decoded_program, decoded_defs) =
        geos_pixel_v5::spatial_loader::decode_manifest_from_pdb(&pdb_dir)?;
    println!("\n[3] Decoded from PDB: program {} bytes, {} windows",
             decoded_program.len(), decoded_defs.len());

    if decoded_program != program {
        eprintln!("FAIL: decoded program differs from source!");
        std::process::exit(1);
    }
    if decoded_defs != defs {
        eprintln!("FAIL: decoded manifest differs from source!");
        std::process::exit(1);
    }
    println!("    ✓ program byte-identical, manifest byte-identical");

    // 4. Bootstrap WCB memory from the PDB.
    let mut mem = vec![0i32; MEM_WORDS];
    let (loaded_program, loaded_defs, prog_words) =
        geos_pixel_v5::spatial_loader::bootstrap_from_pdb(&mut mem, &pdb_dir)?;
    assert_eq!(loaded_program, program);
    assert_eq!(loaded_defs, defs);
    println!("\n[4] Bootstrapped WCB from PDB: program at word {} ({} words), WCB rows 100..164",
             geos_pixel_v5::spatial_loader::PROGRAM_BASE, prog_words);

    for i in 0..geos_pixel_v5::window::MAX_WINDOWS {
        let b = geos_pixel_v5::window::WCB_BASE + i * geos_pixel_v5::window::WCB_STRIDE;
        println!("    WCB{}: state={} x={} y={} z={} tick_addr={} vis={}",
                 i, mem[b], mem[b + 1], mem[b + 2], mem[b + 5], mem[b + 6], mem[b + 8]);
    }

    // Compare against the canonical hardcoded seed (WCB region only — the
    // program region is intentionally extra). tick_addr (field 6) is excluded:
    // the PDB-loaded manifest points it at PROGRAM_BASE (the loaded program's
    // entry), while seed_wcb_state leaves it 0 (no program loaded).
    let mut reference = vec![0i32; MEM_WORDS];
    seed_wcb_state(&mut reference);
    let mut wcb_match = true;
    for i in 0..geos_pixel_v5::window::MAX_WINDOWS {
        let base = geos_pixel_v5::window::WCB_BASE + i * geos_pixel_v5::window::WCB_STRIDE;
        for j in 0..16 {
            if j == 6 {
                let expected = if mem[base] != 0 { geos_pixel_v5::spatial_loader::PROGRAM_BASE as i32 } else { 0 };
                if mem[base + 6] != expected {
                    wcb_match = false;
                }
            } else if mem[base + j] != reference[base + j] {
                wcb_match = false;
            }
        }
    }
    println!("    WCB region matches canonical seed: {}", if wcb_match { "YES" } else { "NO" });
    if !wcb_match {
        eprintln!("FAIL: PDB-loaded WCB differs from canonical seed");
        std::process::exit(1);
    }

    // Read back the program bytes from spatial memory and verify.
    let mem_program = geos_pixel_v5::spatial_loader::read_program_from_memory(&mem, prog_words);
    let mem_match = &mem_program[..program.len()] == program.as_slice();
    println!("    program bytes in spatial memory match source: {}", if mem_match { "YES" } else { "NO" });
    if !mem_match {
        eprintln!("FAIL: spatial memory program differs from source");
        std::process::exit(1);
    }

    // 5. GPU render + verify framebuffer equality with the canonical seed.
    #[cfg(feature = "gpu")]
    {
        println!("\n[5] GPU render (Vulkan, high-performance adapter)...");
        let ws = WindowSystem::new().expect("WindowSystem init failed");
        println!("    adapter: {}", ws.adapter_name());

        // Render the PDB-loaded state.
        ws.write_memory(&mem);
        let pdb_img = ws.render();

        // Render the canonical seed.
        let mut seed_mem = vec![0i32; MEM_WORDS];
        seed_wcb_state(&mut seed_mem);
        ws.write_memory(&seed_mem);
        let seed_img = ws.render();

        let identical = pdb_img == seed_img;
        println!("    framebuffer identical to canonical seed: {}", if identical { "YES" } else { "NO" });
        if !identical {
            let diff = pdb_img
                .iter()
                .zip(seed_img.iter())
                .filter(|(a, b)| a != b)
                .count();
            eprintln!("FAIL: {} pixel bytes differ between PDB-loaded and seed render", diff);
            std::process::exit(1);
        }

        // Sanity: nonzero pixels present (windows actually rendered).
        let nonzero = pdb_img.iter().filter(|&&b| b != 0).count();
        println!("    nonzero pixel bytes in render: {}", nonzero);
        if nonzero == 0 {
            eprintln!("FAIL: render is blank");
            std::process::exit(1);
        }

        // Color histogram (proves the 3 windows, with z-order overlap).
        let mut hist = std::collections::HashMap::new();
        for c in pdb_img.chunks_exact(4) {
            *hist.entry((c[0], c[1], c[2])).or_insert(0u32) += 1;
        }
        let mut v: Vec<_> = hist.into_iter().collect();
        v.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
        for (color, n) in v.iter().take(6) {
            println!("    color {:?} x {}", color, n);
        }
    }
    #[cfg(not(feature = "gpu"))]
    {
        println!("\n[5] GPU render skipped (run with --features gpu to verify framebuffer).");
        println!("    CPU-side verification above is sufficient for the PDB round-trip.");
    }

    println!("\n=== PHASE 4 SELF-HOSTING VERIFIED ===");
    Ok(())
}
