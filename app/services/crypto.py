"""
Symmetric encryption for sensitive credential fields (IMAP/SMTP passwords).

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the cryptography library,
which ships as a transitive dependency of python-jose[cryptography].

Key management:
- Set CREDENTIAL_ENCRYPTION_KEY in .env as a URL-safe base64-encoded 32-byte key.
- Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
- If the key is missing, encryption/decryption are no-ops (returns plaintext) so the
  app still boots, but a warning is logged on every encrypt/decrypt call.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_fernet = None
_init_attempted = False


def _get_fernet():
    global _fernet, _init_attempted
    if _init_attempted:
        return _fernet
    _init_attempted = True
    try:
        from app.config import settings
        key = getattr(settings, "CREDENTIAL_ENCRYPTION_KEY", None)
        if not key:
            logger.warning(
                "CREDENTIAL_ENCRYPTION_KEY is not set — credentials will be stored unencrypted. "
                "Generate a key with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
            return None
        from cryptography.fernet import Fernet
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        logger.error("Failed to initialize credential encryption: %s", e)
    return _fernet


def encrypt_credential(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a credential string. Returns ciphertext or original if encryption unavailable."""
    if plaintext is None:
        return None
    fernet = _get_fernet()
    if fernet is None:
        return plaintext
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_credential(ciphertext: Optional[str]) -> Optional[str]:
    """
    Decrypt a credential string.
    Gracefully handles plaintext values (pre-encryption migration).
    """
    if ciphertext is None:
        return None
    fernet = _get_fernet()
    if fernet is None:
        return ciphertext
    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except Exception:
        # Value was stored before encryption was enabled — return as-is
        logger.debug("Credential decryption failed — treating value as plaintext (pre-migration)")
        return ciphertext
