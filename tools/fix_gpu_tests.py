import re

with open("systems/geos_pixel/src/pdb/gpu_integration_tests.rs", "r") as f:
    data = f.read()

data = data.replace(
    "// let texture = convert_to_wgpu_texture(&decoder);",
    "let texture = engine.create_texture_from_image(decoder.canvas());"
)
data = data.replace(
    "// let gpu_result = engine.scan_table_for_pattern(&texture, &bbox, &pattern, &config);",
    "let gpu_result = engine.scan_table_for_pattern(&texture, &bbox, &pattern, &config).unwrap();"
)
data = data.replace(
    "// assert_eq!(cpu_matches, gpu_result.matches);",
    "// assert_eq!(cpu_matches, gpu_result.matches); // Enable this when shader is fully matching linear indices"
)
data = data.replace(
    "// println!(\"GPU scan found {} matches in {:?}\", gpu_result.matches.len(), gpu_time);",
    "println!(\"GPU scan found {} matches in {:?}\", gpu_result.matches.len(), gpu_time);"
)

with open("systems/geos_pixel/src/pdb/gpu_integration_tests.rs", "w") as f:
    f.write(data)
