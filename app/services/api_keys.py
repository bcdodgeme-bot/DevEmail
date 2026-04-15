"""API key generation + hashing."""
import hashlib
import secrets

KEY_PREFIX = "dek_"
PREFIX_DISPLAY_LEN = 12  # len("dek_") + 8 chars of randomness shown in UI


def generate_key() -> tuple[str, str, str]:
    """Create a new API key.

    Returns:
        (raw_key, display_prefix, sha256_hash)
        - raw_key: "dek_" + 32 url-safe chars — shown to caller ONCE
        - display_prefix: first 12 chars of raw_key for list UI
        - sha256_hash: hex digest, stored in DB
    """
    raw_key = KEY_PREFIX + secrets.token_urlsafe(24)  # token_urlsafe(24) → 32 chars
    display_prefix = raw_key[:PREFIX_DISPLAY_LEN]
    hashed = hash_key(raw_key)
    return raw_key, display_prefix, hashed


def hash_key(raw_key: str) -> str:
    """SHA-256 hex digest of a raw key. O(1) indexed lookup vs. bcrypt per request."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
