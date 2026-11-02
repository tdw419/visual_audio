#!/usr/bin/env python3
"""
Semantic Color Explorer for Visual Audio System.
Provides an interactive GUI to explore the semantic color mapping of words.

TASK_I003: Semantic color exploration
"""

import sys
import os
import pygame
import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.wordbase_compat import connect

class WordInfo:
    def __init__(self, word: str, word_id: int, pronunciation: str, pos: str, definition: str, color_hex: str):
        self.word = word
        self.word_id = word_id
        self.pronunciation = pronunciation
        self.pos = pos
        self.definition = definition or "No definition available"
        self.color_hex = color_hex
        self.color_rgb = self._hex_to_rgb(color_hex)
        
    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        if not hex_color or hex_color == 'None':
            return (128, 128, 128)
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6:
            return (128, 128, 128)
        try:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        except ValueError:
            return (128, 128, 128)

class ColorExplorer:
    def __init__(self, png_path: str):
        self.png_path = Path(png_path)
        self.screen_width = 1200
        self.screen_height = 800
        
        # Word info store
        self.words_info: List[WordInfo] = []
        self.colors_map: Dict[str, List[WordInfo]] = {}
        self.active_color_filter: Optional[str] = None
        
        # UI state
        self.hovered_word: Optional[WordInfo] = None
        
        # Load words
        self._load_words()
        
    def _load_words_from_directory(self, directory: Path) -> List[int]:
        """Parse word IDs from PNG filenames in a directory."""
        word_ids = set()
        pattern = re.compile(r'^(\d+)(?:_\w+)?\.png$')
        
        if not directory.exists() or not directory.is_dir():
            raise ValueError(f"Not a directory: {directory}")
            
        for file in directory.glob('*.png'):
            match = pattern.match(file.name)
            if match:
                word_ids.add(int(match.group(1)))
        
        if not word_ids:
            raise ValueError(f"No valid tile files found in {directory}")
            
        return sorted(word_ids)
    
    def _load_words_from_file(self, file_path: Path) -> List[int]:
        """Load word IDs from JSON or text sidecar files."""
        if file_path.suffix == '.json':
            with open(file_path, 'r') as f:
                data = json.load(f)
                if 'words' in data:
                    words = data['words']
                elif 'word_ids' in data:
                    return data['word_ids']
                else:
                    raise ValueError(f"JSON file must contain 'words' or 'word_ids' key")
                # Query IDs from word names
                db = connect()
                placeholders = ','.join('?' * len(words))
                query = f"SELECT id FROM words WHERE word IN ({placeholders}) COLLATE NOCASE"
                cursor = db.execute(query, words)
                ids = [row[0] for row in cursor.fetchall()]
                db.close()
                if not ids:
                    raise ValueError(f"No matching words found in wordbase for {len(words)} words")
                return ids
        elif file_path.suffix == '.txt':
            with open(file_path, 'r') as f:
                words = f.read().split()
            db = connect()
            placeholders = ','.join('?' * len(words))
            query = f"SELECT id FROM words WHERE word IN ({placeholders}) COLLATE NOCASE"
            cursor = db.execute(query, words)
            ids = [row[0] for row in cursor.fetchall()]
            db.close()
            if not ids:
                raise ValueError(f"No matching words found in wordbase for {len(words)} words")
            return ids
        else:
            raise ValueError(f"Unsupported file type: {file_path.suffix}")
    
    def _load_words(self):
        word_ids = []
        try:
            if self.png_path.is_dir():
                # Load from tiles directory
                word_ids = self._load_words_from_directory(self.png_path)
            elif self.png_path.is_file():
                # Check for JSON or TXT sidecar
                json_path = self.png_path.with_suffix('.json')
                text_path = self.png_path.with_suffix('.txt')
                
                if json_path.exists():
                    word_ids = self._load_words_from_file(json_path)
                elif text_path.exists():
                    word_ids = self._load_words_from_file(text_path)
                else:
                    raise ValueError(f"No sidecar found for {self.png_path}. Expected {json_path.name} or {text_path.name}")
            else:
                raise ValueError(f"Path does not exist: {self.png_path}")
                
        except Exception as e:
            print(f"Error loading word IDs: {e}", file=sys.stderr)
            sys.exit(1)
        
        # Load word info from wordbase
        if not word_ids:
            raise ValueError("No word IDs to load")
            
        db = connect()
        placeholders = ','.join('?' * len(word_ids))
        query = f"SELECT id, word, pronunciation, pos, definition, color_hex FROM words WHERE id IN ({placeholders})"
        cursor = db.execute(query, word_ids)
        
        for row in cursor.fetchall():
            info = dict(zip(['id', 'word', 'pronunciation', 'pos', 'definition', 'color_hex'], row))
            color_hex = info['color_hex'] or '#808080'
            word_info = WordInfo(info['word'], info['id'], info['pronunciation'], info['pos'], info['definition'], color_hex)
            self.words_info.append(word_info)
            if color_hex not in self.colors_map:
                self.colors_map[color_hex] = []
            self.colors_map[color_hex].append(word_info)
        db.close()
        
        if not self.words_info:
            raise ValueError(f"No matching words found in wordbase for {len(word_ids)} word IDs")
        
    def analyze(self):
        print(f"Analysis of {self.png_path}:")
        print(f"Total words: {len(self.words_info)}")
        print("\nSemantic Color Groups:")
        # Sort colors by frequency
        sorted_colors = sorted(self.colors_map.items(), key=lambda x: len(x[1]), reverse=True)
        for color, words in sorted_colors:
            unique_words = sorted(list(set(w.word for w in words)))
            poses = sorted(list(set(w.pos for w in words)))
            pos_str = ', '.join(poses) if poses else 'unknown'
            print(f"  {color} ({pos_str}): {len(words)} words")
            print(f"    Examples: {', '.join(unique_words[:5])}{'...' if len(unique_words) > 5 else ''}")
            
    def explore(self):
        pygame.init()
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("Visual Audio - Semantic Color Explorer")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 32)
        self.small_font = pygame.font.Font(None, 24)
        
        running = True
        
        # Layout metrics
        legend_rect = pygame.Rect(20, 20, 250, self.screen_height - 40)
        content_rect = pygame.Rect(300, 20, self.screen_width - 320, self.screen_height - 40)
        
        # Color legend entries
        sorted_colors = sorted(self.colors_map.items(), key=lambda x: len(x[1]), reverse=True)
        color_buttons = []
        y = legend_rect.top + 40
        for color, words in sorted_colors:
            poses = sorted(list(set(w.pos for w in words)))
            pos_str = ', '.join(poses) if poses else 'unknown'
            label = f"{pos_str} ({len(words)})"
            rect = pygame.Rect(legend_rect.left + 10, y, legend_rect.width - 20, 30)
            color_buttons.append({'color': color, 'rect': rect, 'label': label, 'rgb': words[0].color_rgb})
            y += 40
        
        # Word tiles
        tile_size = 120
        tiles_per_row = (content_rect.width - 20) // (tile_size + 10)
        
        while running:
            dt = self.clock.tick(60)
            
            # Event handling
            mouse_pos = pygame.mouse.get_pos()
            self.hovered_word = None
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        # Check legend clicks
                        for btn in color_buttons:
                            if btn['rect'].collidepoint(event.pos):
                                if self.active_color_filter == btn['color']:
                                    self.active_color_filter = None  # Toggle off
                                else:
                                    self.active_color_filter = btn['color']
            
            # Check for hover over tiles
            filtered_words = self.words_info
            if self.active_color_filter:
                filtered_words = [w for w in self.words_info if w.color_hex == self.active_color_filter]
            
            for i, word_info in enumerate(filtered_words):
                col = i % tiles_per_row
                row = i // tiles_per_row
                tile_rect = pygame.Rect(
                    content_rect.left + 10 + col * (tile_size + 10),
                    content_rect.top + 10 + row * (tile_size + 10),
                    tile_size,
                    tile_size
                )
                if tile_rect.collidepoint(mouse_pos):
                    self.hovered_word = word_info
            
            # Drawing
            self.screen.fill((30, 30, 35))
            
            # Draw legend
            pygame.draw.rect(self.screen, (40, 40, 45), legend_rect)
            legend_title = self.font.render("Semantic Colors", True, (255, 255, 255))
            self.screen.blit(legend_title, (legend_rect.left + 10, legend_rect.top + 10))
            
            for btn in color_buttons:
                pygame.draw.rect(self.screen, (30, 30, 35), btn['rect'])
                pygame.draw.rect(self.screen, btn['rgb'], btn['rect'].inflate(-10, -10))
                
                # Highlight active filter
                if self.active_color_filter == btn['color']:
                    pygame.draw.rect(self.screen, (255, 255, 255), btn['rect'], 2)
                
                # Draw label
                label_surf = self.small_font.render(btn['label'], True, (255, 255, 255))
                label_rect = label_surf.get_rect(center=btn['rect'].center)
                self.screen.blit(label_surf, label_rect)
            
            # Draw content area
            pygame.draw.rect(self.screen, (35, 35, 40), content_rect)
            
            # Draw tiles
            for i, word_info in enumerate(filtered_words):
                col = i % tiles_per_row
                row = i // tiles_per_row
                tile_rect = pygame.Rect(
                    content_rect.left + 10 + col * (tile_size + 10),
                    content_rect.top + 10 + row * (tile_size + 10),
                    tile_size,
                    tile_size
                )
                
                # Tile background
                bg_color = word_info.color_rgb
                pygame.draw.rect(self.screen, bg_color, tile_rect)
                pygame.draw.rect(self.screen, (60, 60, 65), tile_rect, 2)
                
                # Word text (truncated if too long)
                display_word = word_info.word[:12]
                word_surf = self.font.render(display_word, True, (255, 255, 255))
                word_rect = word_surf.get_rect(center=(tile_rect.centerx, tile_rect.centery - 10))
                self.screen.blit(word_surf, word_rect)
                
                # POS label
                pos_surf = self.small_font.render(word_info.pos[:6], True, (200, 200, 200))
                pos_rect = pos_surf.get_rect(center=(tile_rect.centerx, tile_rect.centery + 15))
                self.screen.blit(pos_surf, pos_rect)
            
            # Tooltip for hovered word
            if self.hovered_word:
                tooltip_width = 300
                tooltip_height = 120
                tooltip_rect = pygame.Rect(
                    mouse_pos[0] + 15,
                    mouse_pos[1] + 15,
                    tooltip_width,
                    tooltip_height
                )
                
                # Keep tooltip on screen
                if tooltip_rect.right > self.screen_width:
                    tooltip_rect.right = mouse_pos[0] - 10
                    tooltip_rect.left = tooltip_rect.right - tooltip_width
                if tooltip_rect.bottom > self.screen_height:
                    tooltip_rect.bottom = mouse_pos[1] - 10
                    tooltip_rect.top = tooltip_rect.bottom - tooltip_height
                
                pygame.draw.rect(self.screen, (20, 20, 20), tooltip_rect)
                pygame.draw.rect(self.screen, self.hovered_word.color_rgb, tooltip_rect, 2)
                
                # Word and pronunciation
                word_surf = self.font.render(f"{self.hovered_word.word} (ID: {self.hovered_word.word_id})", True, (255, 255, 255))
                self.screen.blit(word_surf, (tooltip_rect.left + 10, tooltip_rect.top + 10))
                
                pron_surf = self.small_font.render(self.hovered_word.pronunciation, True, (180, 180, 180))
                self.screen.blit(pron_surf, (tooltip_rect.left + 10, tooltip_rect.top + 40))
                
                # POS
                pos_surf = self.small_font.render(f"POS: {self.hovered_word.pos}", True, (180, 180, 180))
                self.screen.blit(pos_surf, (tooltip_rect.left + 10, tooltip_rect.top + 65))
                
                # Definition (truncated)
                def_text = self.hovered_word.definition[:50]
                if len(self.hovered_word.definition) > 50:
                    def_text += "..."
                def_surf = self.small_font.render(def_text, True, (150, 150, 150))
                self.screen.blit(def_surf, (tooltip_rect.left + 10, tooltip_rect.top + 90))
            
            pygame.display.flip()
        
        pygame.quit()

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tools/color_explorer.py <command> <path>")
        print("Commands:")
        print("  explore <path>  - Interactive GUI exploration (directory or PNG with sidecar)")
        print("  analyze <path>  - Headless analysis (directory or PNG with sidecar)")
        sys.exit(1)
    
    command = sys.argv[1]
    path = sys.argv[2] if len(sys.argv) > 2 else "."
    
    explorer = ColorExplorer(path)
    
    if command == "explore":
        explorer.explore()
    elif command == "analyze":
        explorer.analyze()
    else:
        print(f"Unknown command: {command}")
        print("Use 'explore' or 'analyze'")
        sys.exit(1)

if __name__ == "__main__":
    main()