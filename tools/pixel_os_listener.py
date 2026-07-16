#!/usr/bin/env python3
"""
pixel_os_listener.py — Resident listener daemon for the visual audio OS.

Continuously watches for audio input and applies pixel ops to framebuffer.png.
This is the actual OS experience: a living surface that responds to spoken commands.

The daemon supports:
1. File-based queue: watches a directory for new .wav files
2. Live audio input: monitors audio device for in-band commands
3. Continuous operation: runs until SIGINT/SIGTERM
4. Robust error handling: logs errors but keeps running
5. Provenance tracking: optional signatures for security

Architecture:
- LLM (utter): creates dual-band WAV (narration + ops)
- Daemon (listen): decodes high band, applies ops to framebuffer
- Framebuffer: persistent state (framebuffer.png)

Usage:
  python3 pixel_os_listener.py --mode queue --watch-dir ./voicebook/queue
  python3 pixel_os_listener.py --mode live --device-id 0
"""

import argparse
import json
import os
import sys
import time
import signal
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Set
import threading
import queue

import numpy as np
import soundfile as sf
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pixel_screen import load_fb, apply_ops, hex_color
from spoken_screen import decode_data_band
from boot_manifest import launch_boot, BootManifestError
from wordbase_compat import connect, word_id, materialize, tokenize
from word_compiler import ensure_cmudict, parse_cmudict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('pixel_os_listener.log')
    ]
)
logger = logging.getLogger(__name__)


