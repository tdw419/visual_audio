# glyph_dispatch -- convenience targets
#
# `make verify` is the gate. It must exit 0 for any change to land, and it is
# exactly what an autonomous loop or CI runs.

PY ?= python3

.PHONY: verify sha256 gen clean

verify:
	$(PY) verify.py

# regenerate the SHA-256 glyph assembly from the generator
gen:
	$(PY) src/glyph/sha256_kernel.py

# just the SHA-256 lockstep oracle
sha256:
	$(PY) tools/sha256_lockstep_test.py

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	find . -name '*.pyc' -delete
