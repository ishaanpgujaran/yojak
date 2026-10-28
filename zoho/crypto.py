from cryptography.fernet import Fernet, InvalidToken
from app.config import settings

# Creates Fernet instance using key
def get_fernet() -> Fernet:
    """Create a Fernet instace using the configured encryption key."""
    return Fernet(settings.zoho_token_encryption_key.encode("utf-8"))


# Encrypts Refresh token using fernet
def encrypt_refresh_token(refresh_token: str) -> bytes:
    """Encrypt a Zoho refresh token before storing it in the database."""

    if not refresh_token:
        raise ValueError("Refresh token cannot be empty.")
    
    fernet = get_fernet()

    return fernet.encrypt(refresh_token.encode("utf-8"))


# Decryts Refresh token using fernet
def decrypt_refresh_token(encrypted_token: bytes) -> str:
    """Decrypt a Refresh token retrieved from the database."""

    if not encrypted_token:
        raise ValueError("Encrypted refresh token cannot be empty.")
    
    fernet = get_fernet()

    try:
        decrypted_token = fernet.decrypt(encrypted_token)
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt refresh token. Check the encryption key and stored ciphertext") from exc
    
    return decrypted_token.decode("utf-8")