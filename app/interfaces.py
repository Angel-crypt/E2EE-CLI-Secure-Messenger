"""Interfaces minimas de aplicacion para desacoplar adaptadores.

Estas interfaces permiten migrar a websocket/transportes reales sin refactor
transversal del dominio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


class CryptoProviderPort(Protocol):
    """Puerto para primitivas crypto de sesion (Fase 2)."""

    def generate_ecdh_keypair(self) -> tuple[str, object]: ...

    def derive_fernet_key(
        self, private_key: object, remote_public_pem: str
    ) -> bytes: ...

    def encrypt(self, fernet_key: bytes, plaintext: str) -> str: ...

    def decrypt(self, fernet_key: bytes, ciphertext: str) -> str: ...

    def fingerprint_public_key(self, public_pem: str) -> str: ...


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
