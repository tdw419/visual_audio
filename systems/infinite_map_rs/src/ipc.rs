use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::sync::mpsc::{channel, Receiver, Sender};
use std::thread;
use crate::overlay::Annotation;

pub const SOCKET_PATH: &str = "/tmp/spatial_compositor.sock";

#[derive(Serialize, Deserialize, Debug)]
#[serde(tag = "action")]
pub enum IpcRequest {
    #[serde(rename = "spawn_node")]
    SpawnNode {
        id: String,
        x: f32,
        y: f32,
        cmd: Option<String>,
    },
    #[serde(rename = "read_node")]
    ReadNode { id: String },
    #[serde(rename = "spawn_image_node")]
    SpawnImageNode { id: String, x: f32, y: f32, path: String },
    #[serde(rename = "write_node")]
    WriteNode { id: String, data: String },
    #[serde(rename = "close_node")]
    CloseNode { id: String },
    #[serde(rename = "list_nodes")]
    ListNodes,
    #[serde(rename = "focus_node")]
    FocusNode { id: String, zoom: Option<f32> },
    #[serde(rename = "pan_camera")]
    PanCamera { x: f32, y: f32, zoom: Option<f32> },
    #[serde(rename = "set_annotations")]
    SetAnnotations { items: Vec<Annotation> },
    #[serde(rename = "layout_nodes")]
    LayoutNodes { mode: String },
    #[serde(rename = "update_markdown")]
    UpdateMarkdownNode { id: String, x: f32, y: f32, source: String },
}

#[derive(Serialize, Deserialize, Debug)]
pub struct IpcResponse {
    pub status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub lines: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nodes: Option<Vec<String>>,
}

pub enum IpcMessage {
    Request(IpcRequest, Sender<IpcResponse>),
}

pub struct IpcServer {
    pub rx: Receiver<IpcMessage>,
}

impl IpcServer {
    pub fn start() -> std::io::Result<Self> {
        let _ = std::fs::remove_file(SOCKET_PATH);
        let listener = UnixListener::bind(SOCKET_PATH)?;
        let (tx, rx) = channel::<IpcMessage>();

        thread::spawn(move || {
            for stream in listener.incoming() {
                if let Ok(stream) = stream {
                    let tx = tx.clone();
                    thread::spawn(move || handle_client(stream, tx));
                }
            }
        });

        Ok(Self { rx })
    }
}

fn handle_client(mut stream: UnixStream, tx: Sender<IpcMessage>) {
    let reader = BufReader::new(stream.try_clone().unwrap());
    for line in reader.lines() {
        if let Ok(line_str) = line {
            if let Ok(req) = serde_json::from_str::<IpcRequest>(&line_str) {
                let (resp_tx, resp_rx) = channel::<IpcResponse>();
                if tx.send(IpcMessage::Request(req, resp_tx)).is_ok() {
                    if let Ok(resp) = resp_rx.recv() {
                        let mut resp_str = serde_json::to_string(&resp).unwrap();
                        resp_str.push('\n');
                        let _ = stream.write_all(resp_str.as_bytes());
                    }
                }
            }
        }
    }
}
