// Hilbert Compute Benchmark - Phase 3
// Proves two things:
// 1. Sub-1ms latency for decode when texture is already loaded
// 2. Byte-for-byte correctness against CPU reference extraction

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Instant;
use virtio_pixel_rs::{
    hilbert_compute::HilbertDecoder, wgpu_texture_loader::MkvTexture,
    SpatialMkvExtractor, wgpu_texture_loader,
};

fn main() -> anyhow::Result<()> {
    env_logger::init();

    println!("========================================");
    println!("Hilbert Compute Benchmark - Phase 3");
    println!("========================================");
    println!();

    // Load MKV path - use visual_audio.mkv (455MB ubuntu disk) or fall back
    let mkv_path = PathBuf::from("../../visual_audio.mkv");
    let mkv_path = if !mkv_path.exists() {
        PathBuf::from("../../test_spatial_10mb.mkv")
    } else {
        mkv_path
    };

    if !mkv_path.exists() {
        eprintln!("ERROR: No MKV found - need visual_audio.mkv or test_spatial_10mb.mkv");
        return Ok(());
    }

    println!("[1] Initializing WGPU...");
    let (_instance, _adapter, device, queue) = wgpu_texture_loader::init_wgpu()?;
    let device = Arc::new(device);
    let queue = Arc::new(queue);
    println!("    ✓ WGPU initialized");
    println!();

    // Load frame 1 (first data frame) as GPU texture
    println!("[2] Loading MKV frame as GPU texture...");
    let frame_idx = 1; // First data frame (after directory)

    let load_start = Instant::now();
    let texture = MkvTexture::load_frame(&device, &queue, &mkv_path, frame_idx)?;
    let load_time = load_start.elapsed();

    println!(
        "    ✓ Frame {} loaded in {:.2?} ms",
        frame_idx,
        load_time.as_millis()
    );
    println!(
        "    Texture: {}×{} pixels",
        texture.extent.width,
        texture.extent.height
    );
    println!();

    // Initialize Hilbert compute shader
    println!("[3] Initializing Hilbert compute shader...");
    let decoder = HilbertDecoder::new(device, queue)?;
    println!("    ✓ Compute shader pipeline compiled");
    println!();

    // Calculate test size based on frame dimensions (use 32K for safety)
    let frame_capacity = (texture.extent.width as usize) * (texture.extent.height as usize);
    let test_size = (32 * 1024).min(frame_capacity as u32); // Max 32KB
    let test_offset = 0u32;

    println!("[4] Test 1: Latency Benchmark ({} bytes)", test_size);
    println!("    Decoding from GPU vs CPU baseline...");
    println!();

    // Warm up (compile shader, etc.)
    decoder.decode(&texture, test_offset, 1024)?;

    // Run benchmark
    let mut gpu_times = Vec::new();
    let iterations = 100;

    for i in 0..iterations {
        let start = Instant::now();
        let _decoded = decoder.decode(&texture, test_offset, test_size)?;
        let elapsed = start.elapsed();
        gpu_times.push(elapsed);

        if (i + 1) % 20 == 0 {
            println!("      Progress: {}/{}", i + 1, iterations);
        }
    }

    let gpu_avg: f64 = gpu_times
        .iter()
        .map(|d| d.as_secs_f64() * 1000.0)
        .sum::<f64>()
        / iterations as f64;
    let gpu_min = gpu_times.iter().min().unwrap();
    let gpu_max = gpu_times.iter().max().unwrap();
    let gpu_p95 = {
        let mut sorted = gpu_times.clone();
        sorted.sort();
        sorted[(iterations as usize * 95 / 100).min(iterations as usize - 1)]
    };

    println!("    GPU Results:");
    println!("      Average: {:.3} ms", gpu_avg);
    println!("      Min:     {:.3} ms", gpu_min.as_secs_f64() * 1000.0);
    println!("      Max:     {:.3} ms", gpu_max.as_secs_f64() * 1000.0);
    println!("      P95:     {:.3} ms", gpu_p95.as_secs_f64() * 1000.0);
    println!();

    // CPU baseline
    println!("    Running CPU baseline...");
    let cpu_start = Instant::now();
    let mut extractor = SpatialMkvExtractor::new(&mkv_path, "test.pixel")?;
    let cpu_result = extractor.read(test_offset as u64, test_size as u64)?;
    let cpu_elapsed = cpu_start.elapsed();
    let cpu_baseline_ms = cpu_elapsed.as_secs_f64() * 1000.0;

    println!("      CPU baseline: {:.2} ms", cpu_baseline_ms);
    println!();

    // Test 2: Correctness verification
    println!("[5] Test 2: Byte-for-Byte Correctness");
    println!("    Verifying GPU decode against CPU reference...");
    println!();

    let gpu_result = decoder.decode(&texture, test_offset, test_size)?;

    // Compare byte-by-byte
    assert_eq!(gpu_result.len(), cpu_result.len(), "Length mismatch");

    let first_mismatch = gpu_result
        .iter()
        .zip(cpu_result.iter())
        .enumerate()
        .find(|(_i, (gpu, cpu))| gpu != cpu);

    match first_mismatch {
        Some((offset, (gpu_byte, cpu_byte))) => {
            eprintln!("ERROR: Byte mismatch at offset {}", offset);
            eprintln!("  GPU:  0x{:02x}", gpu_byte);
            eprintln!("  CPU:  0x{:02x}", cpu_byte);
            return Err(anyhow::anyhow!("GPU/CPU decode mismatch"));
        }
        None => println!("    ✓ All {} bytes match", gpu_result.len()),
    }
    println!();

    // Summary
    println!("========================================");
    println!("PHASE 3 RESULTS");
    println!("========================================");
    println!();
    println!("Phase 3 Deliverables:");
    println!(
        "  1. GPU Texture Loading:      {:.2} ms (one-time)",
        load_time.as_millis()
    );
    println!("  2. Hilbert Decode Latency:   {:.3} ms (avg)", gpu_avg);
    println!(
        "  3. Sub-1ms Target:           {}",
        if gpu_avg < 1.0 {
            "✓ MET"
        } else {
            "✗ NOT MET"
        }
    );
    println!("  4. Byte-for-Byte Correctness: ✓ VERIFIED");
    println!();
    println!("Performance vs CPU Baseline:");
    let speedup = cpu_baseline_ms / gpu_avg;
    println!(
        "  Speedup: {:.1}× (from {:.2} ms → {:.3} ms)",
        speedup, cpu_baseline_ms, gpu_avg
    );
    println!();

    if gpu_avg < 1.0 {
        println!("🎉 PHASE 3 COMPLETE: Hilbert Compute Shader Proven");
    } else {
        println!("⚠️  PHASE 3 COMPLETE: Latency above target but verified correct");
    }

    Ok(())
}