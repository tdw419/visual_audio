"""
Natural Language Programming (NLP) Submodule

Provides natural language → code → pixels compilation capabilities.

Components:
- SemanticParser: Parse English commands into semantic structures
- CodeGenerator: Generate Python code from semantic structures
- NaturalLanguageCompiler: End-to-end English → pixels pipeline
"""

from .natural_language_compiler import (
    SemanticParser,
    CodeGenerator,
    NaturalLanguageCompiler,
    VerbType,
    ObjectType,
    ParsedCommand,
)

__all__ = [
    "SemanticParser",
    "CodeGenerator",
    "NaturalLanguageCompiler",
    "VerbType",
    "ObjectType",
    "ParsedCommand",
]