"""Controlador de aplicacion (orquestador puro).

Responsabilidad:
- coordinar servicios de dominio,
- construir y validar mensajes de chat,
- devolver respuestas uniformes para adaptadores (CLI/websocket).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.interfaces import (
    ClockPort,
    CryptoProviderPort,
    InMemoryNotificationBus,
    SystemClock,
)
from app.protocol import ProtocolValidationError, make_error, validate_message
from app.services.key_exchange_service import KeyExchangeService
from app.services.user_service import SessionUserService


class AppController:
    """Orquesta flujos de registro, key exchange y envio de mensaje."""

    def __init__(
        self,
        crypto_provider: CryptoProviderPort | None = None,
        clock: ClockPort | None = None,
        key_exchange_service: KeyExchangeService | None = None,
    ) -> None:
        self._clock = clock or SystemClock()
        self._notifications_bus = InMemoryNotificationBus()
        self._crypto = crypto_provider

        self._key_exchange = key_exchange_service or KeyExchangeService(
            timeout_seconds=5,
            clock=self._clock,
        )
        self._user_service = SessionUserService(
            key_exchange_service=self._key_exchange,
            clock=self._clock,
        )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def register(self, raw_message: dict[str, Any]) -> dict[str, Any]:
        """Procesa registro de usuario desde mensaje REGISTER."""
        valid, error_or_message = self._validate_or_error(raw_message)
        if not valid:
            return self._fail(error_or_message)

        message = error_or_message
        ok, error = self._user_service.register(message["from"])
        if not ok:
            return self._fail(error or self._internal_error("REGISTER"))

        return self._ok({"event": "REGISTERED", "username": message["from"]})

    def handshake_init(
        self, raw_message: dict[str, Any], now_seconds: int | None = None
    ) -> dict[str, Any]:
        """Procesa inicio de key exchange desde HANDSHAKE_INIT."""
        current_seconds = self._resolve_now_seconds(now_seconds)

        valid, error_or_message = self._validate_or_error(raw_message)
        if not valid:
            return self._fail(error_or_message)

        message = error_or_message
        if not self._user_service.is_user_active(message["from"]):
            return self._fail(
                make_error(
                    code="401_NOT_REGISTERED",
                    message="No se pudo completar la operación solicitada.",
                    to=message["from"],
                    details={"operation": "HANDSHAKE_INIT"},
                    retriable=False,
                )
            )
        if not self._user_service.is_user_active(message["to"]):
            return self._fail(
                make_error(
                    code="404_USER_OFFLINE",
                    message="No se pudo completar la operación solicitada.",
                    to=message["from"],
                    details={"operation": "HANDSHAKE_INIT"},
                    retriable=True,
                )
            )

        ok, error = self._key_exchange.start_handshake(
            message["from"], message["to"], current_seconds
        )
        if not ok:
            return self._fail(error or self._internal_error("HANDSHAKE_INIT"))

        return self._ok(
            {
                "event": "HANDSHAKE_STARTED",
                "from": message["from"],
                "to": message["to"],
                "state": self._key_exchange.channel_state(
                    message["from"], message["to"]
                ),
            }
        )

    def send_message(
        self, raw_message: dict[str, Any], now_seconds: int | None = None
    ) -> dict[str, Any]:
        """Procesa envio de MESSAGE validando canal y participantes."""
        current_seconds = self._resolve_now_seconds(now_seconds)

        ok, error, handshake_started = self._validate_outgoing_with_handshake(
            raw_message, current_seconds
        )
        if not ok:
            final_error = error or self._internal_error("MESSAGE")
            self._publish_notification(final_error)
            response = self._fail(final_error)
            if handshake_started:
                response["data"] = {
                    "event": "HANDSHAKE_STARTED",
                    "from": raw_message.get("from"),
                    "to": raw_message.get("to"),
                    "state": self._key_exchange.channel_state(
                        raw_message.get("from", ""), raw_message.get("to", "")
                    ),
                }
            return response

        return self._ok(
            {
                "event": "MESSAGE_ACCEPTED",
                "from": raw_message["from"],
                "to": raw_message["to"],
                "payload": raw_message["payload"],
            }
        )

    def send_text_message(
        self,
        sender: str,
        target: str,
        text: str,
        now_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Construye y valida mensaje de texto de conversacion (flujo CLI/app)."""
        current_seconds = self._resolve_now_seconds(now_seconds)

        ok_build, message, error = self._build_message_from_text(sender, target, text)
        if not ok_build:
            return self._fail(error or self._internal_error("MESSAGE"))

        if message is None:
            return self._fail(self._internal_error("MESSAGE"))

        return self.send_message(message, current_seconds)

    def disconnect(self, username: str) -> dict[str, Any]:
        """Cierra sesion de usuario y actualiza presencia."""
        self._user_service.disconnect(username)
        return self._ok({"event": "DISCONNECTED", "username": username})

    def list_users(self) -> dict[str, Any]:
        """Retorna usuarios en runtime con username + estado."""
        return self._ok({"users": self._user_service.list_users()})

    def pull_notifications(self, username: str) -> dict[str, Any]:
        """Retorna y limpia notificaciones push dirigidas para un usuario."""
        items = self._notifications_bus.pull_for_user(username)
        return self._ok({"notifications": items})

    def create_handshake_offer(
        self, user_a: str, user_b: str, now_seconds: int | None = None
    ) -> dict[str, Any]:
        """Crea frame HANDSHAKE_INIT con clave efímera local para transporte real."""
        current_seconds = self._resolve_now_seconds(now_seconds)

        current_state = self._key_exchange.channel_state(user_a, user_b)
        if current_state == "ACTIVE":
            return self._ok(
                {
                    "event": "HANDSHAKE_COMPLETED",
                    "from": user_a,
                    "to": user_b,
                    "state": current_state,
                    "frame": None,
                }
            )

        if (
            current_state == "ESTABLISHING"
            and self._key_exchange.has_pending_private_key(user_a, user_b)
        ):
            return self._ok(
                {
                    "event": "HANDSHAKE_STARTED",
                    "from": user_a,
                    "to": user_b,
                    "state": current_state,
                    "frame": None,
                }
            )

        if not self._user_service.is_user_active(user_a):
            return self._fail(
                make_error(
                    code="401_NOT_REGISTERED",
                    message="No se pudo completar la operación solicitada.",
                    to=user_a,
                    details={"operation": "HANDSHAKE_INIT"},
                    retriable=False,
                )
            )
        if not self._user_service.is_user_active(user_b):
            return self._fail(
                make_error(
                    code="404_USER_OFFLINE",
                    message="No se pudo completar la operación solicitada.",
                    to=user_a,
                    details={"operation": "HANDSHAKE_INIT"},
                    retriable=True,
                )
            )

        if self._crypto is None:
            return self._fail(self._internal_error("HANDSHAKE_INIT"))

        public_key, private_key = self._crypto.generate_ecdh_keypair()
        self._key_exchange.set_pending_private_key(user_a, user_b, private_key)

        frame = {
            "message_id": str(uuid4()),
            "timestamp": self._now_iso(),
            "type": "HANDSHAKE_INIT",
            "from": user_a,
            "to": user_b,
            "payload": {
                "username": user_a,
                "public_key": public_key,
                "nonce": uuid4().hex,
                "reason": "ON_DEMAND",
            },
        }

        started = self.handshake_init(frame, current_seconds)
        if not started["ok"]:
            return started

        return self._ok(
            {
                "event": "HANDSHAKE_STARTED",
                "from": user_a,
                "to": user_b,
                "state": self._key_exchange.channel_state(user_a, user_b),
                "frame": frame,
            }
        )

    def process_handshake_frame(
        self, raw_message: dict[str, Any], now_seconds: int | None = None
    ) -> dict[str, Any]:
        """Procesa frame HANDSHAKE_INIT remoto y activa canal cifrado."""
        current_seconds = self._resolve_now_seconds(now_seconds)
        valid, error_or_message = self._validate_or_error(raw_message)
        if not valid:
            return self._fail(error_or_message)

        message = error_or_message
        if message["type"] != "HANDSHAKE_INIT":
            return self._fail(
                make_error(
                    code="400_INVALID_TYPE",
                    message="No se pudo completar la operación solicitada.",
                    to=message.get("to"),
                    details={"operation": "HANDSHAKE_INIT"},
                    retriable=False,
                )
            )

        sender = message["from"]
        target = message["to"]

        current_state = self._key_exchange.channel_state(sender, target)
        if (
            current_state == "ACTIVE"
            and self._key_exchange.get_session_key(sender, target) is not None
        ):
            return self._ok(
                {
                    "event": "HANDSHAKE_COMPLETED",
                    "from": sender,
                    "to": target,
                    "state": current_state,
                    "frame": None,
                }
            )

        if not self._user_service.is_user_active(target):
            return self._fail(
                make_error(
                    code="401_NOT_REGISTERED",
                    message="No se pudo completar la operación solicitada.",
                    to=target,
                    details={"operation": "HANDSHAKE_INIT"},
                    retriable=False,
                )
            )

        if self._crypto is None:
            return self._fail(self._internal_error("HANDSHAKE_INIT"))

        remote_public = message["payload"]["public_key"]
        local_private = self._key_exchange.pop_pending_private_key(sender, target)
        response_frame: dict[str, Any] | None = None

        try:
            if local_private is None:
                local_public, local_private = self._crypto.generate_ecdh_keypair()
                session_key = self._crypto.derive_fernet_key(
                    local_private, remote_public
                )
                response_frame = {
                    "message_id": str(uuid4()),
                    "timestamp": self._now_iso(),
                    "type": "HANDSHAKE_INIT",
                    "from": target,
                    "to": sender,
                    "payload": {
                        "username": target,
                        "public_key": local_public,
                        "nonce": uuid4().hex,
                        "reason": "ON_DEMAND",
                    },
                }
            else:
                session_key = self._crypto.derive_fernet_key(
                    local_private, remote_public
                )
        except ValueError:
            return self._fail(
                make_error(
                    code="400_INVALID_PAYLOAD",
                    message="No se pudo completar la operación solicitada.",
                    to=target,
                    details={"operation": "HANDSHAKE_INIT"},
                    retriable=False,
                )
            )

        remote_fp = self._crypto.fingerprint_public_key(remote_public)
        self._key_exchange.activate_secure_channel(
            sender, target, key=session_key, fp=remote_fp, now=current_seconds
        )
        self._publish_fingerprint_warning(target, sender)

        return self._ok(
            {
                "event": "HANDSHAKE_COMPLETED",
                "from": sender,
                "to": target,
                "state": self._key_exchange.channel_state(sender, target),
                "frame": response_frame,
            }
        )

    def receive_message(
        self, raw_message: dict[str, Any], now_seconds: int | None = None
    ) -> dict[str, Any]:
        """Valida replay y descifra MESSAGE entrante para CLI."""
        current_seconds = self._resolve_now_seconds(now_seconds)
        ok, plaintext, error = self._decrypt_incoming_message(
            raw_message, current_seconds
        )
        if not ok:
            return self._fail(error or self._internal_error("MESSAGE"))

        return self._ok(
            {
                "event": "MESSAGE_RECEIVED",
                "from": raw_message["from"],
                "to": raw_message["to"],
                "plaintext": plaintext,
            }
        )

    def get_channel_state(self, user_a: str, user_b: str) -> dict[str, Any]:
        """Retorna estado actual del canal para un par de usuarios."""
        return self._ok(
            {
                "from": user_a,
                "to": user_b,
                "state": self._key_exchange.channel_state(user_a, user_b),
            }
        )

    # ------------------------------------------------------------------ #
    # Message construction and validation (absorbed from ChatService)     #
    # ------------------------------------------------------------------ #

    def _build_message_from_text(
        self, sender: str, target: str, text: str
    ) -> tuple[bool, dict[str, Any] | None, dict[str, Any] | None]:
        """Construye MESSAGE de protocolo desde texto plano."""
        text_normalized = text.strip()
        if not text_normalized:
            return (
                False,
                None,
                make_error(
                    code="400_INVALID_PAYLOAD",
                    message="No se pudo completar la operación solicitada.",
                    to=sender,
                    details={"operation": "MESSAGE"},
                    retriable=False,
                ),
            )

        if sender == target:
            return (
                False,
                None,
                make_error(
                    code="400_INVALID_TO",
                    message="No se pudo completar la operación solicitada.",
                    to=sender,
                    details={"operation": "MESSAGE"},
                    retriable=False,
                ),
            )

        ciphertext = text_normalized
        session_key = self._key_exchange.get_session_key(sender, target)
        if session_key is not None and self._crypto is not None:
            ciphertext = self._crypto.encrypt(session_key, text_normalized)

        message: dict[str, Any] = {
            "message_id": str(uuid4()),
            "timestamp": self._now_iso(),
            "type": "MESSAGE",
            "from": sender,
            "to": target,
            "payload": {
                "ciphertext": ciphertext,
                "encoding": "base64url",
                "algorithm": "FERNET",
                "nonce": uuid4().hex,
                "sent_at": self._now_iso(),
            },
        }

        try:
            validate_message(message)
        except ProtocolValidationError:
            return (
                False,
                None,
                make_error(
                    code="400_INVALID_PAYLOAD",
                    message="No se pudo completar la operación solicitada.",
                    to=sender,
                    details={"operation": "MESSAGE"},
                    retriable=False,
                ),
            )

        return True, message, None

    def _validate_outgoing_with_handshake(
        self, message: dict[str, Any], now_seconds: int
    ) -> tuple[bool, dict[str, Any] | None, bool]:
        """Valida envio e inicia handshake on-demand si falta canal."""
        validated, error = self._validate_message_and_participants(message)
        if error is not None or validated is None:
            return False, error, False

        sender = validated["from"]
        target = validated["to"]

        if self._key_exchange.channel_state(sender, target) != "ACTIVE":
            started, start_error = self._key_exchange.ensure_handshake_started(
                sender, target, now_seconds
            )
            if start_error is not None:
                return False, start_error, False

            return (
                False,
                make_error(
                    code="403_SECURE_CHANNEL_REQUIRED",
                    message="No se pudo completar la operación solicitada.",
                    to=sender,
                    details={
                        "operation": "MESSAGE",
                        "handshake_started": bool(started),
                    },
                    retriable=True,
                ),
                bool(started),
            )

        return True, None, False

    def _validate_message_and_participants(
        self, message: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Valida estructura MESSAGE y estado de participantes."""
        try:
            validated = validate_message(message)
        except ProtocolValidationError as exc:
            return (
                None,
                make_error(
                    code=exc.code,
                    message="No se pudo completar la operación solicitada.",
                    to=message.get("from"),
                    details={"operation": "MESSAGE"},
                    retriable=False,
                ),
            )

        sender = validated["from"]
        target = validated["to"]

        if not self._user_service.is_user_active(sender):
            return (
                None,
                make_error(
                    code="401_NOT_REGISTERED",
                    message="No se pudo completar la operación solicitada.",
                    to=sender,
                    details={"operation": "MESSAGE"},
                    retriable=False,
                ),
            )

        if not self._user_service.is_user_active(target):
            return (
                None,
                make_error(
                    code="404_USER_OFFLINE",
                    message="No se pudo completar la operación solicitada.",
                    to=sender,
                    details={"operation": "MESSAGE"},
                    retriable=True,
                ),
            )

        return validated, None

    def _decrypt_incoming_message(
        self, message: dict[str, Any], now_seconds: int
    ) -> tuple[bool, str | None, dict[str, Any] | None]:
        """Valida replay y descifra ciphertext de un MESSAGE entrante."""
        validated, error = self._validate_message_and_participants(message)
        if error is not None or validated is None:
            return False, None, error

        sender = validated["from"]
        target = validated["to"]
        payload = validated["payload"]

        replay_ok, replay_error = self._key_exchange.validate_replay(
            sender,
            target,
            nonce=payload["nonce"],
            sent_at_iso=payload["sent_at"],
            now=now_seconds,
        )
        if not replay_ok:
            return False, None, replay_error

        session_key = self._key_exchange.get_session_key(sender, target)
        if session_key is None or self._crypto is None:
            return (
                False,
                None,
                make_error(
                    code="403_SECURE_CHANNEL_REQUIRED",
                    message="No se pudo completar la operación solicitada.",
                    to=target,
                    details={"operation": "MESSAGE"},
                    retriable=True,
                ),
            )

        try:
            plaintext = self._crypto.decrypt(session_key, payload["ciphertext"])
        except ValueError:
            return (
                False,
                None,
                make_error(
                    code="400_INVALID_PAYLOAD",
                    message="No se pudo completar la operación solicitada.",
                    to=target,
                    details={"operation": "MESSAGE"},
                    retriable=False,
                ),
            )

        return True, plaintext, None

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _validate_or_error(
        self, raw_message: dict[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        try:
            return True, validate_message(raw_message)
        except ProtocolValidationError as exc:
            return (
                False,
                make_error(
                    code=exc.code,
                    message="No se pudo completar la operación solicitada.",
                    to=raw_message.get("from"),
                    details={"operation": raw_message.get("type", "UNKNOWN")},
                    retriable=False,
                ),
            )

    def _ok(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "data": data}

    def _fail(self, error: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "error": error}

    def _internal_error(self, operation: str) -> dict[str, Any]:
        return make_error(
            code="500_INTERNAL_ERROR",
            message="No se pudo completar la operación solicitada.",
            details={"operation": operation},
            retriable=False,
        )

    def _publish_notification(self, error: dict[str, Any]) -> None:
        target = error.get("to")
        if not isinstance(target, str):
            return
        self._notifications_bus.publish_to_user(target, error)

    def _publish_fingerprint_warning(self, local_user: str, remote_user: str) -> None:
        warning = self._key_exchange.consume_fingerprint_warning(
            remote_user, local_user
        )
        if warning is None:
            return
        self._notifications_bus.publish_to_user(
            local_user,
            make_error(
                code="409_REMOTE_KEY_CHANGED",
                message="No se pudo completar la operación solicitada.",
                to=local_user,
                details={
                    "operation": "HANDSHAKE_INIT",
                    "event": warning["event"],
                    "previous_fingerprint": warning["previous_fingerprint"],
                    "current_fingerprint": warning["current_fingerprint"],
                },
                retriable=True,
            ),
        )

    def _resolve_now_seconds(self, now_seconds: int | None) -> int:
        if now_seconds is not None:
            return now_seconds
        return self._clock.now_seconds()

    def _now_iso(self) -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
