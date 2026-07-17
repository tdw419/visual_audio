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
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.wordbase_compat import connect

class WordInfo:
    def __init__(self, word: str, pronunciation: str, pos: str, definition: str, color_hex: str):
        self.word = word
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
        
    def _load_words(self):
        words = []
        try:
            json_path = self.png_path.with_suffix('.json')
            if json_path.exists():
                with open(json_path, 'r') as f:
                    data = json.load(f)
                    if 'words' in data:
                        words = data['words']
            else:
                text_path = self.png_path.with_suffix('.txt')
                if text_path.exists():
                    with open(text_path, 'r') as f:
                        words = f.read().split()
                else:
                    words = ["The", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog"]
        except Exception as e:
            print(f"Error loading words: {e}")
            words = []
            
        db = connect()
        for word in words:
            cursor = db.execute("SELECT word, pronunciation, pos, definition, color_hex FROM words WHERE word = ? COLLATE NOCASE", (word,))
            row = cursor.fetchone()
            if row:
                info = dict(zip(['word', 'pronunciation', 'pos', 'definition', 'color_hex'], row))
                color_hex = info['color_hex'] or '#808080'
                word_info = WordInfo(info['word'], info['pronunciation'], info['pos'], info['definition'], color_hex)
                self.words_info.append(word_info)
                if color_hex not in self.colors_map:
                    self.colors_map[color_hex] = []
                self.colors_map[color_hex].append(word_info)
        db.close()
        
    def analyze(self):
        print(f"Analysis of {self.png_path}:")
        print(f"Total words: {len(self.words_info)}")
        print("\nSemantic Color Groups:")
        # Sort colors by frequency
        sorted_colors = sorted(self.colors_map.items(), key=lambda x: len(x[1]), reverse=True)
        for color, words in sorted_colors:
            unique_words = sorted(list(set(w.word for w in words)))
            poses = list(set(w.pos for w in words))
            print(f"  {color} ({', '.join(poses)}): {len(words)} words")
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
            poses = list(set(w.pos for w in words))
            label = f"{', '.join(poses)} ({len(words)})"
            rect = pygame.Rect(legend_rect.left + 10, y, legend_rect.width - 20, 30)
            color_buttons.append({'color': color, 'rect': rect, 'label': label, 'rgb': words[0].color_rgb})
            y += 40
            
        # Word buttons
        word_buttons = []
        
        def update_word_buttons():
            nonlocal word_buttons
            word_buttons.clear()
            x, y = content_rect.left, content_rect.top + 40
            for w_info in self.words_info:
                if self.active_color_filter and w_info.color_hex != self.active_color_filter:
                    continue
                    
                text_surface = self.font.render(w_info.word, True, (255, 255, 255))
                w, h = text_surface.get_size()
                rect = pygame.Rect(x, y, w + 20, h + 10)
                
                if x + rect.width > content_rect.right:
                    x = content_rect.left
                    y += h + 20
                    rect.topleft = (x, y)
                    
                word_buttons.append({'info': w_info, 'rect': rect, 'surface': text_surface})
                x += rect.width + 10
                
        update_word_buttons()
        
        while running:
            mouse_pos = pygame.mouse.get_pos()
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        # Check color legend clicks
                        clicked_legend = False
                        for btn in color_buttons:
                            if btn['rect'].collidepoint(mouse_pos):
                                if self.active_color_filter == btn['color']:
                                    self.active_color_filter = None # Toggle off
                                else:
                                    self.active_color_filter = btn['color']
                                update_word_buttons()
                                clicked_legend = True
                                break
                        
                        if not clicked_legend:
                            # If click outside, clear filter
                            if not legend_rect.collidepoint(mouse_pos):
                                self.active_color_filter = None
                                update_word_buttons()
                                
            self.screen.fill((30, 30, 30))
            
            # Draw legend
            pygame.draw.rect(self.screen, (40, 40, 40), legend_rect, border_radius=8)
            title = self.font.render("Semantic Colors", True, (255, 255, 255))
            self.screen.blit(title, (legend_rect.left + 10, legend_rect.top + 10))
            
            for btn in color_buttons:
                # Highlight active
                if self.active_color_filter == btn['color']:
                    pygame.draw.rect(self.screen, (80, 80, 80), btn['rect'], border_radius=4)
                
                # Color box
                color_box = pygame.Rect(btn['rect'].left + 5, btn['rect'].top + 5, 20, 20)
                pygame.draw.rect(self.screen, btn['rgb'], color_box, border_radius=2)
                pygame.draw.rect(self.screen, (200, 200, 200), color_box, 1, border_radius=2)
                
                # Label
                label_surf = self.small_font.render(btn['label'], True, (200, 200, 200))
                self.screen.blit(label_surf, (color_box.right + 10, btn['rect'].top + 7))
                
            # Draw words
            pygame.draw.rect(self.screen, (40, 40, 40), content_rect, border_radius=8)
            filter_text = "All Words" if not self.active_color_filter else f"Filtered by: {self.active_color_filter}"
            header = self.font.render(filter_text, True, (255, 255, 255))
            self.screen.blit(header, (content_rect.left + 10, content_rect.top + 10))
            
            self.hovered_word = None
            for btn in word_buttons:
                is_hovered = btn['rect'].collidepoint(mouse_pos)
                if is_hovered:
                    self.hovered_word = btn['info']
                    bg_color = (min(255, btn['info'].color_rgb[0] + 40), min(255, btn['info'].color_rgb[1] + 40), min(255, btn['info'].color_rgb[2] + 40))
                else:
                    bg_color = btn['info'].color_rgb
                    
                pygame.draw.rect(self.screen, bg_color, btn['rect'], border_radius=4)
                pygame.draw.rect(self.screen, (255, 255, 255), btn['rect'], 1, border_radius=4)
                self.screen.blit(btn['surface'], (btn['rect'].left + 10, btn['rect'].top + 5))
                
            # Draw tooltip for hovered word
            if self.hovered_word:
                tt_lines = [
                    self.hovered_word.word,
                    f"Pronunciation: {self.hovered_word.pronunciation}",
                    f"POS: {self.hovered_word.pos}",
                    f"Def: {self.hovered_word.definition}"
                ]
                
                tt_surfaces = []
                tt_width = 0
                for i, line in enumerate(tt_lines):
                    font = self.font if i == 0 else self.small_font
                    surf = font.render(line, True, (255, 255, 255))
                    tt_surfaces.append(surf)
                    tt_width = max(tt_width, surf.get_width())
                    
                tt_height = sum(s.get_height() + 5 for s in tt_surfaces) + 10
                
                # Position tooltip near mouse but keep on screen
                tt_x = mouse_pos[0] + 15
                tt_y = mouse_pos[1] + 15
                if tt_x + tt_width + 20 > self.screen_width:
                    tt_x = self.screen_width - tt_width - 20
                if tt_y + tt_height + 20 > self.screen_height:
                    tt_y = self.screen_height - tt_height - 20
                    
                tt_rect = pygame.Rect(tt_x, tt_y, tt_width + 20, tt_height + 10)
                pygame.draw.rect(self.screen, (20, 20, 20), tt_rect, border_radius=5)
                pygame.draw.rect(self.screen, (150, 150, 150), tt_rect, 1, border_radius=5)
                
                curr_y = tt_rect.top + 10
                for surf in tt_surfaces:
                    self.screen.blit(surf, (tt_rect.left + 10, curr_y))
                    curr_y += surf.get_height() + 5
                    
            pygame.display.flip()
            self.clock.tick(60)
            
        pygame.quit()

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 color_explorer.py <command> <png_path>")
        print("Commands:")
        print("  analyze - List all semantic color groups without UI")
        print("  explore - Launch interactive semantic color explorer GUI")
        sys.exit(1)
        
    command = sys.argv[1]
    png_path = sys.argv[2]
    
    explorer = ColorExplorer(png_path)
    
    if command == "analyze":
        explorer.analyze()
    elif command == "explore":
        explorer.explore()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
