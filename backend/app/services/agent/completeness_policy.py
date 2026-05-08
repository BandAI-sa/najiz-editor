from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.services.agent.repetition_guard import (
    CRITICAL_FIELD_KEYWORDS,
    FieldCriticality,
    classify_field_criticality,
)

logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class CompletenessVerdict:
    may_proceed: bool
    overall_percentage: int
    critical_filled: int
    critical_total: int
    recommended_filled: int
    recommended_total: int
    missing_critical: list[str]
    missing_recommended: list[str]
    user_message: str = ""


class CompletenessPolicy:
    """Enforces minimum data completeness before transitioning to READY_TO_DRAFT.

    - All CRITICAL fields must be filled (100% critical coverage required)
    - RECOMMENDED fields contribute to percentage but don't block
    - OPTIONAL fields are ignored for completeness calculation

    This is a policy object, not a service. It makes a decision, it doesn't
    store state. It reads session.extracted_data + case requirements and
    returns a CompletenessVerdict.
    """

    def __init__(self, min_recommended_percentage: int = 0):
        self.min_recommended_pct = min_recommended_percentage

    def evaluate(
        self,
        required_fields: list[tuple[str, bool]],
        extracted_data: dict[str, Any],
    ) -> CompletenessVerdict:
        """Evaluate whether the session has enough data for drafting.

        Args:
            required_fields: list of (field_name, is_required) from CaseRequirements
            extracted_data: current session.extracted_data
        """
        critical_fields: list[str] = []
        recommended_fields: list[str] = []

        for name, required in required_fields:
            tier = classify_field_criticality(name, required=required)
            if tier == FieldCriticality.CRITICAL:
                critical_fields.append(name)
            elif tier == FieldCriticality.RECOMMENDED:
                recommended_fields.append(name)

        critical_filled = [f for f in critical_fields if _has_value(extracted_data, f)]
        critical_missing = [f for f in critical_fields if not _has_value(extracted_data, f)]
        recommended_filled = [f for f in recommended_fields if _has_value(extracted_data, f)]
        recommended_missing = [f for f in recommended_fields if not _has_value(extracted_data, f)]

        critical_total = len(critical_fields)
        rec_total = len(recommended_fields)

        all_scoreable = critical_total + rec_total
        all_filled = len(critical_filled) + len(recommended_filled)
        overall_pct = round((all_filled / max(all_scoreable, 1)) * 100)

        all_critical_met = len(critical_missing) == 0

        rec_pct = round((len(recommended_filled) / max(rec_total, 1)) * 100) if rec_total else 100
        recommended_met = rec_pct >= self.min_recommended_pct

        may_proceed = all_critical_met and recommended_met

        user_message = ""
        if not all_critical_met:
            field_list = "، ".join(critical_missing[:5])
            user_message = (
                f"باقي معلومات أساسية قبل ما نبدأ الصياغة: {field_list}.\n"
                f"هالمعلومات ضرورية عشان الصحيفة تكون مقبولة نظاميًا."
            )
        elif not recommended_met:
            user_message = (
                f"البيانات الأساسية مكتملة، بس يفضّل نكمّل بعض المعلومات "
                f"عشان تطلع الصحيفة بأفضل صورة."
            )

        if not may_proceed:
            logger.info(
                "CompletenessPolicy: blocked draft — critical_missing=%s rec_pct=%d%%",
                critical_missing,
                rec_pct,
            )

        return CompletenessVerdict(
            may_proceed=may_proceed,
            overall_percentage=overall_pct,
            critical_filled=len(critical_filled),
            critical_total=critical_total,
            recommended_filled=len(recommended_filled),
            recommended_total=rec_total,
            missing_critical=critical_missing,
            missing_recommended=recommended_missing,
            user_message=user_message,
        )


def _has_value(data: dict[str, Any], field_name: str) -> bool:
    val = data.get(field_name)
    if val is None:
        return False
    return bool(str(val).strip())
