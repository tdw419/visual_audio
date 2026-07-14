#!/usr/bin/env python3
"""
phoneme_redundancy_demo.py — Demonstration of phoneme sequence error recovery.

Shows how missing or corrupted phonemes can be recovered using:
1. Fuzzy matching against CMUdict
2. Context-aware suggestions
3. Position-based preferences
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from phoneme_redundancy import PhonemeRecovery, CMUdictFuzzyMatcher


def demo_fuzzy_matching():
    """Demonstrate fuzzy matching of phoneme sequences."""
    print("=" * 70)
    print("DEMO 1: Fuzzy Matching (Corrupted Phoneme Sequences)")
    print("=" * 70)
    
    matcher = CMUdictFuzzyMatcher()
    
    # Test cases: (description, corrupted_phonemes, max_errors)
    test_cases = [
        (
            "Perfect 'software' (S AO F T W EH R)",
            ['S', 'AO', 'F', 'T', 'W', 'EH', 'R'],
            0
        ),
        (
            "Corrupted 'software' (missing final 'R')",
            ['S', 'AO', 'F', 'T', 'W', 'EH'],
            1
        ),
        (
            "Corrupted 'software' (missing 'AO' and 'R')",
            ['S', 'F', 'T', 'W', 'EH'],
            2
        ),
        (
            "Corrupted 'hello' (HH EH L OW -> HH _ L OW)",
            ['HH', 'L', 'OW'],
            1
        ),
        (
            "Corrupted 'world' (W ER L D -> W _ L D)",
            ['W', 'L', 'D'],
            1
        ),
    ]
    
    for desc, phonemes, max_errors in test_cases:
        print(f"\n{desc}")
        print(f"  Input: {' '.join(phonemes)}")
        
        matches = matcher.find_matching_words(phonemes, max_errors=max_errors)
        
        if matches:
            print(f"  Top matches:")
            for word, word_phonemes, errors in matches[:3]:
                print(f"    {word}: {' '.join(word_phonemes)} (errors: {errors})")
        else:
            print(f"  No matches found")


def demo_wildcard_matching():
    """Demonstrate wildcard pattern matching."""
    print("\n" + "=" * 70)
    print("DEMO 2: Wildcard Pattern Matching")
    print("=" * 70)
    
    matcher = CMUdictFuzzyMatcher()
    
    test_cases = [
        ("S _ T", ['S', None, 'T']),
        ("H _ L _ O", ['HH', None, 'L', None, 'OW']),
        ("_ A T", [None, 'AE', 'T']),
    ]
    
    for desc, pattern in test_cases:
        print(f"\nPattern: {desc}")
        matches = matcher.find_wildcard_match(pattern)
        
        if matches:
            print(f"  Found {len(matches)} matches:")
            for word, phonemes in matches[:5]:
                print(f"    {word}: {' '.join(phonemes)}")
        else:
            print(f"  No matches found")


def demo_phoneme_recovery():
    """Demonstrate missing phoneme recovery."""
    print("\n" + "=" * 70)
    print("DEMO 3: Missing Phoneme Recovery")
    print("=" * 70)
    
    recovery = PhonemeRecovery()
    
    test_cases = [
        ("Missing middle phoneme: 's_ftware'", ['S', None, 'F', 'T', 'W', 'EH', 'R'], 1),
        ("Missing initial phoneme: '_top'", [None, 'T', 'AA', 'P'], 0),
        ("Missing final phoneme: 'he_'", ['HH', 'EH', None], 2),
        ("Missing in context: 'speak _oftware into'", 
         [['S', 'P', 'IY', 'K'], ['S', None, 'F', 'T', 'W', 'EH', 'R'], ['IH', 'N', 'T', 'UW']], 
         None),
    ]
    
    for desc, phonemes, missing_idx in test_cases:
        print(f"\n{desc}")
        
        if isinstance(phonemes[0], list):
            # Context-aware recovery
            words_phonemes = phonemes
            recovered = recovery.recover_with_context(words_phonemes, 1)
            print(f"  Original: {' '.join(p if p else '_' for p in words_phonemes[1])}")
            print(f"  Recovered: {' '.join(p if p else '_' for p in recovered)}")
        else:
            # Single word recovery
            print(f"  Original: {' '.join(p if p else '_' for p in phonemes)}")
            suggestions = recovery.recover_missing_phoneme(phonemes, missing_idx)
            
            if suggestions:
                print(f"  Top suggestions for missing phoneme:")
                for ph, score in suggestions[:5]:
                    print(f"    {ph}: {score:.3f}")


def demo_word_completion():
    """Demonstrate word completion from partial phonemes."""
    print("\n" + "=" * 70)
    print("DEMO 4: Word Completion Suggestions")
    print("=" * 70)
    
    recovery = PhonemeRecovery()
    
    test_cases = [
        ("'sof' (start of 'software')", ['S', 'AO', 'F']),
        ("'hel' (start of 'hello')", ['HH', 'EH', 'L']),
        ("'wo' (start of 'world')", ['W', 'ER']),
    ]
    
    for desc, partial in test_cases:
        print(f"\n{desc}")
        print(f"  Partial: {' '.join(partial)}")
        
        completions = recovery.suggest_completions(partial)
        
        if completions:
            print(f"  Top completions:")
            for word, phonemes, score in completions[:5]:
                print(f"    {word}: {' '.join(phonemes)} (score: {score:.3f})")
        else:
            print(f"  No completions found")


def demo_context_aware_recovery():
    """Demonstrate context-aware sentence recovery."""
    print("\n" + "=" * 70)
    print("DEMO 5: Context-Aware Sentence Recovery")
    print("=" * 70)
    
    recovery = PhonemeRecovery()
    
    # Sentence: "speak software into existence"
    # With errors: "speak s_ftware into _xistence"
    sentence_words = [
        ['S', 'P', 'IY', 'K'],  # "speak" (correct)
        ['S', None, 'F', 'T', 'W', 'EH', 'R'],  # "s_ftware" (missing 'AO')
        ['IH', 'N', 'T', 'UW'],  # "into" (correct)
        [None, 'K', 'S', 'IH', 'S', 'T', 'AH', 'N', 'S'],  # "_xistence" (missing 'EH' or 'IH')
    ]
    
    print("Original sentence: 'speak software into existence'")
    print("Corrupted: 'speak s_ftware into _xistence'")
    print()
    
    print("Recovering each word...")
    for i, word_phonemes in enumerate(sentence_words):
        original_display = ' '.join(p if p else '_' for p in word_phonemes)
        recovered = recovery.recover_with_context(sentence_words, i)
        recovered_display = ' '.join(p if p else '_' for p in recovered)
        
        print(f"  Word {i}: {original_display}")
        print(f"    -> {recovered_display}")


def demo_realistic_error_scenarios():
    """Demonstrate realistic error scenarios."""
    print("\n" + "=" * 70)
    print("DEMO 6: Realistic Error Scenarios")
    print("=" * 70)
    
    matcher = CMUdictFuzzyMatcher()
    
    scenarios = [
        (
            "Dropped phoneme (middle)",
            "visual",
            ['V', 'IH', 'Z', 'UW', 'AH', 'L'],  # "visu_al" missing one
            1
        ),
        (
            "Swapped phonemes (adjacent)",
            "test",
            ['T', 'EH', 'S', 'T'],  # "tets" (EH/S swapped - 2 errors from correct "T EH S T")
            2
        ),
        (
            "Noise corruption (wrong vowel)",
            "hello",
            ['HH', 'AH', 'L', 'L', 'OW'],  # Wrong vowel (AH instead of EH)
            1
        ),
        (
            "Partial pattern (only beginning)",
            "software",
            ['S', 'T'],  # Just "st"
            3
        ),
    ]
    
    for desc, target_word, corrupted, max_errors in scenarios:
        print(f"\n{desc}")
        print(f"  Target word: '{target_word}'")
        print(f"  Corrupted: {' '.join(corrupted)}")
        
        matches = matcher.find_matching_words(corrupted, max_errors=max_errors)
        
        if matches:
            # Check if target is in matches
            found = any(word == target_word.lower() for word, _, _ in matches)
            
            print(f"  Top 5 matches:")
            for word, phonemes, errors in matches[:5]:
                marker = " <-- TARGET" if word == target_word.lower() else ""
                print(f"    {word}: {' '.join(phonemes)} (errors: {errors}){marker}")
            
            if found:
                print(f"  ✓ Target word recovered!")
            else:
                print(f"  ✗ Target word not in top matches")
        else:
            print(f"  No matches found")


def main():
    """Run all demonstrations."""
    print("\n")
    print("=" * 70)
    print("PHONEME SEQUENCE REDUNDANCY DEMONSTRATION")
    print("=" * 70)
    print("\nThis demo shows how missing or corrupted phonemes can be recovered")
    print("using fuzzy matching, context analysis, and dictionary lookup.")
    print()
    
    try:
        demo_fuzzy_matching()
        demo_wildcard_matching()
        demo_phoneme_recovery()
        demo_word_completion()
        demo_context_aware_recovery()
        demo_realistic_error_scenarios()
        
        print("\n" + "=" * 70)
        print("DEMONSTRATION COMPLETE")
        print("=" * 70)
        print("\nThe phoneme redundancy system enables recovery from:")
        print("  • Missing phonemes (using context and position preferences)")
        print("  • Corrupted phonemes (using fuzzy matching)")
        print("  • Partial patterns (using word completion)")
        print("  • Contextual errors (using surrounding words)")
        print("\nThis makes the phoneme codec more robust to transmission errors")
        print("and improves human intelligibility of garbled speech.")
        print()
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())