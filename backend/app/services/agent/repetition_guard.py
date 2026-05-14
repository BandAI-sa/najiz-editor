from __future__ import annotations

import logging
from enum import StrEnum

logger = logging.getLogger("uvicorn.error")


class FieldCriticality(StrEnum):
    """Three-tier classification for how aggressively a field can be skipped."""
    CRITICAL = "required_critical"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


class RepetitionAction(StrEnum):
    NORMAL = "normal"
    EXPLAIN_IMPORTANCE = "explain_importance"
    REPHRASE_WITH_HINT = "rephrase_with_hint"
    ESCALATE_WITH_EXAMPLE = "escalate_with_example"
    OFFER_SKIP = "offer_skip"
    SKIP_OPTIONAL = "skip_optional"


FIELD_EXAMPLES: dict[str, str] = {
    "تاريخ": "يعني مثلاً: 2024-01-15 أو 15/01/2024 أو 1 محرم 1445",
    "مبلغ": "يعني مثلاً: 50000 (أرقام فقط)",
    "قيمة": "يعني مثلاً: 150000",
    "اسم": "يعني مثلاً: أحمد بن محمد العلي",
    "رقم": "يعني مثلاً: 1234567890",
    "هاتف": "يعني مثلاً: 0551234567",
    "هوية": "يعني مثلاً: 1012345678",
    "عنوان": "يعني مثلاً: حي النزهة، شارع الأمير سلطان، الرياض",
    "وقائع": "يعني مثلاً: \"استأجرت الشقة بتاريخ كذا وما دفع الإيجار من شهر كذا\"",
    "طلبات": "يعني مثلاً: \"أطلب إلزامه بدفع المبلغ المستحق\"",
    "أسانيد": "يعني مثلاً:\n• عقد إيجار\n• رسائل واتساب\n• صور\n• شهود",
    "موضوع": "يعني مثلاً: \"مطالبة مالية بسبب عدم سداد إيجار\"",
}

FIELD_IMPORTANCE_REASONS: dict[str, str] = {
    "اسم المدعي": "المحكمة ما تقبل الصحيفة بدون اسم المدعي الكامل.",
    "اسم المدعى عليه": "بدون اسم المدعى عليه ما نقدر نوجّه الدعوى.",
    "تاريخ": "التاريخ مهم عشان المحكمة تتأكد إن الدعوى مقدمة في وقتها.",
    "مبلغ": "المبلغ يحدد اختصاص المحكمة اللي تنظر الدعوى.",
    "قيمة": "القيمة تحدد اختصاص المحكمة.",
    "هوية": "رقم الهوية مطلوب عشان نتأكد من هوية الأطراف.",
    "عنوان": "العنوان مطلوب عشان يتم تبليغ الطرف الثاني رسميًا.",
    "وقائع": "الوقائع هي أساس الدعوى — بدونها ما تكتمل الصحيفة.",
    "طلبات": "الطلبات توضّح للمحكمة وش اللي تطلبه بالضبط.",
    "أسانيد": "المستندات والأسانيد تدعم موقفك في الدعوى.",
    "موضوع": "موضوع الدعوى يحدد نوع القضية واختصاص المحكمة.",
}

CRITICAL_FIELD_KEYWORDS = frozenset({
    "اسم المدعي", "اسم المدعى عليه", "هوية المدعي", "هوية المدعى عليه",
    "موضوع الدعوى", "وقائع", "طلبات", "أسانيد",
})


def classify_field_criticality(
    field_name: str,
    *,
    required: bool = True,
) -> FieldCriticality:
    if not required:
        return FieldCriticality.OPTIONAL
    if field_name in CRITICAL_FIELD_KEYWORDS:
        return FieldCriticality.CRITICAL
    for keyword in ("اسم", "هوية", "موضوع", "وقائع", "طلبات"):
        if keyword in field_name:
            return FieldCriticality.CRITICAL
    return FieldCriticality.RECOMMENDED


