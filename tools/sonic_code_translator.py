#!/usr/bin/env python3
"""
sonic_code_translator.py — Make code sound pleasing when spoken through visual audio.

Translates code structure into musical/rhythmic patterns that:
- Sound melodious to human listeners
- Convey code meaning through prosody and intonation
- Use musical patterns to represent programming constructs
- Make code-listening an aesthetic experience

Architecture:
1. Code AST Parser → Extract structure (functions, loops, variables)
2. Musical Mapper → Map constructs to musical patterns (pitch, rhythm, timbre)
3. Audio Generator → Use UPIC engine to synthesize pleasant audio
4. Dual-Band Encoder → Add metadata band for AI understanding
"""

import ast
import json
import os
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from upic_engine import (
    UPICProject, UPICVoice, UPICWaveformTable, UPICEnvelope,
    create_basic_waveform
)

SAMPLE_RATE = 44100
BASE_FREQUENCY = 261.63  # C4 (middle C) as musical foundation


class MusicalConstruct(Enum):
    """Programming constructs mapped to musical patterns."""
    
    # Control structures (different pitch centers)
    FUNCTION = "function"
    CLASS = "class"
    IF = "conditional"
    FOR_LOOP = "for_loop"
    WHILE_LOOP = "while_loop"
    TRY = "exception"
    
    # Variables and data (different timbres)
    VARIABLE = "variable"
    CONSTANT = "constant"
    STRING = "string"
    NUMBER = "number"
    
    # Operations (different rhythms)
    ASSIGNMENT = "assignment"
    COMPARISON = "comparison"
    OPERATION = "operation"
    CALL = "function_call"
    RETURN = "return"
    
    # Structure markers (musical cadences)
    INDENT = "indent"
    DEDENT = "dedent"
    STATEMENT_END = "statement_end"
    BLOCK_START = "block_start"
    BLOCK_END = "block_end"


@dataclass
class MusicalEvent:
    """A single musical event representing a code construct."""
    construct: MusicalConstruct
    start_time: float
    duration: float
    pitch: float
    amplitude: float
    waveform: str
    text: str  # Original code text for reference


