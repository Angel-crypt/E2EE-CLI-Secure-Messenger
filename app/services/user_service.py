"""Servicio de sesion y usuarios.

Implementa reglas simples:
- una sola sesion activa por username,
- presencia basada en estado real de conexion,
- invalidacion de canales seguros al desconectar/reconectar,
- errores estructurados compatibles con el protocolo.
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.protocol import make_error


class SessionUserService:
    """Gestiona sesiones activas, presencia y canales seguros.

    Nota:
        Es un servicio en memoria (runtime actual), sin persistencia.
    """

    def __init__(self) -> None:
        """Inicializa almacenamiento en memoria de usuarios y canales."""
        self._users: dict[str, dict[str, Any]] = {}
        self._secure_channels: set[frozenset[str]] = set()

    def register(self, username: str) -> tuple[bool, dict[str, Any] | None]:
        """Intenta registrar una sesion para un usuario.

        Args:
            username: Identidad solicitada por el cliente.

        Returns:
            Tupla ``(ok, error)``:
            - ``ok=True`` y ``error=None`` si el registro fue aceptado.
            - ``ok=False`` y ``error`` estructurado si ya hay sesion activa.
        """
        user = self._users.get(username)

        if user and user["status"] == "ACTIVE":
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

        now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        self._users[username] = {
            "session_id": str(uuid4()),
            "username": username,
            "status": "ACTIVE",
            "connected_at": now,
            "disconnected_at": None,
            "state": "online",
        }

        self._invalidate_channels_for_user(username)
        return True, None

    def disconnect(self, username: str) -> None:
        """Cierra la sesion activa de un usuario y marca presencia offline.

        Args:
            username: Usuario a desconectar.

        Returns:
            None.
        """
        user = self._users.get(username)
        if not user or user["status"] != "ACTIVE":
            return

        user["status"] = "CLOSED"
        user["state"] = "offline"
        user["disconnected_at"] = (
            datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        )
        self._invalidate_channels_for_user(username)

    def list_users(self) -> list[dict[str, str]]:
        """Lista usuarios conocidos con formato ``username + state``.

        Returns:
            Lista ordenada alfabéticamente por ``username``.
        """
        users = [
            {"username": data["username"], "state": data["state"]}
            for data in self._users.values()
        ]
        users.sort(key=lambda item: item["username"])
        return users

    def mark_secure_channel(self, user_a: str, user_b: str) -> None:
        """Marca un canal seguro activo entre dos usuarios.

        Args:
            user_a: Primer participante.
            user_b: Segundo participante.

        Returns:
            None.
        """
        self._secure_channels.add(frozenset({user_a, user_b}))

    def can_send_message(
        self, sender: str, target: str
    ) -> tuple[bool, dict[str, Any] | None]:
        """Valida si ``sender`` puede enviar `MESSAGE` a ``target``.

        Reglas verificadas:
        - sender registrado y activo,
        - target registrado y activo,
        - canal seguro activo entre ambos.

        Args:
            sender: Usuario emisor.
            target: Usuario destinatario.

        Returns:
            Tupla ``(ok, error)``:
            - ``ok=True`` si puede enviar.
            - ``ok=False`` con `ERROR` estructurado en caso contrario.
        """
        sender_data = self._users.get(sender)
        if not sender_data or sender_data["status"] != "ACTIVE":
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

        target_data = self._users.get(target)
        if not target_data or target_data["status"] != "ACTIVE":
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

        pair = frozenset({sender, target})
        if pair not in self._secure_channels:
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

    def _invalidate_channels_for_user(self, username: str) -> None:
        """Invalida todos los canales que incluyen al usuario.

        Args:
            username: Usuario cuyos canales deben cerrarse.
        """
        self._secure_channels = {
            channel for channel in self._secure_channels if username not in channel
        }
