import { Application, Graphics, Text, Container } from 'https://pixijs.download/v8.0.0/pixi.mjs';

const OPCODES = {
    0x01: 'LDI',
    0x02: 'MOV',
    0x03: 'ADD',
    0x04: 'SUB',
    0x05: 'JL',
    0x06: 'JZ',
    0x07: 'JMP',
    0x08: 'SYS_READ',
    0x09: 'SYS_CALL',
    0x0A: 'LOAD',
    0x0B: 'STORE',
    0x0C: 'OR',
    0x0D: 'AND',
    0x0E: 'SHL',
    0xFF: 'HALT'
};

const GRID_SIZE = 256;
const SPECIAL_OFFSET = 16;

class PixelFormulaEngine {
    constructor() {
        this.regs = new Int32Array(256);
        this.memory = new Uint8Array(GRID_SIZE * GRID_SIZE);
        this.pc = 0;
        this.running = false;
        this.ws = new WebSocket(`ws://${location.host}`);
        
        this.mouseX = 0;
        this.mouseY = 0;
        this.mouseDown = 0;
        
        this.windowGraphics = null;
        this.app = null;
    }

    async init() {
        this.app = new Application();
        const container = document.getElementById('canvas-container');
        await this.app.init({ resizeTo: container, backgroundAlpha: 0 }); // transparent to show gradient
        container.appendChild(this.app.canvas);

        this.windowGraphics = new Graphics();
        this.app.stage.addChild(this.windowGraphics);

        // Load the RTS PNG container
        await this.loadRTSContainer('/rts/window_coordinator.rts.png');
        
        this.ws.onmessage = (msg) => {
            const data = JSON.parse(msg.data);
            if(data.type === 'init') {
                document.getElementById('status').innerText = 'Connected: ' + data.message;
            }
        };

        // Setup mouse listeners for the Visual Shell (mapped to the reality-gui container)
        const realityGui = document.getElementById('reality-gui');
        realityGui.addEventListener('mousemove', (e) => {
            const rect = realityGui.getBoundingClientRect();
            this.mouseX = e.clientX - rect.left;
            this.mouseY = e.clientY - rect.top;
        });
        realityGui.addEventListener('mousedown', () => { this.mouseDown = 1; });
        realityGui.addEventListener('mouseup', () => { this.mouseDown = 0; });

        this.running = true;
        this.app.ticker.add(() => this.step());
    }

    d2xy(n, d) {
        let x = 0, y = 0;
        let s = 1;
        let temp = d;
        while (s < n) {
            let rx = 1 & (temp / 2);
            let ry = 1 & (temp ^ rx);
            if (ry === 0) {
                if (rx === 1) {
                    x = s - 1 - x;
                    y = s - 1 - y;
                }
                let t = x; x = y; y = t;
            }
            x += s * rx;
            y += s * ry;
            temp = Math.floor(temp / 4);
            s *= 2;
        }
        return [x, y];
    }

    async loadRTSContainer(url) {
        const img = new Image();
        img.src = url;
        await new Promise(r => img.onload = r);
        
        const canvas = document.createElement('canvas');
        canvas.width = GRID_SIZE;
        canvas.height = GRID_SIZE;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0);
        
        const imgData = ctx.getImageData(0, 0, GRID_SIZE, GRID_SIZE).data;
        
        // Decode Hilbert Curve pixels to bytes using SPECIAL_OFFSET
        for(let d=0; d<this.memory.length; d++) {
            const [x, y] = this.d2xy(GRID_SIZE, d);
            const idx = (y * GRID_SIZE + x) * 4;
            const r = imgData[idx];
            const g = imgData[idx+1];
            const b = imgData[idx+2];
            
            // Reconstruct id
            const id_val = (r << 16) | (g << 8) | b;
            if(id_val >= SPECIAL_OFFSET) {
                this.memory[d] = id_val - SPECIAL_OFFSET;
            } else {
                this.memory[d] = 0; // padding/empty
            }
        }
        
