"""
Variophone Emulator Module

Recreates the historical optical sound synthesizer from the 1930s.
Uses rotating polygonal optical cogs with different numbers of teeth to create complex waveforms.

Historical Context:
The Variophone was developed in the 1930s at the Moscow Experimental Film Studio.
It used optical sound-on-film technology with rotating discs (cogs) that had
different numbers of teeth/sides, creating unique harmonic patterns.
"""

import numpy as np
from typing import List, Tuple, Optional
import warnings


class VariophoneCog:
    """
    Represents a single optical cog in the Variophone synthesizer.
    
    Each cog has a specific number of teeth that determines its waveform shape:
    - 3 teeth ≈ triangle wave
    - 4 teeth ≈ square wave  
    - 5+ teeth ≈ polygonal approximation of complex waves
    """
    
    def __init__(self, num_teeth: int, base_frequency: float, 
                 rotation_speed: float = 1.0, amplitude: float = 1.0):
        """
        Initialize a Variophone cog.
        
        Args:
            num_teeth: Number of teeth on the cog (determines harmonic content)
            base_frequency: Fundamental frequency in Hz
            rotation_speed: Speed factor affecting modulation rate (0.1 to 10.0)
            amplitude: Peak amplitude (0.0 to 1.0)
        """
        if num_teeth < 3:
            raise ValueError("Number of teeth must be at least 3")
        if base_frequency <= 0:
            raise ValueError("Base frequency must be positive")
        if not (0.0 <= amplitude <= 1.0):
            raise ValueError("Amplitude must be between 0.0 and 1.0")
        
        self.num_teeth = num_teeth
        self.base_frequency = base_frequency
        self.rotation_speed = rotation_speed
        self.amplitude = amplitude
        
        # Calculate harmonic content based on number of teeth
        # More teeth = richer harmonic spectrum
        self.harmonics = self._calculate_harmonics()
    
    def _calculate_harmonics(self) -> List[float]:
        """
        Calculate harmonic strengths based on number of teeth.
        
        Polygonal cogs create odd and even harmonics based on their symmetry.
        Returns list of (harmonic_number, strength) tuples.
        """
        harmonics = []
        
        # Base harmonics from polygonal shape
        for n in range(1, self.num_teeth + 1):
            if n % 2 == 1:
                # Odd harmonics are stronger (similar to square/triangle waves)
                strength = 1.0 / n
            else:
                # Even harmonics are weaker
                strength = 0.5 / n
            
            harmonics.append((n, strength))
        
        return harmonics


