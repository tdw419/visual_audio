"""
Phoneme Sequence Redundancy - Error recovery for phoneme sequences.

Provides multiple recovery strategies when phonemes are missing, corrupted,
or unclear in speech transmission:
1. CMUdict fuzzy matching - find words matching partial phoneme patterns
2. Context-based recovery - use surrounding phonemes to guess missing ones
3. Position-aware selection - prefer phonemes that fit English patterns
"""

import re
import hashlib
import os
from typing import Dict, List, Tuple, Optional, Set
from collections import Counter, defaultdict
import urllib.request

# CMUdict constants
CMUDICT_URL = "https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict"
CMUDICT_PATH = os.path.expanduser("~/.cmudict/cmudict.dict")

# English phoneme transition patterns (from CMUdict analysis)
# Keys are 2-phoneme sequences, values are probability scores 0-1
TRANSITION_PATTERNS = {
    # Vowel + consonant patterns
    ('IH', 'N'): 0.95,    # Common in "in"
    ('AH', 'N'): 0.94,    # Common in "an"
    ('IY', 'Z'): 0.93,    # Common in plural "ease"
    ('EH', 'N'): 0.92,    # Common in "end"
    ('AE', 'N'): 0.91,    # Common in "and"
    ('UW', 'N'): 0.90,    # Common in "on"
    
    # Consonant + vowel patterns
    ('P', 'IY'): 0.96,    # Common in "pee"
    ('T', 'IY'): 0.95,    # Common in "tea"
    ('K', 'AE'): 0.94,    # Common in "cat"
    ('B', 'AE'): 0.93,    # Common in "bad"
    ('D', 'AH'): 0.92,    # Common in "duh"
    ('S', 'T'): 0.91,     # Common in "st" clusters
    ('T', 'R'): 0.90,     # Common in "tr" clusters
    
    # Common clusters
    ('S', 'T'): 0.95,     # "stop"
    ('S', 'P'): 0.94,     # "spoon"
    ('S', 'K'): 0.93,     # "sky"
    ('T', 'R'): 0.92,     # "tree"
    ('P', 'R'): 0.91,     # "pray"
    ('K', 'L'): 0.90,     # "clock"
    ('G', 'R'): 0.89,     # "grow"
    ('F', 'L'): 0.88,     # "fly"
    ('TH', 'R'): 0.87,    # "three"
    
    # Common endings
    ('N', 'D'): 0.96,     # "end"
    ('T', 'S'): 0.95,     # plural "cats"
    ('NG', 'Z'): 0.94,    # "sings"
    ('L', 'D'): 0.93,     # "old"
    ('R', 'D'): 0.92,     # "bird"
    ('S', 'T'): 0.91,     # "last"
}

# Position-based phoneme preferences
# Common phonemes at word beginnings, middles, and endings
POSITION_PREFERENCES = {
    'start': {
        'IH': 0.8, 'AH': 0.8, 'EH': 0.7, 'P': 0.6, 'T': 0.6, 'K': 0.6,
        'S': 0.6, 'M': 0.5, 'N': 0.5, 'L': 0.5, 'R': 0.5
    },
    'middle': {
        'IH': 0.9, 'AH': 0.9, 'AE': 0.8, 'N': 0.7, 'T': 0.6, 'S': 0.6,
        'L': 0.5, 'R': 0.5, 'D': 0.5, 'K': 0.5
    },
    'end': {
        'Z': 0.8, 'S': 0.8, 'D': 0.7, 'N': 0.7, 'T': 0.6, 'L': 0.6,
        'R': 0.5, 'K': 0.5, 'IH': 0.5
    }
}