class ListenerDaemon:
    """Resident listener daemon for the visual audio OS."""

    def __init__(
        self,
        framebuffer_path: str = 'framebuffer.png',
        provenance_required: bool = False,
        public_key_path: str = None,
        enable_boot: bool = False,
        boot_image_dir: str = None,
        boot_dry_run: bool = False
    ):
        """
        Initialize the listener daemon.

        Args:
            framebuffer_path: Path to the framebuffer image
            provenance_required: Whether to require signed utterances
            public_key_path: Path to Ed25519 public key for verification
            enable_boot: Allow ["boot", ...] ops to launch QEMU (opt-in)
            boot_image_dir: Trusted directory holding bootable images
            boot_dry_run: Validate/log boot ops without launching QEMU
        """
        self.framebuffer_path = framebuffer_path
        self.provenance_required = provenance_required
        self.public_key_path = public_key_path
        self.enable_boot = enable_boot
        self.boot_image_dir = boot_image_dir
        self.boot_dry_run = boot_dry_run
        self.running = False
        self.op_queue = queue.Queue()
        self.processed_files: set = set()
        self.wordbase_initialized = False
        self.worker_thread = None
        self.resources_lock = threading.Lock()
        self.db = None
        self.cmudict = None

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()

    def _initialize_resources(self):
        """Initialize database and resources."""
        if self.db is None:
            self.db = connect()
            self.cmudict = parse_cmudict(ensure_cmudict())
            logger.info("Initialized wordbase and CMUdict")

    def _process_audio_file(self, wav_path: str) -> Optional[list]:
        """
        Process a single WAV file and extract ops.

        Args:
            wav_path: Path to WAV file

        Returns:
            List of ops, or None on failure
        """
        try:
            audio, sr = sf.read(wav_path)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)

            # Decode high-band data with optional authentication
            public_key = self.public_key_path if self.provenance_required else None
            data_bytes = decode_data_band(audio, sr, public_key)
            ops = json.loads(data_bytes.decode('utf-8'))

            logger.info(f"Decoded {len(ops)} ops from {wav_path}")
            return ops

        except Exception as e:
            logger.error(f"Failed to process {wav_path}: {e}")
            return None

    def _verify_signature(self, wav_path: str, ops: list) -> bool:
        """Verify utterance signature against trusted public key (DEPRECATED)."""
        logger.warning("_verify_signature() is deprecated - in-band signatures are now verified in decode_data_band()")
        return True

    def _dispatch_ops(self, ops: list) -> bool:
        """
        Route decoded ops: ["boot", ...] ops launch QEMU (gated), everything
        else is drawn to the framebuffer.

        Boot ops are only honored when provenance is required — which, given the
        downgrade fix in decode_data_band(), guarantees every op that reached
        here came from a signature-verified frame — and when boot has been
        explicitly enabled by the operator. Otherwise they are refused, never
        silently dropped into the framebuffer path.
        """
        boot_ops = [op for op in ops if isinstance(op, (list, tuple)) and op and op[0] == 'boot']
        draw_ops = [op for op in ops if not (isinstance(op, (list, tuple)) and op and op[0] == 'boot')]

        ok = True
        for op in boot_ops:
            ok = self._handle_boot_op(op) and ok
        if draw_ops:
            ok = self._apply_ops_to_framebuffer(draw_ops) and ok
        return ok

    def _handle_boot_op(self, op) -> bool:
        """Validate and (unless dry-run) launch a signed boot manifest."""
        if not self.provenance_required:
            logger.error("Refusing boot op: provenance not required (unsigned frames could launch QEMU)")
            return False
        if not self.enable_boot:
            logger.error("Refusing boot op: boot not enabled (pass --enable-boot to opt in)")
            return False
        if not self.boot_image_dir:
            logger.error("Refusing boot op: no --boot-image-dir configured")
            return False
        try:
            argv = launch_boot(op, self.boot_image_dir, dry_run=self.boot_dry_run)
        except BootManifestError as e:
            logger.error(f"Rejected boot op {op!r}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to launch boot op {op!r}: {e}")
            return False

        verb = "Would launch" if self.boot_dry_run else "Launched"
        logger.info(f"{verb} QEMU from signed boot op: {' '.join(argv)}")
        return True

    def _apply_ops_to_framebuffer(self, ops: list) -> bool:
        """
        Apply ops to the framebuffer.

        Args:
            ops: List of pixel ops

        Returns:
            True if successful
        """
        try:
            self._initialize_resources()

            fb = load_fb(self.framebuffer_path)
            fb = apply_ops(fb, ops)
            Image.fromarray(fb, mode='RGB').save(self.framebuffer_path)

            logger.info(f"Applied {len(ops)} ops to {self.framebuffer_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to apply ops: {e}")
            return False

    def _worker_loop(self):
        """Background worker thread that processes ops from queue."""
        logger.info("Worker thread started")
        while self.running:
            try:
                # Get op with timeout to allow checking running flag
                item = self.op_queue.get(timeout=1.0)
                if item is None:  # Poison pill
                    break

                source, ops = item
                if ops:
                    self._dispatch_ops(ops)

                self.op_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker thread error: {e}")

        logger.info("Worker thread stopped")

    def start(self):
        """Start the daemon."""
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        logger.info("Listener daemon started")

    def stop(self):
        """Stop the daemon."""
        self.running = False
        if self.worker_thread:
            # Send poison pill to worker thread
            self.op_queue.put(None)
            self.worker_thread.join(timeout=5.0)
        logger.info("Listener daemon stopped")

    def run_queue_mode(self, watch_dir: str, poll_interval: float = 1.0):
        """
        Run in file queue mode.

        Args:
            watch_dir: Directory to watch for new WAV files
            poll_interval: Seconds between polls
        """
        logger.info(f"Starting queue mode: watching {watch_dir}")
        watch_path = Path(watch_dir)
        watch_path.mkdir(parents=True, exist_ok=True)

        # Scan existing files on startup
        for wav_file in watch_path.glob("*.wav"):
            self.processed_files.add(str(wav_file))

        try:
            while self.running:
                # Scan for new files
                for wav_file in watch_path.glob("*.wav"):
                    wav_path = str(wav_file)
                    if wav_path not in self.processed_files:
                        logger.info(f"Processing new file: {wav_file.name}")
                        ops = self._process_audio_file(wav_path)
                        if ops:
                            self.op_queue.put((wav_file.name, ops))
                        self.processed_files.add(wav_path)

                time.sleep(poll_interval)

        except Exception as e:
            logger.error(f"Queue mode error: {e}")
            raise

    def run_live_mode(self, device_id: int, buffer_duration: float = 2.0,
                      threshold: float = 0.1):
        """
        Run in live audio mode.

        Args:
            device_id: Audio device ID
            buffer_duration: Duration of audio buffer in seconds
            threshold: Audio threshold to trigger processing
        """
        logger.info(f"Starting live mode: device {device_id}")

        try:
            import sounddevice as sd
        except ImportError:
            logger.error("sounddevice not installed. Install with: pip install sounddevice")
            logger.info("Falling back to queue mode - use --mode queue instead")
            return

        def audio_callback(indata, frames, time_info, status):
            """Callback for live audio input."""
            if status:
                logger.warning(f"Audio callback status: {status}")

            # Check if audio exceeds threshold
            if np.abs(indata).max() > threshold:
                # Process audio chunk
                audio = indata[:, 0] if indata.ndim > 1 else indata
                ops = self._process_audio_chunk(audio)
                if ops:
                    self.op_queue.put(("live", ops))

        try:
            stream = sd.InputStream(
                device=device_id,
                channels=1,
                samplerate=44100,
                callback=audio_callback,
                blocksize=int(44100 * buffer_duration)
            )

            with stream:
                logger.info("Listening for live audio (press Ctrl+C to stop)")
                while self.running:
                    time.sleep(0.1)

        except Exception as e:
            logger.error(f"Live mode error: {e}")
            raise

    def _process_audio_chunk(self, audio: np.ndarray) -> Optional[list]:
        """
        Process a chunk of live audio and extract ops.

        Args:
            audio: Audio chunk

        Returns:
            List of ops, or None if no valid ops found
        """
        try:
            # Attempt to decode data band with optional authentication
            public_key = self.public_key_path if self.provenance_required else None
            data_bytes = decode_data_band(audio, 44100, public_key)
            ops = json.loads(data_bytes.decode('utf-8'))
            logger.debug(f"Decoded {len(ops)} ops from live audio")
            return ops

        except Exception:
            # Not a valid utterance - this is normal for live audio
            return None


