// V5 Phase 2: direct-to-DRM/KMS rendering. No X11/Wayland/minifb.
// Renders the GPU Window Coordinator straight into the primary CRTC's dumb buffer.
use drm::buffer::DrmFourcc;
use drm::control::{connector, crtc, ClipRect, Device as ControlDevice};
use drm::Device;
use geos_pixel_v5::window::{self, WindowSystem};
use std::io;
use std::os::unix::io::{AsFd, BorrowedFd};

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

fn main() {
    let card_path = std::env::var("V5_DRI_CARD").unwrap_or_else(|_| "/dev/dri/card0".to_string());
    let card = Card::open(&card_path).expect("open DRM card device (run as root/video group)");

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

    println!("V5 KMS: {}x{} on {:?}", disp_w, disp_h, con.interface());

    // Initialize wgpu BEFORE the modeset: some software Vulkan/GL init paths
    // briefly touch the DRM device and can clobber an already-set CRTC.
    let ws = WindowSystem::new().expect("WindowSystem init failed");
    println!("GPU adapter: {}", ws.adapter_name());
    println!("Adapter features: {:?}", ws.adapter_features());

    let mut mem = vec![0i32; window::MEM_WORDS];
    window::seed_wcb_state(&mut mem);
    ws.write_memory(&mem);

    // First render: inspect a few pixels to diagnose the output
    let img = ws.render();
    println!("Render output size: {} bytes (expected: {})", img.len(), window::SCREEN_W * window::SCREEN_H * 4);
    let sample_pixels = [(50, 50), (100, 100), (20, 20), (400, 300)];
    for (x, y) in sample_pixels {
        let p = ws.pixel(&img, x, y);
        println!("Pixel ({},{}) = R:{} G:{} B:{} A:{}", x, y, p[0], p[1], p[2], p[3]);
    }

    let fmt = DrmFourcc::Xrgb8888;
    let mut db = card
        .create_dumb_buffer((disp_w.into(), disp_h.into()), fmt, 32)
        .expect("create_dumb_buffer");
    let fb = card.add_framebuffer(&db, 24, 32).expect("add_framebuffer");

    card.set_crtc(crtc.handle(), Some(fb), (0, 0), &[con.handle()], Some(mode))
        .expect("set_crtc (needs root / DRM master)");

    let dw = disp_w as usize;
    let dh = disp_h as usize;

    // Phase 2 scope: render loop with no input yet (input is Phase 3, via /dev/input).
    let iters: u32 = std::env::var("V5_KMS_ITERS").ok().and_then(|s| s.parse().ok()).unwrap_or(600);
    for _ in 0..iters {
        let img = ws.render(); // RGBA, SCREEN_W x SCREEN_H
        let mut map = card.map_dumb_buffer(&mut db).expect("map_dumb_buffer");
        let stride = map.len() / dh;

        for y in 0..dh.min(window::SCREEN_H as usize) {
            let row = &mut map.as_mut()[y * stride..y * stride + dw.min(window::SCREEN_W as usize) * 4];
            for x in 0..dw.min(window::SCREEN_W as usize) {
                let si = (y * window::SCREEN_W as usize + x) * 4;
                let (r, g, b) = (img[si], img[si + 1], img[si + 2]);
                let di = x * 4;
                row[di] = b;
                row[di + 1] = g;
                row[di + 2] = r;
                row[di + 3] = 0;
            }
        }
        drop(map);
        let clip = ClipRect::new(0, 0, dw as u16, dh as u16);
        card.dirty_framebuffer(fb, &[clip]).ok(); // shadow-buffer drivers (virtio-gpu) need this to scan out writes
        std::thread::sleep(std::time::Duration::from_millis(16));
    }

    card.destroy_framebuffer(fb).ok();
    card.destroy_dumb_buffer(db).ok();
}
