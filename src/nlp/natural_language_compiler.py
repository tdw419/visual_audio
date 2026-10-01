#!/usr/bin/env python3
"""
Natural Language Compiler (NLC) — Plain English → Executable Code

This compiler transforms natural language commands into Python code,
which can then be encoded as pixels via PixelTokenizer and stored in
Visual Audio MKV containers.

Architecture:
  English Input → Semantic Parser → Code Generator → Python → Pixels → MKV → Execute

Example:
  "create a red pixel at 10, 20"
  → parse_english()
  → generate_code()
  → "pixels.set_pixel(10, 20, (255, 0, 0))"
  → PixelTokenizer.encode_to_pixels()
  → RGB pixels
  → MKV storage
  → Execute
"""

import re
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class VerbType(Enum):
    """Supported action verbs in English commands."""
    CREATE = "create"
    MAKE = "make"
    DRAW = "draw"
    SET = "set"
    CHANGE = "change"
    ADD = "add"
    REMOVE = "remove"
    DELETE = "delete"
    CLEAR = "clear"
    MOVE = "move"
    RESIZE = "resize"
    COLOR = "color"
    PRINT = "print"
    DISPLAY = "display"
    CALCULATE = "calculate"
    COMPUTE = "compute"
    CALL = "call"
    RUN = "run"
    EXECUTE = "execute"


class ObjectType(Enum):
    """Supported object types."""
    PIXEL = "pixel"
    PIXELS = "pixels"
    RECTANGLE = "rectangle"
    CIRCLE = "circle"
    LINE = "line"
    TEXT = "text"
    WINDOW = "window"
    VARIABLE = "variable"
    FUNCTION = "function"


@dataclass
class ParsedCommand:
    """Result of parsing an English command."""
    verb: VerbType
    object_type: ObjectType
    parameters: Dict[str, Any]
    modifiers: List[str]
    original: str

    def __repr__(self):
        return f"ParsedCommand(verb={self.verb}, object={self.object_type}, params={self.parameters})"


