"""Tests for mytnb.crypto encryption module."""

import base64
import json

from mytnb.crypto import (
    EncryptedPayload,
    _pkcs7_pad,
    _pkcs7_unpad,
    encrypt_request,
)


class TestPKCS7Padding:
    def test_pad_adds_bytes(self):
        data = b"hello"  # 5 bytes → needs 11 bytes of padding
        padded = _pkcs7_pad(data)
        assert len(padded) == 16
        assert padded[-1] == 11

    def test_pad_full_block_adds_extra_block(self):
        data = b"a" * 16  # exactly one block → needs full 16-byte pad block
        padded = _pkcs7_pad(data)
        assert len(padded) == 32
        assert padded[-1] == 16

    def test_pad_single_byte(self):
        data = b"a" * 15  # 15 bytes → needs 1 byte of padding
        padded = _pkcs7_pad(data)
        assert len(padded) == 16
        assert padded[-1] == 1

    def test_roundtrip(self):
        original = b"test data 12345"
        assert _pkcs7_unpad(_pkcs7_pad(original)) == original

    def test_unpad_invalid_zero(self):
        import pytest
        with pytest.raises(ValueError, match="Invalid PKCS7"):
            _pkcs7_unpad(b"hello\x00")

    def test_unpad_invalid_too_large(self):
        import pytest
        with pytest.raises(ValueError, match="Invalid PKCS7"):
            _pkcs7_unpad(b"hello" + bytes([20]))


class TestEncryptRequest:
    def test_returns_encrypted_payload(self):
        payload = encrypt_request({"key": "value"})
        assert isinstance(payload, EncryptedPayload)

    def test_ae_is_valid_base64(self):
        payload = encrypt_request({"test": 123})
        decoded = base64.b64decode(payload.ae)
        assert len(decoded) > 0
        # AES-CBC output must be a multiple of 16 bytes
        assert len(decoded) % 16 == 0

    def test_ak_is_valid_base64_rsa_ciphertext(self):
        payload = encrypt_request({"test": True})
        decoded = base64.b64decode(payload.ak)
        # RSA-2048 produces 256 bytes of ciphertext
        assert len(decoded) == 256

    def test_av_is_valid_base64_iv(self):
        payload = encrypt_request({"test": True})
        decoded = base64.b64decode(payload.av)
        # AES IV is 16 bytes
        assert len(decoded) == 16

    def test_to_dict(self):
        payload = encrypt_request({"a": 1})
        d = payload.to_dict()
        assert set(d.keys()) == {"ae", "ak", "av"}
        assert all(isinstance(v, str) for v in d.values())

    def test_different_calls_produce_different_output(self):
        data = {"same": "data"}
        p1 = encrypt_request(data)
        p2 = encrypt_request(data)
        # Random key/IV means different ciphertexts each time
        assert p1.ae != p2.ae
        assert p1.ak != p2.ak
        assert p1.av != p2.av

    def test_staging_key(self):
        payload = encrypt_request({"test": 1}, use_staging_key=True)
        # Should still produce valid output with staging key
        assert len(base64.b64decode(payload.ak)) == 256

    def test_complex_nested_data(self):
        data = {
            "AccountNumber": "220123456789",
            "isOwner": True,
            "usrInf": {
                "sspuid": "abc-123",
                "did": "device-id",
                "lang": "EN",
            },
        }
        payload = encrypt_request(data)
        assert len(base64.b64decode(payload.ae)) > 0

    def test_empty_dict(self):
        payload = encrypt_request({})
        decoded = base64.b64decode(payload.ae)
        # "{}" is 2 bytes → padded to 16 → encrypted to 16 bytes
        assert len(decoded) == 16

    def test_list_data(self):
        payload = encrypt_request([1, 2, 3])
        assert len(base64.b64decode(payload.ae)) > 0

    def test_string_data(self):
        payload = encrypt_request("just a string")
        assert len(base64.b64decode(payload.ae)) > 0
