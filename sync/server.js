const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const path = require('path');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

app.use(express.static(path.join(__dirname, 'public')));
// Serve the RTS containers
app.use('/rts', express.static(path.join(__dirname, '../systems/glyph_os')));

wss.on('connection', (ws) => {
    console.log('[pxOS] Visual Shell connected.');

    ws.on('message', (message) => {
        try {
            const data = JSON.parse(message);
            console.log('[pxOS] Received:', data);
            
            if (data.type === 'sys_call') {
                console.log(`[pxOS] Executing SYS_CALL ${data.id} - Patch-and-Copy Visual VCC`);
                // Bounce back the render state
                ws.send(JSON.stringify({
                    type: 'render_update',
                    status: 'success'
                }));
            }
        } catch (e) {
            console.error('[pxOS] Message error:', e);
        }
    });

    ws.send(JSON.stringify({
        type: 'init',
        message: 'pxOS Substrate Active - Pixels Move Pixels'
    }));
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
    console.log(`[pxOS] Substrate Server running at http://localhost:${PORT}`);
});
