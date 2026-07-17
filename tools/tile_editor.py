#!/usr/bin/env python3
"""
Interactive Tile Editor for Visual Audio System.
Provides drag-and-drop reordering, click-to-edit, and realtime audio generation.

TASK_I002: Interactive tile manipulation
"""

import sys
import os
import pygame
import json
import shutil
import soundfile as sf
from pathlib import Path
import numpy as np
from typing import List, Dict, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.upic_engine import UPICProject
from tools.phonemes import *


class Tile:
    """Represents a single word tile in the editor."""
    
    def __init__(self, word: str, index: int, position: Tuple[int, int], size: Tuple[int, int]):
        self.word = word
        self.index = index
        self.rect = pygame.Rect(position[0], position[1], size[0], size[1])
        self.selected = False
        self.dragging = False
        self.color = (70, 130, 180)  # Steel blue
        self.hover_color = (100, 160, 210)  # Lighter blue on hover
        self.selected_color = (255, 140, 0)  # Orange when selected
        self.dragging_color = (180, 180, 100)  # Yellow-ish when dragging
    
    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        """Draw the tile on the given surface."""
        if self.dragging:
            color = self.dragging_color
        elif self.selected:
            color = self.selected_color
        else:
            color = self.color
        
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        pygame.draw.rect(surface, (255, 255, 255), self.rect, 2, border_radius=8)
        
        # Render word
        text_surface = font.render(self.word, True, (255, 255, 255))
        text_rect = text_surface.get_rect(center=self.rect.center)
        surface.blit(text_surface, text_rect)
    
    def is_hovered(self, mouse_pos: Tuple[int, int]) -> bool:
        """Check if mouse is hovering over this tile."""
        return self.rect.collidepoint(mouse_pos)


