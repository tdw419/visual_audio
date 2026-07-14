"""
Tests for phoneme sequence redundancy (TASK_E003).

Tests the error recovery capabilities for phoneme sequences, including:
- Fuzzy matching against CMUdict
- Wildcard pattern matching
- Context-aware phoneme recovery
- Word completion suggestions
"""

import pytest
import sys
import os
from typing import List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from phoneme_redundancy import (
    PhonemeRecovery,
    CMUdictFuzzyMatcher,
    TRANSITION_PATTERNS,
    POSITION_PREFERENCES,
    recover_text_phonemes
)


@pytest.fixture
def recovery():
    """Fixture providing a PhonemeRecovery instance."""
    # Use a small cached CMUdict for testing
    return PhonemeRecovery()


@pytest.fixture
def matcher(recovery):
    """Fixture providing a CMUdictFuzzyMatcher instance."""
    return recovery.matcher


class TestCMUdictFuzzyMatcher:
    """Test CMUdict fuzzy matching capabilities."""
    
    def test_load_cmudict(self, matcher):
        """Test that CMUdict is loaded correctly."""
        assert matcher.cmudict is not None
        assert len(matcher.cmudict) > 100000  # CMUdict has 126k+ words
    
    def test_find_matching_words_exact(self, matcher):
        """Test exact phoneme matching."""
        # "software" phonemes: S AO F T W EH R
        phonemes = ['S', 'AO', 'F', 'T', 'W', 'EH', 'R']
        matches = matcher.find_matching_words(phonemes, max_errors=0)
        
        # Should find "software" as top match
        assert len(matches) > 0
        best_word, best_phonemes, errors = matches[0]
        assert errors == 0
    
    def test_find_matching_words_fuzzy(self, matcher):
        """Test fuzzy matching with allowed errors."""
        # Corrupted "software": S AO F T W (missing EH R)
        corrupted = ['S', 'AO', 'F', 'T', 'W']
        matches = matcher.find_matching_words(corrupted, max_errors=2)
        
        # Should find words similar to the partial pattern
        assert len(matches) > 0
    
    def test_wildcard_matching(self, matcher):
        """Test wildcard pattern matching."""
        # Pattern: S _ T (any phoneme in middle)
        pattern = ['S', None, 'T']
        matches = matcher.find_wildcard_match(pattern)
        
        # Should find words like "stop", "sit", "sat", etc.
        assert len(matches) > 0
    
    def test_find_words_with_sequence(self, matcher):
        """Test finding words containing a sequence."""
        # Find words containing "S T" sequence
        sequence = ['S', 'T']
        matches = matcher.find_words_with_sequence(sequence)
        
        # Should find words like "stop", "start", etc.
        assert len(matches) > 0
    
    def test_transition_probability(self, matcher):
        """Test phoneme transition probability lookup."""
        # Common transition: "S" -> "T"
        prob = matcher.get_transition_probability('S', 'T')
        assert prob > 0.5  # Should be a high-probability transition
        
        # Rare transition
        prob = matcher.get_transition_probability('X', 'Y')
        assert prob == 0.0  # Should be 0 if not in patterns
    
    def test_position_preference(self, matcher):
        """Test phoneme position preference scoring."""
        # Common initial phoneme
        score = matcher.get_position_preference('S', 'start')
        assert score > 0.5
        
        # Common ending phoneme
        score = matcher.get_position_preference('Z', 'end')
        assert score > 0.5
    
    def test_edit_distance(self, matcher):
        """Test edit distance calculation."""
        # Identical sequences
        seq1 = ['S', 'T', 'R']
        seq2 = ['S', 'T', 'R']
        dist = matcher._edit_distance(seq1, seq2)
        assert dist == 0
        
        # One substitution
        seq1 = ['S', 'T', 'R']
        seq2 = ['S', 'P', 'R']
        dist = matcher._edit_distance(seq1, seq2)
        assert dist == 1


