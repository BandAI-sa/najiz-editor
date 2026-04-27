from __future__ import annotations

import re

from app.models.classification import (
    ClassificationNode,
    InterviewField,
    InterviewFieldOption,
    InterviewForm,
    InterviewSupportItem,
)
from app.models.common import InlineNotice
from app.models.session import Phase, Session, SessionStatus
from app.repositories.classification_repository import ClassificationRepository
from app.services.agent.models import AgentTurnResult


class Phase1InterviewerService:
    def __init__(self, repo: ClassificationRepository):
        self.repo = repo

    async def start(self, session: Session) -> AgentTurnResult:
        case = await self.repo.get_case(session.classification.case_id) if session.classification else None
        if case is None or case.requirements is None:
            notice = InlineNotice(
                tone="warning",
                icon="⚠️",
                title="تعذر تحميل نموذج البيانات",
                message="تعذر تحميل متطلبات هذا النوع من الدعاوى. يرجى اختيار تصنيف آخر أو المتابعة يدويًا.",
                aria_label="تنبيه: تعذر تحميل نموذج بيانات الدعوى.",
            )
            session.inline_notice = notice
            session.interview_form = None
            return AgentTurnResult(
                reply=notice.message,
                next_action="await_manual_support",
                inline_notice=notice,
            )

        form = self._build_interview_form(case)
        session.status = SessionStatus.INTERVIEW
        session.phase = Phase.ONE
        session.interview_form = form
        session.inline_notice = None
        session.flags.missing_fields = self._missing_field_labels(form, session.extracted_data)
        session.completion_percentage = self._completion_percentage(form, session.extracted_data)

        if not form.fields:
            session.status = SessionStatus.READY_TO_DRAFT
            session.phase = Phase.TWO
            session.completion_percentage = 100
            return AgentTurnResult(
                reply="لا توجد حقول إلزامية إضافية لهذا التصنيف. يمكنك الانتقال إلى الصياغة مباشرة.",
                next_action="go_to_phase2",
                interview_form=form,
            )

        return AgentTurnResult(
            reply="تم اعتماد نوع الدعوى. يرجى استكمال نموذج البيانات الإلزامية قبل الانتقال إلى الصياغة.",
            next_action="fill_form",
            interview_form=form,
        )

    async def process_turn(self, session: Session, message: str) -> AgentTurnResult:
        case = await self.repo.get_case(session.classification.case_id) if session.classification else None
        form = session.interview_form or (self._build_interview_form(case) if case and case.requirements else None)
        if form is None:
            return AgentTurnResult(
                reply="لا يتوفر نموذج منظم لهذا التصنيف حالياً. يرجى العودة لاختيار التصنيف أو المحاولة لاحقاً.",
                next_action="await_manual_support",
            )

        notice = InlineNotice(
            tone="warning",
            icon="⚠️",
            title="تم نقل جمع البيانات إلى النموذج",
            message="تم نقل الأسئلة الإلزامية إلى نموذج منظم. يرجى استكمال الحقول المطلوبة في النموذج للمتابعة.",
            aria_label="تنبيه: استخدم نموذج البيانات بدلاً من الرد عبر المحادثة.",
        )
        session.inline_notice = notice
        session.interview_form = form
        return AgentTurnResult(
            reply=notice.message,
            next_action="fill_form",
            interview_form=form,
            inline_notice=notice,
        )

    async def submit_form(self, session: Session, values: dict[str, str]) -> AgentTurnResult:
        case = await self.repo.get_case(session.classification.case_id) if session.classification else None
        if case is None or case.requirements is None:
            notice = InlineNotice(
                tone="warning",
                icon="⚠️",
                title="تعذر حفظ بيانات الدعوى",
                message="تعذر التحقق من نموذج هذه الدعوى حالياً. يرجى إعادة اختيار التصنيف أو المحاولة لاحقاً.",
                aria_label="تنبيه: تعذر حفظ بيانات النموذج.",
            )
            session.inline_notice = notice
            return AgentTurnResult(
                reply=notice.message,
                next_action="await_manual_support",
                inline_notice=notice,
            )

        form = session.interview_form or self._build_interview_form(case)
        normalized_values = self._normalize_form_values(form, values)
        form_errors = self._validate_form(form, normalized_values)

        if form_errors:
            notice = InlineNotice(
                tone="warning",
                icon="⚠️",
                title="أكمل الحقول الإلزامية",
                message="لا يمكن المتابعة قبل استكمال جميع الحقول الإلزامية الظاهرة في النموذج.",
                aria_label="تنبيه: توجد حقول إلزامية ناقصة في نموذج الدعوى.",
            )
            session.status = SessionStatus.INTERVIEW
            session.phase = Phase.ONE
            session.interview_form = form
            session.inline_notice = notice
            session.flags.missing_fields = [field.label for field in form.fields if field.key in form_errors]
            session.completion_percentage = self._completion_percentage(form, normalized_values, by_key=True)
            return AgentTurnResult(
                reply=notice.message,
                next_action="fill_form",
                metadata={"form_errors": form_errors},
                interview_form=form,
                inline_notice=notice,
            )

        for field in form.fields:
            value = normalized_values.get(field.key, "").strip()
            if value:
                session.extracted_data[field.label] = value

        session.extracted_field_names = sorted(session.extracted_data.keys())
        session.flags.missing_fields = []
        session.completion_percentage = 100
        session.status = SessionStatus.READY_TO_DRAFT
        session.phase = Phase.TWO
        session.interview_form = form
        session.inline_notice = None

        return AgentTurnResult(
            reply="اكتملت البيانات المطلوبة. يمكنك الآن اختيار صيغة صحيفة الدعوى ثم بدء الصياغة.",
            next_action="go_to_phase2",
            interview_form=form,
        )

    def _build_interview_form(self, case: ClassificationNode | None) -> InterviewForm:
        if case is None or case.requirements is None:
            return InterviewForm(
                title="نموذج بيانات الدعوى",
                description="لا تتوفر متطلبات تفصيلية لهذا التصنيف حالياً.",
                submit_label="اعتماد البيانات والمتابعة",
            )

        fields: list[InterviewField] = []
        support_items: list[InterviewSupportItem] = []

        for index, item in enumerate(case.requirements.data_fields, start=1):
            group_id, group_label = self._group_for_label(item.name)
            input_type = self._input_type_for_label(item.name)
            fields.append(
                InterviewField(
                    key=f"auth_{index:02d}",
                    label=item.name,
                    hint=item.hint or self._default_hint(item.name),
                    placeholder=self._placeholder_for_field(item.name, input_type),
                    aria_label=f"حقل إلزامي: {item.name}",
                    input_type=input_type,
                    group_id=group_id,
                    group_label=group_label,
                    required=item.required,
                )
            )
            support_items.append(
                InterviewSupportItem(
                    support_id=f"field_{index:02d}",
                    title=item.name,
                    summary="حقل إلزامي يجب تعبئته قبل الانتقال إلى الصياغة." if item.required else "حقل إضافي مرتبط بهذا النوع من الدعاوى.",
                    details=item.hint or f"يرتبط هذا الحقل مباشرة بمتطلبات دعوى {case.title} ويؤثر على اكتمال النموذج.",
                    aria_label=f"تفاصيل الدعم للحقل {item.name}",
                )
            )

        for index, item in enumerate(case.requirements.attachments, start=1):
            support_items.append(
                InterviewSupportItem(
                    support_id=f"attachment_{index:02d}",
                    title=item.name,
                    summary="مرفق إلزامي لهذا النوع من الدعاوى." if item.required else "مرفق داعم يمكن إرفاقه عند الحاجة.",
                    details=item.hint or f"هذا المرفق مرتبط بمتطلبات دعوى {case.title} ويستحسن توضيح مدى توفره قبل الصياغة النهائية.",
                    aria_label=f"تفاصيل الدعم للمرفق {item.name}",
                )
            )
            if item.required:
                fields.append(
                    InterviewField(
                        key=f"agent_attachment_{index:02d}",
                        label=f"هل المرفق التالي متوفر: {item.name}؟",
                        hint="هذا سؤال إضافي أضافه النظام استناداً إلى متطلبات نوع الدعوى.",
                        aria_label=f"سؤال إضافي حول توفر المرفق {item.name}",
                        input_type="radio",
                        group_id="evidence",
                        group_label="المرفقات والأسانيد",
                        required=True,
                        source="agent",
                        badge_label="سؤال إضافي",
                        options=[
                            InterviewFieldOption(label="نعم", value="نعم"),
                            InterviewFieldOption(label="لا", value="لا"),
                        ],
                    )
                )

        for index, note in enumerate(case.requirements.notes, start=1):
            support_items.append(
                InterviewSupportItem(
                    support_id=f"note_{index:02d}",
                    title=f"ملاحظة نظامية {index}",
                    summary="ملاحظة مرتبطة بمتطلبات هذه الدعوى.",
                    details=note,
                    aria_label=f"تفاصيل الملاحظة النظامية رقم {index}",
                )
            )

        for index, hint in enumerate(case.hints, start=1):
            support_items.append(
                InterviewSupportItem(
                    support_id=f"hint_{index:02d}",
                    title=f"إرشاد إجرائي {index}",
                    summary="إرشاد مختصر يساعد على تعبئة البيانات بدقة.",
                    details=hint,
                    aria_label=f"تفاصيل الإرشاد الإجرائي رقم {index}",
                )
            )

        for index, exception in enumerate(case.exceptions, start=1):
            support_items.append(
                InterviewSupportItem(
                    support_id=f"exception_{index:02d}",
                    title=f"تنبيه مهم {index}",
                    summary="تنبيه متعلق بنطاق هذه الدعوى أو استثناءاتها.",
                    details=exception,
                    aria_label=f"تفاصيل التنبيه المهم رقم {index}",
                )
            )

        return InterviewForm(
            title="نموذج بيانات الدعوى",
            description=f"أكمل جميع الحقول الإلزامية الخاصة بدعوى {case.title} قبل الانتقال إلى الصياغة.",
            submit_label="اعتماد البيانات والمتابعة",
            fields=fields,
            support_items=support_items,
        )

    @staticmethod
    def _group_for_label(label: str) -> tuple[str, str]:
        if any(token in label for token in ("المدعي", "المدعى", "الأطراف", "الوكيل", "الولي", "الورثة")):
            return ("parties", "بيانات الأطراف")
        if "تاريخ" in label:
            return ("dates", "التواريخ")
        if any(token in label for token in ("مرفق", "مستند", "صك", "وثيقة", "عقد", "إثبات", "شهادة")):
            return ("evidence", "المرفقات والأسانيد")
        return ("case_details", "تفاصيل الدعوى")

    @staticmethod
    def _input_type_for_label(label: str) -> str:
        if "تاريخ" in label:
            return "date"
        if label.startswith("هل ") or label.startswith("هل"):
            return "radio"
        if any(token in label for token in ("بيان", "موضوع", "سبب", "أسباب", "وصف", "تفصيل", "ملابسات")):
            return "textarea"
        return "text"

    @staticmethod
    def _default_hint(label: str) -> str:
        if "تاريخ" in label:
            return "أدخل التاريخ بصيغة واضحة كما هو متاح لديك."
        if any(token in label for token in ("هوية", "سجل")):
            return "أدخل الرقم أو البيان التعريفي كما هو وارد في المستندات الرسمية."
        if any(token in label for token in ("عنوان", "العنوان")):
            return "أدخل العنوان الوطني أو عنوان التبليغ المعتمد."
        return "أدخل البيانات كما وردت في المستندات أو الوقائع المتاحة لديك."

    @staticmethod
    def _placeholder_for_field(label: str, input_type: str) -> str:
        if input_type == "date":
            return ""
        if input_type == "textarea":
            return f"اكتب تفاصيل {label}"
        return f"أدخل {label}"

    @staticmethod
    def _normalize_form_values(form: InterviewForm, values: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        incoming = values or {}
        for field in form.fields:
            raw_value = incoming.get(field.key, "")
            normalized[field.key] = raw_value.strip() if isinstance(raw_value, str) else str(raw_value).strip()
        return normalized

    @staticmethod
    def _validate_form(form: InterviewForm, values: dict[str, str]) -> dict[str, str]:
        errors: dict[str, str] = {}
        for field in form.fields:
            value = values.get(field.key, "").strip()
            if field.required and not value:
                errors[field.key] = "هذا الحقل إلزامي."
                continue
            if field.input_type == "date" and value and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                errors[field.key] = "يرجى إدخال التاريخ بصيغة صحيحة."
                continue
            if field.input_type == "radio" and value:
                allowed = {option.value for option in field.options}
                if value not in allowed:
                    errors[field.key] = "يرجى اختيار إجابة صحيحة."
        return errors

    @classmethod
    def _missing_field_labels(
        cls,
        form: InterviewForm,
        extracted_data: dict[str, str],
    ) -> list[str]:
        missing: list[str] = []
        for field in form.fields:
            value = str(extracted_data.get(field.label, "")).strip()
            if field.required and not value:
                missing.append(field.label)
        return missing

    @classmethod
    def _completion_percentage(
        cls,
        form: InterviewForm,
        values: dict[str, str],
        *,
        by_key: bool = False,
    ) -> int:
        required_fields = [field for field in form.fields if field.required]
        if not required_fields:
            return 100

        completed = 0
        for field in required_fields:
            raw_value = values.get(field.key if by_key else field.label, "")
            if str(raw_value).strip():
                completed += 1

        return round((completed / len(required_fields)) * 100)