class MusicalCodeMapper:
    """Maps programming constructs to musical patterns."""
    
    # Scale: C major pentatonic (pleasant, consonant)
    # C4, D4, E4, G4, A4, C5, D5, E5, G5, A5
    PENTATONIC_SCALE = [
        261.63,  # C4
        293.66,  # D4
        329.63,  # E4
        392.00,  # G4
        440.00,  # A4
        523.25,  # C5
        587.33,  # D5
        659.25,  # E5
        783.99,  # G5
        880.00,  # A5
    ]
    
    # Waveforms for different construct types
    WAVEFORMS = {
        # Control structures: pure sine tones
        MusicalConstruct.FUNCTION: 'sine',
        MusicalConstruct.CLASS: 'sine',
        MusicalConstruct.IF: 'sine',
        MusicalConstruct.FOR_LOOP: 'sine',
        MusicalConstruct.WHILE_LOOP: 'sine',
        MusicalConstruct.TRY: 'sine',
        
        # Variables: triangle waves (softer)
        MusicalConstruct.VARIABLE: 'triangle',
        MusicalConstruct.CONSTANT: 'triangle',
        
        # Literals: richer timbres
        MusicalConstruct.STRING: 'sine',
        MusicalConstruct.NUMBER: 'triangle',
        
        # Operations: square waves (percussive)
        MusicalConstruct.ASSIGNMENT: 'square',
        MusicalConstruct.COMPARISON: 'square',
        MusicalConstruct.OPERATION: 'square',
        MusicalConstruct.CALL: 'triangle',
        MusicalConstruct.RETURN: 'sine',
        
        # Structure: gentle sine
        MusicalConstruct.INDENT: 'sine',
        MusicalConstruct.DEDENT: 'sine',
        MusicalConstruct.STATEMENT_END: 'sine',
        MusicalConstruct.BLOCK_START: 'sine',
        MusicalConstruct.BLOCK_END: 'sine',
    }
    
    # Duration patterns (in seconds)
    DURATIONS = {
        # Control structures: longer, more sustained
        MusicalConstruct.FUNCTION: 0.8,
        MusicalConstruct.CLASS: 1.0,
        MusicalConstruct.IF: 0.4,
        MusicalConstruct.FOR_LOOP: 0.5,
        MusicalConstruct.WHILE_LOOP: 0.6,
        MusicalConstruct.TRY: 0.5,
        
        # Variables: moderate
        MusicalConstruct.VARIABLE: 0.3,
        MusicalConstruct.CONSTANT: 0.3,
        MusicalConstruct.STRING: 0.4,
        MusicalConstruct.NUMBER: 0.2,
        
        # Operations: brief, rhythmic
        MusicalConstruct.ASSIGNMENT: 0.15,
        MusicalConstruct.COMPARISON: 0.2,
        MusicalConstruct.OPERATION: 0.15,
        MusicalConstruct.CALL: 0.25,
        MusicalConstruct.RETURN: 0.5,
        
        # Structure: very brief markers
        MusicalConstruct.INDENT: 0.05,
        MusicalConstruct.DEDENT: 0.05,
        MusicalConstruct.STATEMENT_END: 0.1,
        MusicalConstruct.BLOCK_START: 0.15,
        MusicalConstruct.BLOCK_END: 0.2,
    }
    
    # Pitch mapping (indices into PENTATONIC_SCALE)
    PITCHES = {
        # Control structures: lower register (foundational)
        MusicalConstruct.FUNCTION: 0,      # C4
        MusicalConstruct.CLASS: 1,         # D4
        MusicalConstruct.IF: 2,            # E4
        MusicalConstruct.FOR_LOOP: 3,      # G4
        MusicalConstruct.WHILE_LOOP: 4,    # A4
        MusicalConstruct.TRY: 5,           # C5
        
        # Variables: middle register
        MusicalConstruct.VARIABLE: 3,      # G4
        MusicalConstruct.CONSTANT: 4,      # A4
        MusicalConstruct.STRING: 5,        # C5
        MusicalConstruct.NUMBER: 6,        # D5
        
        # Operations: higher register (active)
        MusicalConstruct.ASSIGNMENT: 6,    # D5
        MusicalConstruct.COMPARISON: 7,    # E5
        MusicalConstruct.OPERATION: 7,     # E5
        MusicalConstruct.CALL: 8,          # G5
        MusicalConstruct.RETURN: 9,        # A5
        
        # Structure: very high or low markers
        MusicalConstruct.INDENT: 0,        # C4
        MusicalConstruct.DEDENT: 0,        # C4
        MusicalConstruct.STATEMENT_END: 1, # D4
        MusicalConstruct.BLOCK_START: 2,   # E4
        MusicalConstruct.BLOCK_END: 2,     # E4
    }
    
    # Amplitude (loudness) mapping
    AMPLITUDES = {
        # Control structures: moderate
        MusicalConstruct.FUNCTION: 0.7,
        MusicalConstruct.CLASS: 0.75,
        MusicalConstruct.IF: 0.6,
        MusicalConstruct.FOR_LOOP: 0.65,
        MusicalConstruct.WHILE_LOOP: 0.65,
        MusicalConstruct.TRY: 0.6,
        
        # Variables: softer
        MusicalConstruct.VARIABLE: 0.5,
        MusicalConstruct.CONSTANT: 0.55,
        MusicalConstruct.STRING: 0.6,
        MusicalConstruct.NUMBER: 0.5,
        
        # Operations: crisp
        MusicalConstruct.ASSIGNMENT: 0.6,
        MusicalConstruct.COMPARISON: 0.55,
        MusicalConstruct.OPERATION: 0.5,
        MusicalConstruct.CALL: 0.65,
        MusicalConstruct.RETURN: 0.7,
        
        # Structure: subtle
        MusicalConstruct.INDENT: 0.3,
        MusicalConstruct.DEDENT: 0.3,
        MusicalConstruct.STATEMENT_END: 0.4,
        MusicalConstruct.BLOCK_START: 0.45,
        MusicalConstruct.BLOCK_END: 0.5,
    }
    
    @classmethod
    def get_pitch(cls, construct: MusicalConstruct, variation: int = 0) -> float:
        """Get pitch for a construct with optional variation for musical interest."""
        base_idx = cls.PITCHES[construct]
        # Add variation (octave jumps or stepwise motion)
        idx = (base_idx + variation) % len(cls.PENTATONIC_SCALE)
        return cls.PENTATONIC_SCALE[idx]
    
    @classmethod
    def get_duration(cls, construct: MusicalConstruct) -> float:
        """Get duration for a construct."""
        return cls.DURATIONS[construct]
    
    @classmethod
    def get_waveform(cls, construct: MusicalConstruct) -> str:
        """Get waveform type for a construct."""
        return cls.WAVEFORMS[construct]
    
    @classmethod
    def get_amplitude(cls, construct: MusicalConstruct) -> float:
        """Get amplitude for a construct."""
        return cls.AMPLITUDES[construct]


