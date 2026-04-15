"""Cliente WebSocket mínimo para transporte de frames JSON."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from websockets.asyncio.client import connect
from websockets.asyncio.client import ClientConnection


class WebSocketClient:
    """Adaptador mínimo de transporte: connect/send/receive/close."""

    def __init__(self) -> None:
        self._connection: ClientConnection | None = None

    async def connect(self, url: str, username: str) -> None:
        separator = "&" if "?" in url else "?"
        connection_url = f"{url}{separator}username={quote(username)}"
        self._connection = await connect(connection_url)

    async def send(self, frame: dict[str, Any]) -> None:
        connection = self._require_connection()
        await connection.send(json.dumps(frame))

    async def receive(self) -> dict[str, Any]:
        connection = self._require_connection()
        raw = await connection.recv()
        if not isinstance(raw, str):
            raise RuntimeError("Solo se admiten frames de texto JSON")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise RuntimeError("Frame JSON inválido: se esperaba objeto")
        return data

    async def close(self) -> None:
        if self._connection is None:
            return
        await self._connection.close()
        self._connection = None

    def _require_connection(self) -> ClientConnection:
        if self._connection is None:
            raise RuntimeError("WebSocket no conectado")
        return self._connection
