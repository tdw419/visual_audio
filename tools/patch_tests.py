import re

with open("systems/geos_pixel/src/pdb/gpu_integration_tests.rs", "r") as f:
    data = f.read()

data = data.replace(
    "let empty_pattern = vec![];",
    "let empty_pattern: Vec<u8> = vec![];"
)
data = data.replace(
    "let decoder = PdbDecoder::load_png(temp_path).unwrap();",
    "let mut decoder = PdbDecoder::load_png(temp_path).unwrap();"
)
data = data.replace(
    "pub mod gpu_integration_tests;",
    "mod gpu_integration_tests;"
)

with open("systems/geos_pixel/src/pdb/gpu_integration_tests.rs", "w") as f:
    f.write(data)
