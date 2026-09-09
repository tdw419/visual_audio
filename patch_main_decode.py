import os
with open("systems/virtio_pixel_rs_v3_riscv/src/main.rs", "r") as f:
    main_rs = f.read()

import re

# Replace hello.img with hello.rts.png
png_size = os.path.getsize("boot_images/hello.rts.png")
main_rs = re.sub(r'static HELLO_IMG: \[u8; \d+\] = \*include_bytes!\("\.\./hello\.img"\);', 
                 f'static HELLO_PNG: [u8; {png_size}] = *include_bytes!("../../boot_images/hello.rts.png");', main_rs)

# Inside rust_main, decode the PNG
decode_logic = """
    let image_png = &HELLO_PNG[..];
    virtio_pixel_rs_v3_riscv::println!("Decoding PXC1 Hilbert PNG ({} bytes)...", image_png.len());
    let mut decoder = virtio_pixel_rs_v3_shared::decoder::PixelDecoder::new();
    let image_vec = match decoder.decode_geos_pixel_container(image_png) {
        Ok(v) => v,
        Err(e) => {
            virtio_pixel_rs_v3_riscv::println!("Decode error: {}", e);
            loop {}
        }
    };
    let image = &image_vec[..];
    virtio_pixel_rs_v3_riscv::println!("Decode success! Output size: {} bytes", image.len());
"""

# Find `let image = &HELLO_IMG[..];` and replace it
main_rs = re.sub(r'let image = &HELLO_IMG\[\.\.\];', decode_logic, main_rs)

with open("systems/virtio_pixel_rs_v3_riscv/src/main.rs", "w") as f:
    f.write(main_rs)

