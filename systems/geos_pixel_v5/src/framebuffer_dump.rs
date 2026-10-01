//! Ground-truth pixel snapshots for anything with a real framebuffer.
//!
//! Extracted from `examples/v5_interactive.rs`'s SIGUSR1 hook after that
//! technique caught what a log/UART-text blind spot could not (see
//! `tools/boot_xv6_gpu.py`'s periodic-UART-printer bug, which made a
//! *working* boot look silently stuck for an entire session). A captured
//! PNG is much harder to misread than a log line that just isn't printing.
//!
//! This only applies where a framebuffer actually exists - a headless
//! emulator (no display surface at all) has nothing to screenshot; its
//! equivalent ground-truth capture is a full internal-state dump instead
//! (see `tools/boot_xv6_gpu.py`'s `dump_full_cpu_state()`).
//!
//! Two trigger modes, usable independently or together:
//! - **Signal-triggered**: call [`install_sigusr1_hook`] once at startup,
//!   then call [`FrameDumper::maybe_dump`] each frame - it dumps only when
//!   SIGUSR1 was received since the last check.
//! - **Periodic**: construct with [`FrameDumper::with_interval`] to dump
//!   automatically every N frames or every duration, building up a
//!   directory of snapshots ("every step") instead of a single
//!   overwritten file.

use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

#[cfg(feature = "evdev")]
use std::sync::atomic::{AtomicBool, Ordering};

#[cfg(feature = "evdev")]
static DUMP_REQUESTED: AtomicBool = AtomicBool::new(false);

#[cfg(feature = "evdev")]
extern "C" fn request_dump(_sig: libc::c_int) {
    DUMP_REQUESTED.store(true, Ordering::SeqCst);
}

/// Registers a SIGUSR1 handler that arms the next [`FrameDumper::maybe_dump`]
/// call. Requires the `evdev` feature (for `libc`). Safe to call once per
/// process; calling it again just re-installs the same handler.
#[cfg(feature = "evdev")]
pub fn install_sigusr1_hook() {
    unsafe {
        libc::signal(libc::SIGUSR1, request_dump as libc::sighandler_t);
    }
}

/// Trigger policy for automatic (non-signal) dumps.
#[derive(Clone, Copy, Debug)]
pub enum Interval {
    /// Dump every Nth call to `maybe_dump` (N=1 dumps every frame).
    Frames(u64),
    /// Dump at most once per this duration.
    Time(Duration),
    /// Never dump automatically - only on SIGUSR1 or explicit `dump_now`.
    Never,
}

/// Writes numbered PNG snapshots to a directory, on either a SIGUSR1
/// signal or a periodic interval. Every dump is a fresh file
/// (`frame_00000001.png`, ...) rather than one overwritten path, so a full
/// session builds a real "every step" record instead of just the latest
/// state.
pub struct FrameDumper {
    dir: PathBuf,
    interval: Interval,
    frame_count: u64,
    seq: u64,
    last_dump_at: Instant,
}

impl FrameDumper {
    /// No automatic dumps - signal-triggered only. Call
    /// [`install_sigusr1_hook`] separately if you want SIGUSR1 to work.
    pub fn signal_only(dir: impl AsRef<Path>) -> std::io::Result<Self> {
        Self::with_interval(dir, Interval::Never)
    }

    pub fn with_interval(dir: impl AsRef<Path>, interval: Interval) -> std::io::Result<Self> {
        let dir = dir.as_ref().to_path_buf();
        std::fs::create_dir_all(&dir)?;
        Ok(Self {
            dir,
            interval,
            frame_count: 0,
            seq: 0,
            last_dump_at: Instant::now(),
        })
    }

    /// Call once per rendered frame. Dumps `rgba` (tightly packed, `width *
    /// height * 4` bytes) if a SIGUSR1 arrived since the last call, or if
    /// the configured interval elapsed. Returns the written path, if any.
    pub fn maybe_dump(
        &mut self,
        rgba: &[u8],
        width: u32,
        height: u32,
    ) -> std::io::Result<Option<PathBuf>> {
        self.frame_count += 1;

        #[cfg(feature = "evdev")]
        let signaled = DUMP_REQUESTED.swap(false, Ordering::SeqCst);
        #[cfg(not(feature = "evdev"))]
        let signaled = false;

        let periodic = match self.interval {
            Interval::Frames(n) if n > 0 => self.frame_count % n == 0,
            Interval::Time(d) => self.last_dump_at.elapsed() >= d,
            _ => false,
        };

        if signaled || periodic {
            let path = self.dump_now(rgba, width, height)?;
            Ok(Some(path))
        } else {
            Ok(None)
        }
    }

    /// Write a snapshot unconditionally, bypassing signal/interval checks.
    pub fn dump_now(
        &mut self,
        rgba: &[u8],
        width: u32,
        height: u32,
    ) -> std::io::Result<PathBuf> {
        self.seq += 1;
        self.last_dump_at = Instant::now();
        let path = self.dir.join(format!("frame_{:08}.png", self.seq));
        image::save_buffer(&path, rgba, width, height, image::ColorType::Rgba8)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
        Ok(path)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dumps_on_frame_interval_not_before() {
        let dir = std::env::temp_dir().join(format!("fbdump_test_{}", std::process::id()));
        let mut dumper = FrameDumper::with_interval(&dir, Interval::Frames(3)).unwrap();
        let px = vec![0u8; 4 * 2 * 2]; // 2x2 RGBA

        assert!(dumper.maybe_dump(&px, 2, 2).unwrap().is_none());
        assert!(dumper.maybe_dump(&px, 2, 2).unwrap().is_none());
        let path = dumper.maybe_dump(&px, 2, 2).unwrap();
        assert!(path.is_some(), "3rd frame should trigger a dump");
        assert!(path.unwrap().exists());

        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn never_interval_only_dumps_explicitly() {
        let dir = std::env::temp_dir().join(format!("fbdump_test_never_{}", std::process::id()));
        let mut dumper = FrameDumper::with_interval(&dir, Interval::Never).unwrap();
        let px = vec![0u8; 4 * 2 * 2];

        for _ in 0..10 {
            assert!(dumper.maybe_dump(&px, 2, 2).unwrap().is_none());
        }
        let path = dumper.dump_now(&px, 2, 2).unwrap();
        assert!(path.exists());

        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn each_dump_gets_a_distinct_path() {
        let dir = std::env::temp_dir().join(format!("fbdump_test_seq_{}", std::process::id()));
        let mut dumper = FrameDumper::with_interval(&dir, Interval::Never).unwrap();
        let px = vec![0u8; 4 * 2 * 2];

        let p1 = dumper.dump_now(&px, 2, 2).unwrap();
        let p2 = dumper.dump_now(&px, 2, 2).unwrap();
        assert_ne!(p1, p2, "every dump should be a fresh file, not overwritten");

        std::fs::remove_dir_all(&dir).ok();
    }
}
