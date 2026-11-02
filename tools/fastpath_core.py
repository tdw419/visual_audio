#!/usr/bin/env python3
"""CoreFast — SpatialRV64ICore with the pre-decoded fast path enabled.

The in-shader flag DECODED_FASTPATH_DISABLED must be patched before
create_shader_module() runs. The older SHADER_TRANSFORM hook is dead code —
SpatialRV64ICore._init_pipeline() never reads it (verified 2026-09-01), so any
approach that sets that attribute silently produces a SLOW-path core.

We instead intercept Path.read_text for the shader path while the base
_init_pipeline() executes, patching the flag literal. The base class's binding
layout remains the single source of truth.
"""
import sys
from pathlib import Path

import numpy as np

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from spatial_rv64i_cpu import SpatialRV64ICore

FLAG_TRUE = 'let DECODED_FASTPATH_DISABLED: bool = true;'
FLAG_FALSE = 'let DECODED_FASTPATH_DISABLED: bool = false;'
SHADER_PATH = (_TOOLS_DIR / 'SPATIAL_RV64I.wgsl').resolve()


def _init_pipeline_with_flag(core, flag_wanted_text, flag_replacement_text):
    """Run base _init_pipeline with the shader flag forced to a given value."""
    orig_read_text = Path.read_text

    def _patched_read_text(self, *args, **kwargs):
        text = orig_read_text(self, *args, **kwargs)
        if self.resolve() == SHADER_PATH:
            if flag_wanted_text in text:
                text = text.replace(flag_wanted_text, flag_replacement_text)
            # else: shader already at desired value — no-op
        return text

    Path.read_text = _patched_read_text
    try:
        SpatialRV64ICore._init_pipeline(core)
    finally:
        Path.read_text = orig_read_text


class CoreFast(SpatialRV64ICore):
    """Forces the pre-decoded fast path ON regardless of the shader default."""

    def _init_pipeline(self):
        _init_pipeline_with_flag(self, FLAG_TRUE, FLAG_FALSE)


class CoreSlow(SpatialRV64ICore):
    """Forces the fast path OFF (pure decode_and_execute) regardless of default."""

    def _init_pipeline(self):
        _init_pipeline_with_flag(self, FLAG_FALSE, FLAG_TRUE)


def _post_load_sync(core):
    """Make decoded_ops real after a checkpoint load.

    load_checkpoint() restores memory via raw write_buffer and never touches
    _dirty_ranges, so _sync_decoded_ops() no-ops on resume and the decoded_ops
    buffer stays zeroed (dop.len==0 -> fastpath gate fails -> silent decode-path
    fallback). Any 'fast-path' measurement from a checkpoint resume is therefore
    bogus unless we re-decode. Mirror what load_program does: refresh the linear
    shadow from the GPU buffer, mark everything dirty, sync.
    """
    buf = core.queue.read_buffer(core.memory.buffer)
    spatial = np.frombuffer(buf, dtype=np.uint32)
    core._linear_shadow = spatial[core.hilbert_lut_np]
    n = core._linear_shadow.shape[0] * 4
    core._mark_range_dirty(0, n)
    core._sync_decoded_ops()


def load_checkpoint_fast(path):
    """load_checkpoint() constructing a CoreFast (fast path enabled)."""
    import rv64i_checkpoint as ckpt_mod
    orig = ckpt_mod.SpatialRV64ICore
    ckpt_mod.SpatialRV64ICore = CoreFast
    try:
        core = ckpt_mod.load_checkpoint(path)
    finally:
        ckpt_mod.SpatialRV64ICore = orig
    _post_load_sync(core)
    return core


def load_checkpoint_slow(path):
    """load_checkpoint() constructing a CoreSlow (fast path forced off)."""
    import rv64i_checkpoint as ckpt_mod
    orig = ckpt_mod.SpatialRV64ICore
    ckpt_mod.SpatialRV64ICore = CoreSlow
    try:
        core = ckpt_mod.load_checkpoint(path)
    finally:
        ckpt_mod.SpatialRV64ICore = orig
    return core
