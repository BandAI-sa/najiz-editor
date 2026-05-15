from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.utils.text import parse_date, parse_number

logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    cleaned_value: str
    error_message: str = ""
    field_type: str = "text"


ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
FIELD_TYPE_KEYWORDS: list[tuple[str, str]] = [
    ("تاريخ", "date"),
    ("تواريخ", "date"),
    ("مبلغ", "number"),
    ("قيمة", "number"),
    ("تعويض", "number"),
    ("مساحة", "number"),
    ("رقم", "id_number"),
    ("هوية", "id_number"),
    ("سجل", "id_number"),
    ("هاتف", "phone"),
    ("جوال", "phone"),
    ("بريد", "email"),
    ("email", "email"),
    ("اسم", "name"),
    ("عنوان", "address"),
]

UNKNOWN_INDICATORS = frozenset({
    "لا أعلم", "لا اعلم", "ما أدري", "ما ادري",
    "لا أعرف", "لا اعرف", "مو متأكد", "مش عارف",
    "لا أذكر", "لا اذكر", "ما أذكر", "ما اذكر", "مو ذاكر",
    "غير معروف", "لا يوجد", "ليس لدي",
    "ما اعرف", "ماني عارف", "ماني متأكد", "مش متأكد",
    "مدري", "غير متأكد", "ما عندي فكرة",
})

IRRELEVANT_INDICATORS = frozenset({
    "ما هذا", "ماذا تعني", "ما معنى", "لماذا",
    "كيف", "وش يعني", "ما فائدة", "ايش",
})

_DATE_LIKE_PATTERNS = [
    re.compile(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}"),
    re.compile(r"\d{1,2}[-/]\d{1,2}[-/]\d{4}"),
    re.compile(r"\d{1,2}[-/]\d{1,2}[-/]\d{2}"),
    re.compile(r"\d{4}/\d{1,2}/\d{1,2}"),
    re.compile(r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}"),
]

_HIJRI_MONTH_NAMES = (
    "محرم", "صفر", "ربيع الأول", "ربيع الآخر", "ربيع الثاني",
    "جمادى الأولى", "جمادى الآخرة", "جمادى الثانية",
    "رجب", "شعبان", "رمضان", "شوال",
    "ذو القعدة", "ذو الحجة",
)

_GREGORIAN_MONTH_NAMES = (
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
)


def _detect_field_type(field_name: str) -> str:
    lower = field_name.strip()
    for keyword, ftype in FIELD_TYPE_KEYWORDS:
        if keyword in lower:
            return ftype
    return "text"


def _normalize_arabic_digits(value: str) -> str:
    return value.translate(ARABIC_DIGITS)


def _is_unknown_answer(value: str) -> bool:
    stripped = value.strip().rstrip(".؟?!،,")
    if not stripped:
        return False
    normalized = stripped.translate(
        str.maketrans(
            {
                "أ": "ا",
                "إ": "ا",
                "آ": "ا",
                "ى": "ي",
                "ة": "ه",
                "ؤ": "و",
                "ئ": "ي",
            }
        )
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized in UNKNOWN_INDICATORS:
        return True
    return any(
        phrase in normalized
        for phrase in (
            "ما اعرف",
            "ماني عارف",
            "ماني متأكد",
            "مو متأكد",
            "مش متأكد",
            "ما ادري",
            "مدري",
            "غير متأكد",
            "ما عندي فكرة",
        )
    )


def _is_irrelevant_answer(value: str) -> bool:
    stripped = value.strip().rstrip(".؟?!")
    return any(stripped.startswith(prefix) for prefix in IRRELEVANT_INDICATORS)


def _extract_date_substring(text: str) -> str | None:
    """Try to pull a date-shaped substring out of a longer sentence."""
    for pattern in _DATE_LIKE_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0)
    return None


def _has_month_name(text: str) -> bool:
    lower = text.strip()
    return any(month in lower for month in _HIJRI_MONTH_NAMES + _GREGORIAN_MONTH_NAMES)


def _validate_date(value: str) -> ValidationResult:
    normalized = _normalize_arabic_digits(value.strip())

    parsed = parse_date(normalized)
    if parsed:
        return ValidationResult(valid=True, cleaned_value=str(parsed), field_type="date")

    extracted = _extract_date_substring(normalized)
    if extracted:
        parsed_extracted = parse_date(extracted)
        if parsed_extracted:
            return ValidationResult(valid=True, cleaned_value=str(parsed_extracted), field_type="date")
        return ValidationResult(valid=True, cleaned_value=extracted, field_type="date")

    if _has_month_name(normalized) and re.search(r"\d{2,4}", normalized):
        return ValidationResult(valid=True, cleaned_value=normalized, field_type="date")

    year_match = re.search(r"\b1[34]\d{2}\b", normalized) or re.search(r"\b(19|20)\d{2}\b", normalized)
    if year_match and not re.search(r"[a-zA-Z]", normalized):
        non_digit_non_space = re.sub(r"[\d\s/\-.]", "", normalized)
        if len(non_digit_non_space) <= 10:
            return ValidationResult(valid=True, cleaned_value=normalized, field_type="date")

    return ValidationResult(
        valid=False,
        cleaned_value=value,
        error_message=(
            "ما قدرت أفهم التاريخ من إجابتك.\n"
            "ممكن تكتبه بصيغة مثل:\n"
            "• 2024-01-15\n"
            "• 15/01/2024\n"
            "• 1 محرم 1445"
        ),
        field_type="date",
    )


