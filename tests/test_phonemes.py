"""
Tests for tools/phonemes.py - phoneme envelope generation.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

from tools.phonemes import (
    vowel_envelope,
    stop_envelope,
    fricative_envelope,
    nasal_envelope,
    semivowel_envelope,
    create_phoneme_envelopes,
    get_phoneme_envelope,
    ARPABET_IPA,
    SAMPLE_RATE,
    DURATION,
)


class TestEnvelopeGenerators:
    """Test envelope generator functions."""

    def test_vowel_envelope_basic(self):
        """Test basic vowel envelope generation."""
        envelope = vowel_envelope(f1=500, f2=1500)

        assert isinstance(envelope, list)
        assert len(envelope) == 7  # 7 control points

        # Check first and last points
        assert envelope[0] == (0.0, 500)
        assert envelope[-1] == (1.0, 500)

    def test_vowel_envelope_values(self):
        """Test that vowel envelope has expected formant structure."""
        envelope = vowel_envelope(f1=400, f2=2100)

        # All time values should be in [0, 1]
        times = [t for t, _ in envelope]
        assert all(0.0 <= t <= 1.0 for t in times)

        # All freq values should be reasonable
        freqs = [f for _, f in envelope]
        assert all(50 <= f <= 5000 for f in freqs)

    def test_stop_envelope_basic(self):
        """Test basic stop consonant envelope."""
        envelope = stop_envelope(burst_freq=800, closure=0.3)

        assert isinstance(envelope, list)
        assert len(envelope) == 6

        # Should start at zero (silence)
        assert envelope[0] == (0.0, 0.0)

    def test_stop_envelope_closure(self):
        """Test that stop envelope has closure period."""
        envelope = stop_envelope(burst_freq=1000, closure=0.4)

        # First non-zero point should be after closure
        # envelope[1] is at closure time
        assert envelope[1] == (0.4, 0.0)  # Still silent at closure

    def test_fricative_envelope_basic(self):
        """Test basic fricative envelope."""
        envelope = fricative_envelope((1000, 1500))

        assert isinstance(envelope, list)
        assert len(envelope) == 6

        # Should oscillate between low and high
        lo_freqs = [f for t, f in envelope if t in [0.0, 0.4, 0.8]]
        hi_freqs = [f for t, f in envelope if t in [0.2, 0.6, 1.0]]

        assert all(f == 1000 for f in lo_freqs)
        assert all(f == 1500 for f in hi_freqs)

    def test_fricative_envelope_custom_range(self):
        """Test fricative with custom frequency range."""
        envelope = fricative_envelope((500, 2500))

        # Check extremes
        assert envelope[0][1] == 500
        assert envelope[1][1] == 2500

    def test_nasal_envelope_basic(self):
        """Test basic nasal envelope."""
        envelope = nasal_envelope(freq=400, bandwidth=100)

        assert isinstance(envelope, list)
        assert len(envelope) == 5

        # Should start and end at base frequency
        assert envelope[0][1] == 400
        assert envelope[-1][1] == 400

    def test_nasal_envelope_variation(self):
        """Test that nasal envelope has frequency variation."""
        envelope = nasal_envelope(freq=300, bandwidth=50)

        freqs = [f for _, f in envelope]
        freq_range = max(freqs) - min(freqs)

        # Should have some variation due to bandwidth
        assert freq_range > 0

    def test_nasal_envelope_bandwidth(self):
        """Test nasal envelope with different bandwidth."""
        narrow = nasal_envelope(freq=400, bandwidth=10)
        wide = nasal_envelope(freq=400, bandwidth=200)

        narrow_freqs = [f for _, f in narrow]
        wide_freqs = [f for _, f in wide]

        narrow_range = max(narrow_freqs) - min(narrow_freqs)
        wide_range = max(wide_freqs) - min(wide_freqs)

        assert wide_range > narrow_range

    def test_semivowel_envelope_basic(self):
        """Test basic semivowel/glide envelope."""
        envelope = semivowel_envelope(start=400, end=600)

        assert isinstance(envelope, list)
        assert len(envelope) == 5

        # Should start at start frequency
        assert envelope[0][1] == 400

    def test_semivowel_envelope_round_trip(self):
        """Test that semivowel envelope returns to start."""
        envelope = semivowel_envelope(start=300, end=900)

        # First and last should be the same
        assert envelope[0][1] == envelope[-1][1]

    def test_semivowel_envelope_midpoint(self):
        """Test that semivowel envelope has midpoint."""
        envelope = semivowel_envelope(start=200, end=1000)

        # Index 2 should be the end frequency
        assert envelope[2][1] == 1000

        # Index 1 and 3 should be the midpoint
        expected_mid = (200 + 1000) / 2
        assert abs(envelope[1][1] - expected_mid) < 1
        assert abs(envelope[3][1] - expected_mid) < 1


class TestCreatePhonemeEnvelopes:
    """Test create_phoneme_envelopes function."""

    def test_creates_all_phonemes(self):
        """Test that all 39 phonemes are created."""
        envelopes = create_phoneme_envelopes()

        # Should have 39 phonemes
        assert len(envelopes) == 39

    def test_phoneme_names(self):
        """Test that expected phonemes exist."""
        envelopes = create_phoneme_envelopes()

        # Sample of key phonemes
        key_phonemes = ['AA', 'AE', 'IH', 'IY', 'UW', 'P', 'B', 'T', 'D',
                        'K', 'G', 'S', 'Z', 'SH', 'M', 'N', 'NG', 'L', 'R', 'W', 'Y']

        for phoneme in key_phonemes:
            assert phoneme in envelopes, f"Missing phoneme: {phoneme}"

    def test_all_vowels_present(self):
        """Test that all monophthong vowels are present."""
        envelopes = create_phoneme_envelopes()

        vowels = ['AA', 'AE', 'AH', 'AO', 'EH', 'ER', 'IH', 'IY', 'UH', 'UW']
        for vowel in vowels:
            assert vowel in envelopes

    def test_all_diphthongs_present(self):
        """Test that all diphthongs are present."""
        envelopes = create_phoneme_envelopes()

        diphthongs = ['AW', 'AY', 'EY', 'OY', 'OW']
        for diphthong in diphthongs:
            assert diphthong in envelopes

    def test_all_stops_present(self):
        """Test that all stop consonants are present."""
        envelopes = create_phoneme_envelopes()

        stops = ['P', 'B', 'T', 'D', 'K', 'G', 'CH', 'JH']
        for stop in stops:
            assert stop in envelopes

    def test_all_fricatives_present(self):
        """Test that all fricatives are present."""
        envelopes = create_phoneme_envelopes()

        fricatives = ['F', 'V', 'TH', 'DH', 'S', 'Z', 'SH', 'ZH', 'HH']
        for fricative in fricatives:
            assert fricative in envelopes

    def test_all_nasals_present(self):
        """Test that all nasal consonants are present."""
        envelopes = create_phoneme_envelopes()

        nasals = ['M', 'N', 'NG']
        for nasal in nasals:
            assert nasal in envelopes

    def test_all_semivowels_present(self):
        """Test that all semivowels/glides are present."""
        envelopes = create_phoneme_envelopes()

        semivowels = ['L', 'R', 'W', 'Y']
        for semivowel in semivowels:
            assert semivowel in envelopes

    def test_envelopes_are_upic_envelopes(self):
        """Test that all values are UPICEnvelope objects."""
        envelopes = create_phoneme_envelopes()

        from upic_engine import UPICEnvelope
        for phoneme, envelope in envelopes.items():
            assert isinstance(envelope, UPICEnvelope), \
                f"{phoneme} is not UPICEnvelope: {type(envelope)}"

    def test_envelope_names_match_phonemes(self):
        """Test that envelope names match their phoneme keys."""
        envelopes = create_phoneme_envelopes()

        for phoneme, envelope in envelopes.items():
            assert envelope.name == phoneme, \
                f"Envelope name mismatch: {envelope.name} != {phoneme}"


class TestGetPhonemeEnvelope:
    """Test get_phoneme_envelope function."""

    def test_get_existing_phoneme(self):
        """Test getting an existing phoneme."""
        envelope = get_phoneme_envelope('AA')

        assert envelope is not None
        assert envelope.name == 'AA'

    def test_get_vowel_phoneme(self):
        """Test getting a vowel phoneme."""
        envelope = get_phoneme_envelope('IY')

        assert envelope.name == 'IY'

    def test_get_stop_phoneme(self):
        """Test getting a stop consonant."""
        envelope = get_phoneme_envelope('T')

        assert envelope.name == 'T'

    def test_get_fricative_phoneme(self):
        """Test getting a fricative."""
        envelope = get_phoneme_envelope('SH')

        assert envelope.name == 'SH'

    def test_get_nasal_phoneme(self):
        """Test getting a nasal."""
        envelope = get_phoneme_envelope('NG')

        assert envelope.name == 'NG'

    def test_get_unknown_phoneme_raises_keyerror(self):
        """Test that unknown phoneme raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            get_phoneme_envelope('XX')

        assert 'Unknown phoneme' in str(exc_info.value)
        assert 'XX' in str(exc_info.value)

    def test_error_message_shows_available_phonemes(self):
        """Test that error message shows available phonemes."""
        with pytest.raises(KeyError) as exc_info:
            get_phoneme_envelope('XYZ')

        error_msg = str(exc_info.value)
        # Should mention some known phonemes
        assert 'AA' in error_msg or 'IH' in error_msg

    def test_case_sensitivity(self):
        """Test that phoneme lookup is case-sensitive."""
        # Should work with uppercase
        envelope_upper = get_phoneme_envelope('AA')

        # Lowercase should fail
        with pytest.raises(KeyError):
            get_phoneme_envelope('aa')


