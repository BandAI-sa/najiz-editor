import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.exceptions import EncryptionConfigurationError, NajizError


class EncryptionService:
    def __init__(self, raw_key: str):
        try:
            self._fernet = Fernet(self._normalize_key(raw_key))
        except Exception as exc:  # pragma: no cover - defensive
            raise EncryptionConfigurationError() from exc

    @staticmethod
    def _normalize_key(raw_key: str) -> bytes:
        digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    def encrypt_text(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt_text(self, ciphertext: str | None) -> str:
        if not ciphertext:
            return ""
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise NajizError(
                code="encryption_error",
                message="تعذر فك تشفير البيانات الحساسة.",
                status_code=500,
                recoverable=False,
            ) from exc

    def encrypt_json(self, payload: dict[str, Any]) -> str:
        return self.encrypt_text(json.dumps(payload, ensure_ascii=False))

    def decrypt_json(self, ciphertext: str | None) -> dict[str, Any]:
        raw = self.decrypt_text(ciphertext)
        if not raw:
            return {}
        return json.loads(raw)
