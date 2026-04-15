import pytest

from infrastructure.crypto import CryptoProvider


@pytest.mark.unit
def test_ecdh_hkdf_base64url_derivation_is_compatible_between_peers():
    provider = CryptoProvider()

    alice_public, alice_private = provider.generate_ecdh_keypair()
    bob_public, bob_private = provider.generate_ecdh_keypair()

    alice_key = provider.derive_fernet_key(alice_private, bob_public)
    bob_key = provider.derive_fernet_key(bob_private, alice_public)

    assert alice_key == bob_key
    assert isinstance(alice_key, bytes)
    assert len(alice_key) == 44


@pytest.mark.unit
def test_derive_fernet_key_rejects_invalid_remote_public_key():
    provider = CryptoProvider()
    _, private_key = provider.generate_ecdh_keypair()

    with pytest.raises(ValueError):
        provider.derive_fernet_key(private_key, "invalid-pem")


@pytest.mark.unit
def test_encrypt_decrypt_roundtrip_uses_fernet_key_material():
    provider = CryptoProvider()
    alice_public, alice_private = provider.generate_ecdh_keypair()
    bob_public, bob_private = provider.generate_ecdh_keypair()
    _ = bob_private

    fernet_key = provider.derive_fernet_key(alice_private, bob_public)
    plaintext = "hola canal seguro"

    ciphertext = provider.encrypt(fernet_key, plaintext)
    decrypted = provider.decrypt(fernet_key, ciphertext)

    assert ciphertext != plaintext
    assert decrypted == plaintext


@pytest.mark.unit
def test_public_key_fingerprint_is_deterministic_and_changes_with_key():
    provider = CryptoProvider()
    public_key_a, _ = provider.generate_ecdh_keypair()
    public_key_b, _ = provider.generate_ecdh_keypair()

    fp_a1 = provider.fingerprint_public_key(public_key_a)
    fp_a2 = provider.fingerprint_public_key(public_key_a)
    fp_b = provider.fingerprint_public_key(public_key_b)

    assert fp_a1 == fp_a2
    assert fp_a1 != fp_b
