from __future__ import annotations

import pytest
from websockets.asyncio.server import serve

from infrastructure.websocket_client import WebSocketClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_websocket_client_connect_send_receive_close_roundtrip():
    async def echo_handler(ws):
        async for raw in ws:
            await ws.send(raw)

    async with serve(echo_handler, "127.0.0.1", 0) as server:
        socket = server.sockets[0]
        host, port = socket.getsockname()[:2]
        url = f"ws://{host}:{port}"

        client = WebSocketClient()
        await client.connect(url, "alice")

        frame = {
            "message_id": "4c0e20a4-4a69-40a3-a3e2-25bf1f2b40f8",
            "timestamp": "2026-04-15T21:00:00Z",
            "type": "MESSAGE",
            "from": "alice",
            "to": "bob",
            "payload": {
                "ciphertext": "abc123",
                "encoding": "base64url",
                "algorithm": "FERNET",
                "nonce": "nonce-1",
                "sent_at": "2026-04-15T21:00:00Z",
            },
        }

        await client.send(frame)
        received = await client.receive()

        assert received == frame

        await client.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_websocket_client_rejects_send_when_not_connected():
    client = WebSocketClient()

    with pytest.raises(RuntimeError):
        await client.send({"type": "MESSAGE", "payload": {}})
