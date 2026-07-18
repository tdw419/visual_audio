#!/usr/bin/env python3
"""
Real test for color_explorer.py (TASK_I003)
Tests that analyze mode correctly reads actual tiles and fails on invalid input.
"""

import subprocess
import sys
import sqlite3
from pathlib import Path

WORDBASE_PATH = Path(__file__).parent.parent / "db" / "wordbase.db"
COLOR_EXPLORER = Path(__file__).parent.parent / "tools" / "color_explorer.py"

def test_analyze_fails_on_missing_file():
    """Test: analyze should fail on non-existent path."""
    result = subprocess.run(
        [sys.executable, COLOR_EXPLORER, "analyze", "/tmp/does_not_exist.png"],
        capture_output=True,
        text=True
    )
    assert result.returncode != 0, "analyze should fail on missing file"
    assert "Path does not exist" in result.stderr or "Path does not exist" in result.stdout, \
        f"Expected 'Path does not exist' error, got: {result.stderr}"
    print("✓ test_analyze_fails_on_missing_file: PASSED")

def test_analyze_fails_on_png_without_sidecar():
    """Test: analyze should fail on PNG without JSON/TXT sidecar."""
    # Create a PNG without sidecar
    test_png = Path("/tmp/test_no_sidecar.png")
    test_png.touch()
    
    try:
        result = subprocess.run(
            [sys.executable, COLOR_EXPLORER, "analyze", str(test_png)],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0, "analyze should fail on PNG without sidecar"
        assert "No sidecar found" in result.stderr or "No sidecar found" in result.stdout, \
            f"Expected 'No sidecar found' error, got: {result.stderr}"
        print("✓ test_analyze_fails_on_png_without_sidecar: PASSED")
    finally:
        test_png.unlink(missing_ok=True)

def test_analyze_works_with_tiles_directory():
    """Test: analyze should work with tiles directory (real data)."""
    tiles_dir = Path(__file__).parent.parent / "voicebook" / "tiles"
    
    if not tiles_dir.exists() or not any(tiles_dir.glob("*.png")):
        print("⚠ test_analyze_works_with_tiles_directory: SKIPPED (no tiles)")
        return
    
    result = subprocess.run(
        [sys.executable, COLOR_EXPLORER, "analyze", str(tiles_dir)],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0, f"analyze failed on tiles dir: {result.stderr}"
    assert "Total words:" in result.stdout, "Should report word count"
    assert "Semantic Color Groups:" in result.stdout, "Should report color groups"
    
    # Verify at least one color group is listed
    assert "#" in result.stdout, "Should list at least one hex color"
    
    print("✓ test_analyze_works_with_tiles_directory: PASSED")

def test_analyze_works_with_json_sidecar():
    """Test: analyze should work with JSON sidecar containing word IDs."""
    # Get some real word IDs from wordbase
    db = sqlite3.connect(WORDBASE_PATH)
    cursor = db.execute("""
        SELECT id, word, color_hex
        FROM words
        WHERE color_hex IS NOT NULL
        LIMIT 4
    """)
    words = [{"id": row[0], "word": row[1], "color": row[2]} for row in cursor.fetchall()]
    db.close()
    
    if len(words) < 4:
        print("⚠ test_analyze_works_with_json_sidecar: SKIPPED (not enough words)")
        return
    
    # Create test fixture
    import json
    test_png = Path("/tmp/test_color_explorer_png.png")
    test_png.touch()
    test_json = Path("/tmp/test_color_explorer_png.json")
    with open(test_json, 'w') as f:
        json.dump({"word_ids": [w["id"] for w in words]}, f)
    
    try:
        result = subprocess.run(
            [sys.executable, COLOR_EXPLORER, "analyze", str(test_png)],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0, f"analyze failed on JSON sidecar: {result.stderr}"
        assert f"Total words: {len(words)}" in result.stdout, \
            f"Should report {len(words)} words, got: {result.stdout}"
        
        # Verify all expected colors are present
        for w in words:
            assert w["color"] in result.stdout, \
                f"Color {w['color']} for word {w['word']} not found in output"
        
        print("✓ test_analyze_works_with_json_sidecar: PASSED")
    finally:
        test_png.unlink(missing_ok=True)
        test_json.unlink(missing_ok=True)

def main():
    print("Running color_explorer tests...")
    print()
    
    test_analyze_fails_on_missing_file()
    test_analyze_fails_on_png_without_sidecar()
    test_analyze_works_with_tiles_directory()
    test_analyze_works_with_json_sidecar()
    
    print()
    print("All tests passed!")

if __name__ == "__main__":
    main()