class RepetitionGuard:
    """Tracks per-field ask counts within session.metadata and recommends
    escalation strategies based on field criticality tier.

    Pure Python — zero LLM cost, zero network calls.

    Escalation ladder:
      Attempt 1: NORMAL (ask normally)
      Attempt 2: EXPLAIN_IMPORTANCE (explain why this field matters legally)
      Attempt 3: REPHRASE_WITH_HINT (rephrase + format examples)
      Attempt 4: ESCALATE_WITH_EXAMPLE (stripped-down "just type the value")
      Attempt 5+:
        - CRITICAL fields: keep asking (ESCALATE_WITH_EXAMPLE forever)
        - RECOMMENDED fields: OFFER_SKIP (suggest skip but don't auto-skip)
        - OPTIONAL fields: SKIP_OPTIONAL (auto-skip)
    """

    def __init__(
        self,
        max_normal: int = 1,
        max_explain: int = 2,
        max_hint: int = 3,
        max_escalate: int = 4,
    ):
        self.max_normal = max_normal
        self.max_explain = max_explain
        self.max_hint = max_hint
        self.max_escalate = max_escalate

    def check_and_increment(
        self,
        metadata: dict,
        field_name: str,
        *,
        field_required: bool = True,
        criticality: FieldCriticality | None = None,
    ) -> RepetitionAction:
        tier = criticality or classify_field_criticality(field_name, required=field_required)
        attempts = metadata.setdefault("field_attempts", {})
        count = attempts.get(field_name, 0) + 1
        attempts[field_name] = count

        if count <= self.max_normal:
            return RepetitionAction.NORMAL

        if count <= self.max_explain:
            logger.info(
                "RepetitionGuard: field=%s tier=%s attempt=%d action=explain_importance",
                field_name, tier, count,
            )
            return RepetitionAction.EXPLAIN_IMPORTANCE

        if count <= self.max_hint:
            logger.info(
                "RepetitionGuard: field=%s tier=%s attempt=%d action=rephrase_with_hint",
                field_name, tier, count,
            )
            return RepetitionAction.REPHRASE_WITH_HINT

        if count <= self.max_escalate:
            logger.info(
                "RepetitionGuard: field=%s tier=%s attempt=%d action=escalate_with_example",
                field_name, tier, count,
            )
            return RepetitionAction.ESCALATE_WITH_EXAMPLE

        if tier == FieldCriticality.CRITICAL:
            logger.info(
                "RepetitionGuard: field=%s tier=CRITICAL attempt=%d — cannot skip, re-escalating",
                field_name, count,
            )
            return RepetitionAction.ESCALATE_WITH_EXAMPLE

        if tier == FieldCriticality.RECOMMENDED:
            logger.info(
                "RepetitionGuard: field=%s tier=RECOMMENDED attempt=%d action=offer_skip",
                field_name, count,
            )
            return RepetitionAction.OFFER_SKIP

        logger.info(
            "RepetitionGuard: field=%s tier=OPTIONAL attempt=%d action=skip_optional",
            field_name, count,
        )
        return RepetitionAction.SKIP_OPTIONAL

    @staticmethod
    def format_example_for_field(field_name: str) -> str | None:
        for keyword, example in FIELD_EXAMPLES.items():
            if keyword in field_name:
                return example
        return None

    @staticmethod
    def _importance_reason(field_name: str) -> str:
        for keyword, reason in FIELD_IMPORTANCE_REASONS.items():
            if keyword in field_name:
                return reason
        return "هذا الحقل مهم لاكتمال صحيفة الدعوى."

    def build_rephrase_message(
        self,
        field_name: str,
        action: RepetitionAction,
        *,
        custom_example: str | None = None,
    ) -> str:
        if action == RepetitionAction.EXPLAIN_IMPORTANCE:
            reason = self._importance_reason(field_name)
            return (
                f"هالمعلومة مهمة لأن {reason}\n"
                f"حاول تعطيني اللي تعرفه حتى لو تقريبي."
            )

        if action == RepetitionAction.REPHRASE_WITH_HINT:
            example = custom_example or self.format_example_for_field(field_name)
            hint = f"\n{example}" if example else ""
            return (
                f"ما قدرت أفهم إجابتك السابقة بشكل واضح.{hint}\n"
                f"ممكن تعيد كتابتها بطريقة ثانية؟"
            )

        if action == RepetitionAction.ESCALATE_WITH_EXAMPLE:
            example = custom_example or self.format_example_for_field(field_name)
            hint = f"\n{example}" if example else ""
            return (
                f"خلني أسهّلها عليك — اكتب القيمة مباشرة بدون شرح إضافي.{hint}"
            )

        if action == RepetitionAction.OFFER_SKIP:
            return (
                f"ما قدرت أستخلص هالمعلومة بعد عدة محاولات.\n"
                f"هالحقل يحسّن جودة الصحيفة بس مو إلزامي.\n"
                f"تبي نتجاوزه؟ اكتب «تجاوز» أو عطني المعلومة."
            )

        if action == RepetitionAction.SKIP_OPTIONAL:
            return (
                f"تم تجاوز هالحقل. تقدر تضيفه لاحقًا عند تعديل الصحيفة."
            )

        return ""

    @staticmethod
    def get_attempt_count(metadata: dict, field_name: str) -> int:
        return metadata.get("field_attempts", {}).get(field_name, 0)

    @staticmethod
    def reset_field(metadata: dict, field_name: str) -> None:
        attempts = metadata.get("field_attempts")
        if attempts and field_name in attempts:
            del attempts[field_name]
