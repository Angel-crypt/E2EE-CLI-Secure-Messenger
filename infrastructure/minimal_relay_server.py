"""Relay WebSocket mínimo honesto-pero-curioso para integración."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import parse_qs, urlparse

from websockets.asyncio.server import Server
from websockets.asyncio.server import ServerConnection
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class MinimalRelayServer:
    """Server relay que enruta frames por `to` sin descifrar payload."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._host = host
        self._port = port
        self._server: Server | None = None
        self._users: dict[str, ServerConnection] = {}
        self.relayed_frames: list[dict[str, Any]] = []

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("Relay no iniciado")
        socket = self._server.sockets[0]
        host, port = socket.getsockname()[:2]
        return f"ws://{host}:{port}"

    async def start(self) -> None:
        if self._server is not None:
            return
        self._server = await serve(self._handler, self._host, self._port)

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None
        self._users.clear()

    async def _handler(self, ws: ServerConnection) -> None:
        current_username = self._username_from_connection(ws)
        if current_username is not None:
            self._users[current_username] = ws
            logger.info(
                "Conectado: %s  (usuarios activos: %d)",
                current_username,
                len(self._users),
            )
        try:
            async for raw in ws:
                if not isinstance(raw, str):
                    continue
                frame = json.loads(raw)
                if not isinstance(frame, dict):
                    continue

                frame_type = frame.get("type")
                sender = frame.get("from")

                if frame_type == "REGISTER" and isinstance(sender, str):
                    self._users[sender] = ws
                    current_username = sender
                    logger.info(
                        "REGISTER  usuario=%s  (usuarios activos: %d)",
                        sender,
                        len(self._users),
                    )
                    continue

                target = frame.get("to")
                if not isinstance(target, str):
                    continue

                self.relayed_frames.append(frame)
                destination = self._users.get(target)
                if destination is None:
                    logger.warning(
                        "%-20s %s → %s  (destino no encontrado)",
                        frame_type,
                        sender,
                        target,
                    )
                    continue
                try:
                    await destination.send(json.dumps(frame))
                    logger.info("%-20s %s → %s", frame_type, sender, target)
                except ConnectionClosed:
                    self._users.pop(target, None)
                    logger.warning(
                        "%-20s %s → %s  (conexión cerrada)", frame_type, sender, target
                    )
        finally:
            if current_username is not None:
                stored = self._users.get(current_username)
                if stored is ws:
                    self._users.pop(current_username, None)
                    logger.info(
                        "Desconectado: %s  (usuarios activos: %d)",
                        current_username,
                        len(self._users),
                    )

    def _username_from_connection(self, ws: ServerConnection) -> str | None:
        request = ws.request
        if request is None:
            return None
        parsed = urlparse(request.path)
        query = parse_qs(parsed.query)
        values = query.get("username")
        if not values:
            return None
        return values[0]
