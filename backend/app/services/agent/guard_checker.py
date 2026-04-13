from __future__ import annotations

from app.models.common import GuardIssue, SeverityLevel
from app.models.session import Session
from app.repositories.classification_repository import ClassificationRepository
from app.utils.text import parse_date, parse_number


class GuardChecker:
    def __init__(self, repo: ClassificationRepository, turn_limit: int, dispute_value_threshold: int):
        self.repo = repo
        self.turn_limit = turn_limit
        self.dispute_value_threshold = dispute_value_threshold

    async def check(self, session: Session) -> list[GuardIssue]:
        issues: list[GuardIssue] = []
        issues.extend(self._check_turn_limit(session))
        issues.extend(self._check_dispute_value(session))
        issues.extend(self._check_date_contradictions(session))
        issues.extend(await self._check_missing_attachments(session))
        return issues

    def _check_turn_limit(self, session: Session) -> list[GuardIssue]:
        if session.message_count <= self.turn_limit:
            return []
        return [
            GuardIssue(
                code="turn_limit",
                severity=SeverityLevel.WARNING,
                title="طول الحوار",
                description="تجاوزت الجلسة الحد الموصى به لعدد الرسائل.",
                recommendation="يفضل مراجعة البيانات الحالية أو التحول لتدخل بشري.",
            )
        ]

    def _check_dispute_value(self, session: Session) -> list[GuardIssue]:
        issues: list[GuardIssue] = []
        for key, value in session.extracted_data.items():
            if "مبلغ" in key or "قيمة" in key or "تعويض" in key:
                numeric = parse_number(str(value))
                if numeric and numeric >= self.dispute_value_threshold:
                    issues.append(
                        GuardIssue(
                            code="high_value_dispute",
                            severity=SeverityLevel.CRITICAL,
                            title="قيمة نزاع مرتفعة",
                            description="القيمة المالية الظاهرة مرتفعة وتستدعي حذرًا إضافيًا.",
                            recommendation="يوصى بمراجعة محامٍ بشري قبل الاعتماد النهائي.",
                            metadata={"field": key, "value": numeric},
                        )
                    )
        return issues

    def _check_date_contradictions(self, session: Session) -> list[GuardIssue]:
        parsed_dates = {
            key: parse_date(str(value))
            for key, value in session.extracted_data.items()
            if "تاريخ" in key
        }
        marriage = parsed_dates.get("تاريخ الزواج")
        divorce = parsed_dates.get("تاريخ الطلاق")
        if marriage and divorce and marriage > divorce:
            return [
                GuardIssue(
                    code="date_contradiction",
                    severity=SeverityLevel.CRITICAL,
                    title="تعارض زمني",
                    description="تاريخ الزواج يأتي بعد تاريخ الطلاق في البيانات الحالية.",
                    recommendation="تحقق من التواريخ قبل متابعة الصياغة.",
                )
            ]
        return []

    async def _check_missing_attachments(self, session: Session) -> list[GuardIssue]:
        if session.classification is None:
            return []
        case = await self.repo.get_case(session.classification.case_id)
        if case is None or case.requirements is None:
            return []
        if not any("مستند" in key or "مرفق" in key for key in session.extracted_data):
            required = [item.name for item in case.requirements.attachments if item.required]
            if required:
                return [
                    GuardIssue(
                        code="missing_attachments",
                        severity=SeverityLevel.WARNING,
                        title="مرفقات أساسية غير مثبتة",
                        description="لا يوجد في البيانات الحالية ما يثبت توفر المرفقات المطلوبة.",
                        recommendation="أكد المستندات المتاحة قبل الاعتماد على المسودة.",
                        metadata={"attachments": required},
                    )
                ]
        return []
