"""Structured form-based interview service.

Restored from the original main branch to coexist with the
conversational SmartInterviewerService in hybrid mode.
"""

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
from app.repositories.classification_repository import (
    ClassificationRepository,
)
from app.services.agent.models import AgentTurnResult


SUPPLEMENTARY_OPTIONAL_FIELDS: tuple[dict[str, str], ...] = (
    {
        "label": "بيانات الوكيل",
        "key": "supp_01",
        "group_id": "agent_info",
        "group_label": "بيانات الوكيل",
        "hint": "اختياري: أضف صفة الوكيل وبياناته كما تفضّل.",
        "placeholder": "اكتب بيانات الوكيل (اختياري)",
        "input_type": "textarea",
    },
    {
        "label": "رقم الوكالة",
        "key": "supp_02",
        "group_id": "agent_info",
        "group_label": "بيانات الوكيل",
        "hint": "اختياري: رقم الوكالة وتاريخها وجهة إصدارها.",
        "placeholder": "أدخل رقم الوكالة (اختياري)",
        "input_type": "text",
    },
    {
        "label": "البريد الإلكتروني",
        "key": "supp_03",
        "group_id": "contact",
        "group_label": "وسائل التواصل",
        "hint": "اختياري: يفضّل بريدًا نشطًا للتواصل.",
        "placeholder": "name@example.com",
        "input_type": "text",
    },
    {
        "label": "الجوال",
        "key": "supp_04",
        "group_id": "contact",
        "group_label": "وسائل التواصل",
        "hint": "اختياري: رقم جوال للتواصل عند الحاجة.",
        "placeholder": "05XXXXXXXX",
        "input_type": "text",
    },
    {
        "label": "العنوان الوطني",
        "key": "supp_05",
        "group_id": "national_address",
        "group_label": "العنوان الوطني",
        "hint": "اختياري: العنوان الوطني أو عنوان التبليغ.",
        "placeholder": "اكتب العنوان الوطني (اختياري)",
        "input_type": "textarea",
    },
    {
        "label": "رقم الهوية",
        "key": "supp_06",
        "group_id": "party_extra",
        "group_label": "معلومات إضافية عن الأطراف",
        "hint": "اختياري: أضف الرقم إذا كان متاحًا لديك.",
        "placeholder": "أدخل رقم الهوية (اختياري)",
        "input_type": "text",
    },
    {
        "label": "بيانات إضافية للأطراف",
        "key": "supp_07",
        "group_id": "party_extra",
        "group_label": "معلومات إضافية عن الأطراف",
        "hint": "اختياري: أي تفاصيل داعمة عن الأطراف.",
        "placeholder": "اكتب أي بيانات إضافية (اختياري)",
        "input_type": "textarea",
    },
    {
        "label": "تقدير المطالبة",
        "key": "supp_08",
        "group_id": "claim_finance",
        "group_label": "تفاصيل المطالبة المالية",
        "hint": "اختياري: تقدير مبدئي للمطالبة المالية إن توفر.",
        "placeholder": "أدخل قيمة تقديرية (اختياري)",
        "input_type": "number",
    },
)

GENERATED_LATER_FIELDS: tuple[str, ...] = (
    "بيانات الوكيل",
    "رقم الوكالة",
    "العنوان الوطني",
    "رقم الهوية",
    "البريد الإلكتروني",
    "الجوال",
    "تقدير المطالبة",
    "بيانات إضافية للأطراف",
)


