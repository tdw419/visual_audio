#!/usr/bin/env python3
"""
Visual Audio UPIC Player - Play .upic.json files using existing audio tools

This script bridges Visual Audio UPIC projects with standard audio players by
converting them to temporary WAV files that can be played directly.
"""

import sys
import os
import tempfile
import subprocess
import argparse
import json
from pathlib import Path
from typing import Optional


def find_visual_audio_root():
    """Find the Visual Audio project root directory."""
    current = Path(__file__).resolve()
    
    # Look for markers of the project root
    while current.parent != current:
        if (current / "src" / "upic_engine.py").exists():
            return current
        if (current / "upic_engine.py").exists():
            return current
        current = current.parent
    
    # Fallback: use directory containing this script
    return Path(__file__).parent.parent


def import_upic_engine():
    """Import the UPIC engine from the project."""
    root = find_visual_audio_root()
    src_path = root / "src"
    
    if src_path.exists():
        sys.path.insert(0, str(src_path))
    else:
        sys.path.insert(0, str(root))
    
    try:
        from upic_engine import UPICProject
        return UPICProject
    except ImportError as e:
        print(f"Error importing UPIC engine: {e}")
        sys.exit(1)


def synthesize_to_wav(project_path: str, output_wav: str, duration: float = 10.0,
                      sample_rate: int = 44100) -> bool:
    """Synthesize UPIC project to WAV file."""
    UPICProject = import_upic_engine()
    
    try:
        # Load project
        project = UPICProject.load_from_file(project_path)
        
        # Synthesize audio
        print(f"Synthesizing {project_path} to {output_wav}...")
        print(f"  Duration: {duration}s, Sample Rate: {sample_rate}Hz")
        print(f"  Voices: {len(project.voices)}, Wavetables: {len(project.wavetables)}")
        
        audio = project.synthesize(duration=duration, sample_rate=sample_rate)
        
        # Export to WAV
        project.export_audio(audio, output_wav)
        
        print(f"✓ Synthesized to {output_wav}")
        return True
        
    except Exception as e:
        print(f"✗ Synthesis failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def play_with_player(wav_file: str, player: Optional[str] = None):
    """Play WAV file with specified or auto-detected player."""
    # Detect available players if not specified
    if player is None:
        player = detect_player()
        if player is None:
            print("✗ No suitable audio player found")
            print("  Please specify one with --player option")
            return False
    
    print(f"Playing with {player}...")
    
    try:
        if player == "ffplay":
            subprocess.run(["ffplay", "-nodisp", "-autoexit", wav_file], check=True)
        elif player == "vlc":
            subprocess.run(["vlc", "--intf", "dummy", "--play-and-exit", wav_file], check=True)
        elif player == "mplayer":
            subprocess.run(["mplayer", "-really-quiet", wav_file], check=True)
        elif player == "mpv":
            subprocess.run(["mpv", "--no-video", "--really-quiet", wav_file], check=True)
        elif player == "aplay":
            subprocess.run(["aplay", wav_file], check=True)
        elif player == "paplay":
            subprocess.run(["paplay", wav_file], check=True)
        elif player == "gst-play-1.0":
            subprocess.run(["gst-play-1.0", wav_file], check=True)
        else:
            # Try generic command
            subprocess.run([player, wav_file], check=True)
        
        return True
    except FileNotFoundError:
        print(f"✗ Player not found: {player}")
        return False
    except subprocess.CalledProcessError as e:
        print(f"✗ Player failed: {e}")
        return False


def detect_player() -> Optional[str]:
    """Auto-detect available audio player."""
    players = [
        ("ffplay", "FFmpeg-based player"),
        ("vlc", "VLC Media Player"),
        ("mpv", "MPV Media Player"),
        ("mplayer", "MPlayer"),
        ("gst-play-1.0", "GStreamer Play"),
        ("paplay", "PulseAudio"),
        ("aplay", "ALSA"),
    ]
    
    for player, description in players:
        try:
            subprocess.run(["which", player], check=True, capture_output=True)
            return player
        except subprocess.CalledProcessError:
            continue
    
    return None


def list_available_players():
    """List detected audio players."""
    print("Detected audio players:")
    players = [
        ("ffplay", "FFmpeg-based player"),
        ("vlc", "VLC Media Player"),
        ("mpv", "MPV Media Player"),
        ("mplayer", "MPlayer"),
        ("gst-play-1.0", "GStreamer Play"),
        ("paplay", "PulseAudio (no seeking)"),
        ("aplay", "ALSA (no seeking)"),
    ]
    
    found = False
    for player, description in players:
        try:
            subprocess.run(["which", player], check=True, capture_output=True)
            print(f"  ✓ {player}: {description}")
            found = True
        except subprocess.CalledProcessError:
            print(f"  ✗ {player}: {description}")
    
    if not found:
        print("  No audio players detected")
        print("\nInstall one of:")
        print("  sudo apt-get install vlc   # VLC Media Player")
        print("  sudo apt-get install mpv   # MPV Media Player")
        print("  sudo apt-get install ffmpeg # FFmpeg")


def stream_play(project_path: str, duration: float = 10.0, sample_rate: int = 44100,
                player: Optional[str] = None):
    """Stream synthesis directly to audio player (real-time)."""
    UPICProject = import_upic_engine()
    
    try:
        # Load project
        project = UPICProject.load_from_file(project_path)
        print(f"Streaming {project_path} in real-time...")
        print(f"  Duration: {duration}s, Sample Rate: {sample_rate}Hz")
        print(f"  Voices: {len(project.voices)}")
        
        # Detect player if not specified
        if player is None:
            player = detect_player()
        
        if player == "aplay":
            # Stream to ALSA aplay
            import numpy as np
            
            chunk_size = 4096
            total_samples = int(duration * sample_rate)
            
            # Open aplay process
            proc = subprocess.Popen(
                ["aplay", "-f", "S16_LE", "-c", "2", "-r", str(sample_rate)],
                stdin=subprocess.PIPE
            )
        
            try:
                for chunk_start in range(0, total_samples, chunk_size):
                    chunk_end = min(chunk_start + chunk_size, total_samples)
                    chunk_samples = chunk_end - chunk_start
                
                    # Synthesize chunk
                    chunk = project.synthesize(
                        duration=chunk_samples / sample_rate,
                        sample_rate=sample_rate,
                        offset=chunk_start / sample_rate
                    )
                
                    # Convert to int16
                    chunk_int16 = np.clip(chunk * 32767, -32768, 32767).astype(np.int16)
                    if proc.stdin:
                        proc.stdin.write(chunk_int16.tobytes())
                        proc.stdin.flush()
            
                if proc.stdin:
                    proc.stdin.close()
                proc.wait()
                print("✓ Playback completed")
                return True
                
            except KeyboardInterrupt:
                print("\nPlayback stopped by user")
                proc.terminate()
                return True
                
        else:
            print(f"✗ Real-time streaming not supported for player: {player}")
            print("  Use aplay for streaming, or convert to WAV first")
            return False
            
    except Exception as e:
        print(f"✗ Streaming failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Play Visual Audio UPIC project files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Play with auto-detected player
  %(prog)s project.upic.json
  
  # Play with specific player
  %(prog)s project.upic.json --player vlc
  
  # Play with custom duration
  %(prog)s project.upic.json --duration 30
  
  # Stream in real-time (requires aplay)
  %(prog)s project.upic.json --stream
  
  # Convert to WAV without playing
  %(prog)s project.upic.json --output output.wav
  
  # List available players
  %(prog)s --list-players
        """
    )
    
    parser.add_argument("project", nargs="?", help="UPIC project file (.upic.json)")
    parser.add_argument("--player", "-p", help="Audio player to use (vlc, mpv, ffplay, aplay, paplay, gst-play-1.0)")
    parser.add_argument("--duration", "-d", type=float, default=10.0, help="Duration in seconds (default: 10)")
    parser.add_argument("--sample-rate", "-r", type=int, default=44100, help="Sample rate in Hz (default: 44100)")
    parser.add_argument("--output", "-o", help="Output WAV file (don't play)")
    parser.add_argument("--stream", "-s", action="store_true", help="Stream in real-time (requires aplay)")
    parser.add_argument("--list-players", "-l", action="store_true", help="List available audio players")
    parser.add_argument("--keep-temp", "-k", action="store_true", help="Keep temporary WAV files")
    
    args = parser.parse_args()
    
    # List players
    if args.list_players:
        list_available_players()
        return
    
    # Require project file
    if not args.project:
        parser.print_help()
        sys.exit(1)
    
    # Validate project file
    if not os.path.exists(args.project):
        print(f"✗ Project file not found: {args.project}")
        sys.exit(1)
    
    if not args.project.endswith('.upic.json'):
        print(f"Warning: File doesn't end with .upic.json: {args.project}")
    
    # Output mode
    if args.output:
        success = synthesize_to_wav(args.project, args.output, args.duration, args.sample_rate)
        sys.exit(0 if success else 1)
    
    # Streaming mode
    if args.stream:
        success = stream_play(args.project, args.duration, args.sample_rate, args.player)
        sys.exit(0 if success else 1)
    
    # Normal play mode: synthesize to temp file, then play
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=not args.keep_temp) as tmp:
        if args.keep_temp:
            # Use a permanent temp file
            import uuid
            tmp_name = f"/tmp/upic_play_{uuid.uuid4().hex[:8]}.wav"
        else:
            tmp_name = tmp.name
        
        success = synthesize_to_wav(args.project, tmp_name, args.duration, args.sample_rate)
        if not success:
            sys.exit(1)
        
        if args.keep_temp:
            print(f"Temporary file: {tmp_name}")
        
        # Play the file
        success = play_with_player(tmp_name, args.player)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()