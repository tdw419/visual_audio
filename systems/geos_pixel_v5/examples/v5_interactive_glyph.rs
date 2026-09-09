// V5 Phase 3+5: Interactive KMS with evdev input + Real-Time Glyph Execution
// Reads mouse events from /dev/input/event0, dispatches to GPU coordinator,
// and runs the glyph interpreter to animate window drift each frame.

#[cfg(feature = "gpu")]
fn main() {
    use drm::buffer::DrmFourcc;
    use drm::control::{connector, crtc, Device as ControlDevice};
    use drm::Device;
    use std::io;
    use std::os::unix::io::{AsFd, BorrowedFd};
    use std::time::Instant;

    #[cfg(feature = "evdev")]
    use geos_pixel_v5::evdev_input::EvdevReader;

    #[cfg(feature = "glyph")]
    use geos_pixel_v5::glyph::{GlyphCpu, GlyphProgram, STACK_BASE};

    struct Card(std::fs::File);

    impl AsFd for Card {
        fn as_fd(&self) -> BorrowedFd<'_> {
            self.0.as_fd()
        }
    }
    impl Device for Card {}
    impl ControlDevice for Card {}

    impl Card {
        fn open(path: &str) -> io::Result<Self> {
            let mut options = std::fs::OpenOptions::new();
            options.read(true).write(true);
            Ok(Card(options.open(path)?))
        }
    }

    let dri_device = std::env::var("V5_DRI_CARD").unwrap_or_else(|_| "/dev/dri/card0".to_string());
    let card = Card::open(&dri_device).expect(&format!("open {} (run as root)", dri_device));

    let res = card.resource_handles().expect("resource_handles");
    let coninfo: Vec<connector::Info> = res
        .connectors()
        .iter()
        .flat_map(|c| card.get_connector(*c, true))
        .collect();
    let crtcinfo: Vec<crtc::Info> = res.crtcs().iter().flat_map(|c| card.get_crtc(*c)).collect();

    let con = coninfo
        .iter()
        .find(|i| i.state() == connector::State::Connected)
        .expect("no connected display connector found");
    let &mode = con.modes().first().expect("connector has no modes");
    let (disp_w, disp_h) = mode.size();
    let crtc = crtcinfo.first().expect("no crtcs");

    println!(
        "V5 Interactive: {}x{} on {:?}",
        disp_w, disp_h, con.interface()
    );

    let fmt = DrmFourcc::Xrgb8888;
    let mut db = card
        .create_dumb_buffer((disp_w.into(), disp_h.into()), fmt, 32)
        .expect("create_dumb_buffer");
    let fb = card.add_framebuffer(&db, 24, 32).expect("add_framebuffer");

    card
        .set_crtc(crtc.handle(), Some(fb), (0, 0), &[con.handle()], Some(mode))
        .expect("set_crtc");

    let ws =
        geos_pixel_v5::window::WindowSystem::new().expect("WindowSystem init failed");
    println!("GPU adapter: {}", ws.adapter_name());

    let mut mem = vec![0i32; geos_pixel_v5::window::MEM_WORDS];
    geos_pixel_v5::window::seed_wcb_state(&mut mem);
    ws.write_memory(&mem);

    let dw = disp_w as usize;
    let dh = disp_h as usize;

    // Initialize evdev reader if feature is available
    #[cfg(feature = "evdev")]
    let mut evdev = match EvdevReader::open(disp_w as i32, disp_h as i32) {
        Ok(reader) => reader,
        Err(e) => {
            eprintln!("Warning: Failed to open evdev device: {}", e);
            eprintln!("Continuing without input support...");
            return;
        }
    };

    // Load and assemble the glyph program
    #[cfg(feature = "glyph")]
    let glyph_program = {
        use std::path::PathBuf;
        let mut glyph_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        glyph_path.push("../../spatial_coordinator.glyph");
        let src =
            std::fs::read_to_string(&glyph_path).expect(&format!("read {:?}", glyph_path));
        let prog = GlyphProgram::assemble(&src, 8)
            .expect("assemble spatial_coordinator.glyph");

        // Seed TICK_ADDR for active windows to their real tick routines
        let tick_labels = [
            ("window_tick0", 0usize),
            ("window_tick1", 1),
            ("window_tick2", 2),
        ];
        for (label, i) in tick_labels {
            let packed = prog
                .label_packed(label)
                .expect(&format!("tick label {} exists", label));
            let base = geos_pixel_v5::wcb::WCB_BASE + i * geos_pixel_v5::wcb::WCB_STRIDE;
            mem[base + 6] = packed as i32; // TICK_ADDR slot
        }

        println!("Loaded glyph program: {} instructions", prog.instrs.len());
        prog
    };

    #[cfg(feature = "glyph")]
    let mut cpu = GlyphCpu::new();

    // How many glyph interpreter steps to run per frame
    // 1000 steps ≈ 10 supervisor passes ≈ ~20 pixels of drift at 2x speed
    const TICKS_PER_FRAME: usize = 1000;

    println!("Phase 3+5: Running interactive loop with evdev input + real-time glyph execution");
    println!("  Click to raise windows, drag to move them");
    println!("  Windows drift automatically via glyph interpreter");
    println!("  Press Ctrl+C to exit");

    let mut frame_count = 0u64;
    let start = Instant::now();
    let mut last_stats = start;
    let mut last_glyph_time = start;

    loop {
        // Read and dispatch evdev events (if available)
        #[cfg(feature = "evdev")]
        {
            let mut processed = 0;
            while processed < 10 {
                if let Ok(Some(ev)) = evdev.next_window_event() {
                    ws.send_event(&ev);
                    processed += 1;
                } else {
                    break;
                }
            }
        }

        // Run glyph interpreter (window drift)
        #[cfg(feature = "glyph")]
        {
            let glyph_start = Instant::now();
            let steps = cpu.run(&glyph_program, &mut mem, TICKS_PER_FRAME);
            let glyph_elapsed = glyph_start.elapsed();

            // Update GPU memory after glyph execution
            ws.write_memory(&mem);

            // Log glyph timing every 5 seconds
            let now = Instant::now();
            if now.duration_since(last_glyph_time).as_secs() >= 5 {
                println!(
                    "Glyph: {} steps/frame, {:.2}ms ({:.1}K steps/sec)",
                    steps,
                    glyph_elapsed.as_secs_f64() * 1000.0,
                    (steps as f64) / glyph_elapsed.as_secs_f64() / 1000.0
                );
                last_glyph_time = now;
            }
        }

        // Render frame
        let img = ws.render();
        let mut map = card.map_dumb_buffer(&mut db).expect("map_dumb_buffer");
        let stride = map.len() / dh;

        for y in 0..dh.min(geos_pixel_v5::window::SCREEN_H as usize) {
            let row = &mut map.as_mut()
                [y * stride..y * stride + dw.min(geos_pixel_v5::window::SCREEN_W as usize) * 4];
            for x in 0..dw.min(geos_pixel_v5::window::SCREEN_W as usize) {
                let si = (y * geos_pixel_v5::window::SCREEN_W as usize + x) * 4;
                let (r, g, b) = (img[si], img[si + 1], img[si + 2]);
                let di = x * 4;
                row[di] = b;
                row[di + 1] = g;
                row[di + 2] = r;
                row[di + 3] = 0;
            }
        }

        // dirty_framebuffer for virtio-gpu shadow buffer sync
        let clips = [drm::control::ClipRect::new(0, 0, disp_w as u16, disp_h as u16)];
        card.dirty_framebuffer(fb, &clips).ok();

        frame_count += 1;
        let now = Instant::now();
        if now.duration_since(last_stats).as_secs() >= 5 {
            let elapsed = now.duration_since(start).as_secs_f64();
            let fps = frame_count as f64 / elapsed;

            // Log window positions (prove glyph execution is working)
            #[cfg(feature = "glyph")]
            {
                let b0 = geos_pixel_v5::wcb::WCB_BASE;
                let b1 = b0 + geos_pixel_v5::wcb::WCB_STRIDE;
                let b2 = b0 + 2 * geos_pixel_v5::wcb::WCB_STRIDE;
                println!(
                    "Stats: {} frames, {:.1} FPS | WCB0=({},{} cnt={}) WCB1=({},{} cnt={}) WCB2=({},{} cnt={})",
                    frame_count,
                    fps,
                    mem[b0 + 1],
                    mem[b0 + 2],
                    mem[b0 + 7],
                    mem[b1 + 1],
                    mem[b1 + 2],
                    mem[b1 + 7],
                    mem[b2 + 1],
                    mem[b2 + 2],
                    mem[b2 + 7]
                );
            }
            #[cfg(not(feature = "glyph"))]
            {
                println!("Stats: {} frames, {:.1} FPS", frame_count, fps);
            }

            last_stats = now;
        }

        std::thread::sleep(std::time::Duration::from_millis(16)); // ~60 FPS
    }

    card.destroy_framebuffer(fb).ok();
    card.destroy_dumb_buffer(db).ok();
}

#[cfg(not(feature = "gpu"))]
fn main() {
    eprintln!("This example requires the 'gpu' feature. Run with: --features gpu");
    std::process::exit(1);
}