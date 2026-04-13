"""Contrato del protocolo y utilidades de validacion.

Este modulo centraliza la validacion de mensajes. Provee:
- validacion de mensajes entrantes,
- errores de validacion estandarizados,
- construccion de mensajes ERROR estructurados.
"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4
import re


USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
ALLOWED_TYPES = {"REGISTER", "HANDSHAKE_INIT", "MESSAGE", "ERROR"}

ROOT_FIELDS = {"message_id", "timestamp", "type", "from", "to", "payload"}
ROOT_REQUIRED = {"message_id", "timestamp", "type", "from", "payload"}

ERROR_CODES = {
    "400_BAD_FORMAT",
    "400_MISSING_FIELD",
    "400_INVALID_FIELD_TYPE",
    "400_INVALID_TYPE",
    "400_INVALID_TO",
    "400_INVALID_PAYLOAD",
    "400_TIMESTAMP_OUT_OF_WINDOW",
    "401_NOT_REGISTERED",
    "403_SECURE_CHANNEL_REQUIRED",
    "404_USER_OFFLINE",
    "409_USERNAME_TAKEN",
    "500_INTERNAL_ERROR",
    "503_ROUTING_UNAVAILABLE",
    "504_KEY_EXCHANGE_TIMEOUT",
}


@dataclass
class ProtocolValidationError(Exception):
    """Se lanza cuando un mensaje viola el contrato del protocolo.

    Atributos:
        code: Codigo de error del protocolo (por ejemplo, ``400_INVALID_PAYLOAD``).
        message: Descripcion legible del error.
        details: Datos estructurados opcionales para diagnostico.
    """

    code: str
    message: str
    details: dict[str, Any] | None = None


def make_error(
    code: str,
    message: str,
    to: str | None = None,
    details: dict[str, Any] | None = None,
    retriable: bool = False,
) -> dict[str, Any]:
    """Construye un mensaje ``ERROR`` estructurado del protocolo.

    Args:
        code: Codigo de error del catalogo.
        message: Descripcion legible del error.
        to: Username destino opcional. Si falta, el error es local/contextual.
        details: Metadatos opcionales del contexto del error.
        retriable: Indica si la operacion puede reintentarse.

    Returns:
        Diccionario de mensaje de protocolo con ``type == 'ERROR'``.
    """

    msg: dict[str, Any] = {
        "message_id": str(uuid4()),
        "timestamp": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "type": "ERROR",
        "from": "server",
        "payload": {
            "code": code,
            "message": message,
            "details": details or {},
            "retriable": retriable,
        },
    }
    if to is not None:
        msg["to"] = to
    return msg


def validate_message(message: dict[str, Any]) -> dict[str, Any]:
    """Valida un mensaje de protocolo y retorna una copia segura.

    La validacion incluye:
    - forma raiz y campos requeridos,
    - tipos y formatos comunes,
    - restricciones de payload por tipo,
    - reglas semanticas por tipo de mensaje.

    Args:
        message: Diccionario crudo a validar.

    Returns:
        Copia profunda del mensaje validado.

    Raises:
        ProtocolValidationError: Si se viola una regla estructural o semantica.
    """

    if not isinstance(message, dict):
        _fail("400_BAD_FORMAT", "El mensaje debe ser un objeto")

    msg = deepcopy(message)

    extra = set(msg.keys()) - ROOT_FIELDS
    if extra:
        _fail("400_BAD_FORMAT", f"Campos raiz no permitidos: {sorted(extra)}")

    missing = ROOT_REQUIRED - set(msg.keys())
    if missing:
        _fail("400_MISSING_FIELD", f"Faltan campos requeridos: {sorted(missing)}")

    _require_type(msg, "message_id", str)
    _require_type(msg, "timestamp", str)
    _require_type(msg, "type", str)
    _require_type(msg, "from", str)
    _require_type(msg, "payload", dict)

    _validate_uuid(msg["message_id"])
    _validate_timestamp(msg["timestamp"])

    if msg["type"] not in ALLOWED_TYPES:
        _fail("400_INVALID_TYPE", "Tipo de mensaje no soportado")

    if msg["type"] == "REGISTER":
        _validate_register(msg)
    elif msg["type"] == "HANDSHAKE_INIT":
        _validate_handshake_init(msg)
    elif msg["type"] == "MESSAGE":
        _validate_message_type(msg)
    elif msg["type"] == "ERROR":
        _validate_error_type(msg)

    return msg


def _validate_register(msg: dict[str, Any]) -> None:
    """Valida restricciones del mensaje ``REGISTER``."""

    _validate_username(msg["from"], field="from", error_code="400_INVALID_PAYLOAD")

    payload = msg["payload"]
    _strict_payload(payload, required={"username", "public_key"}, optional=set())
    _validate_username(
        payload["username"], field="payload.username", error_code="400_INVALID_PAYLOAD"
    )
    if payload["username"] != msg["from"]:
        _fail(
            "400_INVALID_PAYLOAD",
            "En REGISTER, payload.username debe coincidir con from",
        )

    _require_non_empty_str(payload, "public_key", "400_INVALID_PAYLOAD")

    if "to" in msg:
        _require_type(msg, "to", str)
        if msg["to"] != "server":
            _fail("400_INVALID_TO", "En REGISTER, to debe ser 'server' cuando se envia")


def _validate_handshake_init(msg: dict[str, Any]) -> None:
    """Valida restricciones del mensaje ``HANDSHAKE_INIT``."""

    if "to" not in msg:
        _fail("400_MISSING_FIELD", "HANDSHAKE_INIT requiere el campo to")

    _validate_username(msg["from"], field="from", error_code="400_INVALID_PAYLOAD")
    _validate_username(msg["to"], field="to", error_code="400_INVALID_TO")

    payload = msg["payload"]
    _strict_payload(
        payload,
        required={"username", "public_key", "nonce", "reason"},
        optional=set(),
    )

    _validate_username(
        payload["username"], field="payload.username", error_code="400_INVALID_PAYLOAD"
    )
    if payload["username"] != msg["from"]:
        _fail(
            "400_INVALID_PAYLOAD",
            "En HANDSHAKE_INIT, payload.username debe coincidir con from",
        )

    _require_non_empty_str(payload, "public_key", "400_INVALID_PAYLOAD")
    _require_non_empty_str(payload, "nonce", "400_INVALID_PAYLOAD")
    _require_non_empty_str(payload, "reason", "400_INVALID_PAYLOAD")

    if payload["reason"] not in {"ON_DEMAND", "ROTATION", "RETRY"}:
        _fail("400_INVALID_PAYLOAD", "Valor invalido en HANDSHAKE_INIT payload.reason")


def _validate_message_type(msg: dict[str, Any]) -> None:
    """Valida restricciones del mensaje ``MESSAGE``."""

    if "to" not in msg:
        _fail("400_MISSING_FIELD", "MESSAGE requiere el campo to")

    _validate_username(msg["from"], field="from", error_code="400_INVALID_PAYLOAD")
    _validate_username(msg["to"], field="to", error_code="400_INVALID_TO")
    if msg["from"] == msg["to"]:
        _fail("400_INVALID_TO", "En MESSAGE, from y to deben ser distintos")

    payload = msg["payload"]
    _strict_payload(
        payload,
        required={"ciphertext", "encoding", "algorithm"},
        optional=set(),
    )

    _require_non_empty_str(payload, "ciphertext", "400_INVALID_PAYLOAD")
    _require_non_empty_str(payload, "encoding", "400_INVALID_PAYLOAD")
    _require_non_empty_str(payload, "algorithm", "400_INVALID_PAYLOAD")

    if payload["encoding"] not in {"base64", "base64url"}:
        _fail("400_INVALID_PAYLOAD", "Valor invalido en MESSAGE payload.encoding")
    if payload["algorithm"] != "FERNET":
        _fail("400_INVALID_PAYLOAD", "Valor invalido en MESSAGE payload.algorithm")


def _validate_error_type(msg: dict[str, Any]) -> None:
    """Valida restricciones del mensaje ``ERROR``."""

    if msg["from"] != "server":
        _fail("400_INVALID_PAYLOAD", "En ERROR, from debe ser 'server'")

    if "to" in msg:
        _validate_username(msg["to"], field="to", error_code="400_INVALID_TO")

    payload = msg["payload"]
    _strict_payload(
        payload,
        required={"code", "message", "retriable"},
        optional={"details"},
    )

    _require_non_empty_str(payload, "code", "400_INVALID_PAYLOAD")
    _require_non_empty_str(payload, "message", "400_INVALID_PAYLOAD")
    if payload["code"] not in ERROR_CODES:
        _fail("400_INVALID_PAYLOAD", "Codigo desconocido en ERROR payload.code")
    if not isinstance(payload["retriable"], bool):
        _fail("400_INVALID_FIELD_TYPE", "payload.retriable debe ser booleano")
    if "details" in payload and not isinstance(payload["details"], dict):
        _fail("400_INVALID_FIELD_TYPE", "payload.details debe ser un objeto")


def _strict_payload(
    payload: dict[str, Any], required: set[str], optional: set[str]
) -> None:
    """Aplica payload estricto (requeridos + opcionales, sin extras)."""

    extra = set(payload.keys()) - (required | optional)
    if extra:
        _fail("400_BAD_FORMAT", f"Campos de payload no permitidos: {sorted(extra)}")

    missing = required - set(payload.keys())
    if missing:
        _fail(
            "400_MISSING_FIELD",
            f"Faltan campos requeridos en payload: {sorted(missing)}",
        )


def _validate_uuid(value: str) -> None:
    """Valida el formato UUID en string."""

    try:
        UUID(value)
    except Exception:
        _fail("400_INVALID_FIELD_TYPE", "message_id debe ser un UUID valido")


def _validate_timestamp(value: str) -> None:
    """Valida timestamp ISO-8601 (soporta sufijo ``Z``)."""

    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(normalized)
    except Exception:
        _fail("400_INVALID_FIELD_TYPE", "timestamp debe cumplir formato ISO-8601")


def _validate_username(value: Any, field: str, error_code: str) -> None:
    """Valida formato de username para un campo del protocolo."""

    if not isinstance(value, str):
        _fail("400_INVALID_FIELD_TYPE", f"{field} debe ser string")
    if not USERNAME_RE.fullmatch(value):
        _fail(error_code, f"{field} tiene formato de username invalido")


def _require_type(container: dict[str, Any], key: str, expected: type) -> None:
    """Verifica que una clave tenga el tipo de Python esperado."""

    if not isinstance(container.get(key), expected):
        _fail("400_INVALID_FIELD_TYPE", f"{key} tiene tipo invalido")


def _require_non_empty_str(
    container: dict[str, Any], key: str, error_code: str
) -> None:
    """Verifica que una clave contenga string no vacio."""

    value = container.get(key)
    if not isinstance(value, str):
        _fail("400_INVALID_FIELD_TYPE", f"{key} debe ser string")
    if not value:
        _fail(error_code, f"{key} no puede estar vacio")


def _fail(code: str, message: str) -> None:
    """Lanza un error de validacion estandarizado del protocolo."""

    raise ProtocolValidationError(code=code, message=message)