class TestARPABET_IPAMapping:
    """Test ARPAbet to IPA mapping."""

    def test_mapping_exists(self):
        """Test that ARPABET_IPA mapping exists."""
        assert isinstance(ARPABET_IPA, dict)
        assert len(ARPABET_IPA) > 0

    def test_vowel_mappings(self):
        """Test vowel IPA mappings."""
        # Sample vowel mappings
        assert 'AA' in ARPABET_IPA
        assert ARPABET_IPA['AA'] == 'ɑ'

        assert 'IY' in ARPABET_IPA
        assert ARPABET_IPA['IY'] == 'i'

    def test_consonant_mappings(self):
        """Test consonant IPA mappings."""
        assert 'P' in ARPABET_IPA
        assert ARPABET_IPA['P'] == 'p'  # voiceless bilabial plosive

        assert 'S' in ARPABET_IPA
        assert ARPABET_IPA['S'] == 's'

    def test_diphthong_mappings(self):
        """Test diphthong IPA mappings."""
        assert 'AW' in ARPABET_IPA
        assert ARPABET_IPA['AW'] == 'aʊ'

    def test_all_phonemes_have_ipa(self):
        """Test that all 39 phonemes have IPA equivalents."""
        envelopes = create_phoneme_envelopes()

        for phoneme in envelopes.keys():
            assert phoneme in ARPABET_IPA, \
                f"Missing IPA for phoneme: {phoneme}"


