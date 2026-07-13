"""
UPIC-Inspired Drawing Interface Core Engine.

Implements wavetable synthesis, envelope/LFO control curves, and time scaling
inspired by Iannis Xenakis's pioneering graphical sound synthesis system.
"""

import numpy as np
from scipy import signal
from scipy.interpolate import interp1d
import json
from typing import Dict, List, Tuple, Optional, Any
import soundfile as sf


class UPICWaveformTable:
    """Represents a single wavetable for synthesis."""
    
    def __init__(self, name: str, samples: np.ndarray, sample_rate: float = 44100.0):
        self.name = name
        self.samples = samples
        self.sample_rate = sample_rate
        self.length = len(samples)
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'samples': self.samples.tolist(),
            'sample_rate': self.sample_rate,
            'length': self.length
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UPICWaveformTable':
        return cls(
            name=data['name'],
            samples=np.array(data['samples']),
            sample_rate=data['sample_rate']
        )
    
    def get_interpolated_sample(self, phase: float) -> float:
        """Get interpolated sample value for a given phase (0.0 to 1.0)."""
        # Wrap phase to [0, 1]
        phase = phase % 1.0
        
        # Calculate position
        position = phase * (self.length - 1)
        
        # Linear interpolation
        index_floor = int(np.floor(position))
        index_ceil = min(index_floor + 1, self.length - 1)
        fraction = position - index_floor
        
        return (1 - fraction) * self.samples[index_floor] + fraction * self.samples[index_ceil]


class UPICEnvelope:
    """Represents an envelope or LFO control curve."""
    
    def __init__(self, name: str, control_points: List[Tuple[float, float]]):
        """
        Create envelope from control points.
        
        Args:
            name: Envelope name
            control_points: List of (time, value) tuples, time in [0, 1]
        """
        self.name = name
        self.control_points = sorted(control_points, key=lambda x: x[0])
        
        if not self.control_points:
            raise ValueError("Envelope must have at least one control point")
            
        # Validate time range
        if not (0.0 <= self.control_points[0][0] <= 1.0):
            raise ValueError("Control point times must be in [0, 1]")
            
    def evaluate(self, time: float) -> float:
        """Evaluate envelope at a given time (0.0 to 1.0)."""
        time = np.clip(time, 0.0, 1.0)
        
        # If single point, return that value
        if len(self.control_points) == 1:
            return self.control_points[0][1]
        
        # Extract times and values
        times = [cp[0] for cp in self.control_points]
        values = [cp[1] for cp in self.control_points]
        
        # Linear interpolation
        if time <= times[0]:
            return values[0]
        elif time >= times[-1]:
            return values[-1]
        else:
            # Find segment
            for i in range(len(times) - 1):
                if times[i] <= time <= times[i + 1]:
                    # Interpolate within segment
                    t1, t2 = times[i], times[i + 1]
                    v1, v2 = values[i], values[i + 1]
                    fraction = (time - t1) / (t2 - t1) if t2 != t1 else 0
                    return v1 + fraction * (v2 - v1)
        
        return values[-1]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'control_points': self.control_points
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UPICEnvelope':
        return cls(name=data['name'], control_points=data['control_points'])