class CMUdictFuzzyMatcher:
    """
    Fuzzy matching against CMUdict for phoneme sequence recovery.
    
    Uses edit distance and wildcard matching to find words that match
    partial or corrupted phoneme patterns.
    """
    
    def __init__(self, cmudict_path: Optional[str] = None):
        """
        Initialize fuzzy matcher with CMUdict.
        
        Args:
            cmudict_path: Path to cmudict.dict file (downloads if None)
        """
        self.cmudict_path = cmudict_path or CMUDICT_PATH
        self.cmudict = self._load_cmudict()
        self._build_phoneme_index()
    
    def _load_cmudict(self) -> Dict[str, List[str]]:
        """Load and parse CMUdict file."""
        if os.path.exists(self.cmudict_path):
            cmudict_path = self.cmudict_path
        else:
            # Download if not present
            os.makedirs(os.path.dirname(self.cmudict_path), exist_ok=True)
            urllib.request.urlretrieve(CMUDICT_URL, self.cmudict_path)
            cmudict_path = self.cmudict_path
        
        words = {}
        with open(cmudict_path, 'r', encoding='latin-1') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(';;;'):
                    continue
                
                parts = line.split()
                if len(parts) < 2:
                    continue
                
                word = parts[0].lower().split('(')[0]
                phonemes = [''.join(c for c in ph if not c.isdigit()) for ph in parts[1:]]
                
                if word not in words:
                    words[word] = phonemes
        
        return words
    
    def _build_phoneme_index(self):
        """Build index for fast phoneme pattern lookup."""
        self.phoneme_to_words = defaultdict(list)
        self.first_phoneme_to_words = defaultdict(set)  # NEW: words starting with phoneme
        self.bigram_to_words = defaultdict(list)
        self.trigram_to_words = defaultdict(list)

        for word, phonemes in self.cmudict.items():
            # Index words by first phoneme (NEW - for fast prefix matching)
            if phonemes:
                self.first_phoneme_to_words[phonemes[0]].add(word)

            # Index single phonemes
            for i, ph in enumerate(phonemes):
                self.phoneme_to_words[ph].append((word, i))

            # Index bigrams
            for i in range(len(phonemes) - 1):
                bigram = (phonemes[i], phonemes[i + 1])
                self.bigram_to_words[bigram].append((word, i))

            # Index trigrams
            for i in range(len(phonemes) - 2):
                trigram = (phonemes[i], phonemes[i + 1], phonemes[i + 2])
                self.trigram_to_words[trigram].append((word, i))
    
    def find_matching_words(
        self, 
        phonemes: List[str], 
        max_errors: int = 1
    ) -> List[Tuple[str, List[str], int]]:
        """
        Find words that match phoneme pattern with allowed errors.

        Optimized version: Uses phoneme index and bigram filtering to narrow 
        candidates before computing expensive edit distance calculations.

        Args:
            phonemes: Partial or corrupted phoneme sequence
            max_errors: Maximum number of insertions/deletions/substitutions

        Returns:
            List of (word, phonemes, errors) tuples, sorted by errors
        """
        candidates = []

        # Use first phoneme to get candidate words (huge optimization!)
        # This avoids scanning all 133k words
        if phonemes:
            first_ph = phonemes[0]
            if first_ph in self.first_phoneme_to_words:
                # Only check words that start with the first phoneme
                candidate_words = self.first_phoneme_to_words[first_ph].copy()

                # Additional optimization: use bigram filter if we have 2+ phonemes
                if len(phonemes) >= 2:
                    bigram = (phonemes[0], phonemes[1])
                    if bigram in self.bigram_to_words:
                        # Keep only words containing this bigram at position 0
                        bigram_words = set(word for word, pos in self.bigram_to_words[bigram] if pos == 0)
                        candidate_words &= bigram_words
                    # If bigram not found, no candidates (fail fast)
                    else:
                        return []
            else:
                # No words start with this phoneme
                return []
        else:
            candidate_words = set(self.cmudict.keys())

        # Compute edit distance only for filtered candidates
        for word in candidate_words:
            word_phonemes = self.cmudict[word]
            errors = self._edit_distance(phonemes, word_phonemes)
            if errors <= max_errors:
                candidates.append((word, word_phonemes, errors))

        # Sort by errors (fewest first)
        candidates.sort(key=lambda x: x[2])
        return candidates[:10]  # Return top 10
    
    def find_wildcard_match(
        self, 
        pattern: List[Optional[str]]
    ) -> List[Tuple[str, List[str]]]:
        """
        Find words matching pattern with wildcards (None = any phoneme).
        
        Example: ['S', None, 'T'] matches 'S-T', 'S-AH-T', 'S-IH-T', etc.
        
        Args:
            pattern: Pattern list with None for wildcards
        
        Returns:
            List of (word, phonemes) tuples
        """
        candidates = []
        
        for word, word_phonemes in self.cmudict.items():
            if len(word_phonemes) != len(pattern):
                continue
            
            match = True
            for p_ph, w_ph in zip(pattern, word_phonemes):
                if p_ph is not None and p_ph != w_ph:
                    match = False
                    break
            
            if match:
                candidates.append((word, word_phonemes))
        
        return candidates[:20]  # Return top 20
    
    def find_words_with_sequence(
        self, 
        sequence: List[str]
    ) -> List[Tuple[str, List[str], int]]:
        """
        Find words containing the exact phoneme sequence.
        
        Args:
            sequence: Phoneme sequence to find
        
        Returns:
            List of (word, phonemes, position) tuples
        """
        candidates = []
        seq_len = len(sequence)
        
        # Use trigram index for efficiency
        if seq_len == 3 and sequence in self.trigram_to_words:
            candidates = [(word, self.cmudict[word], pos) 
                         for word, pos in self.trigram_to_words[sequence]]
        elif seq_len == 2 and tuple(sequence) in self.bigram_to_words:
            candidates = [(word, self.cmudict[word], pos) 
                         for word, pos in self.bigram_to_words[tuple(sequence)]]
        else:
            # Fall back to linear search
            for word, word_phonemes in self.cmudict.items():
                for i in range(len(word_phonemes) - seq_len + 1):
                    if word_phonemes[i:i+seq_len] == sequence:
                        candidates.append((word, word_phonemes, i))
                        break
        
        return candidates[:20]
    
    def get_transition_probability(self, prev: str, curr: str) -> float:
        """
        Get probability of transition between two phonemes.
        
        Args:
            prev: Previous phoneme
            curr: Current phoneme
        
        Returns:
            Probability score 0-1
        """
        return TRANSITION_PATTERNS.get((prev, curr), 0.0)
    
    def get_position_preference(self, phoneme: str, position: str) -> float:
        """
        Get preference score for a phoneme at a given word position.
        
        Args:
            phoneme: Phoneme to score
            position: 'start', 'middle', or 'end'
        
        Returns:
            Preference score 0-1
        """
        return POSITION_PREFERENCES.get(position, {}).get(phoneme, 0.0)
    
    @staticmethod
    def _edit_distance(seq1: List[str], seq2: List[str]) -> int:
        """
        Calculate minimum edit distance between two sequences.
        
        Uses Wagner-Fischer algorithm for insertions, deletions,
        and substitutions.
        """
        m, n = len(seq1), len(seq2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if seq1[i - 1] == seq2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(
                        dp[i - 1][j],      # Deletion
                        dp[i][j - 1],      # Insertion
                        dp[i - 1][j - 1]   # Substitution
                    )
        
        return dp[m][n]


class PhonemeRecovery:
    """
    Context-aware phoneme sequence recovery.
    
    Combines fuzzy matching, context analysis, and position preferences
    to recover missing or corrupted phonemes.
    """
    
    def __init__(self, cmudict_path: Optional[str] = None):
        """
        Initialize phoneme recovery system.
        
        Args:
            cmudict_path: Path to cmudict.dict file
        """
        self.matcher = CMUdictFuzzyMatcher(cmudict_path)
    
    def recover_missing_phoneme(
        self, 
        phonemes: List[Optional[str]], 
        missing_index: int
    ) -> List[Tuple[str, float]]:
        """
        Suggest replacements for a missing phoneme.
        
        Uses context from surrounding phonemes and position preferences.
        
        Args:
            phonemes: Phoneme sequence with None at missing index
            missing_index: Index of missing phoneme
        
        Returns:
            List of (phoneme, score) tuples, sorted by score
        """
        candidates = []
        n_phonemes = len(phonemes)
        
        # Get context phonemes
        prev_ph = phonemes[missing_index - 1] if missing_index > 0 else None
        next_ph = phonemes[missing_index + 1] if missing_index < n_phonemes - 1 else None
        
        # Determine position
        if missing_index == 0:
            position = 'start'
        elif missing_index == n_phonemes - 1:
            position = 'end'
        else:
            position = 'middle'
        
        # Score all possible phonemes
        for ph in self.matcher.phoneme_to_words.keys():
            score = 0.0
            
            # Transition probability from previous
            if prev_ph:
                score += self.matcher.get_transition_probability(prev_ph, ph) * 0.4
            
            # Transition probability to next
            if next_ph:
                score += self.matcher.get_transition_probability(ph, next_ph) * 0.4
            
            # Position preference
            score += self.matcher.get_position_preference(ph, position) * 0.2
            
            candidates.append((ph, score))
        
        # Sort by score
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:10]
    
    def recover_corrupted_sequence(
        self, 
        phonemes: List[str], 
        confidence_threshold: float = 0.3
    ) -> List[str]:
        """
        Attempt to recover a corrupted phoneme sequence.
        
        Uses fuzzy matching against CMUdict to find the closest word.
        
        Args:
            phonemes: Possibly corrupted phoneme sequence
            confidence_threshold: Minimum score to accept a match
        
        Returns:
            Recovered phoneme sequence
        """
        # Find matching words with fuzzy matching
        matches = self.matcher.find_matching_words(phonemes, max_errors=1)
        
        if not matches:
            return phonemes  # No match found
        
        # Return best match if within threshold
        best_word, best_phonemes, errors = matches[0]
        
        # Calculate confidence score (inverse of errors)
        confidence = 1.0 - (errors / len(phonemes))
        
        if confidence >= confidence_threshold:
            return best_phonemes
        
        return phonemes
    
    def recover_with_context(
        self, 
        words_phonemes: List[List[str]],
        word_index: int
    ) -> List[str]:
        """
        Recover a word using context from surrounding words.
        
        Args:
            words_phonemes: List of phoneme sequences (words)
            word_index: Index of word to recover
        
        Returns:
            Recovered phoneme sequence
        """
        if word_index < 0 or word_index >= len(words_phonemes):
            return words_phonemes[word_index]
        
        target_phonemes = words_phonemes[word_index]
        
        # Try fuzzy matching first
        recovered = self.recover_corrupted_sequence(target_phonemes)
        
        # If fuzzy match fails, use word-level context
        if recovered == target_phonemes:
            # Look for None/marked missing phonemes
            for i, ph in enumerate(target_phonemes):
                if ph is None or ph == '':
                    suggestions = self.recover_missing_phoneme(target_phonemes, i)
                    if suggestions:
                        recovered[i] = suggestions[0][0]  # Use best suggestion
        
        return recovered
    
    def suggest_completions(
        self, 
        partial_phonemes: List[str]
    ) -> List[Tuple[str, List[str], float]]:
        """
        Suggest word completions from partial phoneme sequence.
        
        Args:
            partial_phonemes: Partial phoneme sequence (start of word)
        
        Returns:
            List of (word, phonemes, score) tuples
        """
        completions = []
        
        for word, word_phonemes in self.matcher.cmudict.items():
            if len(word_phonemes) < len(partial_phonemes):
                continue
            
            # Check if word starts with partial sequence
            if word_phonemes[:len(partial_phonemes)] == partial_phonemes:
                # Score based on transition probabilities
                score = 1.0
                for i in range(len(partial_phonemes) - 1):
                    prev = partial_phonemes[i]
                    curr = partial_phonemes[i + 1]
                    score *= (0.5 + 0.5 * self.matcher.get_transition_probability(prev, curr))
                
                completions.append((word, word_phonemes, score))
        
        # Sort by score
        completions.sort(key=lambda x: x[2], reverse=True)
        return completions[:10]


