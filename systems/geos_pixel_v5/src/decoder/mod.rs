/// V3→V4 Ported Pixel Decoder
///
/// This module ports V3's PNG decoding infrastructure (no_std compatible)
/// for use in V4's tiled PDB boot path.
///
/// Key differences from image-crate decoder:
/// - No std/alloc dependencies (suitable for bootloader)
/// - Explicit DEFLATE decompression (miniz_oxide)
/// - Manual PNG unfiltering
/// - Hilbert curve integration via geos_pixel_v5::HilbertCurve

pub mod pixel_decoder;

pub use pixel_decoder::PixelDecoder;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_module_imports() {
        // Verify module structure is correct
        let _decoder = PixelDecoder::new();
    }
}