import re

with open("systems/geos_pixel/src/pdb/gpu_integration_tests.rs", "r") as f:
    data = f.read()

data = data.replace("#[ignore] // Requires actual GPU execution - will be enabled in Phase 2 completion\n", "")
data = data.replace("#[ignore] // Requires actual GPU execution\n", "")

with open("systems/geos_pixel/src/pdb/gpu_integration_tests.rs", "w") as f:
    f.write(data)