def recover_text_phonemes(
    text: str,
    corrupted_phonemes: List[str]
) -> List[str]:
    """
    Recover phonemes for a word using the text as ground truth reference.
    
    This is a helper function for testing and development - it assumes
    the text spelling is known and correct.
    
    Args:
        text: The original text word
        corrupted_phonemes: The corrupted phoneme sequence
    
    Returns:
        Recovered phoneme sequence (or original if no improvement found)
    """
    recovery = PhonemeRecovery()
    
    # Try to recover from CMUdict using the text
    matcher = recovery.matcher
    text_lower = text.lower()
    
    if text_lower in matcher.cmudict:
        # We know the correct answer! Use it.
        return matcher.cmudict[text_lower]
    
    # Otherwise, use fuzzy matching
    recovered = recovery.recover_corrupted_sequence(corrupted_phonemes)
    return recovered


# CLI interface for testing
def main():
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='Phoneme sequence redundancy testing')
    sub = parser.add_subparsers(dest='cmd', required=True)
    
    # Test fuzzy matching
    p_match = sub.add_parser('match', help='fuzzy match phoneme sequences')
    p_match.add_argument('phonemes', nargs='+', help='phoneme sequence (e.g., S T AH P)')
    p_match.add_argument('--max-errors', type=int, default=1, help='max edit distance')
    
    # Test wildcard matching
    p_wild = sub.add_parser('wildcard', help='wildcard pattern matching')
    p_wild.add_argument('pattern', help='pattern with _ for wildcard (e.g., S_T)')
    
    # Test sequence search
    p_seq = sub.add_parser('contains', help='find words containing sequence')
    p_seq.add_argument('phonemes', nargs='+', help='phoneme sequence to find')
    
    # Test phoneme recovery
    p_recov = sub.add_parser('recover', help='recover missing phoneme')
    p_recov.add_argument('phonemes', nargs='+', help='sequence with _ for missing')
    
    args = parser.parse_args()
    
    recovery = PhonemeRecovery()
    
    if args.cmd == 'match':
        candidates = recovery.matcher.find_matching_words(
            args.phonemes, max_errors=args.max_errors
        )
        print(f"Found {len(candidates)} matches:")
        for word, phonemes, errors in candidates:
            print(f"  {word}: {' '.join(phonemes)} (errors: {errors})")
    
    elif args.cmd == 'wildcard':
        pattern = [None if p == '_' else p for p in args.pattern.upper()]
        matches = recovery.matcher.find_wildcard_match(pattern)
        print(f"Found {len(matches)} matches:")
        for word, phonemes in matches:
            print(f"  {word}: {' '.join(phonemes)}")
    
    elif args.cmd == 'contains':
        sequence = args.phonemes
        matches = recovery.matcher.find_words_with_sequence(sequence)
        print(f"Found {len(matches)} words containing {' '.join(sequence)}:")
        for word, phonemes, pos in matches:
            print(f"  {word} (position {pos}): {' '.join(phonemes)}")
    
    elif args.cmd == 'recover':
        phonemes = [None if p == '_' else p for p in args.phonemes.upper()]
        missing_idx = phonemes.index(None)
        suggestions = recovery.recover_missing_phoneme(phonemes, missing_idx)
        print(f"Phonemes: {' '.join(p if p else '_' for p in phonemes)}")
        print(f"Suggestions for missing phoneme at index {missing_idx}:")
        for ph, score in suggestions[:5]:
            print(f"  {ph}: {score:.3f}")


if __name__ == '__main__':
    main()