# TASK_V001 DRAFT SUMMARY

Task: Dense encoder bridge replacement (TASK_V001, Priority: HIGH, Phase: Visual Audio Memory Palace (VAMP))

What was done:
- Confirmed `tools/dense_encoder.py` already exists and implements the dense encoding functions (encode_dense, decode_dense, frame/unframe with 'UA' magic, CRC32 verification, 3 bytes/pixel density via RGB channels).
- Verified `tests/test_vamp_dense_bridge.py` exists and fully exercises the dense encoder API. Running the test suite yields 10/10 passes and demonstrates density metrics approaching 3 bytes/pixel for larger payloads, with CRC verification and 'UA' frame format confirmed by the test assertions.
- Searched for `pixelpack/scripts/memory_to_png.py`. The path does not exist in this repository (no `pixelpack` directory found). Because the reference target cannot be found, I did not perform a concrete integration of `tools/dense_encoder.py` into a file that does not exist.

Verification evidence (from running the test command provided in the task):
```
python3 tests/test_vamp_dense_bridge.py
```
Result: All 10 tests passed:
- test_frame_format_ua: PASS
- test_crc_verification: PASS (including corruption case)
- test_bytes_to_pixels_round_trip: PASS
- test_three_bytes_per_pixel_density: PASS (checks meet size-based thresholds)
- test_encode_decode_round_trip: PASS
- test_all_tiles_crc_verification: PASS
- test_vamp_integration_json: PASS
- test_square_image_layout: PASS
- test_single_row_layout: PASS
- test_png_metadata: PASS
The visual density section also shows framed densities approaching 3 bytes/pixel for larger payloads (e.g., 5000 bytes → ~2.9792 bytes/pixel).

Status of task requirements relative to what exists:
- Encode/decode round-trip: Confirmed via tests.
- 3 bytes/pixel density: Achieved for larger payloads; test thresholds accept overhead on smaller payloads.
- CRC verification on all generated tiles: Confirmed by the CRC-corruption test and the all-tiles CRC test.
- Frame format 'UA': Confirmed by test_frame_format_ua and the dense_encoder.py implementation.

Missing piece due to missing target:
- Integration requirement: The receipt criteria state: "`pixelpack/scripts/memory_to_png.py` uses `tools/dense_encoder.py` for encoding". Since `pixelpack/scripts/memory_to_png.py` does not exist in the current repository tree, I cannot make a concrete change to that file.

Next steps to complete the task:
- Confirm the correct path/name of the script that should use `tools/dense_encoder.py` (e.g., an existing script that currently implements dense encoding inline, or a file that will be added as part of this phase).
- If a target script is identified, modify it to import and use `tools/dense_encoder.encode_dense` for PNG encoding and `tools/dense_encoder.decode_dense` for PNG decoding, ensuring 3 bytes/pixel density and CRC verification are preserved.
- If the target script does not yet exist and should be created, specify its location, intended API, and how it should interface with `tools/dense_encoder.py`. Once created or specified, perform the integration and rerun the test command to confirm nothing regresses.
- Verify backward compatibility with existing Memory Palace building (as stated in the receipt criteria) by running any relevant integration tests or Memory Palace workflows.

Why the task is not yet marked complete:
- The target integration file (`pixelpack/scripts/memory_to_png.py`) was not found in the repository, so the integration step could not be performed. The remaining receipt requirement (backward compatibility) cannot be verified without a concrete target script or workflow to run.

Report:
- Task TASK_V001 drafted: Dense encoder bridge replacement. Core dense_encoder implementation and test suite are present and passing. Integration step awaits target script location or creation.