class UPICVoice:
    """Represents a single synthesis voice in UPIC."""
    
    def __init__(self, name: str, wavetable: UPICWaveformTable):
        self.name = name
        self.wavetable = wavetable
        self.frequency_envelope: Optional[UPICEnvelope] = None
        self.amplitude_envelope: Optional[UPICEnvelope] = None
        self.time_envelope: Optional[UPICEnvelope] = None
        
        # Default parameters
        self.base_frequency = 440.0
        self.base_amplitude = 0.5
        
    def set_frequency_envelope(self, envelope: UPICEnvelope):
        self.frequency_envelope = envelope
        
    def set_amplitude_envelope(self, envelope: UPICEnvelope):
        self.amplitude_envelope = envelope
        
    def set_time_envelope(self, envelope: UPICEnvelope):
        self.time_envelope = envelope
        
    def synthesize(self, duration: float, sample_rate: float = 44100.0) -> np.ndarray:
        """
        Synthesize audio from this voice.
        
        Args:
            duration: Duration in seconds
            sample_rate: Sample rate in Hz
            
        Returns:
            Audio samples as numpy array
        """
        num_samples = int(duration * sample_rate)
        time_points = np.linspace(0, duration, num_samples)
        output = np.zeros(num_samples)
        
        # Current phase accumulator
        phase = 0.0
        
        for i, t in enumerate(time_points):
            # Normalized time for envelopes [0, 1]
            normalized_time = t / duration
            
            # Get frequency from envelope (or base frequency)
            if self.frequency_envelope:
                freq_mod = self.frequency_envelope.evaluate(normalized_time)
                frequency = self.base_frequency * freq_mod
            else:
                frequency = self.base_frequency
            
            # Get amplitude from envelope (or base amplitude)
            if self.amplitude_envelope:
                amplitude = self.base_amplitude * self.amplitude_envelope.evaluate(normalized_time)
            else:
                amplitude = self.base_amplitude
            
            # Get time scaling from envelope
            time_scale = 1.0
            if self.time_envelope:
                time_scale = self.time_envelope.evaluate(normalized_time)
            
            # Calculate phase increment
            phase_increment = (frequency * time_scale) / sample_rate
            phase += phase_increment
            
            # Get interpolated sample from wavetable
            sample = self.wavetable.get_interpolated_sample(phase)
            
            output[i] = amplitude * sample
        
        return output
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'wavetable': self.wavetable.to_dict(),
            'frequency_envelope': self.frequency_envelope.to_dict() if self.frequency_envelope else None,
            'amplitude_envelope': self.amplitude_envelope.to_dict() if self.amplitude_envelope else None,
            'time_envelope': self.time_envelope.to_dict() if self.time_envelope else None,
            'base_frequency': self.base_frequency,
            'base_amplitude': self.base_amplitude
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UPICVoice':
        voice = cls(
            name=data['name'],
            wavetable=UPICWaveformTable.from_dict(data['wavetable'])
        )
        
        if data['frequency_envelope']:
            voice.set_frequency_envelope(UPICEnvelope.from_dict(data['frequency_envelope']))
        if data['amplitude_envelope']:
            voice.set_amplitude_envelope(UPICEnvelope.from_dict(data['amplitude_envelope']))
        if data['time_envelope']:
            voice.set_time_envelope(UPICEnvelope.from_dict(data['time_envelope']))
        
        voice.base_frequency = data['base_frequency']
        voice.base_amplitude = data['base_amplitude']
        
        return voice