class TestPhonemeRecovery:
    """Test phoneme sequence recovery capabilities."""
    
    def test_recover_missing_phoneme_middle(self, recovery):
        """Test recovering a missing middle phoneme."""
        # "s_ftware" (missing 'AO' in "software")
        phonemes = ['S', None, 'F', 'T', 'W', 'EH', 'R']
        suggestions = recovery.recover_missing_phoneme(phonemes, 1)
        
        # Should get suggestions
        assert len(suggestions) > 0
        phoneme, score = suggestions[0]
        assert phoneme is not None
        assert score >= 0.0
    
    def test_recover_missing_phoneme_start(self, recovery):
        """Test recovering a missing initial phoneme."""
        # "_top" (missing 'S')
        phonemes = [None, 'T', 'AA', 'P']
        suggestions = recovery.recover_missing_phoneme(phonemes, 0)
        
        # Should suggest 'S' as top candidate
        assert len(suggestions) > 0
        assert suggestions[0][0] == 'S'
    
    def test_recover_missing_phoneme_end(self, recovery):
        """Test recovering a missing final phoneme."""
        # "so_" (missing 'T')
        phonemes = ['S', 'AA', None]
        suggestions = recovery.recover_missing_phoneme(phonemes, 2)
        
        # Should get suggestions
        assert len(suggestions) > 0
    
    def test_recover_corrupted_sequence(self, recovery):
        """Test recovering corrupted phoneme sequence."""
        # Slightly corrupted "software"
        corrupted = ['S', 'AO', 'F', 'T', 'W', 'EH']  # Missing 'R'
        recovered = recovery.recover_corrupted_sequence(corrupted)
        
        # Should either recover or return original
        assert len(recovered) >= len(corrupted)
    
    def test_recover_with_context(self, recovery):
        """Test word recovery using context from surrounding words."""
        words_phonemes: List[List[Optional[str]]] = [
            ['S', 'P', 'IY', 'K'],  # "speak"
            ['S', None, 'F', 'T', 'W', 'EH', 'R'],  # "s_ftware" (missing 'AO')
            ['IH', 'N', 'T', 'UW'],  # "into"
        ]
        
        recovered = recovery.recover_with_context(words_phonemes, 1)
        
        # Should attempt to fill in missing phoneme
        assert None not in recovered
    
    def test_suggest_completions(self, recovery):
        """Test word completion suggestions."""
        # Start of "software"
        partial = ['S', 'AO', 'F']
        completions = recovery.suggest_completions(partial)
        
        # Should get suggestions
        assert len(completions) > 0
        word, phonemes, score = completions[0]
        assert word is not None
        assert len(phonemes) >= len(partial)
        assert score > 0.0


class TestRecoveryIntegration:
    """Integration tests for phoneme recovery."""
    
    def test_text_phoneme_recovery_known_word(self, recovery):
        """Test recovery when the original text is known."""
        text = "software"
        corrupted = ['S', 'AO', 'F', 'T', 'W', 'EH']  # Missing 'R'
        
        recovered = recover_text_phonemes(text, corrupted)
        
        # Should recover to full sequence
        assert len(recovered) > len(corrupted)
        # All phonemes should be non-None
        assert None not in recovered
    
    def test_recover_common_word_with_errors(self, recovery):
        """Test recovery of common words with errors."""
        test_cases = [
            # (text, corrupted_phonemes)
            ("hello", ['HH', None, 'L', 'OW']),
            ("world", ['W', None, 'R', 'L', 'D']),
            ("test", ['T', None, 'S', 'T']),
        ]
        
        for text, corrupted in test_cases:
            recovered = recover_text_phonemes(text, corrupted)
            # Should attempt recovery
            assert len(recovered) > 0
            # Should not have None values
            assert None not in recovered or all(p is not None for p in recovered)
    
    def test_context_aware_recovery_sentence(self, recovery):
        """Test recovery in a sentence context."""
        # "speak _oftware into" (missing 'AO' in "software")
        words = [
            ['S', 'P', 'IY', 'K'],  # "speak"
            ['S', None, 'F', 'T', 'W', 'EH', 'R'],  # "s_ftware"
            ['IH', 'N', 'T', 'UW'],  # "into"
        ]
        
        for i in range(len(words)):
            recovered = recovery.recover_with_context(words, i)
            # Should attempt recovery
            assert len(recovered) > 0


