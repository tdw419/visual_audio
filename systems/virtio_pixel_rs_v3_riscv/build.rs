fn main() {
    // Use absolute path for linker script
    let manifest_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap();
    let linker_script = format!("{}/src/linker.ld", manifest_dir);
    println!("cargo:rerun-if-changed={}", linker_script);
    println!("cargo:rustc-link-arg=-T{}", linker_script);
}