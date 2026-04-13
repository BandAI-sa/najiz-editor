from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.security import EncryptionService


def test_encrypts_and_decrypts_json_payload():
    service = EncryptionService("unit-test-secret")
    payload = {"client_name": "نواف", "claim": "تعويض"}

    encrypted = service.encrypt_json(payload)

    assert encrypted != str(payload)
    assert service.decrypt_json(encrypted) == payload
