from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.utils.text import parse_date, parse_number

logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class Contradiction:
    code: str
    field_a: str
    field_b: str
    description: str
    suggestion: str


_COHABITATION_KEYWORDS = frozenset({
    "يعيش مع", "يسكن مع", "في حضانة", "مقيم مع", "تحت رعاية",
})

_SEPARATION_KEYWORDS = frozenset({
    "ممنوع من رؤية", "حُرم من", "لا يستطيع رؤية", "منعه من",
    "لم يرَ", "حرمان من الرؤية", "ممنوع من الزيارة",
})


class ContradictionChecker:
    """Lightweight consistency checker for extracted_data.

    Runs pure-Python heuristics to catch obvious logical contradictions
    before draft generation. Not a reasoning engine — pattern matching
    against known contradiction shapes in Saudi legal case data.

    Plugs in as a pre-draft checkpoint. Does NOT block the flow — returns
    warnings that the orchestrator/guard can surface to the user.
    """

    def check(self, extracted_data: dict[str, Any]) -> list[Contradiction]:
        issues: list[Contradiction] = []
        issues.extend(self._check_date_ordering(extracted_data))
        issues.extend(self._check_custody_vs_visitation(extracted_data))
        issues.extend(self._check_amount_contradictions(extracted_data))
        issues.extend(self._check_party_identity_overlap(extracted_data))
        if issues:
            logger.info(
                "ContradictionChecker found %d issue(s): %s",
                len(issues),
                ", ".join(c.code for c in issues),
            )
        return issues

    def _check_date_ordering(self, data: dict[str, Any]) -> list[Contradiction]:
        issues: list[Contradiction] = []
        date_pairs = [
            ("تاريخ الزواج", "تاريخ الطلاق", "تاريخ الزواج بعد تاريخ الطلاق"),
            ("تاريخ بداية العمل", "تاريخ انتهاء العمل", "تاريخ بداية العمل بعد تاريخ انتهائه"),
            ("تاريخ العقد", "تاريخ انتهاء العقد", "تاريخ العقد بعد تاريخ انتهائه"),
            ("تاريخ الواقعة", "تاريخ تقديم الشكوى", "الواقعة بعد تقديم الشكوى"),
        ]
        for field_a, field_b, desc in date_pairs:
            val_a = data.get(field_a)
            val_b = data.get(field_b)
            if not val_a or not val_b:
                continue
            date_a = parse_date(str(val_a))
            date_b = parse_date(str(val_b))
            if date_a and date_b and date_a > date_b:
                issues.append(Contradiction(
                    code="date_order",
                    field_a=field_a,
                    field_b=field_b,
                    description=f"لاحظت إن {desc} — يمكن فيه خطأ بالتواريخ.",
                    suggestion=f"ممكن تتأكد من {field_a} و{field_b}؟",
                ))
        return issues

    def _check_custody_vs_visitation(self, data: dict[str, Any]) -> list[Contradiction]:
        all_values = " ".join(str(v) for v in data.values())
        has_cohabitation = any(kw in all_values for kw in _COHABITATION_KEYWORDS)
        has_separation = any(kw in all_values for kw in _SEPARATION_KEYWORDS)
        if has_cohabitation and has_separation:
            return [Contradiction(
                code="custody_visitation_conflict",
                field_a="حضانة",
                field_b="رؤية",
                description=(
                    "ذكرت إن الطفل يقيم معك، "
                    "وفي نفس الوقت ذكرت إنك ممنوع من رؤيته."
                ),
                suggestion="هل تقصد إن فيه خلاف على أوقات الزيارة أو الاستضافة؟ وضّح لي عشان الصحيفة تكون دقيقة.",
            )]
        return []

    def _check_amount_contradictions(self, data: dict[str, Any]) -> list[Contradiction]:
        issues: list[Contradiction] = []
        salary = None
        compensation = None
        for key, value in data.items():
            num = parse_number(str(value)) if value else None
            if num is None:
                continue
            if "راتب" in key or "أجر" in key:
                salary = (key, num)
            if "تعويض" in key or "مطالبة" in key:
                compensation = (key, num)

        if salary and compensation:
            sal_key, sal_val = salary
            comp_key, comp_val = compensation
            if comp_val > 0 and sal_val > 0 and comp_val < sal_val:
                issues.append(Contradiction(
                    code="compensation_less_than_salary",
                    field_a=sal_key,
                    field_b=comp_key,
                    description="مبلغ التعويض اللي ذكرته أقل من الراتب الشهري.",
                    suggestion="هل تقصد مبلغ شهر واحد؟ أو المفروض يكون المبلغ أكبر عشان يشمل كامل الفترة؟",
                ))
        return issues

    def _check_party_identity_overlap(self, data: dict[str, Any]) -> list[Contradiction]:
        claimant_name = str(data.get("اسم المدعي", "")).strip()
        defendant_name = str(data.get("اسم المدعى عليه", "")).strip()
        if (
            claimant_name
            and defendant_name
            and len(claimant_name) > 3
            and claimant_name == defendant_name
        ):
            return [Contradiction(
                code="same_party_names",
                field_a="اسم المدعي",
                field_b="اسم المدعى عليه",
                description="اسم المدعي واسم المدعى عليه نفس الاسم.",
                suggestion="هل فيه خطأ بالأسماء؟ المفروض يكونون أشخاص مختلفين.",
            )]

        claimant_id = str(data.get("هوية المدعي", data.get("رقم هوية المدعي", ""))).strip()
        defendant_id = str(data.get("هوية المدعى عليه", data.get("رقم هوية المدعى عليه", ""))).strip()
        if claimant_id and defendant_id and len(claimant_id) >= 5 and claimant_id == defendant_id:
            return [Contradiction(
                code="same_party_ids",
                field_a="هوية المدعي",
                field_b="هوية المدعى عليه",
                description="رقم هوية المدعي والمدعى عليه نفس الرقم.",
                suggestion="ممكن تتأكد من أرقام الهويات؟ المفروض تكون مختلفة.",
            )]
        return []