class SemanticParser:
    """
    Parse natural English commands into semantic structures.

    Uses pattern matching and heuristics to extract:
    - Action verbs (create, make, draw, set, ...)
    - Object types (pixel, rectangle, circle, ...)
    - Parameters (position, size, color, value, ...)
    - Modifiers (adjectives, adverbs, ...)
    """

    # Color name → RGB mapping
    COLORS = {
        'red': (255, 0, 0),
        'green': (0, 255, 0),
        'blue': (0, 0, 255),
        'yellow': (255, 255, 0),
        'cyan': (0, 255, 255),
        'magenta': (255, 0, 255),
        'white': (255, 255, 255),
        'black': (0, 0, 0),
        'orange': (255, 165, 0),
        'purple': (128, 0, 128),
        'pink': (255, 192, 203),
        'brown': (165, 42, 42),
        'gray': (128, 128, 128),
        'grey': (128, 128, 128),
    }

    # Number words → integers
    NUMBERS = {
        'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4,
        'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
        'ten': 10, 'eleven': 11, 'twelve': 12
    }

    def __init__(self):
        """Initialize parser."""
        self.patterns = self._init_patterns()

    def _init_patterns(self) -> List[re.Pattern]:
        """Initialize regex patterns for command parsing."""
        patterns = []

        # Pattern 1: "create a [color] [object] at [position]"
        patterns.append(re.compile(
            r'(create|make|draw|add)\s+(?:a\s+)?(\w+)?\s*(\w+)\s+(?:at|position|located)\s+(\d+),\s*(\d+)',
            re.IGNORECASE
        ))

        # Pattern 2: "set [object] [parameter] to [value]"
        patterns.append(re.compile(
            r'(set|change|make)\s+(\w+)\s+(\w+)\s+(?:to|as|be)\s+(\S+)',
            re.IGNORECASE
        ))

        # Pattern 3: "print [text]"
        patterns.append(re.compile(
            r'(print|display|show|output)\s+(?:the\s+)?(.+)',
            re.IGNORECASE
        ))

        # Pattern 4: "calculate [expression]"
        patterns.append(re.compile(
            r'(calculate|compute|evaluate)\s+(.+)',
            re.IGNORECASE
        ))

        # Pattern 5: "call function [name] with [args]"
        patterns.append(re.compile(
            r'(call|run|execute)\s+(?:function\s+)?(\w+)\s+(?:with|using)\s+(.+)',
            re.IGNORECASE
        ))

        return patterns

    def parse(self, english: str) -> ParsedCommand:
        """
        Parse an English command into a semantic structure.

        Args:
            english: Natural language command

        Returns:
            ParsedCommand with verb, object_type, parameters

        Example:
            >>> parser = SemanticParser()
            >>> cmd = parser.parse("create a red pixel at 10, 20")
            >>> cmd.verb
            <VerbType.CREATE>
            >>> cmd.object_type
            <ObjectType.PIXEL>
            >>> cmd.parameters
            {'x': 10, 'y': 20, 'color': (255, 0, 0)}
        """
        english = english.strip().lower()

        # Try pattern matching
        for pattern in self.patterns:
            match = pattern.match(english)
            if match:
                return self._parse_match(match, english)

        # Fallback: simple verb + object extraction
        return self._parse_simple(english)

    def _parse_match(self, match: re.Match, original: str) -> ParsedCommand:
        """Parse a regex match into ParsedCommand."""
        groups = match.groups()

        # Determine pattern type based on group count
        if len(groups) >= 5 and groups[0] in ['create', 'make', 'draw', 'add']:
            # Pattern 1: create a [color] [object] at [position]
            verb_str, color_name, object_str, x_str, y_str = groups[0:5]
            verb = VerbType(verb_str)

            # Parse color
            color = self._parse_color(color_name or groups[2])

            # Parse position
            x = int(x_str) if x_str.isdigit() else self.NUMBERS.get(x_str, 0)
            y = int(y_str) if y_str.isdigit() else self.NUMBERS.get(y_str, 0)

            # Parse object type
            object_type = self._parse_object_type(object_str or groups[2])

            return ParsedCommand(
                verb=verb,
                object_type=object_type,
                parameters={'x': x, 'y': y, 'color': color},
                modifiers=[color_name] if color_name else [],
                original=original
            )

        elif len(groups) >= 4 and groups[0] in ['set', 'change', 'make']:
            # Pattern 2: set [object] [parameter] to [value]
            verb_str, object_str, param_str, value_str = groups[0:4]
            verb = VerbType(verb_str)
            object_type = self._parse_object_type(object_str)
            value = self._parse_value(value_str)

            return ParsedCommand(
                verb=verb,
                object_type=object_type,
                parameters={'parameter': param_str, 'value': value},
                modifiers=[],
                original=original
            )

        elif len(groups) >= 2 and groups[0] in ['print', 'display', 'show', 'output']:
            # Pattern 3: print [text]
            verb_str, text = groups[0:2]
            verb = VerbType(verb_str)

            return ParsedCommand(
                verb=verb,
                object_type=ObjectType.TEXT,
                parameters={'text': text.strip()},
                modifiers=[],
                original=original
            )

        elif len(groups) >= 2 and groups[0] in ['calculate', 'compute', 'evaluate']:
            # Pattern 4: calculate [expression]
            verb_str, expression = groups[0:2]
            verb = VerbType(verb_str)

            return ParsedCommand(
                verb=verb,
                object_type=ObjectType.VARIABLE,
                parameters={'expression': expression.strip()},
                modifiers=[],
                original=original
            )

        elif len(groups) >= 3 and groups[0] in ['call', 'run', 'execute']:
            # Pattern 5: call function [name] with [args]
            verb_str, func_name, args_str = groups[0:3]
            verb = VerbType(verb_str)

            # Parse arguments
            args = [self._parse_value(arg.strip()) for arg in args_str.split(',')]

            return ParsedCommand(
                verb=verb,
                object_type=ObjectType.FUNCTION,
                parameters={'function': func_name, 'arguments': args},
                modifiers=[],
                original=original
            )

        # Fallback
        return self._parse_simple(original)

    def _parse_simple(self, english: str) -> ParsedCommand:
        """Fallback simple parser for unmatched patterns."""
        words = english.split()

        # Extract first word as verb
        if words:
            verb_str = words[0].lower()
            try:
                verb = VerbType(verb_str)
            except ValueError:
                verb = VerbType.CREATE  # Default verb
        else:
            verb = VerbType.CREATE

        # Extract object type from words
        object_type = ObjectType.PIXEL  # Default
        for word in words[1:]:
            try:
                object_type = ObjectType(word.lower())
                break
            except ValueError:
                pass

        return ParsedCommand(
            verb=verb,
            object_type=object_type,
            parameters={},
            modifiers=[],
            original=english
        )

    def _parse_color(self, color_str: str) -> Tuple[int, int, int]:
        """Parse color name or hex to RGB tuple."""
        if not color_str:
            return (128, 128, 128)  # Default gray

        # Check hex format
        if color_str.startswith('#'):
            try:
                hex_str = color_str[1:]
                r = int(hex_str[0:2], 16)
                g = int(hex_str[2:4], 16)
                b = int(hex_str[4:6], 16)
                return (r, g, b)
            except ValueError:
                pass

        # Check named colors
        if color_str.lower() in self.COLORS:
            return self.COLORS[color_str.lower()]

        return (128, 128, 128)

    def _parse_object_type(self, object_str: str) -> ObjectType:
        """Parse object type string to enum."""
        if not object_str:
            return ObjectType.PIXEL

        # Try direct enum match
        try:
            return ObjectType(object_str.lower())
        except ValueError:
            pass

        # Fuzzy matching for common variations
        if 'pixel' in object_str.lower():
            return ObjectType.PIXEL
        elif 'rect' in object_str.lower():
            return ObjectType.RECTANGLE
        elif 'circle' in object_str.lower():
            return ObjectType.CIRCLE
        elif 'line' in object_str.lower():
            return ObjectType.LINE
        elif 'text' in object_str.lower() or 'string' in object_str.lower():
            return ObjectType.TEXT
        elif 'window' in object_str.lower():
            return ObjectType.WINDOW
        elif 'func' in object_str.lower():
            return ObjectType.FUNCTION

        return ObjectType.PIXEL

    def _parse_value(self, value_str: str) -> Any:
        """Parse value string to appropriate Python type."""
        value_str = value_str.strip().strip('"\'').lower()

        # Try integer
        try:
            return int(value_str)
        except ValueError:
            pass

        # Try float
        try:
            return float(value_str)
        except ValueError:
            pass

        # Try boolean
        if value_str in ['true', 'yes', 'on']:
            return True
        elif value_str in ['false', 'no', 'off']:
            return False

        # Try number words
        if value_str in self.NUMBERS:
            return self.NUMBERS[value_str]

        # Try color names
        if value_str in self.COLORS:
            return self.COLORS[value_str]

        # Return as string (original case preserved)
        return value_str.strip('"\'')


