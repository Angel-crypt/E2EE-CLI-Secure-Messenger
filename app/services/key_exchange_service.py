"""Servicio de control de intercambio de claves (fase sin crypto real).

Implementa reglas operativas:
- inicio de handshake bajo demanda,
- estados de canal (NONE, ESTABLISHING, ACTIVE, INVALID),
- timeout de handshake,
- invalidacion de canales por reconexion/desconexion,
- bloqueo de MESSAGE si no existe canal ACTIVE.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.interfaces import ClockPort, SystemClock
from app.protocol import TIMESTAMP_TOLERANCE_SECONDS, make_error


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
    ) -> None:
        """Inicializa almacenamiento runtime de canales.

        Args:
            timeout_seconds: Ventana maxima para handshake en estado ESTABLISHING.
            clock: Puerto de reloj para validaciones temporales.
        """
        self._timeout_seconds = timeout_seconds
        self._clock = clock or SystemClock()
        self._channels: dict[str, dict] = {}
        self._session_keys: dict[str, bytes] = {}
        self._remote_fingerprints: dict[str, str] = {}
        self._seen_nonces: dict[str, set[str]] = {}
        self._fingerprint_warnings: dict[str, dict[str, str]] = {}
        self._pending_private_keys: dict[str, object] = {}

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
        channel = self._channels.get(pair)

        if channel and channel["state"] in {"ACTIVE", "ESTABLISHING"}:
            return True, None

        self._channels[pair] = {
            "pair_key": pair,
            "peer_a": user_a,
            "peer_b": user_b,
            "state": "ESTABLISHING",
            "started_at": current_seconds,
            "established_at": None,
            "invalidated_at": None,
        }
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
        if self.channel_state(user_a, user_b) in {"ACTIVE", "ESTABLISHING"}:
            return False, None
        ok, error = self.start_handshake(user_a, user_b, now_seconds)
        if not ok:
            return False, error
        return True, None

    def activate_secure_channel(
        self, user_a: str, user_b: str, key: bytes, fp: str, now: int
    ) -> None:
        """Activa canal seguro con key de sesión y fingerprint remota runtime."""
        pair = self._pair_key(user_a, user_b)
        existing = self._channels.get(pair)
        peer_a = existing["peer_a"] if existing else user_a
        peer_b = existing["peer_b"] if existing else user_b

        previous_fp = self._remote_fingerprints.get(pair)
        if previous_fp is not None and previous_fp != fp:
            self._fingerprint_warnings[pair] = {
                "event": "REMOTE_KEY_CHANGED",
                "previous_fingerprint": previous_fp,
                "current_fingerprint": fp,
            }

        self._session_keys[pair] = key
        self._remote_fingerprints[pair] = fp
        self._seen_nonces[pair] = set()

        self._channels[pair] = {
            "pair_key": pair,
            "peer_a": peer_a,
            "peer_b": peer_b,
            "state": "ACTIVE",
            "started_at": existing["started_at"] if existing else now,
            "established_at": now,
            "invalidated_at": None,
        }

    def validate_replay(
        self, user_a: str, user_b: str, nonce: str, sent_at_iso: str, now: int
    ) -> tuple[bool, dict[str, Any] | None]:
        """Valida timestamp+nonce antes de aceptar payload cifrado."""
        pair = self._pair_key(user_a, user_b)
        if self.channel_state(user_a, user_b) != "ACTIVE":
            return (
                False,
                make_error(
                    code="403_SECURE_CHANNEL_REQUIRED",
                    message="No se pudo completar la operación solicitada.",
                    to=user_a,
                    details={"operation": "MESSAGE"},
                    retriable=True,
                ),
            )

        sent_at_seconds = self._parse_iso_timestamp_seconds(sent_at_iso)
        if sent_at_seconds is None:
            return (
                False,
                make_error(
                    code="400_REPLAY_TIMESTAMP_INVALID",
                    message="No se pudo completar la operación solicitada.",
                    to=user_a,
                    details={"operation": "MESSAGE"},
                    retriable=False,
                ),
            )

        if abs(now - sent_at_seconds) > TIMESTAMP_TOLERANCE_SECONDS:
            return (
                False,
                make_error(
                    code="400_REPLAY_TIMESTAMP_INVALID",
                    message="No se pudo completar la operación solicitada.",
                    to=user_a,
                    details={"operation": "MESSAGE"},
                    retriable=False,
                ),
            )

        seen = self._seen_nonces.setdefault(pair, set())
        if nonce in seen:
            return (
                False,
                make_error(
                    code="409_REPLAY_DETECTED",
                    message="No se pudo completar la operación solicitada.",
                    to=user_a,
                    details={"operation": "MESSAGE"},
                    retriable=False,
                ),
            )
        seen.add(nonce)
        return True, None

    def get_session_key(self, user_a: str, user_b: str) -> bytes | None:
        """Retorna key Fernet runtime para el par si existe."""
        return self._session_keys.get(self._pair_key(user_a, user_b))

    def set_pending_private_key(
        self, user_a: str, user_b: str, private_key: object
    ) -> None:
        """Guarda clave privada efímera local para completar handshake."""
        self._pending_private_keys[self._pair_key(user_a, user_b)] = private_key

    def pop_pending_private_key(self, user_a: str, user_b: str) -> object | None:
        """Consume clave privada efímera local del handshake en curso."""
        return self._pending_private_keys.pop(self._pair_key(user_a, user_b), None)

    def has_pending_private_key(self, user_a: str, user_b: str) -> bool:
        """Indica si existe clave privada efímera pendiente para el par."""
        return self._pair_key(user_a, user_b) in self._pending_private_keys

    def consume_fingerprint_warning(
        self, user_a: str, user_b: str
    ) -> dict[str, str] | None:
        """Consume warning de cambio de fingerprint si existe."""
        pair = self._pair_key(user_a, user_b)
        return self._fingerprint_warnings.pop(pair, None)

    def invalidate_user_channels(
        self, username: str, now_seconds: int | None = None
    ) -> None:
        """Invalida todos los canales donde participa el usuario.

        Args:
            username: Usuario cuyos canales deben invalidarse.
            now_seconds: Tiempo actual en segundos.
        """
        current_seconds = self._resolve_now_seconds(now_seconds)
        for pair, channel in self._channels.items():
            if username in {channel["peer_a"], channel["peer_b"]}:
                channel["state"] = "INVALID"
                channel["invalidated_at"] = current_seconds
                self._session_keys.pop(pair, None)
                self._seen_nonces.pop(pair, None)
                self._pending_private_keys.pop(pair, None)

    def channel_state(self, user_a: str, user_b: str) -> str:
        """Obtiene estado actual del canal para un par.

        Args:
            user_a: Usuario participante A.
            user_b: Usuario participante B.

        Returns:
            Estado del canal: ``NONE``, ``ESTABLISHING``, ``ACTIVE`` o ``INVALID``.
        """
        channel = self._channels.get(self._pair_key(user_a, user_b))
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

    def _parse_iso_timestamp_seconds(self, timestamp: str) -> int | None:
        normalized = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
