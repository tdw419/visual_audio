with open("systems/virtio_pixel_rs_v3_riscv/src/main.rs", "r") as f:
    main_rs = f.read()

# Fix the pub mod uart at the top
main_rs = main_rs.replace("pub mod uart;\n", "", 1)
main_rs = main_rs.replace("#![no_main]\nextern crate alloc;", "#![no_main]\nextern crate alloc;\n\npub mod uart;")

with open("systems/virtio_pixel_rs_v3_riscv/src/main.rs", "w") as f:
    f.write(main_rs)
