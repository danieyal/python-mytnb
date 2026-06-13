"""Encryption module for myTNB API request payloads.

Implements the AES-256-CBC + RSA-OAEP hybrid encryption used by the
myTNB mobile app (APISecurityManager).

Encryption flow:
  1. Serialize request data to JSON
  2. Generate random AES-256 key (32 bytes) and IV (16 bytes)
  3. Encrypt JSON with AES-256-CBC, PKCS7 padding → base64 → `ae`
  4. Encrypt AES key with RSA-OAEP (SHA-1) using embedded public key → base64 → `ak`
  5. Base64-encode the IV → `av`
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# ── RSA Public Keys (extracted from myTNB.Mobile.Resources.Keys) ──────────

# Production key (PKey.txt) - 2048-bit RSA, exponent 65537
_PROD_MODULUS_B64 = (
    "2PUbfII3l4qZYNfvoIavtqL5PoXbnX093tJFHjre6Bspsy8gPMBoerv/GsjOpWVl"
    "f44y9ey9XUBuIzFYLYmtfAG0CQX90pJ4aDgnUpCiw02D/NShwVRwmujyFjhB3T"
    "beBbHofue/4KHZrbz2UQD0AgnC/HZiHRp2rFoWRGcud+xrUH6NJiF5YPYRgGKRi/"
    "s0xOn4xHgU2kpDCuE9/u2HFwxcJQZM+ekQNzo3OMSM53IiTZocToVEi82fJRCBi"
    "VuprgR3kpoK9gwQkvoScRNY8qcEhLmQr/qJKoI6jBLLkgdvKJoqAlUtKGy9XBsI5"
    "v9JNV0p5IHFgyAhxP701uHKIQ=="
)

_PROD_EXPONENT_B64 = "AQAB"

# Staging key (SKey.txt) - for development/testing
_STAGING_MODULUS_B64 = (
    "5NMh+MJ+Mb9Fly2tyOtA+SgUE/M5sfYx0xDyfFLuXvQwzTyyHUSRTGvSk1kv4Gz"
    "7hY4AFHk+/0loQ4YxaWByFh+mMzu2JVJT4iR+xtLTMeY81wbELl78crKevMutJG"
    "WPX8DEOBrAdpLo2REu6KB085sULrHhbVX9h2aLt0YFYb+IKErxWbkTkI2/VRQjR2"
    "tU9kOmLxUTTH76ibkVD2GfD8AtZhKNJXSINuIPkovZ8sZPCQI11nhHurc07diCKF"
    "6YHqJADwe6vukmhaa2Flyc03weQFBopFx3NcQvI69lrOf/URr0GZj8HX8vq8SWuK"
    "GSbcvPuA3+5FsrEBIFKZg3wQ=="
)

_STAGING_EXPONENT_B64 = "AQAB"


def _build_rsa_public_key(modulus_b64: str, exponent_b64: str) -> RSAPublicKey:
    """Build an RSA public key from base64-encoded modulus and exponent."""
    n = int.from_bytes(base64.b64decode(modulus_b64), byteorder="big")
    e = int.from_bytes(base64.b64decode(exponent_b64), byteorder="big")
    return rsa.RSAPublicNumbers(e, n).public_key()


_PROD_KEY = _build_rsa_public_key(_PROD_MODULUS_B64, _PROD_EXPONENT_B64)
_STAGING_KEY = _build_rsa_public_key(_STAGING_MODULUS_B64, _STAGING_EXPONENT_B64)


# ── PKCS7 padding ────────────────────────────────────────────────────────

def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    """Apply PKCS7 padding."""
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes) -> bytes:
    """Remove PKCS7 padding."""
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16:
        raise ValueError("Invalid PKCS7 padding")
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        raise ValueError("Invalid PKCS7 padding")
    return data[:-pad_len]


# ── Public API ────────────────────────────────────────────────────────────

@dataclass
class EncryptedPayload:
    """Encrypted request payload (dt object)."""

    ae: str  # Base64(AES-256-CBC(JSON data))
    ak: str  # Base64(RSA-OAEP(AES key))
    av: str  # Base64(IV)

    def to_dict(self) -> dict[str, str]:
        return {"ae": self.ae, "ak": self.ak, "av": self.av}


def encrypt_request(
    data: Any,
    *,
    use_staging_key: bool = False,
) -> EncryptedPayload:
    """Encrypt a request payload for the myTNB legacy API.

    Args:
        data: The request data (will be JSON-serialized).
        use_staging_key: Use the staging RSA key instead of production.

    Returns:
        EncryptedPayload with ae, ak, av fields.
    """
    rsa_key = _STAGING_KEY if use_staging_key else _PROD_KEY

    # 1. Serialize to JSON bytes
    json_str = json.dumps(data, separators=(",", ":"))
    plaintext = json_str.encode("utf-8")

    # 2. Generate random AES-256 key and IV
    aes_key = os.urandom(32)  # 256-bit key
    iv = os.urandom(16)  # 128-bit IV

    # 3. AES-256-CBC encrypt with PKCS7 padding
    padded = _pkcs7_pad(plaintext)
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    ae = base64.b64encode(ciphertext).decode("ascii")

    # 4. RSA-OAEP encrypt the AES key
    encrypted_key = rsa_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA1()),
            algorithm=hashes.SHA1(),
            label=None,
        ),
    )
    ak = base64.b64encode(encrypted_key).decode("ascii")

    # 5. Base64-encode the IV
    av = base64.b64encode(iv).decode("ascii")

    return EncryptedPayload(ae=ae, ak=ak, av=av)
