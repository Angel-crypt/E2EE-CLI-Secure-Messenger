"""Interfaces minimas de aplicacion para desacoplar adaptadores.

Estas interfaces permiten migrar a websocket/transportes reales sin refactor
transversal del dominio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


class ClockPort(Protocol):
    """Puerto de tiempo para reglas temporales y pruebas deterministas."""

    def now_seconds(self) -> int:
        """Retorna tiempo actual en segundos."""
        ...


class NotificationPort(Protocol):
    """Puerto de notificaciones dirigidas por usuario."""

    def publish_to_user(self, username: str, message: dict[str, Any]) -> None:
        """Publica mensaje dirigido para un usuario."""
        ...

    def pull_for_user(self, username: str) -> list[dict[str, Any]]:
        """Retorna y limpia mensajes dirigidos del usuario."""
        ...


class AppControllerPort(Protocol):
    """Contrato minimo para controladores de aplicacion."""

    def register(self, raw_message: dict[str, Any]) -> dict[str, Any]: ...

    def handshake_init(
        self, raw_message: dict[str, Any], now_seconds: int | None = None
    ) -> dict[str, Any]: ...

    def send_message(
        self, raw_message: dict[str, Any], now_seconds: int | None = None
    ) -> dict[str, Any]: ...

    def send_text_message(
        self,
        sender: str,
        target: str,
        text: str,
        now_seconds: int | None = None,
    ) -> dict[str, Any]: ...

    def disconnect(self, username: str) -> dict[str, Any]: ...

    def list_users(self) -> dict[str, Any]: ...

    def pull_notifications(self, username: str) -> dict[str, Any]: ...


class SystemClock(ClockPort):
    """Implementacion por defecto de reloj del sistema."""

    def now_seconds(self) -> int:
        return int(datetime.utcnow().timestamp())


@dataclass
class InMemoryNotificationBus(NotificationPort):
    """Buzon en memoria para push dirigido en fase sin red."""

    _store: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def publish_to_user(self, username: str, message: dict[str, Any]) -> None:
        self._store.setdefault(username, []).append(message)

    def pull_for_user(self, username: str) -> list[dict[str, Any]]:
        items = self._store.get(username, [])
        self._store[username] = []
        return items