class TestTransitionPatterns:
    """Test transition pattern data."""
    
    def test_transition_patterns_exist(self):
        """Test that transition patterns are defined."""
        assert len(TRANSITION_PATTERNS) > 0
        
        # Check some known high-probability transitions
        assert ('S', 'T') in TRANSITION_PATTERNS
        assert TRANSITION_PATTERNS[('S', 'T')] > 0.5
    
    def test_transition_patterns_valid_range(self):
        """Test that all transition probabilities are valid."""
        for key, prob in TRANSITION_PATTERNS.items():
            assert 0.0 <= prob <= 1.0, f"Invalid probability for {key}: {prob}"


class TestPositionPreferences:
    """Test position preference data."""
    
    def test_position_preferences_exist(self):
        """Test that position preferences are defined."""
        assert 'start' in POSITION_PREFERENCES
        assert 'middle' in POSITION_PREFERENCES
        assert 'end' in POSITION_PREFERENCES
        
        for pos, prefs in POSITION_PREFERENCES.items():
            assert len(prefs) > 0
    
    def test_position_preferences_valid_range(self):
        """Test that all preference scores are valid."""
        for pos, prefs in POSITION_PREFERENCES.items():
            for phoneme, score in prefs.items():
                assert 0.0 <= score <= 1.0, f"Invalid score for {phoneme} at {pos}: {score}"


class TestRealisticScenarios:
    """Test realistic error scenarios."""
    
    def test_dropped_phoneme_middle(self, recovery):
        """Test dropped phoneme in middle of word."""
        # "visual" -> "vis_al" (dropped 'UW' or 'AH')
        corrupted = ['V', 'IH', 'Z', None, 'UW', 'AH', 'L']
        recovered = recovery.recover_corrupted_sequence(corrupted)
        
        # Should attempt recovery
        assert len(recovered) > 0
    
    def test_swapped_phonemes(self, recovery):
        """Test swapped adjacent phonemes."""
        # "test" -> "tets" (swapped EH and T)
        # This tests fuzzy matching with substitution
        corrupted = ['T', 'EH', 'S', 'T']
        matches = recovery.matcher.find_matching_words(corrupted, max_errors=1)
        
        # Should find "test" with 1 error (the swap)
        assert len(matches) > 0
    
    def test_noise_corruption(self, recovery):
        """Test sequence with noise (extra/missing phonemes)."""
        # "hello" with noise
        corrupted = ['HH', 'AH', 'L', 'L', 'OW']  # Wrong vowel
        matches = recovery.matcher.find_matching_words(corrupted, max_errors=1)
        
        # Should find "hello" with 1 error
        assert len(matches) > 0
    
    def test_very_corrupted_word(self, recovery):
        """Test recovery of heavily corrupted word."""
        # Only partial pattern remains
        corrupted = ['S', 'T']  # Start of "software"
        completions = recovery.suggest_completions(corrupted)
        
        # Should suggest completions
        assert len(completions) > 0


class TestPerformance:
    """Test performance characteristics."""
    
    def test_fuzzy_match_speed(self, recovery):
        """Test that fuzzy matching is reasonably fast."""
        import time
        
        phonemes = ['S', 'AO', 'F', 'T', 'W', 'EH', 'R']
        
        start = time.time()
        for _ in range(100):
            recovery.matcher.find_matching_words(phonemes, max_errors=1)
        elapsed = time.time() - start
        
        # Should complete 100 matches in under 5 seconds
        assert elapsed < 5.0, f"Too slow: {elapsed}s for 100 matches"
    
    def test_wildcard_match_speed(self, recovery):
        """Test that wildcard matching is reasonably fast."""
        import time
        
        pattern = ['S', None, 'T']
        
        start = time.time()
        for _ in range(100):
            recovery.matcher.find_wildcard_match(pattern)
        elapsed = time.time() - start
        
        # Should complete 100 matches in under 1 second
        assert elapsed < 1.0, f"Too slow: {elapsed}s for 100 matches"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])