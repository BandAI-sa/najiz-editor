from dataclasses import dataclass, field
from typing import Any

from app.models.api import ErrorResponse


@dataclass
class NajizError(Exception):
    code: str
    message: str
    status_code: int = 400
    recoverable: bool = True
    details: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            error_code=self.code,
            message=self.message,
            recoverable=self.recoverable,
            details=self.details,
        )


class SessionNotFoundError(NajizError):
    def __init__(self, session_id: str):
        super().__init__(
            code="session_not_found",
            message="الجلسة غير موجودة.",
            status_code=404,
            recoverable=False,
            details={"session_id": session_id},
        )


class ValidationReportError(NajizError):
    def __init__(self, report: dict[str, Any]):
        super().__init__(
            code="classification_validation_failed",
            message="بيانات التصنيفات غير صالحة للتحميل.",
            status_code=500,
            recoverable=False,
            details={"report": report},
        )


class LLMParseError(NajizError):
    def __init__(self, capability: str, details: dict[str, Any] | None = None):
        super().__init__(
            code="llm_parse_error",
            message="تعذر تفسير استجابة النموذج بالشكل المطلوب.",
            status_code=502,
            recoverable=True,
            details={"capability": capability, **(details or {})},
        )


class EncryptionConfigurationError(NajizError):
    def __init__(self):
        super().__init__(
            code="encryption_configuration_error",
            message="إعداد مفتاح التشفير غير صالح.",
            status_code=500,
            recoverable=False,
        )
