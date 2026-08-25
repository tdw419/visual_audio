// V5 Phase 3: Interactive KMS with evdev input
// Reads mouse events from /dev/input/event0, dispatches to GPU coordinator

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

    // Frame-dump hook: SIGUSR1 writes the current frame to /tmp/v5_frame_dump.png
    // so an external process can inspect what's on screen without needing a
    // compositor or DRM buffer handle of its own (dumb-buffer GEM handles are
    // private to this process's DRM fd, so they can't just be mmap'd from
    // outside without PRIME/dma-buf export).
    #[cfg(feature = "evdev")]
    static DUMP_REQUESTED: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
    #[cfg(feature = "evdev")]
    extern "C" fn request_dump(_sig: libc::c_int) {
        DUMP_REQUESTED.store(true, std::sync::atomic::Ordering::SeqCst);
    }
    #[cfg(feature = "evdev")]
    unsafe {
        libc::signal(libc::SIGUSR1, request_dump as libc::sighandler_t);
    }

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

    println!("V5 Interactive: {}x{} on {:?}", disp_w, disp_h, con.interface());

    let fmt = DrmFourcc::Xrgb8888;
    let mut db = card
        .create_dumb_buffer((disp_w.into(), disp_h.into()), fmt, 32)
        .expect("create_dumb_buffer");
    let fb = card.add_framebuffer(&db, 24, 32).expect("add_framebuffer");

    card.set_crtc(crtc.handle(), Some(fb), (0, 0), &[con.handle()], Some(mode))
        .expect("set_crtc");

    let ws = geos_pixel_v5::window::WindowSystem::new().expect("WindowSystem init failed");
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

    println!("Phase 3: Running interactive loop with evdev input");
    println!("  Click to raise windows, drag to move them");
    println!("  Press Ctrl+C to exit");

    let mut frame_count = 0u64;
    let start = Instant::now();
    let mut last_stats = start;

    loop {
        // Read and dispatch evdev events (if available)
        #[cfg(feature = "evdev")]
        {
            // Process all available events without blocking
            let mut processed = 0;
            while processed < 10 {  // Limit per-frame to prevent starvation
                if let Ok(Some(ev)) = evdev.next_window_event() {
                    println!("EVENT: type={} x={} y={} dx={} dy={}",
                             ev.event_type, ev.x, ev.y, ev.dx, ev.dy);
                    ws.send_event(&ev);
                    // Read back WCB state after the dispatch to verify the
                    // GPU interact shader actually mutated memory.
                    let mem = ws.read_memory();
                    for i in 0..geos_pixel_v5::window::MAX_WINDOWS {
                        let b = geos_pixel_v5::window::WCB_BASE + i * geos_pixel_v5::window::WCB_STRIDE;
                        println!("  WCB{}: state={} x={} y={} z={} vis={}",
                                 i, mem[b], mem[b+1], mem[b+2], mem[b+5], mem[b+8]);
                    }
                    processed += 1;
                } else {
                    break;
                }
            }
        }

        // Render frame
        let img = ws.render();

        #[cfg(feature = "evdev")]
        if DUMP_REQUESTED.swap(false, std::sync::atomic::Ordering::SeqCst) {
            let path = "/tmp/v5_frame_dump.png";
            match image::save_buffer(
                path,
                &img[..dw.min(geos_pixel_v5::window::SCREEN_W as usize)
                    * dh.min(geos_pixel_v5::window::SCREEN_H as usize)
                    * 4],
                dw.min(geos_pixel_v5::window::SCREEN_W as usize) as u32,
                dh.min(geos_pixel_v5::window::SCREEN_H as usize) as u32,
                image::ColorType::Rgba8,
            ) {
                Ok(()) => println!("Frame dumped to {}", path),
                Err(e) => eprintln!("Frame dump failed: {}", e),
            }
        }

        let mut map = card.map_dumb_buffer(&mut db).expect("map_dumb_buffer");
        let stride = map.len() / dh;

        for y in 0..dh.min(geos_pixel_v5::window::SCREEN_H as usize) {
            let row = &mut map.as_mut()[y * stride..y * stride + dw.min(geos_pixel_v5::window::SCREEN_W as usize) * 4];
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
            println!("Stats: {} frames, {:.1} FPS", frame_count, fps);
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