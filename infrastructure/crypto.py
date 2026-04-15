"""Primitivas crypto de Fase 2: ECDH + HKDF + Fernet.

Implementa derivación por sesión usando `SECP384R1`, HKDF SHA-256 con salida
de 32 bytes y adaptación `base64.urlsafe_b64encode` para llaves compatibles con
Fernet.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class CryptoProvider:
    """Proveedor de operaciones criptográficas para sesión segura runtime."""

    def generate_ecdh_keypair(self) -> tuple[str, object]:
        """Genera keypair efímero ECDH sobre curva SECP384R1."""
        private_key = ec.generate_private_key(ec.SECP384R1())
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return public_key.decode("utf-8"), private_key

    def derive_fernet_key(self, private_key: object, remote_public_pem: str) -> bytes:
        """Deriva llave Fernet compartida desde privada local y pública remota."""
        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise ValueError("private_key debe ser una EllipticCurvePrivateKey válida")

        try:
            remote_key = serialization.load_pem_public_key(
                remote_public_pem.encode("utf-8")
            )
        except Exception as exc:
            raise ValueError("remote_public_pem inválida") from exc

        if not isinstance(remote_key, ec.EllipticCurvePublicKey):
            raise ValueError("remote_public_pem no representa una clave EC válida")

        if not isinstance(remote_key.curve, ec.SECP384R1):
            raise ValueError("La clave remota debe usar SECP384R1")

        shared_secret = private_key.exchange(ec.ECDH(), remote_key)
        hkdf_bytes = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"phase2-fernet-transport",
        ).derive(shared_secret)
        return base64.urlsafe_b64encode(hkdf_bytes)

    def encrypt(self, fernet_key: bytes, plaintext: str) -> str:
        """Cifra texto UTF-8 con Fernet."""
        token = Fernet(fernet_key).encrypt(plaintext.encode("utf-8"))
        return token.decode("utf-8")

    def decrypt(self, fernet_key: bytes, ciphertext: str) -> str:
        """Descifra token Fernet y retorna texto UTF-8."""
        try:
            raw = Fernet(fernet_key).decrypt(ciphertext.encode("utf-8"))
        except InvalidToken as exc:
            raise ValueError("ciphertext inválido para la key de sesión") from exc
        return raw.decode("utf-8")

    def fingerprint_public_key(self, public_pem: str) -> str:
        """Retorna fingerprint SHA-256 hex de la clave pública PEM."""
        digest = hashlib.sha256(public_pem.encode("utf-8")).hexdigest()
        return digest
