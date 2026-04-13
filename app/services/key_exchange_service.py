"""Servicio de control de intercambio de claves (fase sin crypto real).

Implementa reglas operativas:
- inicio de handshake bajo demanda,
- estados de canal (NONE, ESTABLISHING, ACTIVE, INVALID),
- timeout de handshake,
- invalidacion de canales por reconexion/desconexion,
- bloqueo de MESSAGE si no existe canal ACTIVE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.protocol import make_error


@dataclass
class _ChannelData:
    """Representa el estado runtime de un canal seguro entre dos usuarios.

    Atributos:
        peer_a: Primer participante del canal.
        peer_b: Segundo participante del canal.
        state: Estado actual del canal.
        started_at: Timestamp (segundos) del inicio del handshake.
        established_at: Timestamp (segundos) de activacion del canal.
        invalidated_at: Timestamp (segundos) de invalidacion del canal.
    """

    peer_a: str
    peer_b: str
    state: str
    started_at: int | None = None
    established_at: int | None = None
    invalidated_at: int | None = None


class KeyExchangeService:
    """Gestiona estado de handshake y disponibilidad de canal seguro.

    Nota:
        Este servicio no hace criptografia real. Solo modela estados de canal
        para permitir avanzar CLI y logica de aplicacion en esta fase.
    """

    def __init__(self, timeout_seconds: int = 5) -> None:
        """Inicializa almacenamiento runtime de canales.

        Args:
            timeout_seconds: Ventana maxima para handshake en estado ESTABLISHING.
        """
        self._timeout_seconds = timeout_seconds
        self._channels: dict[frozenset[str], _ChannelData] = {}

    def start_handshake(
        self, user_a: str, user_b: str, now_seconds: int
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
        pair = self._pair(user_a, user_b)
        channel = self._channels.get(pair)

        if channel and channel.state == "ACTIVE":
            return True, None

        self._channels[pair] = _ChannelData(
            peer_a=user_a,
            peer_b=user_b,
            state="ESTABLISHING",
            started_at=now_seconds,
            established_at=None,
            invalidated_at=None,
        )
        return True, None

    def complete_handshake(self, user_a: str, user_b: str, now_seconds: int) -> None:
        """Marca handshake como completado y activa el canal.

        Args:
            user_a: Usuario participante A.
            user_b: Usuario participante B.
            now_seconds: Tiempo actual en segundos.
        """
        pair = self._pair(user_a, user_b)
        channel = self._channels.get(pair)
        if not channel:
            channel = _ChannelData(peer_a=user_a, peer_b=user_b, state="NONE")
            self._channels[pair] = channel

        channel.state = "ACTIVE"
        channel.established_at = now_seconds
        channel.invalidated_at = None

    def can_send_message(
        self, sender: str, target: str, now_seconds: int
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
        self, user_a: str, user_b: str, now_seconds: int
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
        pair = self._pair(user_a, user_b)
        channel = self._channels.get(pair)
        if not channel or channel.state != "ESTABLISHING" or channel.started_at is None:
            return False, None

        if now_seconds - channel.started_at <= self._timeout_seconds:
            return False, None

        channel.state = "INVALID"
        channel.invalidated_at = now_seconds
        return (
            True,
            make_error(
                code="504_KEY_EXCHANGE_TIMEOUT",
                message="No se pudo completar la operación solicitada.",
                to=channel.peer_a,
                details={"operation": "HANDSHAKE_INIT"},
                retriable=True,
            ),
        )

    def invalidate_user_channels(self, username: str, now_seconds: int) -> None:
        """Invalida todos los canales donde participa el usuario.

        Args:
            username: Usuario cuyos canales deben invalidarse.
            now_seconds: Tiempo actual en segundos.
        """
        for channel in self._channels.values():
            if username in {channel.peer_a, channel.peer_b}:
                channel.state = "INVALID"
                channel.invalidated_at = now_seconds

    def channel_state(self, user_a: str, user_b: str) -> str:
        """Obtiene estado actual del canal para un par.

        Args:
            user_a: Usuario participante A.
            user_b: Usuario participante B.

        Returns:
            Estado del canal: ``NONE``, ``ESTABLISHING``, ``ACTIVE`` o ``INVALID``.
        """
        channel = self._channels.get(self._pair(user_a, user_b))
        if not channel:
            return "NONE"
        return channel.state

    def _pair(self, user_a: str, user_b: str) -> frozenset[str]:
        """Normaliza clave de canal para que sea independiente del orden."""
        return frozenset({user_a, user_b})
