"""Servicio de sesion y usuarios.

Implementa reglas simples:
- una sola sesion activa por username,
- presencia basada en estado real de conexion,
- invalidacion de canales por reconexion/desconexion,
- errores estructurados compatibles con el protocolo.

La validacion de canal seguro se delega a `KeyExchangeService`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.interfaces import ClockPort, SystemClock
from app.protocol import make_error
from app.services.key_exchange_service import KeyExchangeService


class SessionUserService:
    """Gestiona sesiones activas y presencia de usuarios.

    Nota:
        Es un servicio en memoria (runtime actual), sin persistencia.
    """

    def __init__(
        self,
        key_exchange_service: KeyExchangeService | None = None,
        clock: ClockPort | None = None,
    ) -> None:
        """Inicializa almacenamiento runtime de usuarios y dependencia de canales.

        Args:
            key_exchange_service: Servicio de key exchange a utilizar.
                Si no se provee, se crea uno por defecto (timeout 5s).
            clock: Puerto de reloj para timestamps y consistencia temporal.
        """
        self._clock = clock or SystemClock()
        self._key_exchange = key_exchange_service or KeyExchangeService(
            timeout_seconds=5, clock=self._clock
        )
        self._active_sessions: dict[str, dict[str, Any]] = {}
        self._known_users: set[str] = set()

    def register(self, username: str) -> tuple[bool, dict[str, Any] | None]:
        """Intenta registrar una sesion para un usuario.

        Args:
            username: Identidad solicitada por el cliente.

        Returns:
            Tupla ``(ok, error)``:
            - ``ok=True`` y ``error=None`` si el registro fue aceptado.
            - ``ok=False`` y ``error`` estructurado si ya hay sesion activa.
        """
        if username in self._active_sessions:
            return (
                False,
                make_error(
                    code="409_USERNAME_TAKEN",
                    message="No se pudo completar la operación solicitada.",
                    to=username,
                    details={"operation": "REGISTER"},
                    retriable=False,
                ),
            )

        now_iso = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        now_seconds = self._clock.now_seconds()

        self._active_sessions[username] = {
            "session_id": str(uuid4()),
            "connected_at": now_iso,
            "connected_at_epoch": now_seconds,
        }
        self._known_users.add(username)
        return True, None

    def disconnect(self, username: str) -> None:
        """Cierra la sesion activa de un usuario y marca presencia offline.

        Args:
            username: Usuario a desconectar.
        """
        if username not in self._active_sessions:
            return

        now_seconds = self._clock.now_seconds()
        del self._active_sessions[username]
        self._key_exchange.invalidate_user_channels(username, now_seconds)

    def list_users(self) -> list[dict[str, str]]:
        """Lista usuarios conocidos con formato ``username + state``.

        Returns:
            Lista ordenada alfabeticamente por ``username``.
        """
        return [
            {
                "username": u,
                "state": "online" if u in self._active_sessions else "offline",
            }
            for u in sorted(self._known_users)
        ]

    def is_user_active(self, username: str) -> bool:
        """Indica si un usuario tiene sesion activa.

        Args:
            username: Usuario a consultar.

        Returns:
            ``True`` si existe sesion ``ACTIVE`` para el usuario.
        """
        return username in self._active_sessions
