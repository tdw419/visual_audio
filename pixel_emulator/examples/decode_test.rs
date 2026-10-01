//! Test RV64 instruction decoder
//!
//! Demonstrates decoding of various RISC-V instruction formats.

use pixel_emulator::RV64Decoder;

fn main() {
    env_logger::init();

    println!("=== RV64 Instruction Decoder Test ===\n");

    // Test various instruction formats

    // I-type: ADDI x1, x0, 0x100
    println!("I-type: ADDI x1, x0, 0x100");
    let addi_bits: u32 = 0x00100093;
    match RV64Decoder::decode(addi_bits) {
        Ok(inst) => println!("  Decoded: {:?}\n", inst),
        Err(e) => println!("  Error: {:?}\n", e),
    }

    // U-type: LUI x2, 0x1000
    println!("U-type: LUI x2, 0x1000");
    let lui_bits: u32 = 0x00001137;
    match RV64Decoder::decode(lui_bits) {
        Ok(inst) => println!("  Decoded: {:?}\n", inst),
        Err(e) => println!("  Error: {:?}\n", e),
    }

    // S-type: SW x3, 0(x1)
    println!("S-type: SW x3, 0(x1)");
    let sw_bits: u32 = 0x00312023;
    match RV64Decoder::decode(sw_bits) {
        Ok(inst) => println!("  Decoded: {:?}\n", inst),
        Err(e) => println!("  Error: {:?}\n", e),
    }

    // B-type: BEQ x1, x2, 0x10
    println!("B-type: BEQ x1, x2, 0x10");
    let beq_bits: u32 = 0x00209463;
    match RV64Decoder::decode(beq_bits) {
        Ok(inst) => println!("  Decoded: {:?}\n", inst),
        Err(e) => println!("  Error: {:?}\n", e),
    }

    // J-type: JAL x1, 0x100
    println!("J-type: JAL x1, 0x100");
    let jal_bits: u32 = 0x080000ef;
    match RV64Decoder::decode(jal_bits) {
        Ok(inst) => println!("  Decoded: {:?}\n", inst),
        Err(e) => println!("  Error: {:?}\n", e),
    }

    // R-type: ADD x3, x1, x2
    println!("R-type: ADD x3, x1, x2");
    let add_bits: u32 = 0x002081b3;
    match RV64Decoder::decode(add_bits) {
        Ok(inst) => println!("  Decoded: {:?}\n", inst),
        Err(e) => println!("  Error: {:?}\n", e),
    }

    println!("=== Decoder test complete ===");
}