def main():
    parser = argparse.ArgumentParser(
        description="Resident listener daemon for the visual audio OS"
    )
    parser.add_argument(
        '--mode',
        choices=['queue', 'live'],
        default='queue',
        help='Operation mode: queue (watch directory) or live (monitor audio device)'
    )
    parser.add_argument(
        '--watch-dir',
        default='./voicebook/queue',
        help='Directory to watch for WAV files (queue mode)'
    )
    parser.add_argument(
        '--device-id',
        type=int,
        default=0,
        help='Audio device ID (live mode)'
    )
    parser.add_argument(
        '--fb',
        default='framebuffer.png',
        help='Framebuffer image path'
    )
    parser.add_argument(
        '--poll-interval',
        type=float,
        default=1.0,
        help='Polling interval for queue mode (seconds)'
    )
    parser.add_argument(
        '--provenance',
        action='store_true',
        help='Require signed utterances'
    )
    parser.add_argument(
        '--public-key',
        help='Path to Ed25519 public key for verification (required with --provenance)'
    )
    parser.add_argument(
        '--enable-boot',
        action='store_true',
        help='Allow signed ["boot", arch, image] ops to launch QEMU (requires --provenance)'
    )
    parser.add_argument(
        '--boot-image-dir',
        help='Trusted directory of bootable images (required with --enable-boot)'
    )
    parser.add_argument(
        '--boot-dry-run',
        action='store_true',
        help='Validate and log boot ops without actually launching QEMU'
    )

    args = parser.parse_args()

    # Validate provenance requirements
    if args.provenance and not args.public_key:
        parser.error("--provenance requires --public-key to be specified")

    # Boot must be signed and pointed at a trusted image directory.
    if args.enable_boot and not args.provenance:
        parser.error("--enable-boot requires --provenance (only signed frames may launch QEMU)")
    if args.enable_boot and not args.boot_image_dir:
        parser.error("--enable-boot requires --boot-image-dir")

    # Create daemon
    daemon = ListenerDaemon(
        framebuffer_path=args.fb,
        provenance_required=args.provenance,
        public_key_path=args.public_key,
        enable_boot=args.enable_boot,
        boot_image_dir=args.boot_image_dir,
        boot_dry_run=args.boot_dry_run
    )

    # Start daemon
    daemon.start()

    try:
        # Run in selected mode
        if args.mode == 'queue':
            daemon.run_queue_mode(args.watch_dir, args.poll_interval)
        else:
            daemon.run_live_mode(args.device_id)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        daemon.stop()


if __name__ == '__main__':
    main()