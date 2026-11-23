"""Authenticated token encryption at rest using vetted cryptography (Fernet / AES-128-CBC + HMAC-SHA256).

Guarantees:
- Vetted authenticated encryption (cryptography.fernet.Fernet).
- Authenticated encryption at rest (AEAD properties: ciphertext integrity + confidentiality).
- Deterministic SHA-256 hashing for fast database lookup and deduplication without decryption.
- Zero plaintext fallback.
- Key rotation support via MultiFernet.
- Strict PII masking: raw tokens are never exposed in API schemas or application logs.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from services.api.config import settings
from services.api.notifications.exceptions import NotificationException

logger = logging.getLogger(__name__)

# Fixed salt for PBKDF2 key derivation from SECRET_KEY when PUSH_TOKEN_ENCRYPTION_KEY is unset
_KDF_SALT = b"upostit_vetted_fernet_push_token_salt_v1"
_CIPHER_PREFIX = "fernet:"


class EncryptionConfigError(NotificationException):
    """Raised when encryption key configuration is unavailable or corrupt."""

    def __init__(self, message: str = "Push token encryption key is unavailable or unconfigured") -> None:
        super().__init__(message, code="ENCRYPTION_CONFIG_ERROR")


class TokenEncryptionError(NotificationException):
    """Raised when authenticated token encryption or decryption fails."""

    def __init__(self, message: str = "Token cryptographic operation failed") -> None:
        super().__init__(message, code="TOKEN_ENCRYPTION_ERROR")


def derive_fernet_key_from_secret(secret: str) -> bytes:
    """Derives a vetted 32-byte url-safe base64-encoded key from a master secret using PBKDF2-HMAC-SHA256."""
    if not secret or len(secret) < 16:
        raise EncryptionConfigError("Master secret key is too short or empty for cryptographic key derivation")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_KDF_SALT,
        iterations=100_000,
    )
    key_bytes = kdf.derive(secret.encode("utf-8"))
    return base64.urlsafe_b64encode(key_bytes)


def get_fernet_suite() -> Fernet | MultiFernet:
    """Instantiates the Fernet cipher suite using environment configuration.

    Supports key rotation if multiple comma-separated keys are configured in
    PUSH_TOKEN_ENCRYPTION_KEY (primary key first, followed by previous keys).
    """
    configured_key = settings.PUSH_TOKEN_ENCRYPTION_KEY.strip()

    if configured_key:
        raw_keys = [k.strip() for k in configured_key.split(",") if k.strip()]
        fernets: list[Fernet] = []
        for k in raw_keys:
            try:
                fernets.append(Fernet(k.encode("ascii") if isinstance(k, str) else k))
            except Exception as exc:
                raise EncryptionConfigError(f"Invalid Fernet encryption key format: {exc}") from exc
        if len(fernets) == 1:
            return fernets[0]
        return MultiFernet(fernets)

    # Derive from master application secret
    if not settings.SECRET_KEY:
        raise EncryptionConfigError("Neither PUSH_TOKEN_ENCRYPTION_KEY nor SECRET_KEY is configured")

    derived = derive_fernet_key_from_secret(settings.SECRET_KEY)
    return Fernet(derived)


def hash_push_token(raw_token: str) -> str:
    """Computes deterministic SHA-256 hex digest of an FCM token for deduplication and indexed lookup."""
    clean = raw_token.strip()
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()


def encrypt_push_token(raw_token: str) -> str:
    """Encrypts an FCM push token using vetted authenticated encryption (Fernet).

    Args:
        raw_token: The plaintext FCM registration token string.

    Returns:
        String prefixed with 'fernet:' containing the base64 authenticated ciphertext.

    Raises:
        TokenEncryptionError: If input is empty or encryption fails.
        EncryptionConfigError: If cryptographic key is unavailable.
    """
    clean = raw_token.strip()
    if not clean:
        raise TokenEncryptionError("Cannot encrypt empty push token")

    suite = get_fernet_suite()
    try:
        ciphertext_bytes = suite.encrypt(clean.encode("utf-8"))
        return f"{_CIPHER_PREFIX}{ciphertext_bytes.decode('ascii')}"
    except Exception as exc:
        logger.exception("Failed encrypting device push token: %s", type(exc).__name__)
        raise TokenEncryptionError(f"Failed encrypting device push token: {exc}") from exc


def decrypt_push_token(stored_token: str) -> str:
    """Decrypts and authenticates a push token stored at rest.

    Args:
        stored_token: The stored ciphertext string. Must begin with 'fernet:'.

    Returns:
        The decrypted plaintext FCM registration token.

    Raises:
        TokenEncryptionError: If the token format is invalid, corrupt, or tampered.
    """
    if not stored_token or not stored_token.startswith(_CIPHER_PREFIX):
        # Strict enforcement: zero plaintext fallback permitted
        raise TokenEncryptionError(
            "Push token does not have authenticated encryption header; plaintext fallback is prohibited"
        )

    raw_ciphertext = stored_token[len(_CIPHER_PREFIX) :].encode("ascii")
    suite = get_fernet_suite()

    try:
        decrypted_bytes = suite.decrypt(raw_ciphertext)
        return decrypted_bytes.decode("utf-8")
    except InvalidToken as exc:
        logger.error("Token decryption failed: ciphertext was tampered with or encryption key is incorrect")
        raise TokenEncryptionError("Invalid or corrupt token authentication tag") from exc
    except Exception as exc:
        logger.exception("Unexpected token decryption failure: %s", type(exc).__name__)
        raise TokenEncryptionError(f"Failed decrypting device push token: {exc}") from exc


def mask_token_for_display(raw_or_encrypted_token: str) -> str:
    """Masks a token for PII-safe responses and logs without exposing raw credentials.

    Example output: 'fcm_...abcd'
    """
    clean = raw_or_encrypted_token.strip()
    if clean.startswith(_CIPHER_PREFIX):
        clean = clean[len(_CIPHER_PREFIX) :]

    if len(clean) <= 8:
        return "***"
    return f"{clean[:4]}...{clean[-4:]}"