class CodeToMusicalEvents(ast.NodeVisitor):
    """Parse code AST and generate musical events."""
    
    def __init__(self):
        self.events: List[MusicalEvent] = []
        self.current_time = 0.0
        self.nesting_depth = 0
        self.mapper = MusicalCodeMapper()
    
    def _add_event(self, construct: MusicalConstruct, text: str, duration: float = None):
        """Add a musical event at current time."""
        if duration is None:
            duration = self.mapper.get_duration(construct)
        
        # Add pitch variation based on nesting depth for musical interest
        variation = self.nesting_depth % 2
        
        event = MusicalEvent(
            construct=construct,
            start_time=self.current_time,
            duration=duration,
            pitch=self.mapper.get_pitch(construct, variation),
            amplitude=self.mapper.get_amplitude(construct),
            waveform=self.mapper.get_waveform(construct),
            text=text
        )
        self.events.append(event)
        self.current_time += duration
    
    def _add_indent(self):
        """Add indent marker event."""
        self._add_event(MusicalConstruct.INDENT, "→", 0.05)
    
    def _add_dedent(self):
        """Add dedent marker event."""
        self._add_event(MusicalConstruct.DEDENT, "←", 0.05)
    
    def _add_statement_end(self):
        """Add statement end marker event."""
        self._add_event(MusicalConstruct.STATEMENT_END, ";", 0.1)
    
    def visit_FunctionDef(self, node):
        """Visit function definition."""
        self._add_event(MusicalConstruct.FUNCTION, f"def {node.name}")
        self.nesting_depth += 1
        self._add_indent()
        
        # Visit body
        for stmt in node.body:
            self.visit(stmt)
        
        self.nesting_depth -= 1
        self._add_dedent()
    
    def visit_ClassDef(self, node):
        """Visit class definition."""
        self._add_event(MusicalConstruct.CLASS, f"class {node.name}")
        self.nesting_depth += 1
        self._add_indent()
        
        # Visit body
        for stmt in node.body:
            self.visit(stmt)
        
        self.nesting_depth -= 1
        self._add_dedent()
    
    def visit_If(self, node):
        """Visit if statement."""
        self._add_event(MusicalConstruct.IF, "if")
        self.visit(node.test)
        
        self.nesting_depth += 1
        self._add_indent()
        
        # Visit body
        for stmt in node.body:
            self.visit(stmt)
        
        self.nesting_depth -= 1
        self._add_dedent()
        
        # Visit else
        if node.orelse:
            self._add_event(MusicalConstruct.IF, "else")
            self.nesting_depth += 1
            self._add_indent()
            for stmt in node.orelse:
                self.visit(stmt)
            self.nesting_depth -= 1
            self._add_dedent()
    
    def visit_For(self, node):
        """Visit for loop."""
        self._add_event(MusicalConstruct.FOR_LOOP, "for")
        self.visit(node.target)
        self.visit(node.iter)
        
        self.nesting_depth += 1
        self._add_indent()
        
        # Visit body
        for stmt in node.body:
            self.visit(stmt)
        
        self.nesting_depth -= 1
        self._add_dedent()
    
    def visit_While(self, node):
        """Visit while loop."""
        self._add_event(MusicalConstruct.WHILE_LOOP, "while")
        self.visit(node.test)
        
        self.nesting_depth += 1
        self._add_indent()
        
        # Visit body
        for stmt in node.body:
            self.visit(stmt)
        
        self.nesting_depth -= 1
        self._add_dedent()
    
    def visit_Try(self, node):
        """Visit try statement."""
        self._add_event(MusicalConstruct.TRY, "try")
        
        self.nesting_depth += 1
        self._add_indent()
        
        # Visit body
        for stmt in node.body:
            self.visit(stmt)
        
        self.nesting_depth -= 1
        self._add_dedent()
        
        # Visit handlers
        for handler in node.handlers:
            self._add_event(MusicalConstruct.TRY, "except")
            self.nesting_depth += 1
            self._add_indent()
            for stmt in handler.body:
                self.visit(stmt)
            self.nesting_depth -= 1
            self._add_dedent()
    
    def visit_Assign(self, node):
        """Visit assignment."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._add_event(MusicalConstruct.VARIABLE, target.id)
            elif isinstance(target, ast.Attribute):
                self.visit(target)
        
        self._add_event(MusicalConstruct.ASSIGNMENT, "=")
        self.visit(node.value)
        self._add_statement_end()
    
    def visit_Name(self, node):
        """Visit variable name."""
        self._add_event(MusicalConstruct.VARIABLE, node.id)
    
    def visit_Constant(self, node):
        """Visit constant value."""
        if isinstance(node.value, str):
            self._add_event(MusicalConstruct.STRING, f'"{node.value[:20]}..."')
        elif isinstance(node.value, (int, float)):
            self._add_event(MusicalConstruct.NUMBER, str(node.value))
        elif isinstance(node.value, bool):
            self._add_event(MusicalConstruct.CONSTANT, str(node.value))
    
    def visit_BinOp(self, node):
        """Visit binary operation."""
        self.visit(node.left)
        op_type = type(node.op).__name__
        self._add_event(MusicalConstruct.OPERATION, op_type)
        self.visit(node.right)
    
    def visit_Compare(self, node):
        """Visit comparison."""
        self.visit(node.left)
        for op in node.ops:
            op_type = type(op).__name__
            self._add_event(MusicalConstruct.COMPARISON, op_type)
        for comparator in node.comparators:
            self.visit(comparator)
    
    def visit_Call(self, node):
        """Visit function call."""
        if isinstance(node.func, ast.Name):
            self._add_event(MusicalConstruct.CALL, node.func.id)
        
        # Visit arguments
        for arg in node.args:
            self.visit(arg)
    
    def visit_Return(self, node):
        """Visit return statement."""
        self._add_event(MusicalConstruct.RETURN, "return")
        if node.value:
            self.visit(node.value)
        self._add_statement_end()
    
    def visit_Expr(self, node):
        """Visit expression statement."""
        self.visit(node.value)
        self._add_statement_end()
    
    def visit_Module(self, node):
        """Visit module (root)."""
        for stmt in node.body:
            self.visit(stmt)


def synthesize_musical_events(events: List[MusicalEvent]) -> np.ndarray:
    """Synthesize musical events into audio using UPIC engine."""
    if not events:
        return np.array([])
    
    total_duration = events[-1].start_time + events[-1].duration
    
    # Create UPIC project
    project = UPICProject("sonic_code")
    
    # Add wavetables for different waveform types
    wavetables = {}
    waveform_types = set(event.waveform for event in events)
    
    for wf_type in waveform_types:
        waveform = create_basic_waveform(wf_type)
        wt = UPICWaveformTable(wf_type, waveform, SAMPLE_RATE)
        project.add_wavetable(wt)
        wavetables[wf_type] = wt
    
    # Group events by waveform for efficiency
    events_by_waveform = {}
    for event in events:
        if event.waveform not in events_by_waveform:
            events_by_waveform[event.waveform] = []
        events_by_waveform[event.waveform].append(event)
    
    # Create voices for each waveform type
    for wf_type, wf_events in events_by_waveform.items():
        if not wf_events:
            continue
        
        # Build frequency envelope
        freq_points = []
        amp_points = []
        
        for event in wf_events:
            # Frequency envelope points
            t_start = event.start_time / total_duration
            t_end = (event.start_time + event.duration) / total_duration
            
            freq_points.append((t_start, event.pitch))
            freq_points.append((t_end, event.pitch))
            
            # Amplitude envelope points
            amp_points.append((t_start, event.amplitude))
            amp_points.append((t_end, event.amplitude))
        
        # Create envelopes
        freq_envelope = UPICEnvelope(f"{wf_type}_freq", freq_points)
        amp_envelope = UPICEnvelope(f"{wf_type}_amp", amp_points)
        
        project.add_envelope(freq_envelope)
        project.add_envelope(amp_envelope)
        
        # Create voice
        voice = UPICVoice(f"{wf_type}_voice", wavetables[wf_type])
        voice.base_frequency = 1.0
        voice.base_amplitude = 1.0
        voice.set_frequency_envelope(freq_envelope)
        voice.set_amplitude_envelope(amp_envelope)
        project.add_voice(voice)
    
    # Synthesize audio
    audio = project.synthesize(total_duration, SAMPLE_RATE)
    
    # Normalize
    if np.max(np.abs(audio)) > 0:
        audio = audio / np.max(np.abs(audio)) * 0.9
    
    return audio


def code_to_pleasant_audio(
    code: str,
    output_path: str = "pleasant_code.wav",
    project_path: str = None
) -> Tuple[np.ndarray, List[MusicalEvent]]:
    """
    Convert code to pleasant-sounding audio.
    
    Args:
        code: Python source code
        output_path: Output WAV file path
        project_path: Optional UPIC project file path
    
    Returns:
        Tuple of (audio_array, musical_events)
    """
    # Parse code into AST
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Failed to parse code: {e}")
    
    # Generate musical events from AST
    parser = CodeToMusicalEvents()
    parser.visit(tree)
    events = parser.events
    
    if not events:
        raise ValueError("No musical events generated from code")
    
    print(f"Generated {len(events)} musical events from code")
    print(f"Total duration: {events[-1].start_time + events[-1].duration:.2f}s")
    
    # Synthesize audio
    audio = synthesize_musical_events(events)
    
    # Save audio
    sf.write(output_path, audio, SAMPLE_RATE)
    print(f"Saved audio to: {output_path}")
    
    # Save project metadata
    if project_path:
        metadata = {
            'source_code': code,
            'events': [
                {
                    'construct': event.construct.value,
                    'start_time': event.start_time,
                    'duration': event.duration,
                    'pitch': event.pitch,
                    'amplitude': event.amplitude,
                    'waveform': event.waveform,
                    'text': event.text
                }
                for event in events
            ],
            'total_duration': events[-1].start_time + events[-1].duration,
            'sample_rate': SAMPLE_RATE
        }
        
        with open(project_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"Saved project metadata to: {project_path}")
    
    return audio, events


def print_musical_summary(events: List[MusicalEvent]):
    """Print a summary of musical events."""
    print("\nMusical Event Summary:")
    print("-" * 60)
    
    # Group by construct type
    by_construct = {}
    for event in events:
        if event.construct not in by_construct:
            by_construct[event.construct] = []
        by_construct[event.construct].append(event)
    
    for construct, construct_events in sorted(by_construct.items(), key=lambda x: x[0].value):
        print(f"{construct.value:20s}: {len(construct_events):3d} events")
        print(f"  Example: {construct_events[0].text}")
        print(f"  Pitch: {construct_events[0].pitch:.1f} Hz, Duration: {construct_events[0].duration:.3f}s")
        print()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Convert code to pleasant-sounding audio using musical patterns"
    )
    parser.add_argument('input', help='Python source file or code string')
    parser.add_argument('-o', '--output', default='pleasant_code.wav', 
                        help='Output WAV file')
    parser.add_argument('-p', '--project', help='Output project metadata file')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Print detailed musical event summary')
    
    args = parser.parse_args()
    
    # Read input
    if os.path.exists(args.input):
        with open(args.input, 'r') as f:
            code = f.read()
    else:
        code = args.input
    
    print(f"Converting code to pleasant audio...")
    print(f"Code length: {len(code)} characters")
    
    try:
        audio, events = code_to_pleasant_audio(
            code,
            output_path=args.output,
            project_path=args.project
        )
        
        if args.verbose:
            print_musical_summary(events)
        
        print(f"\n✓ Success! Generated {len(audio)/SAMPLE_RATE:.2f}s of pleasant code audio")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())