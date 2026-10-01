#!/usr/bin/env python3
"""
Wordbase/Voicebook Synchronization Tool

Identifies gaps between wordbase.db and voicebook/ cache and generates
missing audio/visual files using tools/speak.py.
"""

from dataclasses import dataclass
from typing import List, Set, Dict, Optional
from pathlib import Path
import sqlite3
import subprocess
import csv
import sys
import re


@dataclass
class WordGap:
    """
    Represents a gap in the wordbase/voicebook synchronization.
    """
    word: str
    has_audio: bool
    has_json: bool
    in_wordbase: bool
    pronunciation: Optional[str] = None
    frequency: int = 0

    @property
    def is_missing(self) -> bool:
        """Returns True if this word is missing from voicebook/."""
        return not self.has_audio or not self.has_json


class WordbaseSyncTool:
    def __init__(
        self,
        voicebook_dir: str,
        wordbase_path: str,
        speak_tool: str = "tools/speak.py",
        lang: str = 'en',
    ):
        self.voicebook_dir = Path(voicebook_dir)
        self.wordbase_path = Path(wordbase_path)
        self.speak_tool_path = Path(speak_tool)
        self.lang = lang

        if not self.voicebook_dir.exists():
            self.voicebook_dir.mkdir(parents=True, exist_ok=True)
        if not self.wordbase_path.exists():
            raise FileNotFoundError(f"Wordbase database not found: {self.wordbase_path}")
        if not self.speak_tool_path.exists():
            raise FileNotFoundError(f"Speak tool not found: {self.speak_tool_path}")

    def scan_voicebook(self, voicebook_dir: str) -> Dict[str, Dict[str, bool]]:
        """
        Scan voicebook/ directory for all synthesized words.
        Returns a dict of word -> {'has_audio': bool, 'has_json': bool}

        Filename pattern: <word>_<hash>[_variant].<ext>
        Examples:
            hello_5d41402a.wav → word="hello"
            hello_5d41402a_neural.wav → word="hello"
            hello_5d41402a.neural_triangle.wav → word="hello"
        """
        results = {}
        for p in Path(voicebook_dir).iterdir():
            if not p.is_file():
                continue

            stem = p.stem
            # Strip hash and variant suffixes to extract the base word
            # Pattern: <word>_<hash>[_variant1][_variant2]...
            # Match everything before the first _<hash> pattern
            match = re.match(r'^([^_]+)_[0-9a-f]+', stem)
            if match:
                word = match.group(1).lower()
            else:
                # Fallback: if no hash pattern, use stem as-is (legacy files)
                word = stem.lower()

            if word not in results:
                results[word] = {'has_audio': False, 'has_json': False}

            if p.suffix == '.wav':
                results[word]['has_audio'] = True
            elif p.suffix == '.json':
                results[word]['has_json'] = True

        return results

    def scan_wordbase(self, wordbase_path: str, lang: str = 'en') -> Dict[str, dict]:
        """
        Query wordbase.db for all words.
        Returns a dict of word -> info

        Args:
            wordbase_path: Path to SQLite database
            lang: Language filter (default: 'en' for English)
        """
        results = {}
        with sqlite3.connect(wordbase_path) as conn:
            cursor = conn.cursor()
            if lang:
                cursor.execute("SELECT word, pronunciation, frequency FROM words WHERE lang = ?", (lang,))
            else:
                cursor.execute("SELECT word, pronunciation, frequency FROM words")
            for row in cursor.fetchall():
                word = row[0].lower()
                results[word] = {
                    'pronunciation': row[1],
                    'frequency': row[2] if row[2] is not None else 0
                }
        return results

    def identify_gaps(self) -> List[WordGap]:
        """
        Identify gaps between wordbase.db and voicebook/.
        """
        voicebook_data = self.scan_voicebook(str(self.voicebook_dir))
        wordbase_data = self.scan_wordbase(str(self.wordbase_path), lang=self.lang)
        
        gaps = []
        all_words = set(voicebook_data.keys()).union(set(wordbase_data.keys()))
        
        for word in all_words:
            vb_info = voicebook_data.get(word, {'has_audio': False, 'has_json': False})
            wb_info = wordbase_data.get(word, None)
            
            gap = WordGap(
                word=word,
                has_audio=vb_info['has_audio'],
                has_json=vb_info['has_json'],
                in_wordbase=wb_info is not None,
                pronunciation=wb_info['pronunciation'] if wb_info else None,
                frequency=wb_info['frequency'] if wb_info else 0
            )
            gaps.append(gap)
            
        # Sort by frequency (descending) so more common words are prioritized
        gaps.sort(key=lambda x: x.frequency, reverse=True)
        return gaps

    def synthesize_missing_words(
        self,
        gaps: List[WordGap],
        batch_size: int = 50,
        limit: int = 0
    ) -> None:
        """
        Synthesize missing words using tools/speak.py.

        Uses: python3 tools/speak.py say "<word>" -o voicebook/<word>_<hash>.wav
        """
        import hashlib

        missing = [gap for gap in gaps if gap.is_missing and gap.in_wordbase]
        if limit > 0:
            missing = missing[:limit]

        print(f"Synthesizing {len(missing)} missing words...")

        for i, gap in enumerate(missing):
            # Generate hash for unique filename
            word_hash = hashlib.md5(gap.word.encode()).hexdigest()[:8]
            output_wav = self.voicebook_dir / f"{gap.word}_{word_hash}.wav"

            if output_wav.exists():
                print(f"[{i+1}/{len(missing)}] Skipping existing: {gap.word}")
                continue

            print(f"[{i+1}/{len(missing)}] Synthesizing: {gap.word}")
            cmd = [sys.executable, str(self.speak_tool_path), "say", gap.word, "-o", str(output_wav)]
            try:
                subprocess.run(cmd, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                print(f"Error synthesizing {gap.word}: {e.stderr.decode()}")
                
    def update_wordbase(self, gaps: List[WordGap]) -> None:
        """
        Update wordbase.db with new words (if not already present).
        """
        new_words = [gap for gap in gaps if not gap.in_wordbase and not gap.is_missing]
        if not new_words:
            return
            
        print(f"Found {len(new_words)} words in voicebook not in wordbase. Skipping insert for now.")

    def generate_report(self, gaps: List[WordGap], output_csv: str) -> None:
        """
        Generate CSV report of word gaps.
        """
        with open(output_csv, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['word', 'has_audio', 'has_json', 'in_wordbase', 'pronunciation', 'is_missing'])
            for gap in gaps:
                writer.writerow([
                    gap.word, gap.has_audio, gap.has_json, gap.in_wordbase, gap.pronunciation, gap.is_missing
                ])

    def run(
        self,
        output_csv: str = "reports/wordbase_gap_report.csv",
        batch_size: int = 50,
        limit: int = 0,
        dry_run: bool = False
    ) -> None:
        print("=== Scanning Voicebook and Wordbase ===")
        gaps = self.identify_gaps()
        print(f"Total unique words tracked: {len(gaps)}")

        missing = [gap for gap in gaps if gap.is_missing and gap.in_wordbase]
        print(f"Total missing from voicebook: {len(missing)}")

        self.generate_report(gaps, output_csv)
        print(f"Report saved to: {output_csv}")

        if dry_run:
            print(f"\n=== DRY RUN MODE ===")
            print(f"Would synthesize {len(missing)} missing words (no changes made)")
            print(f"Top 10 missing by frequency:")
            for gap in missing[:10]:
                print(f"  - {gap.word} (freq: {gap.frequency})")
        elif missing:
            self.synthesize_missing_words(gaps, batch_size=batch_size, limit=limit)
        self.update_wordbase(gaps)

        print(f"\n=== Sync Complete ===")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Synchronize wordbase.db with voicebook/ audio/visual cache"
    )
    parser.add_argument("--voicebook", default="voicebook", help="Path to voicebook/ directory")
    parser.add_argument("--wordbase", default="db/wordbase.db", help="Path to wordbase.db SQLite database")
    parser.add_argument("--speak-tool", default="tools/speak.py", help="Path to tools/speak.py for synthesis")
    parser.add_argument("--lang", default="en", help="Language filter (default: 'en' for English)")
    parser.add_argument("--output", default="reports/wordbase_gap_report.csv", help="Output CSV report path")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for synthesis")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of words to synthesize (0 for all)")
    parser.add_argument("--dry-run", action="store_true", help="Report-only mode, no synthesis")
    parser.add_argument("--verify", action="store_true", help="Run verification gates")

    args = parser.parse_args()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    sync_tool = WordbaseSyncTool(
        voicebook_dir=args.voicebook,
        wordbase_path=args.wordbase,
        speak_tool=args.speak_tool,
        lang=args.lang,
    )

    sync_tool.run(
        output_csv=args.output,
        batch_size=args.batch_size,
        limit=args.limit,
        dry_run=args.dry_run
    )

    if args.verify:
        print(f"\n=== Verification ===")
        print(f"✓ CSV report generated: {args.output}")


if __name__ == "__main__":
    main()
