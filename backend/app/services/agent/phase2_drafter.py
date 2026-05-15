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
from app.utils.petition_text import (
    PETITION_ROLE_META_KEY,
    normalize_petition_role,
    petition_role_label,
    sanitize_petition_text,
)
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
        draft_model_name: str | None = None,
    ):
        self.repo = repo
        self.classification_repo = classification_repo
        self.evidence_service = evidence_service
        self.llm = llm
        self.draft_temperature = draft_temperature
        self.draft_model_name = draft_model_name

    async def draft(self, session: Session, petition_role: str | None = None) -> AgentTurnResult:
        if session.classification is None:
            return AgentTurnResult(
                reply="لا يمكن بدء الصياغة قبل اعتماد التصنيف.",
                next_action="confirm_classification",
            )
        session.status = SessionStatus.DRAFTING
        session.phase = Phase.TWO

        selected_role = self._resolve_petition_role(session, petition_role)
        case_context = await self.classification_repo.get_case(session.classification.case_id)
        facts = await self._build_facts(session, case_context, selected_role)
        evidence = await self.evidence_service.build(
            selection=session.classification,
            facts_text=facts.content,
            extracted_data=session.extracted_data,
            case_context=case_context,
            petition_role=selected_role,
        )
        requests = await self._build_requests(session, case_context, facts.content, evidence.content, selected_role)
        full_text = self._merge_sections(facts, evidence, requests)

        petition = PetitionDraft(
            session_id=session.session_id,
            version=session.petition_version + 1,
            model=self.draft_model_name,
            facts=facts,
            evidence=evidence,
            requests=requests,
            full_text=full_text,
            metadata={
                "classification": session.classification.model_dump(mode="json"),
                PETITION_ROLE_META_KEY: selected_role,
                "petition_role_label": petition_role_label(selected_role),
            },
        )
        await self.repo.create(petition)
        session.petition_version = petition.version
        session.status = SessionStatus.DRAFT_READY

        return AgentTurnResult(
            reply=f"تم توليد مسودة الصحيفة بصيغة {petition_role_label(selected_role)} وباتت جاهزة للمراجعة والتحسين.",
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

    async def stream(self, session: Session, petition_role: str | None = None) -> AsyncIterator[dict]:
        try:
            result = await self.draft(session, petition_role=petition_role)
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
        petition_role: str,
    ) -> PetitionSection:
        llm_text = await self.llm.generate_text(
            "drafter",
            instructions=self._facts_prompt(case_context, petition_role),
            user_input=[
                {
                    "role": "system",
                    "content": (
                        "أنت محرر قانوني متخصص في إعداد صحائف الدعاوى السعودية المتوافقة مع مسار صحيفة الدعوى في ناجز. "
                        "اكتب قسم الوقائع فقط دون طلبات أو أسانيد. أخرج النص النهائي مباشرة، "
                        "ولا تذكر نفسك أو مهنتك أو جنسيتك، ولا تستخدم عبارات مثل "
                        "'بصفتي محاميًا سعوديًا' أو 'كمحام'.\n\n"
                        "قاعدة صارمة لمنع الاختلاق:\n"
                        "- لا تخترع وقائع أو تواريخ أو مبالغ أو أسماء لم يذكرها المستخدم.\n"
                        "- لا تبالغ في وصف الأضرار أو تُضِف اتهامات أو صفات قانونية لم ترد في البيانات.\n"
                        "- إذا كانت معلومة غير موجودة، استخدم [يحتاج استكمال] ولا تملأ الفراغ بافتراضات.\n"
                        "- ميّز بوضوح بين: (أ) وقائع ذكرها المستخدم، (ب) استنتاجات قانونية مقترحة."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_generation_context(session, case_context, petition_role),
                },
            ],
            temperature=self.draft_temperature,
            max_output_tokens=3400,
        )
        content = sanitize_petition_text(llm_text) if llm_text else self._build_facts_fallback(session, case_context, petition_role)
        return PetitionSection(name=PetitionSectionName.FACTS, title="الوقائع", content=content)

    async def _build_requests(
        self,
        session: Session,
        case_context: ClassificationNode | None,
        facts_text: str,
        evidence_text: str,
        petition_role: str,
    ) -> PetitionSection:
        llm_text = await self.llm.generate_text(
            "drafter",
            instructions=self._requests_prompt(case_context, petition_role),
            user_input=[
                {
                    "role": "system",
                    "content": (
                        "أنت محرر قانوني متخصص في صحائف الدعوى السعودية. صغ قسم الطلبات فقط، بشكل محدد ومباشر "
                        "ومترابط مع الوقائع والأسانيد، ومن دون مبالغة أو اتهامات إنشائية. "
                        "اكتب الطلبات النهائية مباشرة، ولا تذكر نفسك أو مهنتك أو جنسيتك، "
                        "ولا تستخدم عبارات مثل 'بصفتي محاميًا سعوديًا' أو 'كمحام'.\n\n"
                        "قاعدة صارمة لمنع الاختلاق:\n"
                        "- لا تطلب مبالغ أو تعويضات لم يذكرها المستخدم.\n"
                        "- لا تُضِف أوصافًا قانونية مشددة (إهمال جسيم، تعمد، سوء نية) إلا إذا ذكرها المستخدم صراحة.\n"
                        "- إذا لم يحدد المستخدم مبلغًا، اكتب [يحتاج استكمال] في الطلب.\n"
                        "- كل طلب يجب أن يستند إلى واقعة ذكرها المستخدم فعلاً."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"{self._build_generation_context(session, case_context, petition_role)}\n\n"
                        f"قسم الوقائع المصاغ:\n{facts_text}\n\n"
                        f"قسم الأسانيد المصاغ:\n{evidence_text}"
                    ),
                },
            ],
            temperature=self.draft_temperature,
            max_output_tokens=2200,
        )
        content = sanitize_petition_text(llm_text) if llm_text else self._build_requests_fallback(session, case_context, evidence_text, petition_role)
        return PetitionSection(name=PetitionSectionName.REQUESTS, title="الطلبات", content=content)

    def _facts_prompt(self, case_context: ClassificationNode | None, petition_role: str) -> str:
        role_rules = self._petition_role_prompt_rules(petition_role)
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
            9. أخرج الوقائع النهائية فقط دون أي تمهيد عن دورك أو خبرتك أو مهنتك.
            10. ممنوع استخدام عبارات مثل: بصفتي محاميًا سعوديًا، كمحامٍ، أنا محامٍ، أو سأقوم بصياغة الصحيفة.
            11. {role_rules}

            التزامات نظامية وإجرائية يجب استحضارها في الصياغة:
            - الصحيفة السليمة يجب أن تشتمل على بيانات الأطراف، وموضوع الدعوى، والطلبات، والأسانيد.
            - العنوان الوطني للمدعي وبيانات الهوية والصفة عناصر مهمة عند التقديم عبر ناجز.
            - يجب الفصل بين الوقائع والطلبات.
            - لا تُنشئ وقائع أو تواريخ أو مبالغ لم يذكرها المستخدم. إذا استنتجت شيئًا فعبّر عنه بحذر وبين أنه استنتاج.
            - لا تضف أوصافًا مشددة (إهمال جسيم، سوء نية، تعمد) ما لم يذكرها المستخدم صراحة.

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

    def _requests_prompt(self, case_context: ClassificationNode | None, petition_role: str) -> str:
        role_rules = self._petition_role_prompt_rules(petition_role)
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
            8. اكتب الطلبات النهائية فقط دون أي تمهيد عن دورك أو خبرتك أو مهنتك.
            9. ممنوع استخدام عبارات مثل: بصفتي محاميًا سعوديًا، كمحامٍ، أنا محامٍ، أو سأقوم بصياغة الطلبات.
            10. {role_rules}

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
        petition_role: str,
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

            صيغة الصحيفة المختارة:
            - النمط: {petition_role_label(petition_role)}
            - التوجيه: {self._petition_role_context_line(petition_role)}

            البيانات المستخرجة من المستخدم:
            {self._format_extracted_data(session.extracted_data)}

            خريطة الحقول المنظمة (لمنع التبديل بين القيم):
            {self._format_structured_field_map(session.extracted_data, petition_role)}

            بيانات إثرائية إضافية (إن وجدت):
            {self._format_structured_supplementary_context(session.extracted_data)}

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
        petition_role: str,
    ) -> str:
        parties = self._extract_party_lines(session.extracted_data, petition_role)
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
        petition_role: str,
    ) -> str:
        amount = self._extract_first_value(
            session.extracted_data,
            (
                "تقدير المطالبة",
                "مبلغ المطالبة",
                "المبلغ المستحق",
                "مبلغ",
                "قيمة",
                "تعويض",
                "نفقة",
                "أتعاب",
            ),
        )
        primary_request = self._infer_primary_request(session.classification.case_title, amount, petition_role)
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
    def _format_structured_supplementary_context(
        extracted_data: dict,
    ) -> str:
        supplementary_labels = (
            "بيانات الوكيل",
            "رقم الوكالة",
            "رقم الهوية",
            "العنوان الوطني",
            "البريد الإلكتروني",
            "الجوال",
            "تقدير المطالبة",
            "بيانات إضافية للأطراف",
        )
        lines: list[str] = []
        for label in supplementary_labels:
            value = str(extracted_data.get(label, "")).strip()
            if value:
                lines.append(f"- {label}: {value}")
        if not lines:
            return "- لا توجد بيانات إثرائية إضافية مسجلة."
        return "\n".join(lines)

    @classmethod
    def _format_structured_field_map(
        cls,
        extracted_data: dict,
        petition_role: str,
    ) -> str:
        def pick(tokens: tuple[str, ...]) -> str:
            values = cls._collect_values_by_tokens(
                extracted_data, tokens,
            )
            return " | ".join(values) if values else "[يحتاج استكمال]"

        plaintiff_tokens = (
            "مدعي", "طالب", "الطرف الأول", "الطرف الاول",
        )
        defendant_tokens = (
            "مدعى", "مدعي عليه", "الطرف الثاني", "الطرف الثانى",
        )
        representative_tokens = (
            "وكيل", "وكالة", "تفويض", "نيابة", "ولاية",
        )
        lines = [
            f"- بيانات المدعي: {pick(plaintiff_tokens)}",
            f"- بيانات المدعى عليه: {pick(defendant_tokens)}",
            f"- الهوية/السجل: {pick(('هوية', 'إقامة', 'اقامة', 'سجل', 'سجل تجاري', 'رقم الهوية'))}",
            f"- العنوان: {pick(('عنوان', 'العنوان الوطني', 'مقر'))}",
            f"- التواصل (هاتف/جوال/بريد): {pick(('جوال', 'هاتف', 'اتصال', 'بريد', 'email'))}",
            f"- بيانات الوكالة: {pick(representative_tokens) if petition_role == 'agent' else 'غير مطبق في صيغة أصيل'}",
            f"- التقدير المالي/المطالبة: {pick(('تقدير المطالبة', 'مبلغ', 'قيمة', 'تعويض', 'نفقة', 'أتعاب'))}",
            f"- بيانات إضافية للأطراف: {pick(('بيانات إضافية للأطراف', 'بيانات الأطراف', 'أطراف'))}",
            f"- التواريخ: {pick(('تاريخ', 'موعد', 'زمن'))}",
            f"- الوقائع/الوصف: {pick(('وقائع', 'وصف', 'تفاصيل', 'بيان'))}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _collect_values_by_tokens(
        extracted_data: dict,
        tokens: tuple[str, ...],
    ) -> list[str]:
        entries: list[str] = []
        for field, value in extracted_data.items():
            normalized = str(value).strip()
            if not normalized:
                continue
            if any(token in field for token in tokens):
                entries.append(f"{field}: {normalized}")
        return entries

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
    def _extract_party_lines(extracted_data: dict, petition_role: str) -> str:
        non_empty_items = [
            (field, str(value).strip())
            for field, value in extracted_data.items()
            if str(value).strip()
        ]
        plaintiff = [
            f"{field}: {value}"
            for field, value in non_empty_items
            if any(
                token in field
                for token in (
                    "مدعي", "الطرف الأول", "الطرف الاول",
                )
            )
        ]
        for label in ("رقم الهوية", "رقم الوكالة"):
            value = next(
                (item_value for field, item_value in non_empty_items if field.strip() == label),
                None,
            )
            if not value:
                value = next(
                    (
                        item_value
                        for field, item_value in non_empty_items
                        if label in field and "المدعى" not in field
                    ),
                    None,
                )
            if value and not any(line.startswith(f"{label}:") for line in plaintiff):
                plaintiff.append(f"{label}: {value}")
        defendant = [
            f"{field}: {value}"
            for field, value in non_empty_items
            if any(
                token in field
                for token in (
                    "مدعى", "مدعي عليه", "الطرف الثاني", "الطرف الثانى",
                )
            )
        ]
        representative = [
            f"{field}: {value}"
            for field, value in non_empty_items
            if any(
                token in field
                for token in (
                    "وكيل", "وكالة", "ولاية", "صفة", "تفويض", "نيابة",
                )
            )
        ]
        extra_identity_contact = [
            f"{field}: {value}"
            for field, value in non_empty_items
            if any(
                token in field
                for token in (
                    "هوية", "إقامة", "اقامة", "سجل", "عنوان",
                    "جوال", "هاتف", "بريد", "email",
                )
            )
            and not any(
                token in field
                for token in ("مدعي", "مدعى", "وكيل", "وكالة", "ولاية", "صفة")
            )
        ]
        has_identity = any(
            any(
                token in field
                for token in (
                    "هوية", "إقامة", "اقامة", "سجل", "رقم الهوية",
                )
            )
            for field, _ in non_empty_items
        )
        has_address = any(
            any(token in field for token in ("عنوان", "مقر"))
            for field, _ in non_empty_items
        )
        has_representative_name = any(
            "وكيل" in field
            for field, _ in non_empty_items
        )
        has_agency_number = any(
            "وكالة" in field
            for field, _ in non_empty_items
        )
        plaintiff_missing: list[str] = ["الاسم الكامل"]
        if not has_identity:
            plaintiff_missing.append("الهوية/السجل")
        if not has_address:
            plaintiff_missing.append("العنوان الوطني/عنوان التبليغ")
        if not any("صفة" in field for field, _ in non_empty_items):
            plaintiff_missing.append("الصفة")
        plaintiff_fallback = (
            "- [يحتاج استكمال] "
            + "، ".join(plaintiff_missing)
            + "."
        )
        defendant_fallback = (
            "- [يحتاج استكمال] الاسم الكامل/السجل، "
            "وبيانات المدعى عليه التعريفية."
            if has_identity or has_address
            else "- [يحتاج استكمال] الاسم الكامل/السجل، الهوية أو السجل، العنوان."
        )

        lines = [
            (
                "- صفة التقديم: أصيل عن نفسه، وتبقى الصياغة منسوبة مباشرة إلى المدعي."
                if petition_role == "principal"
                else "- صفة التقديم: وكيل عن المدعي، ويجب أن تُصاغ الصحيفة بصيغة تمثيل محايدة دون ذكر مهنة الكاتب."
            ),
            "بيانات المدعي:",
            *([f"- {item}" for item in plaintiff] or [plaintiff_fallback]),
            "بيانات المدعى عليه:",
            *([f"- {item}" for item in defendant] or [defendant_fallback]),
        ]
        if extra_identity_contact:
            lines.extend(
                [
                    "بيانات تعريف/تواصل إضافية من الإدخال:",
                    *[f"- {item}" for item in extra_identity_contact],
                ]
            )
        if representative:
            lines.extend(["بيانات الممثل النظامي أو الوكيل:", *[f"- {item}" for item in representative]])
        elif petition_role == "agent":
            representative_missing = [
                "اسم الوكيل وصفته"
                if not has_representative_name
                else None,
                "رقم الوكالة وتاريخها وجهة إصدارها"
                if not has_agency_number
                else None,
                "نص صلاحية المرافعة",
            ]
            representative_missing = [
                item
                for item in representative_missing
                if item
            ]
            lines.extend(
                [
                    "بيانات الوكيل:",
                    "- [يحتاج استكمال] "
                    + "، ".join(representative_missing)
                    + ".",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def _build_timeline_entries(extracted_data: dict) -> str:
        if not extracted_data:
            return "1. [يحتاج استكمال] لا توجد وقائع مفصلة كافية بعد لعرض التسلسل الزمني."

        non_empty_items = [
            (field, str(value).strip())
            for field, value in extracted_data.items()
            if str(value).strip()
        ]
        ordered_dates = [
            (field, value)
            for field, value in non_empty_items
            if "تاريخ" in field
        ]
        other_items = [
            (field, value)
            for field, value in non_empty_items
            if "تاريخ" not in field
        ]

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
            normalized = str(value).strip()
            if not normalized:
                continue
            if any(
                token in field
                for token in (
                    "مستند", "مرفق", "عقد", "فاتورة", "حوالة",
                    "رسالة", "رسائل", "إيصال", "صك", "كشف",
                    "تقرير", "محضر", "بوليصة", "سند",
                )
            ):
                lines.append(f"- {field}: {normalized}")

        if case_context and case_context.requirements:
            for item in case_context.requirements.attachments:
                label = "مرفق متوقع" if item.required else "مرفق اختياري"
                lines.append(f"- {label}: {item.name}")

        if not lines:
            return "- [يحتاج استكمال] لم تُبيَّن في البيانات الحالية مستندات كافية، ويستحسن إرفاق العقد والمراسلات والإثباتات المؤثرة."
        return "\n".join(lines)

    @staticmethod
    def _extract_first_value(extracted_data: dict, keys: tuple[str, ...]) -> str | None:
        non_empty_items = [
            (field, str(value).strip())
            for field, value in extracted_data.items()
            if str(value).strip()
        ]
        for token in keys:
            for field, value in non_empty_items:
                if field.strip() == token:
                    return value
        for token in keys:
            for field, value in non_empty_items:
                if token in field:
                    return value
        return None

    @staticmethod
    def _infer_primary_request(case_title: str, amount: str | None, petition_role: str) -> str:
        beneficiary = "موكلي" if petition_role == "agent" else "المدعي"
        if "تعويض" in case_title:
            return f"الحكم بإلزام المدعى عليه بتعويض {beneficiary} بمبلغ {amount or '[يحتاج استكمال]'}."
        if "نفقة" in case_title:
            return f"الحكم بإلزام المدعى عليه بالنفقة المستحقة لصالح {beneficiary} بمقدار {amount or '[يحتاج تقدير/استكمال]' }."
        if "طلاق" in case_title or "خلع" in case_title or "فسخ" in case_title:
            return f"الحكم بـ {case_title} وما يترتب عليه نظامًا وفق وقائع الدعوى."
        if "حارس" in case_title:
            return "الحكم بإقامة حارس قضائي على المال أو التركة محل النزاع وفق ما يثبت للمحكمة."
        return f"الحكم لصالح {beneficiary} بما يوافق طبيعة دعوى {case_title} وفق الوقائع الثابتة."

    @staticmethod
    def _infer_support_line(case_context: ClassificationNode | None) -> str:
        if case_context and case_context.requirements and case_context.requirements.attachments:
            return case_context.requirements.attachments[0].name
        return "العقد أو المراسلات أو الهوية أو أي مستند ذي صلة بحسب نوع الدعوى."

    def _resolve_petition_role(self, session: Session, petition_role: str | None) -> str:
        selected_role = normalize_petition_role(petition_role or session.metadata.get(PETITION_ROLE_META_KEY))
        session.metadata[PETITION_ROLE_META_KEY] = selected_role
        return selected_role

    @staticmethod
    def _petition_role_prompt_rules(petition_role: str) -> str:
        if petition_role == "agent":
            return (
                "صيغة التقديم: وكيل؛ اذكر التمثيل عن المدعي بعبارات محايدة مثل 'بصفتي وكيلاً عن المدعي' أو "
                "'نيابة عن موكلي' عند الحاجة، مع التنبيه بصيغة [يحتاج استكمال] إذا كانت بيانات الوكالة ناقصة."
            )
        return (
            "صيغة التقديم: أصيل؛ فلا تذكر وكالة أو موكلاً أو تمثيلاً، "
            "واكتب الصحيفة بصيغة منسوبة مباشرة إلى صاحب الحق نفسه."
        )

    @staticmethod
    def _petition_role_context_line(petition_role: str) -> str:
        if petition_role == "agent":
            return "الصحيفة مطلوبة بصيغة وكيل عن المدعي وبعبارات تمثيل محايدة دون تعريف مهني."
        return "الصحيفة مطلوبة بصيغة أصيل عن نفسه دون أي عبارات وكالة أو تمثيل."
