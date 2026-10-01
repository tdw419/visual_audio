// Pixel-encoded GPU compute as a service on V5: real Linux, real CPU,
// dispatching pixel-encoded SPIR-V compute jobs to the GPU for the parts
// that are actually GPU-shaped - the architecture decided on after
// establishing that single-core "Linux on GPU" is a dead end (see
// PIXEL_GPU_COMPUTE_RECEIPT.md) but many-parallel-lanes GPU compute
// genuinely wins (~40x, verified). This is that pipeline
// (spirv_from_pixels.rs / parallel_pixels_bench.rs) turned into a
// long-running daemon instead of a one-shot benchmark: the GPU device
// opens once at startup, then serves requests.
//
// Protocol: Unix socket, newline-delimited JSON (same shape as
// infinite_map_rs/src/ipc.rs). A `RunKernel` job names two PNGs - one
// holding pixel-encoded SPIR-V bytes, one holding pixel-encoded u32 input
// data - dispatches the shader over the input, and writes the result as a
// third PNG.
//
// Kernel ABI (fixed, matching parallel_collatz.wgsl - see that file for
// why): binding 0 = `storage, read_write array<u32>` data buffer, binding
// 1 = uniform `{ group_count_x: u32 }` params, `@workgroup_size(256)`,
// entry point "main". A more general service would need a richer ABI;
// this is the one already proven to work end-to-end tonight.

use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::time::Instant;

pub const SOCKET_PATH: &str = "/tmp/pixel_compute.sock";

#[derive(Deserialize, Debug)]
#[serde(tag = "action")]
enum Request {
    #[serde(rename = "ping")]
    Ping,
    #[serde(rename = "run_kernel")]
    RunKernel {
        shader_png: String,
        // Exact SPIR-V byte length - a square PNG almost never holds
        // exactly width*height*4 bytes of real content (e.g. 3840 real
        // bytes needs a 31x31 pixel grid, which has 1 trailing padding
        // pixel/4 bytes), and naga's SPIR-V parser rejects any trailing
        // junk word outright (InvalidWordCount) - hit this for real on
        // the first end-to-end test.
        shader_len: usize,
        input_png: String,
        input_len: usize,
        output_png: String,
    },
}

#[derive(Serialize, Debug)]
struct Response {
    status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    elements: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    elapsed_ms: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    simt_efficiency: Option<f64>,
}

impl Response {
    fn ok() -> Self {
        Response { status: "ok".into(), message: None, elements: None, elapsed_ms: None, simt_efficiency: None }
    }
    fn err(msg: impl Into<String>) -> Self {
        Response { status: "error".into(), message: Some(msg.into()), elements: None, elapsed_ms: None, simt_efficiency: None }
    }
}

struct GpuContext {
    device: wgpu::Device,
    queue: wgpu::Queue,
    max_storage_binding: u32,
}