class TileEditor:
    """Interactive tile editor with drag-and-drop and editing capabilities."""
    
    def __init__(self, png_path: str):
        self.png_path = Path(png_path)
        self.screen_width = 1200
        self.screen_height = 800
        self.tile_width = 150
        self.tile_height = 80
        self.tile_padding = 20
        self.tiles_per_row = 6
        
        # Initialize pygame
        pygame.init()
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("Visual Audio - Interactive Tile Editor")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 32)
        self.small_font = pygame.font.Font(None, 24)
        
        # Editor state
        self.tiles: List[Tile] = []
        self.selected_tiles: List[Tile] = []
        self.dragging_tile: Optional[Tile] = None
        self.drag_offset: Tuple[int, int] = (0, 0)
        self.drag_start_index: Optional[int] = None
        self.editing_tile: Optional[Tile] = None
        self.edit_text: str = ""
        
        # Control buttons
        self.buttons = [
            {'label': 'Save & Generate Audio', 'action': 'save', 'rect': pygame.Rect(20, 20, 220, 40)},
            {'label': 'Delete Selected', 'action': 'delete', 'rect': pygame.Rect(260, 20, 160, 40)},
            {'label': 'Duplicate Selected', 'action': 'duplicate', 'rect': pygame.Rect(440, 20, 180, 40)},
            {'label': 'Reset', 'action': 'reset', 'rect': pygame.Rect(640, 20, 100, 40)},
        ]
        
        # Status message
        self.status_message = "Click and drag tiles to reorder. Click to edit words."
        self.status_timer = 0
        
        # Load initial PNG if exists
        if self.png_path.exists():
            self.load_tiles_from_png()
        else:
            # Create default tiles for testing
            default_words = ["The", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog"]
            self.create_tiles_from_words(default_words)
    
    def load_tiles_from_png(self):
        """Load and parse tiles from existing PNG file."""
        try:
            # Try to load from a JSON sidecar file
            json_path = self.png_path.with_suffix('.json')
            if json_path.exists():
                with open(json_path, 'r') as f:
                    data = json.load(f)
                    if 'words' in data:
                        self.create_tiles_from_words(data['words'])
                        self.set_status(f"Loaded {len(data['words'])} tiles from {json_path.name}")
                        return
            
            # If no JSON, create from a text file or default
            text_path = self.png_path.with_suffix('.txt')
            if text_path.exists():
                with open(text_path, 'r') as f:
                    words = f.read().split()
                    self.create_tiles_from_words(words)
                    self.set_status(f"Loaded {len(words)} tiles from {text_path.name}")
            else:
                # Create default tiles for testing
                default_words = ["The", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog"]
                self.create_tiles_from_words(default_words)
                self.set_status("Created default tiles for testing")
        except Exception as e:
            self.set_status(f"Error loading file: {str(e)}")
    
    def create_tiles_from_words(self, words: List[str]):
        """Create tile objects from a list of words."""
        self.tiles = []
        start_y = 100
        
        for i, word in enumerate(words):
            row = i // self.tiles_per_row
            col = i % self.tiles_per_row
            x = 50 + col * (self.tile_width + self.tile_padding)
            y = start_y + row * (self.tile_height + self.tile_padding)
            
            tile = Tile(word, i, (x, y), (self.tile_width, self.tile_height))
            self.tiles.append(tile)
    
    def save_tiles_and_generate_audio(self):
        """Save current tile arrangement and regenerate audio."""
        try:
            words = [tile.word for tile in self.tiles]
            
            # Save to JSON sidecar
            json_path = self.png_path.with_suffix('.json')
            data = {
                'words': words,
                'count': len(words)
            }
            with open(json_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Generate audio from the word sequence
            self.set_status("Generating audio from tile arrangement...")
            pygame.display.flip()
            
            # Import word_compiler for audio generation
            sys.path.insert(0, str(Path(__file__).parent))
            from word_compiler import compile_text, ensure_cmudict, parse_cmudict
            
            # Ensure CMUdict is available
            cmudict_path = ensure_cmudict()
            cmudict = parse_cmudict(cmudict_path)
            
            # Compile text to audio
            audio_path = self.png_path.with_suffix('.wav')
            word_audios = compile_text(" ".join(words), cmudict)
            
            if word_audios:
                # Concatenate all audio segments
                audio_segments = [audio for _, audio in word_audios]
                full_audio = np.concatenate(audio_segments)
                
                # Save to file
                sf.write(str(audio_path), full_audio, 44100)
                
                self.set_status(f"Saved {len(words)} tiles and generated audio!")
            else:
                self.set_status("Saved tiles but audio generation failed")
            
        except Exception as e:
            self.set_status(f"Error saving: {str(e)}")
    
    def set_status(self, message: str):
        """Set status message with timer."""
        self.status_message = message
        self.status_timer = 180  # Show for ~3 seconds at 60 FPS
    
    def handle_tile_click(self, mouse_pos: Tuple[int, int], ctrl_held: bool):
        """Handle click on tiles for selection and editing."""
        clicked_tile = None
        for tile in reversed(self.tiles):  # Check from top (last drawn)
            if tile.is_hovered(mouse_pos):
                clicked_tile = tile
                break
        
        if clicked_tile:
            if ctrl_held:
                # Toggle selection
                if clicked_tile in self.selected_tiles:
                    self.selected_tiles.remove(clicked_tile)
                    clicked_tile.selected = False
                else:
                    self.selected_tiles.append(clicked_tile)
                    clicked_tile.selected = True
            else:
                # Single click - deselect others, start editing
                for tile in self.selected_tiles:
                    tile.selected = False
                self.selected_tiles.clear()
                
                self.editing_tile = clicked_tile
                self.edit_text = clicked_tile.word
                self.set_status(f"Editing tile: {clicked_tile.word} (Type new word, press Enter to confirm, Esc to cancel)")
        else:
            # Clicked on empty space - deselect all
            for tile in self.selected_tiles:
                tile.selected = False
            self.selected_tiles.clear()
    
    def handle_tile_drag_start(self, mouse_pos: Tuple[int, int]):
        """Start dragging a tile."""
        for tile in reversed(self.tiles):
            if tile.is_hovered(mouse_pos):
                self.dragging_tile = tile
                tile.dragging = True
                self.drag_offset = (
                    mouse_pos[0] - tile.rect.x,
                    mouse_pos[1] - tile.rect.y
                )
                self.drag_start_index = self.tiles.index(tile)
                self.set_status("Dragging tile - release to reorder")
                break
    
    def handle_tile_drag_move(self, mouse_pos: Tuple[int, int]):
        """Move dragged tile with mouse."""
        if self.dragging_tile:
            self.dragging_tile.rect.x = mouse_pos[0] - self.drag_offset[0]
            self.dragging_tile.rect.y = mouse_pos[1] - self.drag_offset[1]
    
    def handle_tile_drag_end(self):
        """End dragging and reorder tiles if needed."""
        if not self.dragging_tile:
            return
        
        dragged_tile = self.dragging_tile
        dragged_tile.dragging = False
        
        # Find new position based on center of dragged tile
        dragged_center = dragged_tile.rect.center
        new_index = None
        
        for i, tile in enumerate(self.tiles):
            if tile == dragged_tile:
                continue
            
            # Simple row-major order reordering
            tile_center = tile.rect.center
            
            # If dragged tile is to the left and above, insert before
            if (dragged_center[0] < tile_center[0] and 
                abs(dragged_center[1] - tile_center[1]) < self.tile_height):
                new_index = i
                break
            
            # If dragged tile is in row above
            if dragged_center[1] < tile_center[1]:
                new_index = i
                break
        else:
            # If not found before any tile, place at end
            new_index = len(self.tiles)
        
        if new_index is not None and new_index != self.drag_start_index:
            # Reorder tiles
            tile_to_move = self.tiles.pop(self.drag_start_index)
            # Adjust index if we're moving forward
            if new_index > self.drag_start_index:
                new_index -= 1
            self.tiles.insert(new_index, tile_to_move)
            
            # Update tile indices
            for i, tile in enumerate(self.tiles):
                tile.index = i
            
            self.set_status(f"Reordered tile to position {new_index + 1}")
            # Reposition all tiles to grid
            self._reposition_tiles_to_grid()
        else:
            # Just reposition to grid
            self._reposition_tiles_to_grid()
        
        self.dragging_tile = None
        self.drag_start_index = None
    
    def _reposition_tiles_to_grid(self):
        """Snap all tiles to grid positions."""
        start_y = 100
        
        for i, tile in enumerate(self.tiles):
            row = i // self.tiles_per_row
            col = i % self.tiles_per_row
            x = 50 + col * (self.tile_width + self.tile_padding)
            y = start_y + row * (self.tile_height + self.tile_padding)
            tile.rect.x = x
            tile.rect.y = y
    
    def handle_text_edit(self, event: pygame.event.Event):
        """Handle text editing for clicked tile."""
        if event.key == pygame.K_RETURN:
            # Confirm edit
            if self.editing_tile and self.edit_text.strip():
                self.editing_tile.word = self.edit_text.strip()
                self.set_status(f"Updated tile to: {self.editing_tile.word}")
            self.editing_tile = None
            self.edit_text = ""
        elif event.key == pygame.K_ESCAPE:
            # Cancel edit
            self.editing_tile = None
            self.edit_text = ""
            self.set_status("Edit cancelled")
        elif event.key == pygame.K_BACKSPACE:
            # Delete character
            self.edit_text = self.edit_text[:-1]
        else:
            # Add character (if it's a printable character)
            if event.unicode and len(event.unicode) == 1 and event.unicode.isprintable():
                self.edit_text += event.unicode
    
    def handle_button_click(self, mouse_pos: Tuple[int, int]):
        """Handle clicks on control buttons."""
        for button in self.buttons:
            if button['rect'].collidepoint(mouse_pos):
                if button['action'] == 'save':
                    self.save_tiles_and_generate_audio()
                elif button['action'] == 'delete':
                    self.delete_selected_tiles()
                elif button['action'] == 'duplicate':
                    self.duplicate_selected_tiles()
                elif button['action'] == 'reset':
                    self.load_tiles_from_png()
                return
    
    def delete_selected_tiles(self):
        """Delete all selected tiles."""
        if not self.selected_tiles:
            self.set_status("No tiles selected")
            return
        
        count = len(self.selected_tiles)
        for tile in self.selected_tiles:
            if tile in self.tiles:
                self.tiles.remove(tile)
        
        self.selected_tiles.clear()
        
        # Update indices and reposition
        for i, tile in enumerate(self.tiles):
            tile.index = i
        self._reposition_tiles_to_grid()
        
        self.set_status(f"Deleted {count} tile(s)")
    
    def duplicate_selected_tiles(self):
        """Duplicate all selected tiles."""
        if not self.selected_tiles:
            self.set_status("No tiles selected")
            return
        
        new_tiles = []
        for tile in self.selected_tiles:
            # Create duplicate
            new_tile = Tile(tile.word, len(self.tiles), tile.rect.topleft, (self.tile_width, self.tile_height))
            new_tiles.append(new_tile)
            self.tiles.append(new_tile)
        
        # Reorder and reposition
        for i, tile in enumerate(self.tiles):
            tile.index = i
        self._reposition_tiles_to_grid()
        
        self.set_status(f"Duplicated {len(new_tiles)} tile(s)")
    
    def run(self):
        """Main editor loop."""
        running = True
        
        while running:
            # Handle events
            mouse_pos = pygame.mouse.get_pos()
            keys = pygame.key.get_pressed()
            ctrl_held = keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        # Check if clicking on a button
                        button_clicked = False
                        for button in self.buttons:
                            if button['rect'].collidepoint(mouse_pos):
                                self.handle_button_click(mouse_pos)
                                button_clicked = True
                                break
                        
                        if not button_clicked and not self.editing_tile:
                            # Check if clicking on a tile
                            self.handle_tile_click(mouse_pos, ctrl_held)
                            if not ctrl_held and not any(t.is_hovered(mouse_pos) for t in self.tiles):
                                self.handle_tile_drag_start(mouse_pos)
                
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1 and self.dragging_tile:
                        self.handle_tile_drag_end()
                
                elif event.type == pygame.MOUSEMOTION:
                    if self.dragging_tile:
                        self.handle_tile_drag_move(mouse_pos)
                
                elif event.type == pygame.KEYDOWN:
                    if self.editing_tile:
                        self.handle_text_edit(event)
                    elif event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_DELETE and self.selected_tiles:
                        self.delete_selected_tiles()
            
            # Update status timer
            if self.status_timer > 0:
                self.status_timer -= 1
                if self.status_timer == 0:
                    self.status_message = ""
            
            # Draw everything
            self.draw(mouse_pos)
            
            # Update display
            pygame.display.flip()
            self.clock.tick(60)
        
        pygame.quit()
        return 0
    
    def draw(self, mouse_pos: Tuple[int, int] = (0, 0)):
        """Draw the editor interface."""
        # Background
        self.screen.fill((30, 30, 35))
        
        # Draw title
        title = self.font.render("Visual Audio - Interactive Tile Editor", True, (200, 200, 200))
        self.screen.blit(title, (50, 70))
        
        # Draw buttons
        for button in self.buttons:
            color = (60, 120, 180)
            pygame.draw.rect(self.screen, color, button['rect'], border_radius=5)
            pygame.draw.rect(self.screen, (200, 200, 200), button['rect'], 2, border_radius=5)
            
            label = self.small_font.render(button['label'], True, (255, 255, 255))
            label_rect = label.get_rect(center=button['rect'].center)
            self.screen.blit(label, label_rect)
        
        # Draw tiles
        for tile in self.tiles:
            # Check hover state
            if tile.is_hovered(mouse_pos) and not tile.dragging:
                hover_color = tile.hover_color
            else:
                hover_color = tile.color
            
            # Draw tile background
            if tile.selected:
                bg_color = tile.selected_color
            elif tile.dragging:
                bg_color = tile.dragging_color
            else:
                bg_color = hover_color
            
            pygame.draw.rect(self.screen, bg_color, tile.rect, border_radius=8)
            pygame.draw.rect(self.screen, (255, 255, 255), tile.rect, 2, border_radius=8)
            
            # Draw word
            text_surface = self.font.render(tile.word, True, (255, 255, 255))
            text_rect = text_surface.get_rect(center=tile.rect.center)
            
            # Truncate if too long
            if text_rect.width > tile.rect.width - 20:
                ratio = (tile.rect.width - 20) / text_rect.width
                new_width = int(len(tile.word) * ratio)
                truncated_word = tile.word[:max(1, new_width - 3)] + "..."
                text_surface = self.font.render(truncated_word, True, (255, 255, 255))
                text_rect = text_surface.get_rect(center=tile.rect.center)
            
            self.screen.blit(text_surface, text_rect)
        
        # Draw editing overlay
        if self.editing_tile:
            # Highlight editing tile
            pygame.draw.rect(self.screen, (255, 200, 0), self.editing_tile.rect, 4, border_radius=8)
            
            # Show editing text
            edit_label = self.small_font.render(f"Editing: {self.edit_text}|", True, (255, 255, 100))
            edit_rect = edit_label.get_rect(center=(self.screen_width // 2, self.screen_height - 50))
            pygame.draw.rect(self.screen, (50, 50, 50), edit_rect.inflate(20, 10), border_radius=5)
            self.screen.blit(edit_label, edit_rect)
        
        # Draw status message
        if self.status_message:
            status_color = (100, 200, 100) if "Saved" in self.status_message or "generated" in self.status_message.lower() else (200, 200, 200)
            status_surface = self.small_font.render(self.status_message, True, status_color)
            status_rect = status_surface.get_rect(bottomleft=(50, self.screen_height - 20))
            self.screen.blit(status_surface, status_rect)
        
        # Draw help text
        help_lines = [
            "Controls:",
            "  Click tile: Edit word",
            "  Ctrl+Click: Select multiple",
            "  Drag: Reorder tiles",
            "  Del: Delete selected",
            "  Esc: Cancel edit/Exit"
        ]
        
        help_y = 750
        for line in help_lines:
            help_surface = self.small_font.render(line, True, (150, 150, 150))
            self.screen.blit(help_surface, (self.screen_width - 300, help_y))
            help_y += 25


def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: python3 tile_editor.py <command> <png_path>")
        print("Commands:")
        print("  edit        - Launch interactive editor")
        print("  list        - List tiles in PNG")
        print("  validate    - Validate PNG structure")
        sys.exit(1)
    
    command = sys.argv[1]
    png_path = sys.argv[2]
    
    if command == "edit":
        editor = TileEditor(png_path)
        sys.exit(editor.run())
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()