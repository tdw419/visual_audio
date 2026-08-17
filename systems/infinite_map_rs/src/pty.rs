use portable_pty::{native_pty_system, CommandBuilder, MasterPty, PtySize};
use std::io::{Read, Write};
use std::sync::{Arc, Mutex};
use std::thread;

pub struct TerminalSession {
    pub master: Box<dyn MasterPty + Send>,
    pub writer: Box<dyn Write + Send>,
    pub parser: Arc<Mutex<vt100::Parser>>,
}

impl TerminalSession {
    pub fn new(cols: u16, rows: u16) -> Self {
        let default_shell = std::env::var("SHELL").unwrap_or_else(|_| "/bin/bash".to_string());
        Self::new_with_command(cols, rows, &default_shell)
    }

    pub fn new_with_command(cols: u16, rows: u16, cmd: &str) -> Self {
        let pty_system = native_pty_system();
        let pair = pty_system
            .openpty(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .expect("Failed to open PTY");

        // Split the command to handle args if needed. For now just spawn the shell.
        let parts: Vec<&str> = cmd.split_whitespace().collect();
        let mut command = CommandBuilder::new(parts[0]);
        if parts.len() > 1 {
            command.args(&parts[1..]);
        }
        
        pair.slave.spawn_command(command).expect("Failed to spawn shell");

        let writer = pair.master.take_writer().expect("Failed to get PTY writer");
        let mut reader = pair.master.try_clone_reader().expect("Failed to get PTY reader");

        let parser = Arc::new(Mutex::new(vt100::Parser::new(rows, cols, 0)));
        let parser_clone = Arc::clone(&parser);

        thread::spawn(move || {
            let mut buf = [0u8; 4096];
            while let Ok(n) = reader.read(&mut buf) {
                if n == 0 {
                    break;
                }
                let mut p = parser_clone.lock().unwrap();
                p.process(&buf[..n]);
            }
        });

        Self {
            master: pair.master,
            writer,
            parser,
        }
    }

    pub fn write_input(&mut self, data: &[u8]) {
        let _ = self.writer.write_all(data);
        let _ = self.writer.flush();
    }
}