class CodeGenerator:
    """
    Generate Python code from parsed semantic commands.

    Converts ParsedCommand objects into executable Python statements.
    """

    def __init__(self, indent: str = "    "):
        """
        Initialize code generator.

        Args:
            indent: Indentation string (default: 4 spaces)
        """
        self.indent = indent
        self.indent_level = 0

    def generate(self, command: ParsedCommand) -> str:
        """
        Generate Python code from a parsed command.

        Args:
            command: ParsedCommand from SemanticParser

        Returns:
            Python code string

        Example:
            >>> parser = SemanticParser()
            >>> generator = CodeGenerator()
            >>> cmd = parser.parse("create a red pixel at 10, 20")
            >>> code = generator.generate(cmd)
            >>> print(code)
            pixels.set_pixel(10, 20, (255, 0, 0))
        """
        verb = command.verb
        obj_type = command.object_type
        params = command.parameters

        # Dispatch to appropriate generator
        if verb in [VerbType.CREATE, VerbType.MAKE, VerbType.DRAW, VerbType.ADD]:
            return self._generate_create(obj_type, params)
        elif verb in [VerbType.SET, VerbType.CHANGE]:
            return self._generate_set(obj_type, params)
        elif verb in [VerbType.REMOVE, VerbType.DELETE]:
            return self._generate_remove(obj_type, params)
        elif verb in [VerbType.CLEAR]:
            return self._generate_clear(obj_type, params)
        elif verb in [VerbType.PRINT, VerbType.DISPLAY]:
            return self._generate_print(params)
        elif verb in [VerbType.CALCULATE, VerbType.COMPUTE]:
            return self._generate_calculate(params)
        elif verb in [VerbType.CALL, VerbType.RUN, VerbType.EXECUTE]:
            return self._generate_call(params)
        else:
            return f"# Unknown command: {command.original}"

    def _generate_create(self, obj_type: ObjectType, params: Dict) -> str:
        """Generate code for create/make/draw commands."""
        if obj_type == ObjectType.PIXEL:
            x = params.get('x', 0)
            y = params.get('y', 0)
            color = params.get('color', (128, 128, 128))
            return f"pixels.set_pixel({x}, {y}, {color})"

        elif obj_type == ObjectType.RECTANGLE:
            x = params.get('x', 0)
            y = params.get('y', 0)
            width = params.get('width', 10)
            height = params.get('height', 10)
            color = params.get('color', (128, 128, 128))
            return f"pixels.draw_rect({x}, {y}, {width}, {height}, {color})"

        elif obj_type == ObjectType.CIRCLE:
            x = params.get('x', 0)
            y = params.get('y', 0)
            radius = params.get('radius', 5)
            color = params.get('color', (128, 128, 128))
            return f"pixels.draw_circle({x}, {y}, {radius}, {color})"

        elif obj_type == ObjectType.WINDOW:
            width = params.get('width', 640)
            height = params.get('height', 480)
            title = params.get('title', '"Window"')
            return f"window = Window({width}, {height}, {title})"

        else:
            return f"# Create {obj_type.value}: {params}"

    def _generate_set(self, obj_type: ObjectType, params: Dict) -> str:
        """Generate code for set/change commands."""
        param = params.get('parameter', 'value')
        value = params.get('value', None)

        if param == 'color':
            return f"pixels.set_color({value})"
        elif param == 'position':
            x, y = value if isinstance(value, (list, tuple)) else (0, 0)
            return f"pixels.set_position({x}, {y})"
        else:
            return f"pixels.{param} = {repr(value)}"

    def _generate_remove(self, obj_type: ObjectType, params: Dict) -> str:
        """Generate code for remove/delete commands."""
        x = params.get('x', 0)
        y = params.get('y', 0)
        return f"pixels.remove_pixel({x}, {y})"

    def _generate_clear(self, obj_type: ObjectType, params: Dict) -> str:
        """Generate code for clear commands."""
        return "pixels.clear()"

    def _generate_print(self, params: Dict) -> str:
        """Generate code for print/display commands."""
        text = params.get('text', '')
        return f'print({repr(text)})'

    def _generate_calculate(self, params: Dict) -> str:
        """Generate code for calculate/compute commands."""
        expr = params.get('expression', '0')
        return f"result = {expr}"

    def _generate_call(self, params: Dict) -> str:
        """Generate code for call/run/execute commands."""
        func = params.get('function', 'unknown')
        args = params.get('arguments', [])
        args_str = ', '.join(repr(arg) for arg in args)
        return f"{func}({args_str})"


