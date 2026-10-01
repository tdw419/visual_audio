"""
codec package — Audio codec physical and error-correction layers.
"""

from .phy import Phy16Tone, frame, unframe, encode_framed, decode_framed
from .phy_ecc import PhyECC, encode_ecc, decode_ecc

__all__ = [
    'Phy16Tone',
    'frame',
    'unframe',
    'encode_framed',
    'decode_framed',
    'PhyECC',
    'encode_ecc',
    'decode_ecc',
]