class StructuredInterviewerService:
    """Generates dynamic structured forms from CaseRequirements
    and validates form submissions.

    This is the original interview experience from the main branch,
    extracted into its own service so it can coexist with the
    conversational SmartInterviewerService.
    """

    def __init__(self, repo: ClassificationRepository):
        self.repo = repo

    async def start(
        self, session: Session,
    ) -> AgentTurnResult:
        case = (
            await self.repo.get_case(
                session.classification.case_id,
            )
            if session.classification
            else None
        )
        if case is None or case.requirements is None:
            return AgentTurnResult(
                reply=(
                    "تعذر تحميل متطلبات هذا النوع من "
                    "الدعاوى."
                ),
                next_action="await_manual_support",
            )

        form = self._build_interview_form(case)
        session.interview_form = form
        session.inline_notice = None
        session.flags.missing_fields = (
            self._missing_field_labels(form, session.extracted_data)
        )
        session.completion_percentage = (
            self._completion_percentage(
                form, session.extracted_data,
            )
        )

        if session.completion_percentage == 100:
            return self._build_enrichment_offer_result(session)

        return AgentTurnResult(
            reply=(
                "تم اعتماد نوع الدعوى بنجاح. "
                "أكمل البيانات الأساسية في النموذج، ثم "
                "يمكنك المتابعة للصياغة مباشرة."
            ),
            next_action="fill_form",
            interview_form=form,
        )

    async def process_turn(
        self, session: Session, message: str,
    ) -> AgentTurnResult:
        case = (
            await self.repo.get_case(
                session.classification.case_id,
            )
            if session.classification
            else None
        )
        form = session.interview_form or (
            self._build_interview_form(case)
            if case and case.requirements
            else None
        )
        if form is not None:
            form = self._normalize_form_definition(form)
        if form is None:
            return AgentTurnResult(
                reply=(
                    "لا يتوفر نموذج منظم لهذا التصنيف "
                    "حالياً. يرجى العودة لاختيار التصنيف "
                    "أو المحاولة لاحقاً."
                ),
                next_action="await_manual_support",
            )

        notice = InlineNotice(
            tone="warning",
            icon="⚠️",
            title="تم نقل جمع البيانات إلى النموذج",
            message=(
                "لضمان الدقة، يتم استكمال البيانات الأساسية "
                "من خلال النموذج المنظّم. يمكنك تعبئة الحقول "
                "المطلوبة ثم المتابعة."
            ),
            aria_label=(
                "تنبيه: استخدم نموذج البيانات بدلاً من "
                "الرد عبر المحادثة."
            ),
        )
        session.inline_notice = notice
        session.interview_form = form
        return AgentTurnResult(
            reply=notice.message,
            next_action="fill_form",
            interview_form=form,
            inline_notice=notice,
        )

    async def submit_form(
        self, session: Session, values: dict[str, str],
    ) -> AgentTurnResult:
        case = (
            await self.repo.get_case(
                session.classification.case_id,
            )
            if session.classification
            else None
        )
        if case is None or case.requirements is None:
            notice = InlineNotice(
                tone="warning",
                icon="⚠️",
                title="تعذر حفظ بيانات الدعوى",
                message=(
                    "تعذر التحقق من نموذج هذه الدعوى "
                    "حالياً. يرجى إعادة اختيار التصنيف أو "
                    "المحاولة لاحقاً."
                ),
                aria_label=(
                    "تنبيه: تعذر حفظ بيانات النموذج."
                ),
            )
            session.inline_notice = notice
            return AgentTurnResult(
                reply=notice.message,
                next_action="await_manual_support",
                inline_notice=notice,
            )

        form = self._normalize_form_definition(
            session.interview_form
            or self._build_interview_form(case),
        )
        is_supplementary_form = (
            form.variant == "supplementary_optional"
            or session.metadata.get("supplementary_state")
            == "collecting"
        )
        normalized_values = self._normalize_form_values(
            form, values,
        )
        form_errors = self._validate_form(
            form, normalized_values,
        )

        if form_errors:
            notice = InlineNotice(
                tone="warning",
                icon="⚠️",
                title=(
                    "تحقّق من البيانات المدخلة"
                    if is_supplementary_form
                    else "يلزم استكمال الحقول الأساسية"
                ),
                message=(
                    "يرجى مراجعة الحقول الأساسية غير المكتملة "
                    "للمتابعة."
                    if not is_supplementary_form
                    else "يمكنك تعديل الحقول التي تحتوي تنبيهًا، "
                    "أو ترك البيانات الاختيارية فارغة ثم المتابعة."
                ),
                aria_label=(
                    "تنبيه: توجد بيانات بحاجة للمراجعة في "
                    "النموذج."
                ),
            )
            session.status = SessionStatus.INTERVIEW
            session.phase = Phase.ONE
            session.interview_form = form
            session.inline_notice = notice
            session.flags.missing_fields = [
                field.label
                for field in form.fields
                if field.key in form_errors
            ]
            session.completion_percentage = (
                self._completion_percentage(
                    form, normalized_values, by_key=True,
                )
            )
            return AgentTurnResult(
                reply=notice.message,
                next_action=(
                    "fill_supplementary_form"
                    if is_supplementary_form
                    else "fill_form"
                ),
                metadata={"form_errors": form_errors},
                interview_form=form,
                inline_notice=notice,
            )

        for field in form.fields:
            value = normalized_values.get(
                field.key, "",
            ).strip()
            if value:
                session.extracted_data[field.label] = value

        session.extracted_field_names = sorted(
            session.extracted_data.keys(),
        )
        session.interview_form = form
        session.inline_notice = None

        if is_supplementary_form:
            session.metadata["supplementary_state"] = "completed"
            session.flags.missing_fields = []
            session.completion_percentage = 100
            return self._finalize_ready_for_draft(
                session,
                reply=(
                    "تم حفظ البيانات الإضافية بنجاح. "
                    "يمكنك الآن اختيار صيغة الصحيفة والانتقال "
                    "إلى الصياغة."
                ),
            )

        session.flags.missing_fields = []
        session.completion_percentage = 100
        return self._build_enrichment_offer_result(session)

    async def handle_enrichment_decision(
        self, session: Session, action: str,
    ) -> AgentTurnResult:
        normalized_action = (action or "").strip().lower()
        if normalized_action == "skip":
            session.metadata["supplementary_state"] = "skipped"
            return self._finalize_ready_for_draft(
                session,
                reply=(
                    "تم التخطي. ننتقل الآن إلى اختيار صيغة "
                    "الصحيفة ثم بدء الصياغة."
                ),
            )

        supplementary_form = self._build_supplementary_form()
        session.status = SessionStatus.INTERVIEW
        session.phase = Phase.ONE
        session.metadata["supplementary_state"] = "collecting"
        session.interview_form = supplementary_form
        session.inline_notice = InlineNotice(
            tone="info",
            icon="ℹ️",
            title="بيانات إضافية اختيارية",
            message=(
                "يمكنك تعبئة البيانات الاختيارية المتاحة الآن، "
                "أو ترك أي حقل والانتقال مباشرة."
            ),
            aria_label="تنبيه: هذه البيانات اختيارية وغير مانعة للمتابعة.",
        )
        return AgentTurnResult(
            reply=(
                "ممتاز. هذه خطوة اختيارية لتحسين جودة الصحيفة "
                "قبل الصياغة النهائية."
            ),
            next_action="fill_supplementary_form",
            interview_form=supplementary_form,
            inline_notice=session.inline_notice,
            metadata=self._intake_field_groups_metadata(),
        )

    # ── Form builder ─────────────────────────────────────

    def _build_enrichment_offer_result(
        self, session: Session,
    ) -> AgentTurnResult:
        session.status = SessionStatus.INTERVIEW
        session.phase = Phase.ONE
        session.metadata["supplementary_state"] = "awaiting_decision"
        session.inline_notice = InlineNotice(
            tone="info",
            icon="ℹ️",
            title="بيانات إضافية اختيارية",
            message=(
                "اكتملت البيانات الأساسية. يمكنك إضافة "
                "معلومات اختيارية لتحسين الصحيفة قبل "
                "الصياغة النهائية، أو المتابعة مباشرة."
            ),
            aria_label=(
                "تنبيه: خطوة بيانات إضافية اختيارية قبل الصياغة."
            ),
        )
        return AgentTurnResult(
            reply=(
                "اكتملت البيانات الأساسية. إذا رغبت، يمكنك "
                "إضافة بيانات اختيارية الآن لتحسين الصياغة."
            ),
            next_action="offer_optional_enrichment",
            inline_notice=session.inline_notice,
            metadata=self._intake_field_groups_metadata(),
        )

    def _finalize_ready_for_draft(
        self, session: Session, *, reply: str,
    ) -> AgentTurnResult:
        session.status = SessionStatus.READY_TO_DRAFT
        session.phase = Phase.TWO
        session.completion_percentage = 100
        session.flags.missing_fields = []
        session.inline_notice = None
        session.metadata.pop("current_field", None)
        return AgentTurnResult(
            reply=reply,
            next_action="go_to_phase2",
            metadata=self._intake_field_groups_metadata(),
        )

    def _build_supplementary_form(self) -> InterviewForm:
        fields: list[InterviewField] = []
        for field in SUPPLEMENTARY_OPTIONAL_FIELDS:
            fields.append(
                InterviewField(
                    key=field["key"],
                    label=field["label"],
                    hint=field["hint"],
                    placeholder=field["placeholder"],
                    aria_label=f"حقل اختياري: {field['label']}",
                    input_type=field["input_type"],  # type: ignore[arg-type]
                    group_id=field["group_id"],
                    group_label=field["group_label"],
                    required=False,
                    source="agent",
                    collection_group="supplementary_optional",
                )
            )
        return InterviewForm(
            title="بيانات إضافية اختيارية",
            description=(
                "هذه الحقول اختيارية بالكامل. يمكنك تعبئة ما "
                "يتوفر لديك لتحسين جودة الصحيفة."
            ),
            submit_label="حفظ البيانات الإضافية والمتابعة",
            variant="supplementary_optional",
            helper_text=(
                "البيانات الأساسية مكتملة. أي تفاصيل إضافية هنا "
                "تساعد على صياغة أدق، ويمكن تجاوزها."
            ),
            fields=fields,
            support_items=[],
        )

    @staticmethod
    def _intake_field_groups_metadata() -> dict[str, list[str]]:
        return {
            "core_required": [
                "بيانات المدعي",
                "بيانات المدعى عليه",
                "وصف الطلب الأساسي",
                "الوقائع الجوهرية",
                "التواريخ الجوهرية",
                "المستندات المتاحة",
            ],
            "supplementary_optional": [
                field["label"] for field in SUPPLEMENTARY_OPTIONAL_FIELDS
            ],
            "generated_later": list(GENERATED_LATER_FIELDS),
        }

    def _build_interview_form(
        self, case: ClassificationNode | None,
    ) -> InterviewForm:
        if case is None or case.requirements is None:
            return InterviewForm(
                title="نموذج بيانات الدعوى",
                description=(
                    "لا تتوفر متطلبات تفصيلية لهذا "
                    "التصنيف حالياً."
                ),
                submit_label="اعتماد البيانات والمتابعة",
                variant="core_required",
            )

        fields: list[InterviewField] = []
        support_items: list[InterviewSupportItem] = []

        for index, item in enumerate(
            case.requirements.data_fields, start=1,
        ):
            group_id, group_label = self._group_for_label(
                item.name,
            )
            input_type = self._input_type_for_label(
                item.name,
            )
            fields.append(
                InterviewField(
                    key=f"auth_{index:02d}",
                    label=item.name,
                    hint=(
                        item.hint
                        or self._default_hint(item.name)
                    ),
                    placeholder=self._placeholder_for_field(
                        item.name, input_type,
                    ),
                    aria_label=f"حقل أساسي: {item.name}",
                    input_type=input_type,
                    group_id=group_id,
                    group_label=group_label,
                    required=item.required,
                    collection_group=(
                        "core_required"
                        if item.required
                        else "supplementary_optional"
                    ),
                    options=self._options_for_field(
                        item.name, input_type,
                    ),
                )
            )
            req_label = (
                "بيان أساسي يُستحسن إدخاله في هذه "
                "المرحلة لضمان اكتمال الصحيفة."
                if item.required
                else "حقل إضافي مرتبط بهذا النوع من "
                "الدعاوى."
            )
            support_items.append(
                InterviewSupportItem(
                    support_id=f"field_{index:02d}",
                    title=item.name,
                    summary=req_label,
                    details=(
                        item.hint
                        or (
                            "يرتبط هذا الحقل مباشرة "
                            "بمتطلبات دعوى "
                            f"{case.title} ويؤثر على "
                            "اكتمال النموذج."
                        )
                    ),
                    aria_label=(
                        "تفاصيل الدعم للحقل "
                        f"{item.name}"
                    ),
                )
            )

        for index, item in enumerate(
            case.requirements.attachments, start=1,
        ):
            att_label = (
                "مرفق أساسي لهذا النوع من الدعاوى."
                if item.required
                else "مرفق داعم يمكن إرفاقه عند الحاجة."
            )
            support_items.append(
                InterviewSupportItem(
                    support_id=f"attachment_{index:02d}",
                    title=item.name,
                    summary=att_label,
                    details=(
                        item.hint
                        or (
                            "هذا المرفق مرتبط بمتطلبات "
                            f"دعوى {case.title} "
                            "ويستحسن توضيح مدى توفره "
                            "قبل الصياغة النهائية."
                        )
                    ),
                    aria_label=(
                        "تفاصيل الدعم للمرفق "
                        f"{item.name}"
                    ),
                )
            )
            if item.required:
                fields.append(
                    InterviewField(
                        key=(
                            f"agent_attachment_{index:02d}"
                        ),
                        label=(
                            "هل المرفق التالي متوفر: "
                            f"{item.name}؟"
                        ),
                        hint=(
                            "هذا سؤال إضافي أضافه النظام "
                            "استناداً إلى متطلبات نوع "
                            "الدعوى."
                        ),
                        aria_label=(
                            "سؤال إضافي حول توفر المرفق "
                            f"{item.name}"
                        ),
                        input_type="radio",
                        group_id="evidence",
                        group_label="المرفقات والأسانيد",
                        required=True,
                        source="agent",
                        collection_group="core_required",
                        badge_label="سؤال إضافي",
                        options=[
                            InterviewFieldOption(
                                label="نعم", value="نعم",
                            ),
                            InterviewFieldOption(
                                label="لا", value="لا",
                            ),
                        ],
                    )
                )

        for index, note in enumerate(
            case.requirements.notes, start=1,
        ):
            support_items.append(
                InterviewSupportItem(
                    support_id=f"note_{index:02d}",
                    title=f"ملاحظة نظامية {index}",
                    summary=(
                        "ملاحظة مرتبطة بمتطلبات هذه "
                        "الدعوى."
                    ),
                    details=note,
                    aria_label=(
                        "تفاصيل الملاحظة النظامية رقم "
                        f"{index}"
                    ),
                )
            )

        for index, hint in enumerate(
            case.hints, start=1,
        ):
            support_items.append(
                InterviewSupportItem(
                    support_id=f"hint_{index:02d}",
                    title=f"إرشاد إجرائي {index}",
                    summary=(
                        "إرشاد مختصر يساعد على تعبئة "
                        "البيانات بدقة."
                    ),
                    details=hint,
                    aria_label=(
                        "تفاصيل الإرشاد الإجرائي رقم "
                        f"{index}"
                    ),
                )
            )

        for index, exception in enumerate(
            case.exceptions, start=1,
        ):
            support_items.append(
                InterviewSupportItem(
                    support_id=f"exception_{index:02d}",
                    title=f"تنبيه مهم {index}",
                    summary=(
                        "تنبيه متعلق بنطاق هذه الدعوى "
                        "أو استثناءاتها."
                    ),
                    details=exception,
                    aria_label=(
                        "تفاصيل التنبيه المهم رقم "
                        f"{index}"
                    ),
                )
            )

        return self._normalize_form_definition(
            InterviewForm(
                title="نموذج بيانات الدعوى",
                description=(
                    "أكمل البيانات الأساسية الخاصة "
                    f"بدعوى {case.title}، ثم يمكنك "
                    "المتابعة مباشرة. البيانات الإضافية "
                    "تبقى اختيارية."
                ),
                submit_label="اعتماد البيانات والمتابعة",
                variant="core_required",
                helper_text=(
                    "يركّز هذا النموذج على البيانات "
                    "الأساسية المطلوبة للصياغة."
                ),
                fields=fields,
                support_items=support_items,
            )
        )

    # ── Helpers ───────────────────────────────────────────

    @staticmethod
    def _group_for_label(label: str) -> tuple[str, str]:
        party_tokens = (
            "المدعي", "المدعى", "الأطراف",
            "الوكيل", "الولي", "الورثة",
        )
        if any(t in label for t in party_tokens):
            return ("parties", "بيانات الأطراف")
        if "تاريخ" in label:
            return ("dates", "التواريخ")
        evidence_tokens = (
            "مرفق", "مستند", "صك", "وثيقة",
            "عقد", "إثبات", "شهادة",
        )
        if any(t in label for t in evidence_tokens):
            return ("evidence", "المرفقات والأسانيد")
        return ("case_details", "تفاصيل الدعوى")

    @staticmethod
    def _input_type_for_label(label: str) -> str:
        if "تاريخ" in label:
            return "date"
        if label.strip().startswith("هل"):
            return "radio"
        textarea_tokens = (
            "بيان", "موضوع", "سبب", "أسباب",
            "وصف", "تفصيل", "ملابسات",
        )
        if any(t in label for t in textarea_tokens):
            return "textarea"
        return "text"

    @classmethod
    def _options_for_field(
        cls, label: str, input_type: str,
    ) -> list[InterviewFieldOption]:
        if input_type != "radio":
            return []
        if label.strip().startswith("هل"):
            return [
                InterviewFieldOption(
                    label="نعم", value="نعم",
                ),
                InterviewFieldOption(
                    label="لا", value="لا",
                ),
            ]
        return []

    @classmethod
    def _normalize_form_definition(
        cls, form: InterviewForm,
    ) -> InterviewForm:
        normalized_fields = [
            field.model_copy(
                update={
                    "options": (
                        field.options
                        or cls._options_for_field(
                            field.label, field.input_type,
                        )
                    ),
                }
            )
            for field in form.fields
        ]
        return form.model_copy(
            update={"fields": normalized_fields},
        )

    @staticmethod
    def _default_hint(label: str) -> str:
        if "تاريخ" in label:
            return (
                "أدخل التاريخ بصيغة واضحة كما هو "
                "متاح لديك."
            )
        if any(t in label for t in ("هوية", "سجل")):
            return (
                "أدخل الرقم أو البيان التعريفي كما هو "
                "وارد في المستندات الرسمية."
            )
        if any(t in label for t in ("عنوان", "العنوان")):
            return (
                "أدخل العنوان الوطني أو عنوان التبليغ "
                "المعتمد."
            )
        return (
            "أدخل البيانات كما وردت في المستندات أو "
            "الوقائع المتاحة لديك."
        )

    @staticmethod
    def _placeholder_for_field(
        label: str, input_type: str,
    ) -> str:
        if input_type == "date":
            return ""
        if input_type == "textarea":
            return f"اكتب تفاصيل {label}"
        return f"أدخل {label}"

    @staticmethod
    def _normalize_form_values(
        form: InterviewForm, values: dict[str, str],
    ) -> dict[str, str]:
        normalized: dict[str, str] = {}
        incoming = values or {}
        for field in form.fields:
            raw_value = incoming.get(field.key, "")
            normalized[field.key] = (
                raw_value.strip()
                if isinstance(raw_value, str)
                else str(raw_value).strip()
            )
        return normalized

    @staticmethod
    def _validate_form(
        form: InterviewForm, values: dict[str, str],
    ) -> dict[str, str]:
        errors: dict[str, str] = {}
        for field in form.fields:
            value = values.get(field.key, "").strip()
            if field.required and not value:
                errors[field.key] = "يرجى إكمال هذا الحقل."
                continue
            if (
                field.input_type == "date"
                and value
                and not re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}", value,
                )
            ):
                errors[field.key] = (
                    "يرجى إدخال التاريخ بصيغة صحيحة."
                )
                continue
            if field.input_type == "radio" and value:
                allowed = {
                    opt.value for opt in field.options
                }
                if value not in allowed:
                    errors[field.key] = (
                        "يرجى اختيار إجابة صحيحة."
                    )
        return errors

    @classmethod
    def _missing_field_labels(
        cls,
        form: InterviewForm,
        extracted_data: dict[str, str],
    ) -> list[str]:
        missing: list[str] = []
        for field in form.fields:
            value = str(
                extracted_data.get(field.label, ""),
            ).strip()
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
        required_fields = [
            f for f in form.fields if f.required
        ]
        if not required_fields:
            return 100

        completed = 0
        for field in required_fields:
            lookup = field.key if by_key else field.label
            raw_value = values.get(lookup, "")
            if str(raw_value).strip():
                completed += 1

        return round(
            (completed / len(required_fields)) * 100,
        )