class NaturalLanguageCompiler:
    """
    Main compiler: English → Code → Pixels.

    Orchestrates the full pipeline:
    1. Parse English with SemanticParser
    2. Generate Python code with CodeGenerator
    3. Encode to pixels with PixelTokenizer
    4. Decode back to verify round-trip
    """

    def __init__(self, wordbase_path: Optional[Path] = None):
        """
        Initialize the natural language compiler.

        Args:
            wordbase_path: Path to wordbase database (for PixelTokenizer)
        """
        self.parser = SemanticParser()
        self.generator = CodeGenerator()

        # Lazy import PixelTokenizer (only when needed)
        self._tokenizer = None
        self._wordbase_path = wordbase_path

    @property
    def tokenizer(self):
        """Lazy-load PixelTokenizer."""
        if self._tokenizer is None:
            from src.pixel_tokenizer import PixelTokenizer
            self._tokenizer = PixelTokenizer(self._wordbase_path)
        return self._tokenizer

    def compile(self, english: str, to_pixels: bool = True) -> Dict[str, Any]:
        """
        Compile English command to code and optionally pixels.

        Args:
            english: Natural language command
            to_pixels: If True, encode code to pixels

        Returns:
            Dict with 'code', 'pixels', 'parsed', etc.

        Example:
            >>> compiler = NaturalLanguageCompiler()
            >>> result = compiler.compile("create a red pixel at 10, 20")
            >>> print(result['code'])
            pixels.set_pixel(10, 20, (255, 0, 0))
            >>> print(result['pixels'].shape)
            (N, 3)
        """
        # Step 1: Parse English
        parsed = self.parser.parse(english)

        # Step 2: Generate code
        code = self.generator.generate(parsed)

        result = {
            'original': english,
            'parsed': parsed,
            'code': code,
            'pixels': None
        }

        # Step 3: Encode to pixels (optional)
        if to_pixels:
            try:
                pixels = self.tokenizer.encode_to_pixels(code, add_special_tokens=False)
                result['pixels'] = pixels

                # Verify round-trip
                decoded = self.tokenizer.decode_from_pixels(pixels, skip_special_tokens=True)
                result['roundtrip_ok'] = (code.strip() == decoded.strip())
                result['decoded'] = decoded
            except Exception as e:
                result['encoding_error'] = str(e)

        return result

    def compile_batch(self, commands: List[str], to_pixels: bool = True) -> List[Dict[str, Any]]:
        """
        Compile multiple English commands.

        Args:
            commands: List of natural language commands
            to_pixels: If True, encode code to pixels

        Returns:
            List of compilation result dictionaries
        """
        results = []
        for cmd in commands:
            result = self.compile(cmd, to_pixels=to_pixels)
            results.append(result)
        return results

    def compile_and_save(self, english: str, output_path: str) -> bool:
        """
        Compile English command and save pixels to file.

        Args:
            english: Natural language command
            output_path: Path to save pixel array (.npy)

        Returns:
            True if successful
        """
        import numpy as np

        result = self.compile(english, to_pixels=True)

        if result['pixels'] is not None:
            np.save(output_path, result['pixels'])
            return True

        return False


