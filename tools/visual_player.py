#!/usr/bin/env python3
"""
visual_player.py — Audio playback with live visual word tile synchronization

Features:
- Playback audio with real-time word tile highlighting
- Tiles pulse on phoneme boundaries
- Scrub through audio by dragging across tile grid
- Sync timing extracted from phoneme sequence metadata

Usage:
    python3 visual_player.py demo.wav --visual-sync
    python3 visual_player.py demo.wav --visual-sync --grid-width 10
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

# Optional audio imports - will be loaded lazily
try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    SOUNDFILE_AVAILABLE = False

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except (ImportError, OSError):
    SOUNDDEVICE_AVAILABLE = False
    SOUNDFILE_AVAILABLE = False  # sounddevice requires soundfile
    # Fallback for testing
    print("Warning: audio libraries not available - using fallback mode", file=sys.stderr)

from speak import SAMPLE_RATE


class WordTile:
    """Represents a visual word tile with timing and display info."""
    
    def __init__(self, word: str, start_time: float, end_time: float, phonemes: List[str]):
        self.word = word
        self.start_time = start_time
        self.end_time = end_time
        self.phonemes = phonemes
        self.duration = end_time - start_time
        
        # Phoneme-level timing (assuming equal distribution within word)
        phoneme_times = np.linspace(start_time, end_time, len(phonemes) + 1)
        self.phoneme_boundaries = list(zip(phoneme_times[:-1], phoneme_times[1:]))
        
        # Display state
        self.is_active = False
        self.phoneme_pulse_intensity = 0.0
        
        # Default color (could be enhanced with semantic colors later)
        self.color = (70, 130, 180)  # Steel blue default


class VisualPlayer:
    """Main player class handling audio-visual synchronization."""
    
    def __init__(self, audio_path: str, grid_width: int = 8):
        self.audio_path = audio_path
        self.grid_width = grid_width
        
        # Load audio
        if SOUNDDEVICE_AVAILABLE:
            self.audio, self.sample_rate = sf.read(audio_path)
        else:
            # Fallback: create dummy audio for testing
            self.audio = np.zeros(int(10 * SAMPLE_RATE))
            self.sample_rate = SAMPLE_RATE
        
        self.duration = len(self.audio) / self.sample_rate
        
        # State
        self.is_playing = False
        self.current_time = 0.0
        self.playback_start_time = 0.0
        self.stream = None
        
        # Tiles
        self.tiles: List[WordTile] = []
        
        # Interaction
        self.is_scrubbing = False
        self.scrub_start_time = 0.0
        
    def generate_tiles_from_text(self, text: str) -> List[WordTile]:
        """
        Generate word tiles with timing estimates from text.
        
        Approximate timing based on phoneme count (avg 100ms per phoneme).
        In production, this would use actual forced alignment.
        """
        import re
        
        # Tokenize into words
        words = re.findall(r"\b\w+\b", text)
        
        if not words:
            return []
        
        tiles = []
        current_time = 0.0
        
        for word in words:
            # Look up pronunciation from wordbase
            pronunciation = self._get_pronunciation(word)
            phonemes = pronunciation.split() if pronunciation else [word]
            
            # Estimate duration (100ms per phoneme + 50ms gap)
            estimated_duration = len(phonemes) * 0.1 + 0.05
            
            end_time = current_time + estimated_duration
            
            tile = WordTile(word, current_time, end_time, phonemes)
            tiles.append(tile)
            
            current_time = end_time
        
        # Scale to match actual audio duration
        total_estimated = current_time
        scale_factor = self.duration / total_estimated if total_estimated > 0 else 1.0
        
        for tile in tiles:
            tile.start_time *= scale_factor
            tile.end_time *= scale_factor
            tile.duration *= scale_factor
            
            # Rescale phoneme boundaries too
            tile.phoneme_boundaries = [
                (start * scale_factor, end * scale_factor)
                for start, end in tile.phoneme_boundaries
            ]
        
        return tiles
    
    def _get_pronunciation(self, word: str) -> Optional[str]:
        """Get pronunciation from wordbase database."""
        try:
            from wordbase import WordbaseManager
            wb = WordbaseManager()
            word_data = wb.get_word(word)
            if word_data:
                return word_data.get('pronunciation')
        except Exception as e:
            print(f"Warning: Could not look up pronunciation for '{word}': {e}")
        return None
    
    def get_active_tile(self, time: float) -> Optional[WordTile]:
        """Find the word tile active at the given time."""
        for tile in self.tiles:
            if tile.start_time <= time < tile.end_time:
                return tile
        return None
    
    def get_phoneme_pulse(self, time: float) -> float:
        """
        Calculate phoneme boundary pulse intensity at given time.
        Returns 0.0-1.0 intensity.
        """
        active_tile = self.get_active_tile(time)
        if not active_tile:
            return 0.0
        
        for start, end in active_tile.phoneme_boundaries:
            # Pulse in 50ms window around boundary
            if start <= time < end:
                # Check if near start (phoneme onset)
                if time - start < 0.05:
                    return 1.0 - (time - start) / 0.05
        
        return 0.0
    
    def scrub_from_tile_index(self, tile_index: int, position_in_tile: float = 0.5):
        """
        Scrub through audio by selecting a tile position.
        
        Args:
            tile_index: Index of the tile to scrub to
            position_in_tile: Position within the tile (0.0 = start, 1.0 = end)
        """
        if 0 <= tile_index < len(self.tiles):
            tile = self.tiles[tile_index]
            scrub_time = tile.start_time + (tile.duration * position_in_tile)
            self.seek(scrub_time)
            return scrub_time
        return self.current_time
    
    def scrub_from_position(self, x: float, y: float, grid_width: int, num_tiles: int):
        """
        Scrub through audio by dragging across tile grid.
        
        Args:
            x: Horizontal position in grid (0.0 to grid_width)
            y: Vertical position (row number)
            grid_width: Number of tiles per row
            num_tiles: Total number of tiles
            
        Returns:
            New playback position in seconds
        """
        # Calculate tile index from grid position
        tile_index = int(y * grid_width + x)
        
        # Estimate position within tile based on x offset
        position_in_tile = (x - int(x)) if x >= 0 else 0.0
        
        return self.scrub_from_tile_index(tile_index, position_in_tile)
    
    def play(self):
        """Start audio playback."""
        if self.stream is not None:
            return  # Already playing
        
        self.playback_start_time = time.time() - self.current_time
        self.is_playing = True
        
        if not SOUNDDEVICE_AVAILABLE:
            # Fallback mode: simulate playback
            return
        
        # Create stream starting from current position
        start_sample = int(self.current_time * self.sample_rate)
        audio_segment = self.audio[start_sample:]
        
        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1 if self.audio.ndim == 1 else self.audio.shape[1],
            callback=self._audio_callback
        )
        self.stream.start()
        
        # Feed audio data
        sd.play(audio_segment, self.sample_rate)
    
    def pause(self):
        """Pause playback."""
        if not self.is_playing:
            return
        
        self.is_playing = False
        
        if SOUNDDEVICE_AVAILABLE:
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None
            
            sd.stop()
    
    def stop(self):
        """Stop playback and reset to beginning."""
        self.pause()
        self.current_time = 0.0
        self.playback_start_time = 0.0
    
    def seek(self, position: float):
        """Seek to specific time position."""
        self.current_time = max(0.0, min(position, self.duration))
        self.playback_start_time = time.time() - self.current_time
        
        # Restart stream if playing
        if self.is_playing:
            self.pause()
            self.play()
    
    def _audio_callback(self, outdata, frames, time_info, status):
        """Audio stream callback."""
        if status:
            print(f"Audio callback status: {status}", file=sys.stderr)
        
        # Update current time (use module time, not parameter)
        import time as time_module
        self.current_time = time_module.time() - self.playback_start_time
        
        if self.current_time >= self.duration:
            self.pause()
            self.current_time = 0.0
    
    def update(self) -> Dict:
        """
        Update visual state and return current state for rendering.
        
        Returns:
            Dict with:
                - current_time: float
                - active_tile_index: int or None
                - active_tile_word: str or None
                - phoneme_pulse_intensity: float
                - tiles: List of tile states (word, is_active, color)
        """
        if self.is_playing:
            self.current_time = time.time() - self.playback_start_time
            if self.current_time >= self.duration:
                self.pause()
                self.current_time = 0.0
        
        active_tile = self.get_active_tile(self.current_time)
        active_tile_index = self.tiles.index(active_tile) if active_tile else None
        
        # Update tile states
        for tile in self.tiles:
            tile.is_active = (tile == active_tile)
        
        pulse_intensity = self.get_phoneme_pulse(self.current_time)
        
        return {
            'current_time': self.current_time,
            'active_tile_index': active_tile_index,
            'active_tile_word': active_tile.word if active_tile else None,
            'phoneme_pulse_intensity': pulse_intensity,
            'tiles': [
                {
                    'word': tile.word,
                    'is_active': tile.is_active,
                    'color': tile.color
                }
                for tile in self.tiles
            ]
        }


class SimpleTerminalRenderer:
    """Simple terminal-based tile grid renderer."""
    
    def __init__(self, grid_width: int = 8):
        self.grid_width = grid_width
        
    def render(self, state: Dict) -> str:
        """Render current state to terminal."""
        tiles = state['tiles']
        active_index = state['active_tile_index']
        pulse = state['phoneme_pulse_intensity']
        
        # Build grid
        rows = []
        current_row = []
        
        for i, tile in enumerate(tiles):
            # Determine display
            if tile['is_active']:
                # Active tile with pulse effect
                if pulse > 0.5:
                    display = f"█{tile['word'][:3].upper()}█"
                else:
                    display = f"▓{tile['word'][:3].upper()}▓"
            else:
                # Inactive tile
                display = f"░{tile['word'][:3].lower()}░"
            
            current_row.append(display)
            
            if len(current_row) >= self.grid_width:
                rows.append(' '.join(current_row))
                current_row = []
        
        if current_row:
            rows.append(' '.join(current_row))
        
        # Add status line
        status = f"\nTime: {state['current_time']:.2f}s | Active: {state['active_tile_word'] or 'None'} | Pulse: {pulse:.2f}"
        
        # Clear screen and render
        output = '\n' * 50  # Clear
        output += '=' * 80 + '\n'
        output += 'VISUAL AUDIO PLAYER - Live Sync\n'
        output += '=' * 80 + '\n\n'
        output += '\n'.join(rows)
        output += status
        
        return output


def main():
    parser = argparse.ArgumentParser(
        description="Audio playback with live visual word tile synchronization"
    )
    parser.add_argument('audio', help='Audio file to play')
    parser.add_argument('--visual-sync', action='store_true',
                       help='Enable visual word tile synchronization')
    parser.add_argument('--grid-width', type=int, default=8,
                       help='Number of tiles per row (default: 8)')
    parser.add_argument('--text', help='Text to generate tiles from (for sync)')
    
    args = parser.parse_args()
    
    # Check if audio file exists
    if not os.path.exists(args.audio):
        print(f"Error: Audio file not found: {args.audio}")
        sys.exit(1)
    
    # Initialize player
    player = VisualPlayer(args.audio, grid_width=args.grid_width)
    
    if args.visual_sync:
        # Generate tiles from text or derive from audio
        if args.text:
            text = args.text
        else:
            # Try to extract text from filename or use default
            text = "visual audio word tile synchronization demo"
        
        print(f"Generating {len(text.split())} word tiles...")
        player.tiles = player.generate_tiles_from_text(text)
        print(f"Created {len(player.tiles)} tiles with timing data")
    
    # Initialize renderer
    renderer = SimpleTerminalRenderer(grid_width=args.grid_width)
    
    # Play
    print(f"\nPlaying: {args.audio}")
    print(f"Duration: {player.duration:.2f}s")
    print("\nControls:")
    print("  Ctrl+C: Quit")
    print("  Press any key to pause/resume (not implemented in terminal mode)")
    print("\nStarting playback...\n")
    
    player.play()
    
    try:
        last_render = ''
        while player.is_playing:
            # Update state
            state = player.update()
            
            # Render (only if changed)
            current_render = renderer.render(state)
            if current_render != last_render:
                os.system('clear')
                print(current_render)
                last_render = current_render
            
            # Sleep a bit
            time.sleep(0.03)  # ~30 FPS
            
    except KeyboardInterrupt:
        print("\n\nPlayback stopped by user")
    finally:
        player.stop()
        print("Playback stopped")


if __name__ == '__main__':
    main()