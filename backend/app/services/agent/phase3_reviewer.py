from __future__ import annotations

from app.models.petition import PetitionDraft, PetitionSectionName, ReviewIssue, ReviewReport
from app.models.session import Phase, Session, SessionStatus
from app.repositories.classification_repository import ClassificationRepository
from app.repositories.petition_repository import PetitionRepository
from app.services.agent.models import AgentTurnResult


class Phase3ReviewerService:
    def __init__(self, petition_repo: PetitionRepository, classification_repo: ClassificationRepository):
        self.petition_repo = petition_repo
        self.classification_repo = classification_repo

    async def review(self, session: Session) -> AgentTurnResult:
        petition = await self.petition_repo.get_latest_by_session(session.session_id)
        if petition is None:
            return AgentTurnResult(
                reply="لا توجد مسودة لمراجعتها بعد.",
                next_action="go_to_phase2",
            )

        report = await self._build_report(session, petition)
        petition.review_report = report
        await self.petition_repo.save(petition)
        session.phase = Phase.THREE
        session.status = SessionStatus.REVIEW

        return AgentTurnResult(
            reply="تم إعداد تقرير المراجعة القانونية.",
            next_action="review_ready",
            petition=petition,
            review=report,
        )

    async def handle_fix_request(self, session: Session, instruction: str, issue_id: str | None = None) -> AgentTurnResult:
        petition = await self.petition_repo.get_latest_by_session(session.session_id)
        if petition is None:
            return AgentTurnResult(
                reply="لا توجد صحيفة حالية لإصلاحها.",
                next_action="go_to_phase2",
            )

        target_issue = None
        if petition.review_report and issue_id:
            target_issue = next((issue for issue in petition.review_report.issues if issue.issue_id == issue_id), None)

        target_section = PetitionSectionName.FACTS
        if target_issue and target_issue.section:
            target_section = PetitionSectionName(target_issue.section)
        elif "أسانيد" in instruction:
            target_section = PetitionSectionName.EVIDENCE
        elif "طلبات" in instruction:
            target_section = PetitionSectionName.REQUESTS

        if target_section == PetitionSectionName.FACTS:
            petition.facts.content += f"\n\n[إصلاح]\n{instruction}"
        elif target_section == PetitionSectionName.EVIDENCE:
            petition.evidence.content += f"\n\n[إصلاح]\n{instruction}"
        else:
            petition.requests.content += f"\n\n[إصلاح]\n{instruction}"

        petition.version += 1
        petition.full_text = "\n\n".join(
            [petition.facts.content, petition.evidence.content, petition.requests.content]
        )
        await self.petition_repo.save(petition)
        report = await self._build_report(session, petition)
        petition.review_report = report
        await self.petition_repo.save(petition)

        return AgentTurnResult(
            reply="تم تطبيق الإصلاح وإعادة توليد تقرير المراجعة.",
            next_action="review_ready",
            petition=petition,
            review=report,
        )

    async def _build_report(self, session: Session, petition: PetitionDraft) -> ReviewReport:
        issues: list[ReviewIssue] = []
        case = await self.classification_repo.get_case(session.classification.case_id) if session.classification else None

        if case and case.requirements:
            for item in case.requirements.data_fields:
                if item.required and not session.extracted_data.get(item.name):
                    issues.append(
                        ReviewIssue(
                            severity="حرج",
                            category="موضوعي",
                            description=f"الحقل المطلوب غير موجود في البيانات: {item.name}",
                            suggestion="استكمل الحقل قبل الاعتماد النهائي.",
                            auto_fixable=False,
                            section=PetitionSectionName.FACTS,
                        )
                    )

        if "[يُوصى بالتحقق]" in petition.evidence.content:
            issues.append(
                ReviewIssue(
                    severity="تنبيه",
                    category="إثباتي",
                    description="الأسانيد تتضمن مراجع غير موثقة بالكامل.",
                    suggestion="استبدل أو ادعم المرجع بمصدر قانوني موثوق.",
                    auto_fixable=False,
                    section=PetitionSectionName.EVIDENCE,
                )
            )

        if len(petition.facts.content) < 180:
            issues.append(
                ReviewIssue(
                    severity="اقتراح",
                    category="شكلي",
                    description="قسم الوقائع مختصر جدًا مقارنة بمتطلبات صحيفة متكاملة.",
                    suggestion="أضف تفصيلًا أوضح للتسلسل الزمني والوقائع الجوهرية.",
                    auto_fixable=True,
                    section=PetitionSectionName.FACTS,
                )
            )

        if not petition.requests.content.strip():
            issues.append(
                ReviewIssue(
                    severity="حرج",
                    category="إجرائي",
                    description="قسم الطلبات فارغ.",
                    suggestion="أعد صياغة الطلبات النهائية بشكل صريح.",
                    auto_fixable=True,
                    section=PetitionSectionName.REQUESTS,
                )
            )

        critical_count = sum(1 for issue in issues if issue.severity == "حرج")
        warning_count = sum(1 for issue in issues if issue.severity == "تنبيه")
        suggestion_count = sum(1 for issue in issues if issue.severity == "اقتراح")
        score = max(0, 100 - (critical_count * 30) - (warning_count * 10) - (suggestion_count * 4))

        if critical_count >= 2 or session.flags.needs_human_review:
            recommendation = "يلزم محامٍ بشري"
        elif issues:
            recommendation = "يحتاج تعديلات"
        else:
            recommendation = "جاهز للرفع"

        summary = (
            "الصحيفة تبدو جاهزة مبدئيًا."
            if not issues
            else f"تم رصد {len(issues)} ملاحظات تتنوع بين حرجة وتنبيهية واقتراحية."
        )
        return ReviewReport(
            completeness_score=score,
            issues=issues,
            recommendation=recommendation,
            summary=summary,
        )
