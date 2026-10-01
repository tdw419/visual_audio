#![cfg_attr(not(feature = "std"), no_std)]

extern crate alloc;

pub mod hilbert;
pub mod decoder;
#[cfg(feature = "std")]
pub mod wcb;
#[cfg(feature = "std")]
pub mod glyph;
#[cfg(feature = "std")]
pub mod canvas;
#[cfg(feature = "std")]
pub mod pdb;
#[cfg(all(feature = "std", feature = "gpu"))]
pub mod window;
#[cfg(all(feature = "std", feature = "gpu", feature = "evdev"))]
pub mod evdev_input;
#[cfg(feature = "std")]
pub mod spatial_loader;
#[cfg(feature = "std")]
pub mod framebuffer_dump;

pub use hilbert::HilbertCurve;
pub use decoder::PixelDecoder;
#[cfg(feature = "std")]
pub use canvas::PixelCanvas;
#[cfg(feature = "std")]
pub use pdb::{PdbEncoder, PdbDecoder, VccIntegrity, SqliteToPdb};
#[cfg(feature = "std")]
pub use pdb::tiled::{TileCoord, TileGridConfig, TileMetadata, TiledPdbDecoder, TiledPdbEncoder, TiledPdbHeader, TiledPdbManager};
#[cfg(all(feature = "std", feature = "gpu"))]
pub use pdb::GpuQueryEngine;