class VariophoneEmulator:
    """
    Main Variophone synthesizer emulator.
    
    Simulates multiple optical cogs with configurable parameters,
    supporting polyphonic synthesis and film strip synchronization.
    """
    
    def __init__(self, sample_rate: int = 44100):
        """
        Initialize the Variophone emulator.
        
        Args:
            sample_rate: Audio sample rate in Hz
        """
        self.sample_rate = sample_rate
        self.cogs: List[VariophoneCog] = []
        
        # Film strip synchronization parameters
        self.film_speed = 24.0  # frames per second (standard film speed)
        self.film_width = 0
        self.sync_enabled = False
    
    def add_cog(self, num_teeth: int, base_frequency: float,
                rotation_speed: float = 1.0, amplitude: float = 1.0) -> 'VariophoneEmulator':
        """
        Add a cog to the synthesizer.
        
        Args:
            num_teeth: Number of teeth on the cog
            base_frequency: Fundamental frequency in Hz
            rotation_speed: Speed factor for modulation
            amplitude: Peak amplitude
            
        Returns:
            Self for method chaining
        """
        cog = VariophoneCog(num_teeth, base_frequency, rotation_speed, amplitude)
        self.cogs.append(cog)
        return self
    
    def clear_cogs(self) -> 'VariophoneEmulator':
        """Remove all cogs from the synthesizer."""
        self.cogs.clear()
        return self
    
    def generate_polygonal_waveform(self, cog: VariophoneCog, 
                                    duration: float) -> np.ndarray:
        """
        Generate a polygonal waveform from a single cog.
        
        Args:
            cog: VariophoneCog configuration
            duration: Duration in seconds
            
        Returns:
            Waveform samples (1D array)
        """
        n_samples = int(duration * self.sample_rate)
        t = np.linspace(0, duration, n_samples, endpoint=False)
        
        # Generate stepped waveform representing optical tooth pattern
        phase = 2 * np.pi * cog.base_frequency * t
        
        # Create polygonal pattern by quantizing phase
        # This simulates the discrete teeth on the optical cog
        teeth_angle = 2 * np.pi / cog.num_teeth
        stepped_phase = np.floor((phase + teeth_angle/2) / teeth_angle) * teeth_angle
        
        # Generate waveform with harmonics
        waveform = np.zeros_like(t)
        for harmonic_num, strength in cog.harmonics:
            waveform += strength * np.sin(harmonic_num * stepped_phase)
        
        # Apply amplitude envelope based on cog rotation
        # This simulates the modulation as the cog spins
        modulation = 0.7 + 0.3 * np.sin(2 * np.pi * cog.rotation_speed * t)
        waveform *= modulation
        
        # Scale by amplitude
        waveform *= cog.amplitude
        
        return waveform
    
    def generate_polyphonic_waveform(self, duration: float,
                                    mix_mode: str = 'additive') -> np.ndarray:
        """
        Generate polyphonic waveform from all cogs.
        
        Args:
            duration: Duration in seconds
            mix_mode: How to combine cogs ('additive', 'ring_mod', 'fm')
            
        Returns:
            Combined waveform (1D array)
        """
        if not self.cogs:
            warnings.warn("No cogs configured. Returning silent audio.")
            return np.zeros(int(duration * self.sample_rate))
        
        n_samples = int(duration * self.sample_rate)
        combined_waveform = np.zeros(n_samples)
        
        if mix_mode == 'additive':
            # Simple additive synthesis
            for cog in self.cogs:
                waveform = self.generate_polygonal_waveform(cog, duration)
                combined_waveform += waveform
        
        elif mix_mode == 'ring_mod':
            # Ring modulation between cogs
            if len(self.cogs) < 2:
                warnings.warn("Ring modulation requires at least 2 cogs. Using additive mode.")
                mix_mode = 'additive'
            else:
                for i in range(len(self.cogs) - 1):
                    wave1 = self.generate_polygonal_waveform(self.cogs[i], duration)
                    wave2 = self.generate_polygonal_waveform(self.cogs[i + 1], duration)
                    combined_waveform += wave1 * wave2
        
        elif mix_mode == 'fm':
            # Frequency modulation (FM synthesis)
            if len(self.cogs) < 2:
                warnings.warn("FM synthesis requires at least 2 cogs. Using additive mode.")
                mix_mode = 'additive'
            else:
                carrier = self.generate_polygonal_waveform(self.cogs[0], duration)
                modulator = self.generate_polygonal_waveform(self.cogs[1], duration)
                
                # Apply FM
                t = np.linspace(0, duration, n_samples, endpoint=False)
                modulation_index = 0.5
                combined_waveform = np.sin(2 * np.pi * self.cogs[0].base_frequency * t + 
                                          modulation_index * modulator)
        
        else:
            raise ValueError(f"Unknown mix_mode: {mix_mode}")
        
        # Normalize to prevent clipping
        peak = np.max(np.abs(combined_waveform))
        if peak > 0:
            combined_waveform = combined_waveform / peak * 0.95
        
        return combined_waveform
    
    def simulate_film_strip(self, frames: int, width: int) -> np.ndarray:
        """
        Simulate optical film strip with drawn sound patterns.
        
        Args:
            frames: Number of film frames
            width: Width of each frame in pixels
            
        Returns:
            2D array representing film strip (frames × width)
        """
        self.film_width = width
        film_strip = np.zeros((frames, width))
        
        if not self.cogs:
            return film_strip
        
        # For each cog, draw its pattern on the film strip
        for frame in range(frames):
            for cog in self.cogs:
                # Calculate position based on cog rotation
                phase = (frame / self.film_speed) * cog.base_frequency
                teeth_positions = np.arange(cog.num_teeth) * (2 * np.pi / cog.num_teeth)
                
                # Draw teeth as bright regions on film
                for tooth_pos in teeth_positions:
                    x_pos = int(((tooth_pos + phase) % (2 * np.pi)) / (2 * np.pi) * width)
                    if 0 <= x_pos < width:
                        film_strip[frame, x_pos] += cog.amplitude
        
        # Normalize
        film_strip = np.clip(film_strip, 0, 1)
        
        return film_strip
    
    def generate_from_film_strip(self, film_strip: np.ndarray) -> np.ndarray:
        """
        Generate audio from a simulated film strip.
        
        Args:
            film_strip: 2D array (frames × width) representing optical film
            
        Returns:
            Audio waveform (1D array)
        """
        frames, width = film_strip.shape
        n_samples = int((frames / self.film_speed) * self.sample_rate)
        audio = np.zeros(n_samples)
        
        # Scan film strip and generate audio
        for frame in range(frames):
            frame_start = int((frame / self.film_speed) * self.sample_rate)
            frame_end = int(((frame + 1) / self.film_speed) * self.sample_rate)
            frame_end = min(frame_end, n_samples)
            
            # Use film pattern as amplitude envelope
            if frame_end > frame_start:
                frame_samples = frame_end - frame_start
                pattern = film_strip[frame, :]
                pattern_resampled = np.interp(
                    np.linspace(0, len(pattern), frame_samples),
                    np.arange(len(pattern)),
                    pattern
                )
                audio[frame_start:frame_end] = pattern_resampled
        
        # Apply bandpass filter to simulate optical sound head frequency response
        from scipy.signal import butter, sosfilt
        sos = butter(4, [20, 8000], btype='band', fs=self.sample_rate, output='sos')
        audio = sosfilt(sos, audio)
        
        # Normalize
        peak = np.max(np.abs(audio))
        if peak > 0:
            audio = audio / peak * 0.95
        
        return audio
    
    def get_cog_info(self) -> List[dict]:
        """
        Get information about all configured cogs.
        
        Returns:
            List of dictionaries with cog information
        """
        return [
            {
                'num_teeth': cog.num_teeth,
                'base_frequency': cog.base_frequency,
                'rotation_speed': cog.rotation_speed,
                'amplitude': cog.amplitude,
                'harmonics': len(cog.harmonics)
            }
            for cog in self.cogs
        ]
    
    def set_film_speed(self, fps: float) -> 'VariophoneEmulator':
        """
        Set film strip playback speed.
        
        Args:
            fps: Frames per second
            
        Returns:
            Self for method chaining
        """
        self.film_speed = max(1.0, fps)
        return self


# Convenience function for quick waveform generation
def generate_variophone_waveform(cogs_config: List[Tuple[int, float, float, float]],
                                  duration: float = 2.0,
                                  sample_rate: int = 44100,
                                  mix_mode: str = 'additive') -> np.ndarray:
    """
    Quick function to generate a Variophone waveform.
    
    Args:
        cogs_config: List of (num_teeth, frequency, rotation_speed, amplitude) tuples
        duration: Duration in seconds
        sample_rate: Sample rate in Hz
        mix_mode: Mix mode ('additive', 'ring_mod', 'fm')
        
    Returns:
        Generated waveform (1D array)
    """
    emulator = VariophoneEmulator(sample_rate)
    
    for config in cogs_config:
        emulator.add_cog(*config)
    
    return emulator.generate_polyphonic_waveform(duration, mix_mode)