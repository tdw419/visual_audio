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

            if (data.type === 'sys_call') {
                console.log(`[pxOS] Executing SYS_CALL ${data.id} - Patch-and-Copy Visual VCC`);
                // Bounce back the render state
                ws.send(JSON.stringify({
                    type: 'render_update',
                    status: 'success'
                }));
            } else if (data.type === 'tile_frame') {
                // Relay a live tile frame (e.g. from tools/qemu_frame_server.py)
                // to every connected browser client except the producer.
                console.log(`[pxOS] Relaying live frame for tile_id ${data.tile_id} (${data.png_b64.length} b64 bytes)`);
                wss.clients.forEach((client) => {
                    if (client !== ws && client.readyState === WebSocket.OPEN) {
                        client.send(JSON.stringify(data));
                    }
                });
            } else {
                console.log('[pxOS] Received:', data);
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