def main():
    """CLI entry point for natural language compilation."""
    import argparse
    import json
    import numpy as np

    parser = argparse.ArgumentParser(
        description="Natural Language Compiler — Plain English → Code → Pixels"
    )
    parser.add_argument(
        "command",
        type=str,
        help="Natural language command to compile"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Save pixels to .npy file"
    )
    parser.add_argument(
        "--no-pixels",
        action="store_true",
        help="Skip pixel encoding (code only)"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output"
    )

    args = parser.parse_args()

    # Compile
    compiler = NaturalLanguageCompiler()
    result = compiler.compile(args.command, to_pixels=not args.no_pixels)

    # Save pixels if requested
    if args.output and result['pixels'] is not None:
        np.save(args.output, result['pixels'])
        print(f"✓ Pixels saved to {args.output}")

    # Output result
    output_dict = {
        'original': result['original'],
        'parsed': str(result['parsed']),
        'code': result['code'],
        'pixels_shape': list(result['pixels'].shape) if result['pixels'] is not None else None,
        'roundtrip_ok': result.get('roundtrip_ok', False),
    }

    if args.pretty:
        print(json.dumps(output_dict, indent=2))
    else:
        print(json.dumps(output_dict))

    # Print code for human readability
    print(f"\nGenerated code:\n{result['code']}")


if __name__ == "__main__":
    main()