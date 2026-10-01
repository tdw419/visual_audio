import re
with open('src/main.rs', 'r') as f:
    data = f.read()

handler = """
                                IpcRequest::UpdateImageNode { id, path } => {
                                    if let Ok(img) = image::open(&path) {
                                        let img_rgba = img.to_rgba8();
                                        let width = img_rgba.width();
                                        let height = img_rgba.height();
                                        if let Some(node) = nodes.iter_mut().find(|n| n.id == id) {
                                            node.content.update_image(img_rgba.into_raw(), width, height);
                                        }
                                        let _ = responder.send(IpcResponse {
                                            status: "ok".into(),
                                            message: Some(format!("Updated image node {}", id)),
                                            lines: None,
                                            nodes: None,
                                        });
                                    } else {
                                        let _ = responder.send(IpcResponse {
                                            status: "error".into(),
                                            message: Some(format!("Failed to load image from path {}", path)),
                                            lines: None,
                                            nodes: None,
                                        });
                                    }
                                }
"""

data = data.replace(
    "IpcRequest::SpawnImageNode { id, x, y, path } => {", 
    handler + "\n                                IpcRequest::SpawnImageNode { id, x, y, path } => {"
)
with open('src/main.rs', 'w') as f:
    f.write(data)