class UPICProject:
    """Represents a complete UPIC composition project."""
    
    def __init__(self, name: str):
        self.name = name
        self.wavetables: Dict[str, UPICWaveformTable] = {}
        self.envelopes: Dict[str, UPICEnvelope] = {}
        self.voices: List[UPICVoice] = []
        
    def add_wavetable(self, wavetable: UPICWaveformTable):
        self.wavetables[wavetable.name] = wavetable
        
    def add_envelope(self, envelope: UPICEnvelope):
        self.envelopes[envelope.name] = envelope
        
    def add_voice(self, voice: UPICVoice):
        self.voices.append(voice)
        
    def create_basic_wavetables(self, sample_rate: float = 44100.0, table_size: int = 2048):
        """Create standard wavetables (sine, triangle, square, sawtooth)."""
        
        # Sine wave
        t = np.linspace(0, 2 * np.pi, table_size, endpoint=False)
        sine_samples = np.sin(t)
        self.add_wavetable(UPICWaveformTable("sine", sine_samples, sample_rate))
        
        # Triangle wave
        triangle_samples = signal.sawtooth(t, width=int(0.5))
        self.add_wavetable(UPICWaveformTable("triangle", triangle_samples, sample_rate))
        
        # Square wave
        square_samples = signal.square(t)
        self.add_wavetable(UPICWaveformTable("square", square_samples, sample_rate))
        
        # Sawtooth wave
        sawtooth_samples = signal.sawtooth(t)
        self.add_wavetable(UPICWaveformTable("sawtooth", sawtooth_samples, sample_rate))
        
    def create_basic_envelopes(self):
        """Create standard envelopes (ADSR, LFO shapes)."""
        
        # ADSR envelope
        adsr_points = [
            (0.0, 0.0),      # Attack start
            (0.1, 1.0),      # Attack peak
            (0.3, 0.7),      # Decay
            (0.7, 0.7),      # Sustain
            (0.9, 0.3),      # Release
            (1.0, 0.0)       # End
        ]
        self.add_envelope(UPICEnvelope("ADSR", adsr_points))
        
        # Linear ramp envelope
        ramp_points = [(0.0, 0.0), (1.0, 1.0)]
        self.add_envelope(UPICEnvelope("ramp_up", ramp_points))
        
        # Reverse ramp envelope
        reverse_ramp_points = [(0.0, 1.0), (1.0, 0.0)]
        self.add_envelope(UPICEnvelope("ramp_down", reverse_ramp_points))
        
        # LFO sine envelope
        lfo_points = [(i/10.0, np.sin(i/10.0 * 2 * np.pi) * 0.5 + 0.5) for i in range(11)]
        self.add_envelope(UPICEnvelope("LFO_sine", lfo_points))
        
    def synthesize(self, duration: float, sample_rate: float = 44100.0) -> np.ndarray:
        """
        Synthesize complete composition from all voices.
        
        Args:
            duration: Duration in seconds
            sample_rate: Sample rate in Hz
            
        Returns:
            Mixed audio samples as numpy array
        """
        if not self.voices:
            return np.zeros(int(duration * sample_rate))
        
        # Synthesize all voices
        voice_outputs = []
        for voice in self.voices:
            voice_output = voice.synthesize(duration, sample_rate)
            voice_outputs.append(voice_output)
        
        # Mix all voices
        mixed = np.sum(voice_outputs, axis=0)
        
        # Normalize to prevent clipping
        if np.max(np.abs(mixed)) > 0:
            mixed = mixed / np.max(np.abs(mixed)) * 0.95
        
        return mixed
    
    def export_wav(self, filename: str, duration: float, sample_rate: float = 44100.0):
        """Export composition to WAV file."""
        audio = self.synthesize(duration, sample_rate)
        sf.write(filename, audio, int(sample_rate))
        
    def save_project(self, filename: str):
        """Save project to JSON file."""
        data = {
            'name': self.name,
            'wavetables': {name: wt.to_dict() for name, wt in self.wavetables.items()},
            'envelopes': {name: env.to_dict() for name, env in self.envelopes.items()},
            'voices': [voice.to_dict() for voice in self.voices]
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load_project(cls, filename: str) -> 'UPICProject':
        """Load project from JSON file."""
        with open(filename, 'r') as f:
            data = json.load(f)
        
        project = cls(data['name'])
        
        # Load wavetables
        for name, wt_data in data['wavetables'].items():
            project.add_wavetable(UPICWaveformTable.from_dict(wt_data))
        
        # Load envelopes
        for name, env_data in data['envelopes'].items():
            project.add_envelope(UPICEnvelope.from_dict(env_data))
        
        # Load voices
        for voice_data in data['voices']:
            project.add_voice(UPICVoice.from_dict(voice_data))
        
        return project


def create_basic_waveform(wave_type: str, size: int = 2048) -> np.ndarray:
    """Create basic waveform array."""
    t = np.linspace(0, 2 * np.pi, size, endpoint=False)
    
    if wave_type == "sine":
        return np.sin(t)
    elif wave_type == "triangle":
        return signal.sawtooth(t, width=int(0.5))
    elif wave_type == "square":
        return signal.square(t)
    elif wave_type == "sawtooth":
        return signal.sawtooth(t)
    else:
        raise ValueError(f"Unknown waveform type: {wave_type}")


def create_custom_wavetable(samples: np.ndarray, name: str = "custom") -> UPICWaveformTable:
    """Create wavetable from custom samples."""
    return UPICWaveformTable(name, samples, 44100.0)