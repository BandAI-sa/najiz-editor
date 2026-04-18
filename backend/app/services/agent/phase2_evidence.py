from __future__ import annotations

from textwrap import dedent

from app.models.classification import ClassificationNode, ClassificationSelection, RequirementItem
from app.models.petition import PetitionSection, PetitionSectionName
from app.services.legal.store import LegalReferenceStore
from app.services.llm.base import LLMClient
from app.utils.petition_text import petition_role_label, sanitize_petition_text


class Phase2EvidenceService:
    def __init__(
        self,
        legal_store: LegalReferenceStore,
        llm: LLMClient,
        draft_temperature: float = 0.4,
    ):
        self.legal_store = legal_store
        self.llm = llm
        self.draft_temperature = draft_temperature

    async def build(
        self,
        selection: ClassificationSelection,
        facts_text: str,
        extracted_data: dict,
        case_context: ClassificationNode | None = None,
        petition_role: str = "principal",
    ) -> PetitionSection:
        verified_lines = self._collect_verified_lines(selection)
        documentary_lines = self._build_documentary_lines(extracted_data, case_context)
        procedural_lines = self._build_procedural_lines(extracted_data, case_context, petition_role)

        llm_text = await self.llm.generate_text(
            "drafter",
            instructions=self._evidence_prompt(case_context, petition_role),
            user_input=[
                {
                    "role": "system",
                    "content": (
                        "أنت محرر قانوني متخصص في صياغة صحائف الدعوى السعودية. صغ قسم الأسانيد بحيث يربط كل طلب بسبب ودليل. "
                        "لا تنسب نصًا نظاميًا بوصفه مرجعًا موثقًا إلا إذا ورد في قائمة المراجع الموثقة. "
                        "أي استناد غير موثق يجب أن يسبق بوسم [يُوصى بالتحقق]. "
                        "اكتب النص النهائي مباشرة، ولا تذكر نفسك أو مهنتك أو جنسيتك، ولا تستخدم عبارات مثل "
                        "'بصفتي محاميًا سعوديًا' أو 'كمحام'."
                    ),
                },
                {
                    "role": "user",
                    "content": dedent(
                        f"""
                        التصنيف:
                        - رئيسي: {selection.main_title}
                        - فرعي: {selection.sub_title}
                        - نوع الدعوى: {selection.case_title}

                        الوقائع المصاغة:
                        {facts_text}

                        صيغة الصحيفة المختارة:
                        - النمط: {petition_role_label(petition_role)}

                        البيانات المستخرجة:
                        {self._format_extracted_data(extracted_data)}

                        المراجع الموثقة:
                        {self._join_or_placeholder(verified_lines, '- لا توجد مراجع موثقة مطابقة مباشرة.')}

                        الأسانيد المستندية المتوقعة:
                        {self._join_or_placeholder(documentary_lines, '- لا توجد مستندات ظاهرة كفاية في البيانات الحالية.')}

                        الأسانيد الإجرائية/النظامية:
                        {self._join_or_placeholder(procedural_lines, '- لا توجد متطلبات إضافية ظاهرة.')}
                        """
                    ).strip(),
                },
            ],
            temperature=self.draft_temperature,
            max_output_tokens=2600,
        )
        content = sanitize_petition_text(llm_text) if llm_text else self._build_fallback(verified_lines, documentary_lines, procedural_lines)

        return PetitionSection(
            name=PetitionSectionName.EVIDENCE,
            title="الأسانيد",
            content=content,
            citations=verified_lines,
        )

    def _evidence_prompt(self, case_context: ClassificationNode | None, petition_role: str) -> str:
        role_guard = (
            "- صيغة التقديم: أصيل؛ فلا تذكر وكالة أو موكل أو نيابة ما لم تكن ثابتة صراحة في البيانات."
            if petition_role == "principal"
            else "- صيغة التقديم: وكيل؛ اذكر التمثيل عن المدعي بعبارات محايدة مثل 'بصفتي وكيلاً عن المدعي' أو 'نيابة عن موكلي' دون أي تعريف مهني زائد."
        )
        return dedent(
            f"""
            أنت في مرحلة صياغة الأسانيد في صحيفة دعوى سعودية.

            المطلوب:
            1. قسم الأسانيد إلى:
               - أسانيد مستندية
               - أسانيد نظامية وإجرائية
               - ربط الطلبات بأسبابها وأدلتها
            2. طبّق قاعدة: كل طلب = سبب = مستند يؤيده.
            3. استحضر متطلبات ناجز العملية: بيانات الأطراف، الهوية، العنوان الوطني، الوكالة عند وجود وكيل، الولاية عند وجود ولي، والمرفقات المؤثرة.
            4. لا تذكر نصوصًا نظامية على أنها موثقة إلا إذا وردت ضمن المراجع الموثقة.
            5. إذا لم توجد مرجعية موثقة، استخدم الوسم [يُوصى بالتحقق].
            6. اجعل الصياغة عملية وقابلة للاستخدام داخل صحيفة دعوى، وليست شرحًا نظريًا عامًا.
            7. اكتب الأسانيد النهائية فقط دون أي تمهيد عن دورك أو خبرتك أو مهنتك.
            8. ممنوع استخدام عبارات مثل: بصفتي محاميًا سعوديًا، كمحامٍ، أو سأقوم بصياغة.
            9. {role_guard}

            قواعد منهجية مهمة:
            - الأسانيد ليست مجرد شعارات، بل مستندات ووقائع ونصوص إجرائية أو نظامية مرتبطة مباشرة بالدعوى.
            - لا تكرر الوقائع كما هي؛ بل حوّلها إلى علاقة بين واقعة ودليل.
            - عند ضعف البيانات، نبه إلى الحاجة لاستكمال المستند أو البيان بدل التخمين.

            وصف نوع الدعوى:
            - المسار: {case_context.path if case_context else "غير متاح"}
            - الوصف: {case_context.description if case_context else "غير متاح"}
            """
        ).strip()

    def _build_fallback(
        self,
        verified_lines: list[str],
        documentary_lines: list[str],
        procedural_lines: list[str],
    ) -> str:
        return "\n".join(
            [
                "أولًا: الأسانيد المستندية",
                *documentary_lines,
                "",
                "ثانيًا: الأسانيد النظامية والإجرائية",
                *procedural_lines,
                "",
                "ثالثًا: المراجع النظامية الموثقة أو ما يلزم التحقق منه",
                *(verified_lines or ["- [يُوصى بالتحقق] لا توجد مرجعية نظامية موثقة مطابقة مباشرة في المخزن الحالي."]),
                "",
                "رابعًا: قاعدة الربط بين الطلب والسبب والدليل",
                "- كل طلب يجب أن يستند إلى واقعة واضحة في قسم الوقائع، وإلى مستند أو قرينة أو متطلب إجرائي يؤيده.",
                "- إذا كان الطلب ماليًا أو متعلقًا بتنفيذ التزام أو تعويض، فيلزم إبراز أصل العلاقة والمطالبة السابقة والمستندات الداعمة.",
                "- إذا كانت بعض المرفقات أو بيانات الهوية أو العنوان الوطني أو الصفة غير مكتملة، فينبغي استكمالها قبل الرفع النهائي عبر ناجز.",
            ]
        ).strip()

    def _collect_verified_lines(self, selection: ClassificationSelection) -> list[str]:
        lines: list[str] = []
        for query in (selection.case_title, selection.sub_title, selection.main_title):
            lines.extend(self.legal_store.citation_lines(query))
        deduped: list[str] = []
        for line in lines:
            if line not in deduped:
                deduped.append(line)
        return deduped

    def _build_documentary_lines(
        self,
        extracted_data: dict,
        case_context: ClassificationNode | None,
    ) -> list[str]:
        lines: list[str] = []
        for field, value in extracted_data.items():
            if any(token in field for token in ("عقد", "فاتورة", "حوالة", "إيصال", "رسائل", "مراسلات", "مستند", "صك", "كشف", "تقرير", "شهادة")):
                lines.append(f"- مستند ظاهر من البيانات: {field} = {value}")

        if case_context and case_context.requirements:
            for item in case_context.requirements.attachments:
                prefix = "مرفق إلزامي متوقع" if item.required else "مرفق إضافي متوقع"
                lines.append(f"- {prefix}: {item.name}")

        if not lines:
            lines.append("- [يحتاج استكمال] لم تظهر في البيانات الحالية مستندات مؤثرة كافية، ويستحسن إرفاق العقد أو الحوالة أو المراسلات أو الصك بحسب نوع الدعوى.")
        return lines

    def _build_procedural_lines(
        self,
        extracted_data: dict,
        case_context: ClassificationNode | None,
        petition_role: str,
    ) -> list[str]:
        lines = [
            "- يجب أن تتضمن الصحيفة بيانات المدعي والمدعى عليه وموضوع الدعوى والطلبات والأسانيد بصورة واضحة.",
            "- يلزم استكمال بيانات الهوية والصفة والعنوان الوطني للمدعي بحسب متطلبات التقديم عبر ناجز.",
        ]

        if petition_role == "principal":
            lines.append("- تم اختيار الصياغة بصيغة أصيل، لذا لا تذكر وكالة أو موكل أو تمثيل إلا إذا كانت ثابتة في الملف.")
        else:
            lines.append("- تم اختيار الصياغة بصيغة وكيل، لذا يجب بيان صفة الوكالة والتحقق من سريانها وصلاحية المرافعة، أو التنبيه إلى نقصها بصيغة [يحتاج استكمال].")

        if not any("عنوان" in field for field in extracted_data):
            lines.append("- [يحتاج استكمال] العنوان الوطني أو عنوان الأطراف غير ظاهر في البيانات الحالية.")
        if not any("هوية" in field or "سجل" in field for field in extracted_data):
            lines.append("- [يحتاج استكمال] بيانات الهوية/السجل للأطراف تحتاج استكمالًا قبل الرفع.")
        if any("وكيل" in field for field in extracted_data):
            lines.append("- إذا كان مقدم الطلب وكيلًا، فيلزم التحقق من سريان الوكالة وتضمنها بند المرافعة.")
        if any("ولاية" in field for field in extracted_data):
            lines.append("- إذا كان مقدم الطلب وليًا، فيلزم إرفاق صك الولاية أو ما يثبت الصفة النظامية.")

        if case_context and case_context.requirements:
            for item in case_context.requirements.data_fields:
                if item.required:
                    lines.append(f"- عنصر بياني جوهري لهذا النوع من الدعاوى: {item.name}")
        return lines

    @staticmethod
    def _format_extracted_data(extracted_data: dict) -> str:
        if not extracted_data:
            return "- لا توجد بيانات مستخرجة بعد."
        return "\n".join(f"- {field}: {value}" for field, value in extracted_data.items())

    @staticmethod
    def _join_or_placeholder(items: list[str], placeholder: str) -> str:
        return "\n".join(items) if items else placeholder
