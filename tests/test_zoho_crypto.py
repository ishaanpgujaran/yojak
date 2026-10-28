import pytest
from cryptography.fernet import Fernet

from app.config import settings
from zoho.crypto import(
    decrypt_refresh_token,
    encrypt_refresh_token,
)

def test_refresh_token_encryption_rount_trip():
    original_token = "test-refresh-token-123"

    encrypted_token = encrypt_refresh_token(original_token)
    decrypted_token = decrypt_refresh_token(encrypted_token)

    assert isinstance(encrypted_token, bytes)
    assert encrypted_token != original_token.encode("utf-8")
    assert decrypted_token == original_token


def test_empty_refresh_token_cannot_be_encrypted():
    with pytest.raises(ValueError, match="cannot be empty"):
        encrypt_refresh_token("")


def test_empty_encrypted_refresh_token_cannot_be_decrypted():
    with pytest.raises(ValueError, match="cannot be empty"):
        decrypt_refresh_token(b"")


def test_refresh_token_cannot_be_decrypted_with_wrong_key(monkeypatch):
    original_token = "test-refresh-token-123"

    encrypted_token = encrypt_refresh_token(original_token)

    wrong_key = Fernet.generate_key().decode("utf-8")
    
    monkeypatch.setattr(
        settings,
        "zoho_token_encryption_key",
        wrong_key,
    )

    with pytest.raises(ValueError, match="Unable to decrypt"):
        decrypt_refresh_token(encrypted_token)