impl GpuContext {
    fn new() -> Self {
        let instance = wgpu::Instance::default();
        let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions::default()))
            .expect("no GPU adapter");
        eprintln!("[pixel_compute_service] GPU adapter: {}", adapter.get_info().name);
        let limits = adapter.limits();
        let (device, queue) = pollster::block_on(adapter.request_device(
            &wgpu::DeviceDescriptor { required_limits: limits.clone(), ..Default::default() },
            None,
        ))
        .expect("request_device");
        GpuContext { device, queue, max_storage_binding: limits.max_storage_buffer_binding_size }
    }

    fn run_kernel(
        &self,
        shader_png: &str,
        shader_len: usize,
        input_png: &str,
        input_len: usize,
        output_png: &str,
    ) -> std::io::Result<(u32, f64)> {
        let shader_img = image::open(shader_png)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?
            .to_rgba8();
        let spv_bytes = &shader_img.as_raw()[..shader_len];
        if shader_len % 4 != 0 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                format!("shader_len {shader_len} is not a whole number of 32-bit words"),
            ));
        }
        let words: Vec<u32> = spv_bytes
            .chunks_exact(4)
            .map(|c| u32::from_ne_bytes([c[0], c[1], c[2], c[3]]))
            .collect();

        let input_img = image::open(input_png)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?
            .to_rgba8();
        let (iw, ih) = (input_img.width(), input_img.height());
        let raw = &input_img.into_raw()[..input_len];
        let n = (raw.len() / 4) as u32; // one u32 element per pixel (RGBA8 = 4 bytes)
        let byte_len = (n as u64) * 4;
        if byte_len > self.max_storage_binding as u64 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                format!("input {byte_len}B exceeds max_storage_buffer_binding_size {}B", self.max_storage_binding),
            ));
        }

        use wgpu::util::DeviceExt;
        let shader = self.device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("pixel_compute_service kernel"),
            source: wgpu::ShaderSource::SpirV(std::borrow::Cow::Owned(words)),
        });

        let buffer = self.device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("data"),
            contents: raw,
            usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC | wgpu::BufferUsages::COPY_DST,
        });
        let staging = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("staging"),
            size: byte_len,
            usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });

        let total_workgroups = (n + 255) / 256;
        const MAX_DIM: u32 = 65535;
        let group_count_x = total_workgroups.max(1).min(MAX_DIM);
        let group_count_y = (total_workgroups + group_count_x - 1) / group_count_x.max(1);

        let params_buffer = self.device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("params"),
            contents: bytemuck::bytes_of(&group_count_x),
            usage: wgpu::BufferUsages::UNIFORM,
        });

        // Binding 2: CPPM-style per-workgroup (sum, max) pressure counters -
        // required by this kernel ABI (see parallel_collatz.wgsl). Not
        // every possible kernel needs this third binding, but this
        // service's fixed ABI matches the one already proven end-to-end
        // in parallel_pixels_bench.rs, so it's required here too.
        let total_workgroups_for_stats = group_count_x as u64 * group_count_y.max(1) as u64;
        let stats_bytes = total_workgroups_for_stats * 8;
        let stats_buffer = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("cppm stats"),
            size: stats_bytes,
            usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });
        let stats_staging = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("cppm stats staging"),
            size: stats_bytes,
            usage: wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST,
            mapped_at_creation: false,
        });

        let pipeline = self.device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
            label: Some("pixel_compute_service pipeline"),
            layout: None,
            module: &shader,
            entry_point: "main",
            compilation_options: Default::default(),
        });
        let bind_group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("bind group"),
            layout: &pipeline.get_bind_group_layout(0),
            entries: &[
                wgpu::BindGroupEntry { binding: 0, resource: buffer.as_entire_binding() },
                wgpu::BindGroupEntry { binding: 1, resource: params_buffer.as_entire_binding() },
                wgpu::BindGroupEntry { binding: 2, resource: stats_buffer.as_entire_binding() },
            ],
        });

        let mut encoder = self.device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());
        {
            let mut pass = encoder.begin_compute_pass(&wgpu::ComputePassDescriptor::default());
            pass.set_pipeline(&pipeline);
            pass.set_bind_group(0, &bind_group, &[]);
            pass.dispatch_workgroups(group_count_x, group_count_y.max(1), 1);
        }
        encoder.copy_buffer_to_buffer(&buffer, 0, &staging, 0, byte_len);
        encoder.copy_buffer_to_buffer(&stats_buffer, 0, &stats_staging, 0, stats_bytes);
        self.queue.submit(Some(encoder.finish()));

        let slice = staging.slice(..);
        slice.map_async(wgpu::MapMode::Read, |r| r.unwrap());
        let stats_slice = stats_staging.slice(..);
        stats_slice.map_async(wgpu::MapMode::Read, |r| r.unwrap());
        self.device.poll(wgpu::Maintain::Wait);
        let result: Vec<u8> = slice.get_mapped_range().to_vec();
        let stats: Vec<[u32; 2]> = bytemuck::cast_slice(&stats_slice.get_mapped_range()).to_vec();
        let total_work: f64 = stats.iter().map(|s| s[0] as f64).sum();
        let lockstep_upper_bound: f64 = stats.iter().map(|s| s[1] as f64).sum::<f64>() * 256.0;
        let simt_efficiency = if lockstep_upper_bound > 0.0 { total_work / lockstep_upper_bound } else { 0.0 };

        // Pad to a square, same convention as the encode side used for
        // shader/input (see spirv_from_pixels.rs) - the result is exactly
        // `n` elements, which usually isn't a perfect square pixel count,
        // so the output PNG needs padding too. The caller trims back to
        // `n` using the `elements` field in the response, the same way it
        // already trims the shader/input PNGs using explicit lengths.
        let side = (n as f64).sqrt().ceil() as u32;
        let mut padded = vec![0u8; (side * side * 4) as usize];
        padded[..result.len()].copy_from_slice(&result);
        image::save_buffer(output_png, &padded, side.max(1), side.max(1), image::ColorType::Rgba8)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
        let _ = (iw, ih); // input dims only mattered for reading, not writing output

        Ok((n, simt_efficiency))
    }
}

fn handle_client(stream: UnixStream, gpu: &GpuContext) {
    let mut reader = BufReader::new(stream.try_clone().expect("clone stream"));
    let mut writer = stream;
    let mut line = String::new();
    loop {
        line.clear();
        match reader.read_line(&mut line) {
            Ok(0) => return, // client closed
            Ok(_) => {}
            Err(_) => return,
        }
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let resp = match serde_json::from_str::<Request>(trimmed) {
            Ok(Request::Ping) => Response::ok(),
            Ok(Request::RunKernel { shader_png, shader_len, input_png, input_len, output_png }) => {
                let start = Instant::now();
                match gpu.run_kernel(&shader_png, shader_len, &input_png, input_len, &output_png) {
                    Ok((n, efficiency)) => Response {
                        status: "ok".into(),
                        message: None,
                        elements: Some(n),
                        elapsed_ms: Some(start.elapsed().as_secs_f64() * 1000.0),
                        simt_efficiency: Some(efficiency),
                    },
                    Err(e) => Response::err(e.to_string()),
                }
            }
            Err(e) => Response::err(format!("bad request: {e}")),
        };
        let mut out = serde_json::to_string(&resp).unwrap();
        out.push('\n');
        if writer.write_all(out.as_bytes()).is_err() {
            return;
        }
    }
}

fn main() {
    let gpu = GpuContext::new();
    let _ = std::fs::remove_file(SOCKET_PATH);
    let listener = UnixListener::bind(SOCKET_PATH).expect("bind unix socket");
    eprintln!("[pixel_compute_service] listening on {SOCKET_PATH}");
    for stream in listener.incoming() {
        match stream {
            Ok(s) => handle_client(s, &gpu),
            Err(e) => eprintln!("[pixel_compute_service] accept error: {e}"),
        }
    }
}
