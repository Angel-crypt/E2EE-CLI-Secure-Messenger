"""Servicio de chat (fase sin crypto real ni red).

Responsabilidades:
- validar mensajes de tipo MESSAGE,
- aplicar reglas de conversacion (no auto-envio, no texto vacio),
- estructurar payload de transporte para fase actual,
- delegar validacion de sesion/presencia/canal a servicios especializados.

El controller solo orquesta llamadas; la logica de mensaje vive aqui.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.protocol import ProtocolValidationError, make_error, validate_message
from app.services.key_exchange_service import KeyExchangeService
from app.services.user_service import SessionUserService


class ChatService:
    """Gestiona validacion y construccion de mensajes de chat.

    Nota:
        En esta fase se transforma texto plano en payload MESSAGE mock
        (sin cifrado real) para habilitar flujo de aplicacion y CLI.
    """

    def __init__(
        self,
        user_service: SessionUserService,
        key_exchange_service: KeyExchangeService,
    ) -> None:
        """Inicializa dependencias de dominio.

        Args:
            user_service: Servicio de sesion/presencia.
            key_exchange_service: Servicio de estado de canal seguro.
        """
        self._user_service = user_service
        self._key_exchange = key_exchange_service

    def build_message_from_text(
        self, sender: str, target: str, text: str
    ) -> tuple[bool, dict[str, Any] | None, dict[str, Any] | None]:
        """Construye un MESSAGE de protocolo desde texto de conversacion.

        Args:
            sender: Usuario emisor.
            target: Usuario destinatario.
            text: Texto del mensaje en claro (fase mock).

        Returns:
            Tupla ``(ok, message, error)``:
            - ``ok=True`` y ``message`` listo para enviar si todo es valido.
            - ``ok=False`` y ``error`` estructurado en caso contrario.
        """
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

        message = {
            "message_id": str(uuid4()),
            "timestamp": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "type": "MESSAGE",
            "from": sender,
            "to": target,
            "payload": {
                "ciphertext": text_normalized,
                "encoding": "base64url",
                "algorithm": "FERNET",
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

    def validate_outgoing_message(
        self, message: dict[str, Any], now_seconds: int
    ) -> tuple[bool, dict[str, Any] | None]:
        """Valida prerrequisitos de envio para un MESSAGE ya estructurado.

        Args:
            message: Mensaje de protocolo tipo MESSAGE.
            now_seconds: Tiempo actual (segundos) para validaciones temporales.

        Returns:
            Tupla ``(ok, error)``:
            - ``ok=True`` si puede enviarse.
            - ``ok=False`` con `ERROR` estructurado si falla alguna regla.
        """
        try:
            validated = validate_message(message)
        except ProtocolValidationError as exc:
            return (
                False,
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
                False,
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
                False,
                make_error(
                    code="404_USER_OFFLINE",
                    message="No se pudo completar la operación solicitada.",
                    to=sender,
                    details={"operation": "MESSAGE"},
                    retriable=True,
                ),
            )

        return self._key_exchange.can_send_message(sender, target, now_seconds)

    def validate_outgoing_message_with_handshake(
        self, message: dict[str, Any], now_seconds: int
    ) -> tuple[bool, dict[str, Any] | None, bool]:
        """Valida envio e inicia handshake on-demand si falta canal.

        Args:
            message: Mensaje de protocolo tipo MESSAGE.
            now_seconds: Tiempo actual (segundos).

        Returns:
            Tupla ``(ok, error, handshake_started)``:
            - ``ok=True`` si puede enviarse.
            - ``ok=False`` con error estructurado si no puede.
            - ``handshake_started=True`` si se inicio handshake automatico.
        """
        try:
            validated = validate_message(message)
        except ProtocolValidationError as exc:
            return (
                False,
                make_error(
                    code=exc.code,
                    message="No se pudo completar la operación solicitada.",
                    to=message.get("from"),
                    details={"operation": "MESSAGE"},
                    retriable=False,
                ),
                False,
            )

        sender = validated["from"]
        target = validated["to"]

        if not self._user_service.is_user_active(sender):
            return (
                False,
                make_error(
                    code="401_NOT_REGISTERED",
                    message="No se pudo completar la operación solicitada.",
                    to=sender,
                    details={"operation": "MESSAGE"},
                    retriable=False,
                ),
                False,
            )

        if not self._user_service.is_user_active(target):
            return (
                False,
                make_error(
                    code="404_USER_OFFLINE",
                    message="No se pudo completar la operación solicitada.",
                    to=sender,
                    details={"operation": "MESSAGE"},
                    retriable=True,
                ),
                False,
            )

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
