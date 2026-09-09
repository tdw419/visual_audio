//! WC008 foundation: run the spatial windowing system natively from
//! geos_pixel (the Rust boot-path crate) on the GPU.
//!
//! This is the roadmap's original WC007 verification command made real —
//! `cargo run --example interactive_windows`. It reproduces the
//! Python-incubator scenario (test_window_interaction.py) in Rust:
//! baseline render, click-to-raise, drag-to-move, with WCB state diffed
//! against the Rust semantic mirror (`window::interact_model`) after every
//! event, and rendered pixels asserted at every phase.
//!
//! Run:
//! ```bash
//! cd systems/geos_pixel
//! cargo run --example interactive_windows --features gpu
//! ```

use geos_pixel::window::{self, WindowEvent, WindowSystem};
use image::RgbaImage;

fn main() {
    let ws = WindowSystem::new().expect("WindowSystem init failed");
    println!("GPU adapter: {}", ws.adapter_name());

    let mut mem = vec![0i32; window::MEM_WORDS];
    window::seed_wcb_state(&mut mem);
    ws.write_memory(&mem);

    // ---- Baseline render (same seed as WC006/WC007 incubator) ----
    let img = ws.render();
    assert_eq!(ws.pixel(&img, 10, 10), [34, 34, 34, 255], "background");
    assert_eq!(ws.pixel(&img, 30, 30), [0, 0, 255, 255], "BLUE window");
    assert_eq!(ws.pixel(&img, 60, 60), [255, 0, 0, 255], "RED over BLUE");
    assert_eq!(ws.pixel(&img, 110, 110), [0, 255, 0, 255], "GREEN over RED");
    assert_eq!(ws.pixel(&img, 150, 150), [0, 255, 0, 255], "GREEN (Z=2) beats RED (Z=1)");
    RgbaImage::from_raw(window::SCREEN_W, window::SCREEN_H, img.clone())
        .expect("rgba image")
        .save("/tmp/rust_wc006_baseline.png")
        .expect("save baseline");
    println!("baseline OK: BLUE under RED under GREEN (same as incubator WC006)");

    // ---- Click at (60,60): topmost window there is RED -> raise to front ----
    let ev = WindowEvent::click(60, 60);
    let mut mirror = mem.clone();
    window::interact_model(&mut mirror, &ev);
    ws.send_event(&ev);
    let gpu_mem = ws.read_memory();
    let mism = gpu_mem.iter().zip(mirror.iter()).filter(|(a, b)| a != b).count();
    println!("after click: GPU-vs-mirror mismatches: {mism} (of {} words)", window::MEM_WORDS);
    assert_eq!(mism, 0, "click mutation diverged from semantic mirror");
    println!(
        "after click: WCB0 Z = {} (expect 3 = max_z+1)",
        gpu_mem[window::WCB_BASE + 5]
    );
    assert_eq!(gpu_mem[window::WCB_BASE + 5], 3);
    mem = mirror;

    let img = ws.render();
    assert_eq!(ws.pixel(&img, 150, 150), [255, 0, 0, 255], "RED raised above GREEN at overlap");
    assert_eq!(ws.pixel(&img, 110, 210), [0, 255, 0, 255], "GREEN exclusive region stays GREEN");
    println!("click raise OK: RED now renders above GREEN at the overlap");

    // ---- Drag RED (still topmost at 60,60) by (+100,+50) ----
    let ev = WindowEvent::drag(60, 60, 100, 50);
    let mut mirror = mem.clone();
    window::interact_model(&mut mirror, &ev);
    ws.send_event(&ev);
    let gpu_mem = ws.read_memory();
    let mism = gpu_mem.iter().zip(mirror.iter()).filter(|(a, b)| a != b).count();
    println!("after drag: GPU-vs-mirror mismatches: {mism} (of {} words)", window::MEM_WORDS);
    assert_eq!(mism, 0, "drag mutation diverged from semantic mirror");
    println!(
        "after drag: WCB0 X = {}, Y = {} (expect 150, 100)",
        gpu_mem[window::WCB_BASE + 1],
        gpu_mem[window::WCB_BASE + 2]
    );
    assert_eq!(gpu_mem[window::WCB_BASE + 1], 150);
    assert_eq!(gpu_mem[window::WCB_BASE + 2], 100);

    let img = ws.render();
    assert_eq!(ws.pixel(&img, 60, 60), [0, 0, 255, 255], "old spot back to BLUE");
    assert_eq!(ws.pixel(&img, 250, 150), [255, 0, 0, 255], "RED at new position");
    assert_eq!(ws.pixel(&img, 150, 150), [255, 0, 0, 255], "RED still topmost");
    assert_eq!(ws.pixel(&img, 110, 210), [0, 255, 0, 255], "GREEN exclusive region stays GREEN");
    RgbaImage::from_raw(window::SCREEN_W, window::SCREEN_H, img.clone())
        .expect("rgba image")
        .save("/tmp/rust_wc007_after_drag.png")
        .expect("save after drag");
    println!("drag move OK: RED relocated to (150,100) and remains topmost");

    println!("VERDICT: PASS - geos_pixel (Rust) window system: render + interaction verified on GPU");
}