def _validate_number(value: str) -> ValidationResult:
    normalized = _normalize_arabic_digits(value.strip())
    numeric = parse_number(normalized)
    if numeric is not None:
        return ValidationResult(valid=True, cleaned_value=str(numeric), field_type="number")
    return ValidationResult(
        valid=False,
        cleaned_value=value,
        error_message="أحتاج المبلغ بالأرقام فقط، مثل: 50000",
        field_type="number",
    )


def _validate_phone(value: str) -> ValidationResult:
    normalized = _normalize_arabic_digits(value.strip())
    digits = re.sub(r"[^\d+]", "", normalized)
    if len(digits) >= 7:
        return ValidationResult(valid=True, cleaned_value=digits, field_type="phone")
    return ValidationResult(
        valid=False,
        cleaned_value=value,
        error_message="الرقم اللي كتبته قصير. ممكن تكتب رقم الجوال كامل؟ مثل: 0551234567",
        field_type="phone",
    )


def _validate_email(value: str) -> ValidationResult:
    stripped = value.strip()
    if re.fullmatch(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", stripped):
        return ValidationResult(valid=True, cleaned_value=stripped.lower(), field_type="email")
    return ValidationResult(
        valid=False,
        cleaned_value=value,
        error_message=(
            "يبدو أن البريد الإلكتروني غير مكتمل.\n"
            "مثل: [example@email.com](mailto:example@email.com)"
        ),
        field_type="email",
    )


def _validate_id_number(value: str) -> ValidationResult:
    normalized = _normalize_arabic_digits(value.strip())
    digits = re.sub(r"[^\d]", "", normalized)
    if len(digits) >= 5:
        return ValidationResult(valid=True, cleaned_value=digits, field_type="id_number")
    return ValidationResult(
        valid=False,
        cleaned_value=value,
        error_message="أحتاج الرقم كامل (5 خانات على الأقل). مثل: 1012345678",
        field_type="id_number",
    )


def _validate_name(value: str) -> ValidationResult:
    stripped = value.strip()
    if len(stripped) < 2:
        return ValidationResult(
            valid=False,
            cleaned_value=value,
            error_message="الاسم قصير، ممكن تكتب الاسم الكامل؟ مثل: أحمد بن محمد العلي",
            field_type="name",
        )
    if re.search(r"\d", stripped):
        return ValidationResult(
            valid=False,
            cleaned_value=value,
            error_message="يبدو فيه أرقام بالاسم. ممكن تكتب الاسم فقط بدون أرقام؟",
            field_type="name",
        )
    return ValidationResult(valid=True, cleaned_value=stripped, field_type="name")


def _validate_text(value: str) -> ValidationResult:
    stripped = value.strip()
    if not stripped:
        return ValidationResult(
            valid=False,
            cleaned_value=value,
            error_message="ما وصلتني إجابة، ممكن تكتب المعلومة المطلوبة؟",
            field_type="text",
        )
    if _is_garbage_text(stripped):
        return ValidationResult(
            valid=False,
            cleaned_value=value,
            error_message=(
                "الإجابة غير واضحة أو تبدو عشوائية.\n"
                "ممكن تكتبها بجملة مفهومة ومباشرة؟"
            ),
            field_type="garbage",
        )
    return ValidationResult(valid=True, cleaned_value=stripped, field_type="text")


def _is_garbage_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if re.fullmatch(r"[^\w\u0600-\u06FF]+", stripped):
        return True
    has_arabic = bool(re.search(r"[\u0600-\u06FF]", stripped))
    has_digit = bool(re.search(r"\d", stripped))
    has_latin = bool(re.search(r"[A-Za-z]", stripped))
    # Latin-only blobs like "abc xyz" are treated as garbage in this intake UX.
    if has_latin and not has_arabic and not has_digit:
        return True
    return False


VALIDATORS: dict[str, callable] = {
    "date": _validate_date,
    "number": _validate_number,
    "phone": _validate_phone,
    "email": _validate_email,
    "id_number": _validate_id_number,
    "name": _validate_name,
    "text": _validate_text,
    "address": _validate_text,
}


class AnswerValidationLayer:
    """Validates extracted values against expected types before they reach
    session.extracted_data. Pure Python — zero LLM cost.
    """

    def validate(self, field_name: str, value: str) -> ValidationResult:
        stripped = value.strip()

        if _is_unknown_answer(stripped):
            return ValidationResult(
                valid=False,
                cleaned_value="",
                error_message="ما عليك، لو ما تعرف بالضبط حاول تعطيني اللي تتذكره حتى لو تقريبي.",
                field_type="unknown",
            )

        if _is_irrelevant_answer(stripped):
            return ValidationResult(
                valid=False,
                cleaned_value="",
                error_message="أقدّر استفسارك، بس أحتاج منك إجابة على السؤال عشان نكمّل.",
                field_type="irrelevant",
            )

        if not stripped:
            return ValidationResult(
                valid=False,
                cleaned_value="",
                error_message="ما وصلتني إجابة، ممكن تكتب المعلومة المطلوبة؟",
                field_type="empty",
            )

        field_type = _detect_field_type(field_name)
        validator = VALIDATORS.get(field_type, _validate_text)

        result = validator(stripped)
        if not result.valid:
            logger.info(
                "AnswerValidation rejected: field=%s type=%s value=%s reason=%s",
                field_name,
                field_type,
                stripped[:80],
                result.error_message,
            )
        return result