        console.log("RTS Container loaded into memory");
    }

    step() {
        if(!this.running) return;
        
        // Map system input registers directly before executing
        this.regs[10] = this.mouseX;
        this.regs[11] = this.mouseY;
        this.regs[12] = this.mouseDown;
        
        // Execute a batch of instructions to simulate 60fps frame time
        // Since we jump back to :event_loop, we just run until we hit a SYS_CALL or end of logic
        let executed = 0;
        let traceLog = [];
        
        while(executed < 1000) {
            const currentPc = this.pc;
            const op = this.memory[this.pc];
            if(op === 0) break; // Reached end of program or padding
            
            if(op === OPCODES.HALT) {
                this.running = false;
                break;
            }
            
            let instStr = `${currentPc.toString(16).padStart(4, '0')}: `;
            
            switch(op) {
                case 0x01: // LDI reg, val
                    instStr += `LDI r${this.memory[this.pc+1]}, ${this.memory[this.pc+2]}`;
                    this.regs[this.memory[this.pc+1]] = this.memory[this.pc+2];
                    this.pc += 3;
                    break;
                case 0x02: // MOV dest, src
                    instStr += `MOV r${this.memory[this.pc+1]}, r${this.memory[this.pc+2]}`;
                    this.regs[this.memory[this.pc+1]] = this.regs[this.memory[this.pc+2]];
                    this.pc += 3;
                    break;
                case 0x03: // ADD dest, src1, src2
                    instStr += `ADD r${this.memory[this.pc+1]}, r${this.memory[this.pc+2]}, r${this.memory[this.pc+3]}`;
                    this.regs[this.memory[this.pc+1]] = this.regs[this.memory[this.pc+2]] + this.regs[this.memory[this.pc+3]];
                    this.pc += 4;
                    break;
                case 0x04: // SUB dest, src1, src2
                    instStr += `SUB r${this.memory[this.pc+1]}, r${this.memory[this.pc+2]}, r${this.memory[this.pc+3]}`;
                    this.regs[this.memory[this.pc+1]] = this.regs[this.memory[this.pc+2]] - this.regs[this.memory[this.pc+3]];
                    this.pc += 4;
                    break;
                case 0x05: // JL src1, src2, target
                    instStr += `JL r${this.memory[this.pc+1]}, ${this.memory[this.pc+2]}, :${this.memory[this.pc+3].toString(16)}`;
                    if(this.regs[this.memory[this.pc+1]] < this.memory[this.pc+2]) {
                        this.pc = this.memory[this.pc+3];
                    } else {
                        this.pc += 4;
                    }
                    break;
                case 0x06: // JZ src, target
                    instStr += `JZ r${this.memory[this.pc+1]}, :${this.memory[this.pc+2].toString(16)}`;
                    if(this.regs[this.memory[this.pc+1]] === 0) {
                        this.pc = this.memory[this.pc+2];
                    } else {
                        this.pc += 3;
                    }
                    break;
                case 0x07: // JMP target
                    instStr += `JMP :${this.memory[this.pc+1].toString(16)}`;
                    this.pc = this.memory[this.pc+1];
                    break;
                case 0x08: // SYS_READ
                    instStr += `SYS_READ r${this.memory[this.pc+1]}, 0x${this.memory[this.pc+2].toString(16)}`;
                    this.pc += 3;
                    break;
                case 0x09: // SYS_CALL syscall_id
                    const syscall_id = this.memory[this.pc+1];
                    instStr += `SYS_CALL 0x${syscall_id.toString(16)}`;
                    if(syscall_id === 0x01) {
                        // Visual VCC Patch-and-Copy render
                        this.renderWindow();
                        this.ws.send(JSON.stringify({ type: 'sys_call', id: 0x01 }));
                    } else if(syscall_id === 0x02) {
                        this.renderTitle();
                    } else if(syscall_id === 0x03) {
                        this.renderCloseButton();
                    } else if(syscall_id === 0xFF) {
                        // Close Application / Self Destruct Visual
                        this.windowGraphics.clear();
                        if (this.titleText) this.titleText.visible = false;
                        this.running = false;
                        document.getElementById('status').innerText = 'Application Closed via 0xFF';
                    }
                    this.pc += 2;
                    // Break the execution loop to allow the browser to paint
                    executed = 1000;
                    break;
                case 0x0A: // LOAD dest, addr
                    instStr += `LOAD r${this.memory[this.pc+1]}, [r${this.memory[this.pc+2]}]`;
                    this.regs[this.memory[this.pc+1]] = this.memory[this.regs[this.memory[this.pc+2]]];
                    this.pc += 3;
                    break;
                case 0x0B: // STORE addr, src
                    instStr += `STORE [r${this.memory[this.pc+1]}], r${this.memory[this.pc+2]}`;
                    this.memory[this.regs[this.memory[this.pc+1]]] = this.regs[this.memory[this.pc+2]];
                    this.pc += 3;
                    break;
                case 0x0C: // OR dest, src1, src2
                    instStr += `OR r${this.memory[this.pc+1]}, r${this.memory[this.pc+2]}, r${this.memory[this.pc+3]}`;
                    this.regs[this.memory[this.pc+1]] = this.regs[this.memory[this.pc+2]] | this.regs[this.memory[this.pc+3]];
                    this.pc += 4;
                    break;
                case 0x0D: // AND dest, src1, src2
                    instStr += `AND r${this.memory[this.pc+1]}, r${this.memory[this.pc+2]}, r${this.memory[this.pc+3]}`;
                    this.regs[this.memory[this.pc+1]] = this.regs[this.memory[this.pc+2]] & this.regs[this.memory[this.pc+3]];
                    this.pc += 4;
                    break;
                case 0x0E: // SHL dest, src, shift_val
                    instStr += `SHL r${this.memory[this.pc+1]}, r${this.memory[this.pc+2]}, ${this.memory[this.pc+3]}`;
                    this.regs[this.memory[this.pc+1]] = this.regs[this.memory[this.pc+2]] << this.memory[this.pc+3];
                    this.pc += 4;
                    break;
                default:
                    instStr += `UNKNOWN 0x${op.toString(16)}`;
                    console.error("Unknown opcode:", op);
                    this.running = false;
                    executed = 1000;
                    break;
            }
            
            traceLog.push(instStr);
            executed++;
        }
        
        // Output trace log to the UI (limit to last 15 lines)
        if (traceLog.length > 0) {
            const logEl = document.getElementById('glyph-log');
            let history = logEl.innerText.split('\n');
            history = history.concat(traceLog);
            if (history.length > 25) {
                history = history.slice(history.length - 25);
            }
            logEl.innerText = history.join('\n');
        }
        
        // Update UI layer
        document.getElementById('registers').innerHTML = `
            R0 (X): ${this.regs[0]} <br/>
            R1 (Y): ${this.regs[1]} <br/>
            R2 (W): ${this.regs[2]} <br/>
            R3 (H): ${this.regs[3]} <br/>
            R4 (Drag): ${this.regs[4]} <br/>
            Mouse: ${this.mouseX}, ${this.mouseY} [${this.mouseDown}]
        `;
    }
    
    renderWindow() {
        // Registers 0-3 define the window bounds
        const x = this.regs[0];
        const y = this.regs[1];
        const w = this.regs[2];
        const h = this.regs[3];
        const isDragging = this.regs[4];
        
        this.windowGraphics.clear();
        
        // Glassmorphic border glow
        this.windowGraphics.setStrokeStyle({
            width: 2, 
            color: isDragging ? 0x00ffff : 0x00ff00, 
            alpha: 0.8
        });
        
        // Semi-transparent background
        this.windowGraphics.beginFill(0x1a1a2e, 0.8);
        this.windowGraphics.drawRoundedRect(x, y, w, h, 8);
        this.windowGraphics.endFill();
    }
    
    renderTitle() {
        if (!this.titleText) {
            this.titleText = new Text({
                text: 'Geometry OS Native [v0.1]', 
                style: { fontFamily: 'monospace', fontSize: 16, fill: 0x00ff00 }
            });
            this.app.stage.addChild(this.titleText);
        }
        this.titleText.visible = true;
        this.titleText.x = this.regs[0] + 15;
        this.titleText.y = this.regs[1] + 15;
    }
    
    renderCloseButton() {
        const x = this.regs[0];
        const y = this.regs[1];
        const w = this.regs[2];
        
        // Draw [ X ] box
        this.windowGraphics.setStrokeStyle({ width: 1, color: 0xff0055 });
        this.windowGraphics.beginFill(0x330011, 0.8);
        this.windowGraphics.drawRect(x + w - 30, y + 10, 20, 20);
        this.windowGraphics.endFill();
        
        // Draw the X
        this.windowGraphics.setStrokeStyle({ width: 2, color: 0xff0055 });
        this.windowGraphics.moveTo(x + w - 26, y + 14);
        this.windowGraphics.lineTo(x + w - 14, y + 26);
        this.windowGraphics.moveTo(x + w - 14, y + 14);
        this.windowGraphics.lineTo(x + w - 26, y + 26);
    }
}

const engine = new PixelFormulaEngine();
engine.init();
