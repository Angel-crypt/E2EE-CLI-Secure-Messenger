"""Servicio de control de intercambio de claves (fase sin crypto real).

Implementa reglas operativas:
- inicio de handshake bajo demanda,
- estados de canal (NONE, ESTABLISHING, ACTIVE, INVALID),
- timeout de handshake,
- invalidacion de canales por reconexion/desconexion,
- bloqueo de MESSAGE si no existe canal ACTIVE.
"""

from __future__ import annotations

from typing import Any

from app.interfaces import ClockPort, SystemClock
from app.protocol import make_error
from app.repositories.in_memory_repositories import InMemoryChannelRepository


class KeyExchangeService:
    """Gestiona estado de handshake y disponibilidad de canal seguro.

    Nota:
        Este servicio no hace criptografia real. Solo modela estados de canal
        para permitir avanzar CLI y logica de aplicacion en esta fase.
    """

    def __init__(
        self,
        timeout_seconds: int = 5,
        clock: ClockPort | None = None,
        channel_repository: InMemoryChannelRepository | None = None,
    ) -> None:
        """Inicializa almacenamiento runtime de canales.

        Args:
            timeout_seconds: Ventana maxima para handshake en estado ESTABLISHING.
            clock: Puerto de reloj para validaciones temporales.
            channel_repository: Repositorio en memoria de estado de canales.
        """
        self._timeout_seconds = timeout_seconds
        self._clock = clock or SystemClock()
        self._channel_repository = channel_repository or InMemoryChannelRepository()

    def start_handshake(
        self, user_a: str, user_b: str, now_seconds: int | None = None
    ) -> tuple[bool, dict[str, Any] | None]:
        """Inicia handshake para un par si no existe canal ACTIVE.

        Args:
            user_a: Usuario origen del intercambio.
            user_b: Usuario destino del intercambio.
            now_seconds: Tiempo actual en segundos (reloj de aplicacion).

        Returns:
            Tupla ``(ok, error)``:
            - ``ok=True`` si el estado queda en ESTABLISHING o ya era ACTIVE.
            - ``error=None`` en ambos casos para mantener API simple.
        """
        current_seconds = self._resolve_now_seconds(now_seconds)

        pair = self._pair_key(user_a, user_b)
        channel = self._channel_repository.get_channel(pair)

        if channel and channel["state"] == "ACTIVE":
            return True, None

        self._channel_repository.upsert_channel(
            pair_key=pair,
            peer_a=user_a,
            peer_b=user_b,
            state="ESTABLISHING",
            started_at=current_seconds,
            established_at=None,
            invalidated_at=None,
        )
        return True, None

    def ensure_handshake_started(
        self, user_a: str, user_b: str, now_seconds: int | None = None
    ) -> tuple[bool, dict[str, Any] | None]:
        """Garantiza estado ESTABLISHING cuando no hay canal ACTIVE.

        Args:
            user_a: Usuario origen.
            user_b: Usuario destino.
            now_seconds: Tiempo actual en segundos.

        Returns:
            Tupla ``(started, error)``:
            - ``started=True`` si se inicio un nuevo handshake.
            - ``started=False`` si no fue necesario (ya ACTIVE).
            - ``error`` en caso de fallo inesperado (actualmente ninguno).
        """
        if self.channel_state(user_a, user_b) == "ACTIVE":
            return False, None
        ok, error = self.start_handshake(user_a, user_b, now_seconds)
        if not ok:
            return False, error
        return True, None

    def complete_handshake(
        self, user_a: str, user_b: str, now_seconds: int | None = None
    ) -> None:
        """Marca handshake como completado y activa el canal.

        Args:
            user_a: Usuario participante A.
            user_b: Usuario participante B.
            now_seconds: Tiempo actual en segundos.
        """
        current_seconds = self._resolve_now_seconds(now_seconds)
        pair = self._pair_key(user_a, user_b)
        existing = self._channel_repository.get_channel(pair)
        peer_a = existing["peer_a"] if existing else user_a
        peer_b = existing["peer_b"] if existing else user_b

        self._channel_repository.upsert_channel(
            pair_key=pair,
            peer_a=peer_a,
            peer_b=peer_b,
            state="ACTIVE",
            started_at=existing["started_at"] if existing else None,
            established_at=current_seconds,
            invalidated_at=None,
        )

    def can_send_message(
        self, sender: str, target: str, now_seconds: int | None = None
    ) -> tuple[bool, dict[str, Any] | None]:
        """Valida si existe canal ACTIVE para permitir MESSAGE.

        Args:
            sender: Usuario emisor.
            target: Usuario destinatario.
            now_seconds: Tiempo actual en segundos.

        Returns:
            Tupla ``(ok, error)``:
            - ``ok=True`` si el canal esta ACTIVE.
            - ``ok=False`` y `ERROR` 403 si no hay canal activo.
        """
        _ = now_seconds
        if self.channel_state(sender, target) != "ACTIVE":
            return (
                False,
                make_error(
                    code="403_SECURE_CHANNEL_REQUIRED",
                    message="No se pudo completar la operación solicitada.",
                    to=sender,
                    details={"operation": "MESSAGE"},
                    retriable=True,
                ),
            )
        return True, None

    def check_timeout(
        self, user_a: str, user_b: str, now_seconds: int | None = None
    ) -> tuple[bool, dict[str, Any] | None]:
        """Evalua timeout de handshake para un par de usuarios.

        Args:
            user_a: Usuario participante A.
            user_b: Usuario participante B.
            now_seconds: Tiempo actual en segundos.

        Returns:
            Tupla ``(timed_out, error)``:
            - ``timed_out=True`` y `ERROR` 504 si expiro handshake.
            - ``timed_out=False`` y ``None`` si no aplica timeout.
        """
        current_seconds = self._resolve_now_seconds(now_seconds)

        pair = self._pair_key(user_a, user_b)
        channel = self._channel_repository.get_channel(pair)
        if (
            not channel
            or channel["state"] != "ESTABLISHING"
            or channel["started_at"] is None
        ):
            return False, None

        if current_seconds - channel["started_at"] <= self._timeout_seconds:
            return False, None

        self._channel_repository.upsert_channel(
            pair_key=pair,
            peer_a=channel["peer_a"],
            peer_b=channel["peer_b"],
            state="INVALID",
            started_at=channel["started_at"],
            established_at=channel["established_at"],
            invalidated_at=current_seconds,
        )
        return (
            True,
            make_error(
                code="504_KEY_EXCHANGE_TIMEOUT",
                message="No se pudo completar la operación solicitada.",
                to=channel["peer_a"],
                details={"operation": "HANDSHAKE_INIT"},
                retriable=True,
            ),
        )

    def invalidate_user_channels(
        self, username: str, now_seconds: int | None = None
    ) -> None:
        """Invalida todos los canales donde participa el usuario.

        Args:
            username: Usuario cuyos canales deben invalidarse.
            now_seconds: Tiempo actual en segundos.
        """
        current_seconds = self._resolve_now_seconds(now_seconds)
        self._channel_repository.invalidate_user_channels(username, current_seconds)

    def channel_state(self, user_a: str, user_b: str) -> str:
        """Obtiene estado actual del canal para un par.

        Args:
            user_a: Usuario participante A.
            user_b: Usuario participante B.

        Returns:
            Estado del canal: ``NONE``, ``ESTABLISHING``, ``ACTIVE`` o ``INVALID``.
        """
        channel = self._channel_repository.get_channel(self._pair_key(user_a, user_b))
        if not channel:
            return "NONE"
        return str(channel["state"])

    def _pair_key(self, user_a: str, user_b: str) -> str:
        """Normaliza clave de canal como string estable para persistencia."""
        a, b = sorted([user_a, user_b])
        return f"{a}|{b}"

    def _resolve_now_seconds(self, now_seconds: int | None) -> int:
        if now_seconds is not None:
            return now_seconds
        return self._clock.now_seconds()
