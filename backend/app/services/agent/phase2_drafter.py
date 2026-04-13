from __future__ import annotations

import logging
from textwrap import dedent
from typing import AsyncIterator

from app.models.classification import ClassificationNode, RequirementItem
from app.models.petition import PetitionDraft, PetitionSection, PetitionSectionName
from app.models.session import Phase, Session, SessionStatus
from app.repositories.classification_repository import ClassificationRepository
from app.repositories.petition_repository import PetitionRepository
from app.services.agent.models import AgentTurnResult
from app.services.agent.phase2_evidence import Phase2EvidenceService
from app.services.llm.base import LLMClient
from app.utils.text import chunk_text


logger = logging.getLogger("uvicorn.error")


class Phase2DrafterService:
    def __init__(
        self,
        repo: PetitionRepository,
        classification_repo: ClassificationRepository,
        evidence_service: Phase2EvidenceService,
        llm: LLMClient,
        draft_temperature: float = 0.4,
    ):
        self.repo = repo
        self.classification_repo = classification_repo
        self.evidence_service = evidence_service
        self.llm = llm
        self.draft_temperature = draft_temperature

    async def draft(self, session: Session) -> AgentTurnResult:
        if session.classification is None:
            return AgentTurnResult(
                reply="لا يمكن بدء الصياغة قبل اعتماد التصنيف.",
                next_action="confirm_classification",
            )
        session.status = SessionStatus.DRAFTING
        session.phase = Phase.TWO

        case_context = await self.classification_repo.get_case(session.classification.case_id)
        facts = await self._build_facts(session, case_context)
        evidence = await self.evidence_service.build(
            selection=session.classification,
            facts_text=facts.content,
            extracted_data=session.extracted_data,
            case_context=case_context,
        )
        requests = await self._build_requests(session, case_context, facts.content, evidence.content)
        full_text = self._merge_sections(facts, evidence, requests)

        petition = PetitionDraft(
            session_id=session.session_id,
            version=session.petition_version + 1,
            facts=facts,
            evidence=evidence,
            requests=requests,
            full_text=full_text,
            metadata={"classification": session.classification.model_dump(mode="json")},
        )
        await self.repo.create(petition)
        session.petition_version = petition.version
        session.status = SessionStatus.DRAFT_READY

        return AgentTurnResult(
            reply="تم توليد مسودة الصحيفة بصياغة أقوى ومهيأة للمراجعة والتحسين.",
            next_action="review_draft",
            petition=petition,
        )

    async def handle_edit_request(self, session: Session, instruction: str) -> AgentTurnResult:
        petition = await self.repo.get_latest_by_session(session.session_id)
        if petition is None:
            return await self.draft(session)

        section_name = self._choose_section(instruction)
        if section_name == PetitionSectionName.FACTS:
            petition.facts.content = f"{petition.facts.content}\n\n[تعديل مطلوب]\n{instruction}"
        elif section_name == PetitionSectionName.EVIDENCE:
            petition.evidence.content = f"{petition.evidence.content}\n\n[تحديث مطلوب]\n{instruction}"
        else:
            petition.requests.content = f"{petition.requests.content}\n\n[تعديل مطلوب]\n{instruction}"

        petition.version += 1
        petition.full_text = self._merge_sections(petition.facts, petition.evidence, petition.requests)
        await self.repo.save(petition)
        session.petition_version = petition.version
        session.status = SessionStatus.DRAFT_READY

        return AgentTurnResult(
            reply="تم تعديل القسم المطلوب وإصدار نسخة أحدث من الصحيفة.",
            next_action="review_draft",
            petition=petition,
        )

    async def stream(self, session: Session) -> AsyncIterator[dict]:
        try:
            result = await self.draft(session)
            petition = result.petition
            if petition is None:
                yield {"type": "error", "message": result.reply}
                return

            logger.info(
                "Draft stream started: session_id=%s petition_id=%s version=%s",
                session.session_id,
                petition.petition_id,
                petition.version,
            )
            for section in (petition.facts, petition.evidence, petition.requests):
                logger.info(
                    "Draft stream section prepared: session_id=%s section=%s chars=%s",
                    session.session_id,
                    section.name,
                    len(section.content),
                )
                yield {"type": "start", "section": section.name}
                for chunk in chunk_text(section.content):
                    yield {"type": "chunk", "section": section.name, "content": chunk}
                yield {"type": "end", "section": section.name}
            yield {
                "type": "complete",
                "petition_id": petition.petition_id,
                "version": petition.version,
                "petition": petition.model_dump(mode="json"),
            }
        except Exception:  # pragma: no cover - network/LLM dependent
            logger.exception("Draft stream failed: session_id=%s", session.session_id)
            yield {"type": "error", "message": "تعذر توليد الصحيفة أثناء البث الحي."}

    async def _build_facts(
        self,
        session: Session,
        case_context: ClassificationNode | None,
    ) -> PetitionSection:
        llm_text = await self.llm.generate_text(
            "drafter",
            instructions=self._facts_prompt(case_context),
            user_input=[
                {
                    "role": "system",
                    "content": (
                        "أنت محامٍ سعودي خبير في إعداد صحائف الدعاوى المتوافقة مع نظام المرافعات الشرعية "
                        "ومسار صحيفة الدعوى في ناجز. اكتب قسم الوقائع فقط دون طلبات أو أسانيد."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_generation_context(session, case_context),
                },
            ],
            temperature=self.draft_temperature,
            max_output_tokens=3400,
        )
        content = llm_text or self._build_facts_fallback(session, case_context)
        return PetitionSection(name=PetitionSectionName.FACTS, title="الوقائع", content=content)

    async def _build_requests(
        self,
        session: Session,
        case_context: ClassificationNode | None,
        facts_text: str,
        evidence_text: str,
    ) -> PetitionSection:
        llm_text = await self.llm.generate_text(
            "drafter",
            instructions=self._requests_prompt(case_context),
            user_input=[
                {
                    "role": "system",
                    "content": (
                        "أنت محامٍ سعودي. صغ قسم الطلبات فقط، بشكل محدد ومباشر ومترابط مع الوقائع "
                        "والأسانيد، ومن دون مبالغة أو اتهامات إنشائية."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"{self._build_generation_context(session, case_context)}\n\n"
                        f"قسم الوقائع المصاغ:\n{facts_text}\n\n"
                        f"قسم الأسانيد المصاغ:\n{evidence_text}"
                    ),
                },
            ],
            temperature=self.draft_temperature,
            max_output_tokens=2200,
        )
        content = llm_text or self._build_requests_fallback(session, case_context, evidence_text)
        return PetitionSection(name=PetitionSectionName.REQUESTS, title="الطلبات", content=content)

    def _facts_prompt(self, case_context: ClassificationNode | None) -> str:
        return dedent(
            f"""
            أنت في مرحلة صياغة قسم الوقائع في صحيفة دعوى سعودية ستقدَّم عبر ناجز.

            المطلوب:
            1. ابدأ ببيانات الأطراف بحسب المتاح في البيانات، مع التنبيه على أي نقص بصيغة [يحتاج استكمال].
            2. اذكر موضوع الدعوى والتصنيف القضائي المختار بما ينسجم مع نوع القضية.
            3. اعرض الوقائع زمنيًا وبأسلوب مهني واضح: متى بدأت العلاقة، ماذا حدث، ما الإخلال أو الضرر، وما الذي يثبت كل واقعة.
            4. طبّق قاعدة: واقعة + دليل + أثر.
            5. لا تخلط الوقائع بالطلبات.
            6. تجنب العبارات الانفعالية، والتكرار، والاتهامات غير اللازمة.
            7. إذا كانت معلومة مهمة غير متوفرة، اذكرها بصيغة حيادية مثل [يحتاج استكمال: العنوان الوطني للمدعي].
            8. اكتب النص العربي الجاهز كما لو كان جزءًا من صحيفة دعوى حقيقية، وليس ملخصًا أو نقاطًا عامة.

            التزامات نظامية وإجرائية يجب استحضارها في الصياغة:
            - الصحيفة السليمة يجب أن تشتمل على بيانات الأطراف، وموضوع الدعوى، والطلبات، والأسانيد.
            - العنوان الوطني للمدعي وبيانات الهوية والصفة عناصر مهمة عند التقديم عبر ناجز.
            - يجب الفصل بين الوقائع والطلبات.
            - لا تُنشئ وقائع لم يذكرها المستخدم، وإذا استنتجت شيئًا فعبّر عنه بحذر.

            مثال مرجعي أول:
            موضوع الدعوى: مطالبة مالية
            وقائع نموذجية:
            أولًا: بيانات الأطراف ...
            ثانيًا: بتاريخ ... تم الاتفاق بين المدعي والمدعى عليه على ...
            ثالثًا: نفذ المدعي التزامه بموجب ...
            رابعًا: امتنع المدعى عليه عن السداد/التنفيذ رغم مطالبته بموجب ...

            مثال مرجعي ثانٍ:
            موضوع الدعوى: دعوى تعويض عن ضرر
            وقائع نموذجية:
            1. قام المدعى عليه بفعل محدد ترتب عليه ضرر واضح.
            2. ثبت الضرر بموجب تقرير أو مستند أو مراسلات.
            3. قُدِّرت قيمة الضرر أو بقيت بحاجة إلى تقدير.

            بيانات نوع الدعوى:
            - التصنيف: {case_context.path if case_context else "غير متاح"}
            - وصف نوع الدعوى: {case_context.description if case_context else "غير متاح"}
            """
        ).strip()

    def _requests_prompt(self, case_context: ClassificationNode | None) -> str:
        return dedent(
            f"""
            أنت في مرحلة صياغة قسم الطلبات في صحيفة دعوى سعودية.

            المطلوب:
            1. صغ الطلبات بشكل صريح ومباشر ومحدد.
            2. ابدأ بالطلب الموضوعي الأساسي، ثم الطلبات التابعة أو الإجرائية.
            3. احرص على أن يكون كل طلب له سبب وله مستند أو سند يؤيده.
            4. لا تجمع طلبات لا رابط بينها.
            5. إذا كان تقدير مبلغ أو وصف معين غير مكتمل فاستخدم [يحتاج استكمال] بدل الاختلاق.
            6. يمكن إضافة طلب المصاريف وأتعاب التقاضي فقط بصياغة تحفظية وعند الملاءمة.
            7. اجعل كل طلب مرقمًا وبلغة تصلح مباشرة للإدراج في صحيفة الدعوى.

            صيغة مرجعية مفضلة:
            1. الحكم بـ ...
               - السند الواقعي: ...
               - السند المستندي/الإجرائي: ...

            مثال مرجعي:
            1. إلزام المدعى عليه بسداد مبلغ قدره (...) ريال.
               - السند الواقعي: ثبوت الاتفاق والتنفيذ من جانب المدعي وامتناع المدعى عليه عن الوفاء.
               - السند المستندي: العقد/الحوالة/المراسلات.
            2. إلزامه بما يترتب على ذلك نظامًا.
            3. تحميله المصاريف وما تقضي به الأنظمة عند الاقتضاء.

            وصف نوع الدعوى:
            - التصنيف: {case_context.path if case_context else "غير متاح"}
            - وصف نوع الدعوى: {case_context.description if case_context else "غير متاح"}
            """
        ).strip()

    def _build_generation_context(
        self,
        session: Session,
        case_context: ClassificationNode | None,
    ) -> str:
        requirements = case_context.requirements if case_context else None
        return dedent(
            f"""
            التصنيف القضائي:
            - رئيسي: {session.classification.main_title}
            - فرعي: {session.classification.sub_title}
            - نوع الدعوى: {session.classification.case_title}

            وصف الدعوى:
            {case_context.description if case_context else "غير متاح"}

            البيانات المستخرجة من المستخدم:
            {self._format_extracted_data(session.extracted_data)}

            الحقول النظامية/العملية المهمة غير المكتملة:
            {self._format_missing_fields(session.flags.missing_fields)}

            الحقول المطلوبة لهذا النوع:
            {self._format_requirement_group(requirements.data_fields if requirements else [])}

            المرفقات المتوقعة:
            {self._format_requirement_group(requirements.attachments if requirements else [])}

            الملاحظات والاستثناءات:
            {self._format_case_notes(case_context)}
            """
        ).strip()

    def _build_facts_fallback(
        self,
        session: Session,
        case_context: ClassificationNode | None,
    ) -> str:
        parties = self._extract_party_lines(session.extracted_data)
        timeline = self._build_timeline_entries(session.extracted_data)
        documents = self._infer_document_lines(session.extracted_data, case_context)
        missing = self._format_missing_fields(session.flags.missing_fields)

        lines = [
            "أولًا: بيانات الأطراف بحسب المتاح",
            parties,
            "",
            "ثانيًا: موضوع الدعوى",
            (
                f"تتمثل الدعوى في طلب {session.classification.case_title} ضمن تصنيف "
                f"{session.classification.main_title} > {session.classification.sub_title}."
            ),
            "",
            "ثالثًا: وقائع الدعوى",
            timeline,
            "",
            "رابعًا: المستندات والقرائن المرتبطة بالوقائع",
            documents,
            "",
            "خامسًا: عناصر تحتاج إلى استكمال قبل الرفع النهائي",
            missing,
        ]
        return "\n".join(lines).strip()

    def _build_requests_fallback(
        self,
        session: Session,
        case_context: ClassificationNode | None,
        evidence_text: str,
    ) -> str:
        amount = self._extract_first_value(session.extracted_data, ("مبلغ", "قيمة", "تعويض", "نفقة"))
        primary_request = self._infer_primary_request(session.classification.case_title, amount)
        support_line = self._infer_support_line(case_context)

        lines = [
            f"1. {primary_request}",
            f"   - السند الواقعي: ما ورد في وقائع الدعوى من تحقق سبب المطالبة في {session.classification.case_title}.",
            f"   - السند المستندي/الإجرائي: {support_line}",
            "2. الحكم بما يترتب على ذلك نظامًا وفق طبيعة الدعوى والتصنيف المختار.",
            "   - السند الواقعي: الارتباط المباشر بين الوقائع والنتيجة القضائية المطلوبة.",
            "   - السند المستندي/الإجرائي: المستندات المشار إليها في قسم الأسانيد والمرفقات المطلوبة.",
            "3. إلزام المدعى عليه بالمصاريف وأتعاب التقاضي عند تحقق موجبها النظامي وتقدير المحكمة.",
            "   - السند الواقعي: اضطرار المدعي إلى إقامة الدعوى للمطالبة بحقه.",
            "   - السند المستندي/الإجرائي: [يُوصى بالتحقق] مدى قبول هذا الطلب في نوع الدعوى محل النزاع.",
        ]
        if "[يُوصى بالتحقق]" not in evidence_text:
            lines.append("4. اعتماد ما ورد من أسانيد نظامية مثبتة في قسم الأسانيد دعمًا للطلبات المذكورة.")
        return "\n".join(lines)

    @staticmethod
    def _merge_sections(*sections: PetitionSection) -> str:
        return "\n\n".join(f"{section.title}\n{'=' * len(section.title)}\n{section.content}" for section in sections)

    @staticmethod
    def _choose_section(instruction: str) -> PetitionSectionName:
        if "أسانيد" in instruction:
            return PetitionSectionName.EVIDENCE
        if "طلبات" in instruction or "مطالب" in instruction:
            return PetitionSectionName.REQUESTS
        return PetitionSectionName.FACTS

    @staticmethod
    def _format_extracted_data(extracted_data: dict) -> str:
        if not extracted_data:
            return "- لا توجد بيانات مستخرجة بعد."
        return "\n".join(f"- {field}: {value}" for field, value in extracted_data.items())

    @staticmethod
    def _format_missing_fields(fields: list[str]) -> str:
        if not fields:
            return "- لا توجد حقول مطلوبة متبقية في هذه المرحلة."
        return "\n".join(f"- [يحتاج استكمال] {field}" for field in fields)

    @staticmethod
    def _format_requirement_group(items: list[RequirementItem]) -> str:
        if not items:
            return "- لا توجد متطلبات محددة مسجلة."
        lines = []
        for item in items:
            tag = "إلزامي" if item.required else "اختياري"
            lines.append(f"- {item.name} ({tag})")
        return "\n".join(lines)

    @staticmethod
    def _format_case_notes(case_context: ClassificationNode | None) -> str:
        if case_context is None:
            return "- لا توجد ملاحظات إضافية."
        parts: list[str] = []
        if case_context.hints:
            parts.extend(f"- تلميح: {hint}" for hint in case_context.hints)
        if case_context.exceptions:
            parts.extend(f"- استثناء/تنبيه: {item}" for item in case_context.exceptions)
        if case_context.requirements and case_context.requirements.notes:
            parts.extend(f"- ملاحظة متطلب: {note}" for note in case_context.requirements.notes)
        return "\n".join(parts) if parts else "- لا توجد ملاحظات إضافية."

    @staticmethod
    def _extract_party_lines(extracted_data: dict) -> str:
        plaintiff = [f"{field}: {value}" for field, value in extracted_data.items() if "مدعي" in field or "طالب" in field]
        defendant = [f"{field}: {value}" for field, value in extracted_data.items() if "مدعى" in field or "مدعي عليه" in field]
        representative = [f"{field}: {value}" for field, value in extracted_data.items() if "وكيل" in field or "ولاية" in field or "صفة" in field]

        lines = [
            "بيانات المدعي:",
            *([f"- {item}" for item in plaintiff] or ["- [يحتاج استكمال] الاسم الكامل، الهوية، العنوان الوطني، الصفة."]),
            "بيانات المدعى عليه:",
            *([f"- {item}" for item in defendant] or ["- [يحتاج استكمال] الاسم الكامل/السجل، الهوية أو السجل، العنوان."]),
        ]
        if representative:
            lines.extend(["بيانات الممثل النظامي أو الوكيل:", *[f"- {item}" for item in representative]])
        return "\n".join(lines)

    @staticmethod
    def _build_timeline_entries(extracted_data: dict) -> str:
        if not extracted_data:
            return "1. [يحتاج استكمال] لا توجد وقائع مفصلة كافية بعد لعرض التسلسل الزمني."

        ordered_dates = [(field, value) for field, value in extracted_data.items() if "تاريخ" in field]
        other_items = [(field, value) for field, value in extracted_data.items() if "تاريخ" not in field]

        lines: list[str] = []
        counter = 1
        for field, value in ordered_dates:
            lines.append(f"{counter}. بتاريخ/زمن متعلق بـ {field} وردت المعلومة التالية: {value}.")
            counter += 1

        for field, value in other_items:
            lines.append(f"{counter}. من الوقائع المؤكدة في الملف: {field} = {value}.")
            counter += 1

        lines.append(f"{counter}. ترتب على ما سبق نشوء النزاع المرتبط بطلب {next(iter(extracted_data.keys()), 'الحق المدعى به')}.")
        return "\n".join(lines)

    @staticmethod
    def _infer_document_lines(extracted_data: dict, case_context: ClassificationNode | None) -> str:
        lines: list[str] = []
        for field, value in extracted_data.items():
            if any(token in field for token in ("مستند", "مرفق", "عقد", "فاتورة", "حوالة", "رسالة", "إيصال", "صك", "كشف", "تقرير")):
                lines.append(f"- {field}: {value}")

        if case_context and case_context.requirements:
            for item in case_context.requirements.attachments:
                label = "مرفق متوقع" if item.required else "مرفق اختياري"
                lines.append(f"- {label}: {item.name}")

        if not lines:
            return "- [يحتاج استكمال] لم تُبيَّن في البيانات الحالية مستندات كافية، ويستحسن إرفاق العقد والمراسلات والإثباتات المؤثرة."
        return "\n".join(lines)

    @staticmethod
    def _extract_first_value(extracted_data: dict, keys: tuple[str, ...]) -> str | None:
        for field, value in extracted_data.items():
            if any(token in field for token in keys):
                return str(value)
        return None

    @staticmethod
    def _infer_primary_request(case_title: str, amount: str | None) -> str:
        if "تعويض" in case_title:
            return f"الحكم بإلزام المدعى عليه بتعويض المدعي بمبلغ {amount or '[يحتاج استكمال]'}."
        if "نفقة" in case_title:
            return f"الحكم بإلزام المدعى عليه بالنفقة المستحقة بمقدار {amount or '[يحتاج تقدير/استكمال]' }."
        if "طلاق" in case_title or "خلع" in case_title or "فسخ" in case_title:
            return f"الحكم بـ {case_title} وما يترتب عليه نظامًا وفق وقائع الدعوى."
        if "حارس" in case_title:
            return "الحكم بإقامة حارس قضائي على المال أو التركة محل النزاع وفق ما يثبت للمحكمة."
        return f"الحكم للمدعي بما يوافق طبيعة دعوى {case_title} وفق الوقائع الثابتة."

    @staticmethod
    def _infer_support_line(case_context: ClassificationNode | None) -> str:
        if case_context and case_context.requirements and case_context.requirements.attachments:
            return case_context.requirements.attachments[0].name
        return "العقد أو المراسلات أو الهوية أو أي مستند ذي صلة بحسب نوع الدعوى."
