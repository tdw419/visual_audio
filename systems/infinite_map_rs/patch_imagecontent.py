import re
with open('src/content.rs', 'r') as f:
    data = f.read()

impl_str = """    fn handle_event(&mut self, _event: NodeEvent) {}

    fn update_image(&mut self, rgba: Vec<u8>, w: u32, h: u32) {
        self.rgba_data = rgba;
        self.width = w;
        self.height = h;
        self.needs_upload = true;
    }"""

data = re.sub(r'impl NodeContent for ImageContent \{.*?fn handle_event\(&mut self, _event: NodeEvent\) \{\}', 
              lambda m: m.group(0).replace('fn handle_event(&mut self, _event: NodeEvent) {}', impl_str), 
              data, flags=re.DOTALL)

with open('src/content.rs', 'w') as f:
    f.write(data)
