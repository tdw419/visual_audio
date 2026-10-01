"""L4 isolation: run test_l4_user_mode_mechanism_pin against two engine revisions.

Does NOT touch the repo — writes engine copies to a temp dir, points the test's
import at them via a stub package.
"""
import importlib.util
import sys
import types
from pathlib import Path

REPO = Path('/home/jericho/projects/zion/projects/visual_audio')
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'tools'))
GATE = REPO / 'tests' / 'test_defect23_pte_acceptance.py'


def load_engine(path):
    name = 'eng_' + Path(path).stem
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_gate(engine_path, label):
    eng = load_engine(engine_path)
    # Build a fake 'tools' package whose glyph_isa_v2 is THIS engine rev.
    fake_tools = types.ModuleType('tools')
    fake_tools.__path__ = []
    fake_tools.glyph_isa_v2 = eng
    sys.modules['tools'] = fake_tools
    sys.modules['tools.glyph_isa_v2'] = eng
    # Fresh test module each time so class-level state doesn't leak.
    for m in list(sys.modules):
        if m.startswith(('test_gate',)):
            del sys.modules[m]
    spec = importlib.util.spec_from_file_location('test_gate', GATE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['test_gate'] = mod
    spec.loader.exec_module(mod)
    try:
        mod.test_l4_user_mode_mechanism_pin()
        print(f'{label}: L4 PASS')
    except AssertionError as e:
        print(f'{label}: L4 FAIL -> {e}')
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f'{label}: L4 ERROR -> {type(e).__name__}: {e}')
        traceback.print_exc()


run_gate('/tmp/l4bisect/engine_dfc6126.py', 'engine@dfc6126 (halt_reason, PRE-naming)')
run_gate('/tmp/l4bisect/engine_26a29b7.py', 'engine@26a29b7 (5-site naming)')
run_gate('/tmp/l4bisect/engine_live.py', 'engine@fd24c76 (live HEAD)')