class TestConstants:
    """Test module constants."""

    def test_sample_rate(self):
        """Test SAMPLE_RATE constant."""
        assert SAMPLE_RATE == 44100

    def test_duration(self):
        """Test DURATION constant (20ms per phoneme)."""
        assert DURATION == 0.020
        assert DURATION == 20 / 1000  # 20 milliseconds

    def test_duration_makes_sense(self):
        """Test that 20ms duration produces reasonable audio samples."""
        samples_per_phoneme = SAMPLE_RATE * DURATION

        # Should be 882 samples at 44.1kHz for 20ms
        assert samples_per_phoneme == 882


class TestEnvelopeConsistency:
    """Test consistency across phoneme envelopes."""

    def test_all_envelopes_same_structure(self):
        """Test that all phoneme envelopes have consistent structure."""
        envelopes = create_phoneme_envelopes()

        for phoneme, envelope in envelopes.items():
            # Each envelope should have control points
            assert len(envelope.control_points) > 0

            # All times should be in [0, 1]
            times = [t for t, _ in envelope.control_points]
            assert all(0.0 <= t <= 1.0 for t in times), \
                f"{phoneme} has time outside [0,1]"

    def test_vowel_envelopes_have_two_peaks(self):
        """Test that vowel envelopes show two-peak formant structure."""
        vowels = ['AA', 'AE', 'AH', 'AO', 'EH', 'ER', 'IH', 'IY', 'UH', 'UW']

        for vowel in vowels:
            envelope = get_phoneme_envelope(vowel)
            freqs = [f for _, f in envelope.control_points]

            # Should have variation (not all same)
            assert max(freqs) > min(freqs), \
                f"{vowel} envelope has no frequency variation"

    def test_stop_envelopes_have_burst(self):
        """Test that stop envelopes have burst after closure."""
        stops = ['P', 'B', 'T', 'D', 'K', 'G']

        for stop in stops:
            envelope = get_phoneme_envelope(stop)
            freqs = [f for _, f in envelope.control_points]

            # Should start low (closure) and go high (burst)
            assert freqs[0] < max(freqs), \
                f"{stop} envelope doesn't show burst"

    def test_fricative_envelopes_have_high_freq(self):
        """Test that fricative envelopes have high-frequency energy."""
        fricatives = ['S', 'Z', 'SH', 'F', 'V', 'TH', 'DH']

        for fricative in fricatives:
            envelope = get_phoneme_envelope(fricative)
            freqs = [f for _, f in envelope.control_points]

            # Should have frequencies > 1000 Hz
            assert max(freqs) > 1000, \
                f"{fricative} envelope lacks high-frequency energy"

    def test_nasal_envelopes_low_frequency(self):
        """Test that nasal envelopes are low-frequency."""
        nasals = ['M', 'N', 'NG']

        for nasal in nasals:
            envelope = get_phoneme_envelope(nasal)
            freqs = [f for _, f in envelope.control_points]

            # Nasals should be < 1000 Hz
            assert max(freqs) < 1000, \
                f"{nasal} envelope has frequencies too high"