// Isolation test: modeset + fill dumb buffer solid red, hold for N seconds. No wgpu.
use drm::buffer::DrmFourcc;
use drm::control::{connector, crtc, Device as ControlDevice};
use drm::Device;
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
        let mut o = std::fs::OpenOptions::new();
        o.read(true).write(true);
        Ok(Card(o.open(path)?))
    }
}

fn main() {
    let card_path = std::env::var("V5_DRI_CARD").unwrap_or_else(|_| "/dev/dri/card0".to_string());
    let card = Card::open(&card_path).expect("open");
    let res = card.resource_handles().expect("res");
    let coninfo: Vec<connector::Info> = res.connectors().iter().flat_map(|c| card.get_connector(*c, true)).collect();
    let crtcinfo: Vec<crtc::Info> = res.crtcs().iter().flat_map(|c| card.get_crtc(*c)).collect();
    let con = coninfo.iter().find(|i| i.state() == connector::State::Connected).expect("no connector");
    let &mode = con.modes().first().expect("no mode");
    let (w, h) = mode.size();
    let crtc = crtcinfo.first().expect("no crtc");
    println!("solid test: {}x{}", w, h);

    let fmt = DrmFourcc::Xrgb8888;
    let mut db = card.create_dumb_buffer((w.into(), h.into()), fmt, 32).expect("create_dumb_buffer");
    {
        let mut map = card.map_dumb_buffer(&mut db).expect("map");
        let buf = map.as_mut();
        for px in buf.chunks_exact_mut(4) {
            px[0] = 0; px[1] = 0; px[2] = 255; px[3] = 0; // XRGB: B,G,R,X -> pure red
        }
    }
    let fb = card.add_framebuffer(&db, 24, 32).expect("add_fb");
    card.set_crtc(crtc.handle(), Some(fb), (0, 0), &[con.handle()], Some(mode)).expect("set_crtc");
    println!("set_crtc ok, holding red for 15s");
    std::thread::sleep(std::time::Duration::from_secs(15));
    card.destroy_framebuffer(fb).ok();
    card.destroy_dumb_buffer(db).ok();
}
