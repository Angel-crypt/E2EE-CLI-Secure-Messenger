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
from app.repositories.in_memory_repositories import InMemorySessionRepository
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
        session_repository: InMemorySessionRepository | None = None,
    ) -> None:
        """Inicializa almacenamiento runtime de usuarios y dependencia de canales.

        Args:
            key_exchange_service: Servicio de key exchange a utilizar.
                Si no se provee, se crea uno por defecto (timeout 5s).
            clock: Puerto de reloj para timestamps y consistencia temporal.
            session_repository: Repositorio en memoria para sesiones.
        """
        self._clock = clock or SystemClock()
        self._key_exchange = key_exchange_service or KeyExchangeService(
            timeout_seconds=5, clock=self._clock
        )
        self._session_repository = session_repository or InMemorySessionRepository()

    def register(self, username: str) -> tuple[bool, dict[str, Any] | None]:
        """Intenta registrar una sesion para un usuario.

        Args:
            username: Identidad solicitada por el cliente.

        Returns:
            Tupla ``(ok, error)``:
            - ``ok=True`` y ``error=None`` si el registro fue aceptado.
            - ``ok=False`` y ``error`` estructurado si ya hay sesion activa.
        """
        if self._session_repository.is_user_active(username):
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

        created = self._session_repository.create_active_session(
            username=username,
            session_id=str(uuid4()),
            connected_at_iso=now_iso,
            connected_at_epoch=now_seconds,
        )
        if not created:
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

        self._key_exchange.invalidate_user_channels(username, now_seconds)
        return True, None

    def disconnect(self, username: str) -> None:
        """Cierra la sesion activa de un usuario y marca presencia offline.

        Args:
            username: Usuario a desconectar.
        """
        now_iso = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        now_seconds = self._clock.now_seconds()
        changed = self._session_repository.close_active_session(
            username=username,
            disconnected_at_iso=now_iso,
            disconnected_at_epoch=now_seconds,
        )
        if not changed:
            return

        self._key_exchange.invalidate_user_channels(username, now_seconds)

    def list_users(self) -> list[dict[str, str]]:
        """Lista usuarios conocidos con formato ``username + state``.

        Returns:
            Lista ordenada alfabeticamente por ``username``.
        """
        return self._session_repository.list_users_state()

    def is_user_active(self, username: str) -> bool:
        """Indica si un usuario tiene sesion activa.

        Args:
            username: Usuario a consultar.

        Returns:
            ``True`` si existe sesion ``ACTIVE`` para el usuario.
        """
        return self._session_repository.is_user_active(username)

    def mark_secure_channel(self, user_a: str, user_b: str) -> None:
        """Marca un canal seguro activo delegando al servicio de key exchange.

        Args:
            user_a: Primer participante.
            user_b: Segundo participante.
        """
        self._key_exchange.complete_handshake(user_a, user_b, self._clock.now_seconds())

    def can_send_message(
        self, sender: str, target: str
    ) -> tuple[bool, dict[str, Any] | None]:
        """Valida si ``sender`` puede enviar `MESSAGE` a ``target``.

        Reglas verificadas:
        - sender registrado y activo,
        - target registrado y activo,
        - canal seguro ACTIVE (delegado a KeyExchangeService).

        Args:
            sender: Usuario emisor.
            target: Usuario destinatario.

        Returns:
            Tupla ``(ok, error)``:
            - ``ok=True`` si puede enviar.
            - ``ok=False`` con `ERROR` estructurado en caso contrario.
        """
        if not self._session_repository.is_user_active(sender):
            return (
                False,
                make_error(
                    code="401_NOT_REGISTERED",
                    message="No se pudo completar la operación solicitada.",
                    to=sender,
                    details={"operation": "MESSAGE"},
                    retriable=False,
                ),
            )

        if not self._session_repository.is_user_active(target):
            return (
                False,
                make_error(
                    code="404_USER_OFFLINE",
                    message="No se pudo completar la operación solicitada.",
                    to=sender,
                    details={"operation": "MESSAGE"},
                    retriable=True,
                ),
            )

        return self._key_exchange.can_send_message(
            sender, target, self._clock.now_seconds()
        )
