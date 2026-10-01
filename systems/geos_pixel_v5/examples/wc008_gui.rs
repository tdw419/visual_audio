use geos_pixel_v5::window::{self, WindowEvent, WindowSystem};
use minifb::{Window, WindowOptions, Key, MouseButton, MouseMode};

fn main() {
    let ws = WindowSystem::new().expect("WindowSystem init failed");
    println!("GPU adapter: {}", ws.adapter_name());

    let mut mem = vec![0i32; window::MEM_WORDS];
    window::seed_wcb_state(&mut mem);
    ws.write_memory(&mem);

    let mut window_ui = Window::new(
        "Geometry OS - Native GPU Window Coordinator",
        window::SCREEN_W as usize,
        window::SCREEN_H as usize,
        WindowOptions::default(),
    ).expect("Unable to open window");

    // Limit to ~60fps
    window_ui.limit_update_rate(Some(std::time::Duration::from_micros(16600)));

    let mut is_dragging = false;
    let mut drag_start = (0.0, 0.0);

    while window_ui.is_open() && !window_ui.is_key_down(Key::Escape) {
        // Handle mouse input
        if let Some(pos) = window_ui.get_mouse_pos(MouseMode::Clamp) {
            if window_ui.get_mouse_down(MouseButton::Left) {
                if !is_dragging {
                    is_dragging = true;
                    drag_start = pos;
                    // Click event: raise to top
                    let ev = WindowEvent::click(pos.0 as i32, pos.1 as i32);
                    ws.send_event(&ev);
                } else {
                    // Drag event
                    let dx = (pos.0 - drag_start.0) as i32;
                    let dy = (pos.1 - drag_start.1) as i32;
                    if dx != 0 || dy != 0 {
                        let ev = WindowEvent::drag(drag_start.0 as i32, drag_start.1 as i32, dx, dy);
                        ws.send_event(&ev);
                        drag_start = pos; // update anchor
                    }
                }
            } else {
                is_dragging = false;
            }
        }

        // Render from GPU
        let img = ws.render();
        
        // minifb expects ARGB format (0xAARRGGBB), but our img buffer is RGBA (bytes: R, G, B, A).
        // Let's convert it. The ws.render() returns a flat Vec<u8> where every 4 bytes is R, G, B, A.
        let mut fb: Vec<u32> = Vec::with_capacity(img.len() / 4);
        for chunk in img.chunks_exact(4) {
            let r = chunk[0] as u32;
            let g = chunk[1] as u32;
            let b = chunk[2] as u32;
            let a = chunk[3] as u32;
            fb.push((a << 24) | (r << 16) | (g << 8) | b);
        }

        window_ui.update_with_buffer(&fb, window::SCREEN_W as usize, window::SCREEN_H as usize)
            .unwrap();
    }
}
