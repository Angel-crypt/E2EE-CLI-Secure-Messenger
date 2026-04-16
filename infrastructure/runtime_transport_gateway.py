"""Bridge síncrono para transporte WebSocket async desde CLI."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Any
from urllib.parse import quote

from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect


class RuntimeTransportGateway:
    """Mantiene una conexión WS en thread dedicado para la CLI síncrona."""

    def __init__(self, relay_url: str) -> None:
        self._relay_url = relay_url
        self._incoming: queue.Queue[dict[str, Any]] = queue.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connection: ClientConnection | None = None
        self._thread: threading.Thread | None = None
        self._connected = threading.Event()
        self._stop_event: asyncio.Event | None = None
        self._error: Exception | None = None

    def connect(self, username: str, timeout: float = 5.0) -> None:
        if self._thread is not None:
            return

        self._thread = threading.Thread(
            target=self._thread_main,
            args=(username,),
            name=f"relay-client-{username}",
            daemon=True,
        )
        self._thread.start()

        if not self._connected.wait(timeout=timeout):
            raise RuntimeError("No se pudo establecer conexión con el relay")
        if self._error is not None:
            raise RuntimeError("Fallo conexión con relay") from self._error

    def send_frame(self, frame: dict[str, Any], timeout: float = 5.0) -> None:
        loop = self._loop
        connection = self._connection
        if loop is None or connection is None:
            raise RuntimeError("Relay no conectado")

        future = asyncio.run_coroutine_threadsafe(
            connection.send(json.dumps(frame)), loop
        )
        future.result(timeout=timeout)

    def poll_incoming(self, max_items: int = 20) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for _ in range(max_items):
            try:
                items.append(self._incoming.get_nowait())
            except queue.Empty:
                break
        return items

    def close(self, timeout: float = 5.0) -> None:
        if self._thread is None:
            return

        loop = self._loop
        stop_event = self._stop_event
        if loop is not None and stop_event is not None:
            loop.call_soon_threadsafe(stop_event.set)

        self._thread.join(timeout=timeout)
        self._thread = None
        self._loop = None
        self._connection = None
        self._stop_event = None
        self._connected.clear()

    def _thread_main(self, username: str) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run(username))
        except Exception as exc:  # pragma: no cover - fallback defensivo
            self._error = exc
            self._connected.set()
        finally:
            loop.close()

    async def _run(self, username: str) -> None:
        self._stop_event = asyncio.Event()
        separator = "&" if "?" in self._relay_url else "?"
        url = f"{self._relay_url}{separator}username={quote(username)}"
        async with connect(url) as connection:
            self._connection = connection
            self._connected.set()

            recv_task = asyncio.create_task(self._recv_loop(connection))
            assert self._stop_event is not None
            await self._stop_event.wait()
            recv_task.cancel()
            try:
                await recv_task
            except asyncio.CancelledError:
                pass

    async def _recv_loop(self, connection: ClientConnection) -> None:
        while True:
            try:
                raw = await connection.recv()
            except Exception:
                return
            if not isinstance(raw, str):
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                self._incoming.put(data)
