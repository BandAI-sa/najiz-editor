from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("uvicorn.error")

_FIELD_TEMPLATES: dict[str, str] = {
    "اسم المدعي": "ممكن تعطيني اسمك الكامل كما هو في الهوية؟",
    "اسم المدعى عليه": "وش اسم الطرف الثاني (المدعى عليه) الكامل؟",
    "هوية المدعي": "كم رقم هويتك الوطنية أو الإقامة؟",
    "رقم هوية المدعي": "كم رقم هويتك الوطنية أو الإقامة؟",
    "هوية المدعى عليه": "هل تعرف رقم هوية المدعى عليه؟",
    "رقم هوية المدعى عليه": "هل تعرف رقم هوية المدعى عليه؟",
    "عنوان المدعي": "وش عنوان سكنك الحالي؟ (المدينة والحي)",
    "عنوان المدعى عليه": "هل تعرف عنوان سكن المدعى عليه؟",
    "هاتف المدعي": "كم رقم جوالك للتواصل؟",
    "جوال المدعي": "كم رقم جوالك للتواصل؟",
    "تاريخ الزواج": "متى تم عقد الزواج؟",
    "تاريخ الطلاق": "متى وقع الطلاق؟",
    "تاريخ العقد": "متى تم توقيع العقد؟",
    "تاريخ انتهاء العقد": "متى انتهت مدة العقد أو تم إنهاؤه؟",
    "تاريخ الواقعة": "متى حصلت هالمشكلة تقريبًا؟",
    "تاريخ بداية العمل": "متى بدأت العمل عندهم؟",
    "تاريخ انتهاء العمل": "متى تم إنهاء خدمتك أو استقلت؟",
    "عدد الأطفال": "كم عدد الأطفال؟",
    "اسم الطفل": "وش اسم الطفل الكامل؟",
    "أسماء الأطفال": "وش أسماء الأطفال؟",
    "مبلغ الإيجار": "كم مبلغ الإيجار الشهري أو السنوي؟",
    "مبلغ المطالبة": "كم المبلغ المطلوب في الدعوى؟",
    "قيمة المهر": "كم كان مبلغ المهر المتفق عليه؟",
    "مبلغ النفقة": "كم مبلغ النفقة المطلوب شهريًا؟",
    "مبلغ التعويض": "كم تقدّر مبلغ التعويض المطلوب؟",
    "الراتب": "كم كان راتبك الشهري؟",
    "موضوع الدعوى": "بشكل مختصر، وش موضوع الدعوى؟",
    "وقائع الدعوى": "اشرح لي وش اللي صار بالتفصيل؟",
    "الطلبات": "وش اللي تطلبه من المحكمة بالضبط؟",
    "أسانيد الدعوى": "هل عندك مستندات أو رسائل تدعم كلامك؟",
    "نوع العقد": "وش نوع العقد؟ (إيجار، عمل، بيع، ...)",
    "نوع العقار": "وش نوع العقار؟ (شقة، فيلا، أرض، محل تجاري، ...)",
    "المحكمة المختصة": "هل تعرف المحكمة المختصة أو المنطقة؟",
    "صلة القرابة": "وش صلة القرابة بينك وبين الطرف الثاني؟",
}

_KEYWORD_TEMPLATES: list[tuple[str, str]] = [
    ("اسم", "ممكن تعطيني «{field}»؟"),
    ("تاريخ", "متى كان «{field}»؟"),
    ("مبلغ", "كم «{field}»؟"),
    ("قيمة", "كم «{field}»؟"),
    ("رقم", "كم «{field}»؟"),
    ("هوية", "كم «{field}»؟"),
    ("هاتف", "كم «{field}»؟"),
    ("جوال", "كم «{field}»؟"),
    ("عنوان", "وش «{field}»؟"),
    ("عدد", "كم «{field}»؟"),
    ("نوع", "وش «{field}»؟"),
    ("سبب", "وش «{field}»؟"),
    ("وصف", "ممكن توصف لي «{field}»؟"),
    ("تفاصيل", "ممكن تعطيني تفاصيل «{field}»؟"),
]

_CONTEXT_OPENERS: dict[str, str] = {
    "first": "طيب، خلنا نبدأ.\n",
    "batch_note": "تم تسجيل إجابتك. ",
}

_CONTINUATION_OPENERS: tuple[str, ...] = (
    "ممتاز. ",
    "واضح. ",
    "شكرًا لك. ",
    "وصلت الفكرة. ",
    "فهمت عليك. ",
    "جميل. ",
    "تمام عليك. ",
    "يعطيك العافية. ",
    "واضح جدًا. ",
    "خلنا نكمّل. ",
    "ممتاز. ",
    "طيب. ",
)


class QuestionHumanizer:
    """Generates natural Saudi-style Arabic questions instead of exposing
    raw database field names.

    Pure Python — zero LLM cost. Uses a template lookup table with
    keyword-based fallback.
    """

    _call_count: int = 0

    def humanize(
        self,
        field_name: str,
        *,
        hint: str | None = None,
        is_first_question: bool = False,
        batch_extracted_count: int = 0,
    ) -> str:
        template = _FIELD_TEMPLATES.get(field_name)
        if not template:
            template = self._keyword_fallback(field_name)

        opener = ""
        if is_first_question:
            opener = _CONTEXT_OPENERS["first"]
        elif batch_extracted_count > 0:
            opener = f"تم تسجيل {batch_extracted_count} معلومات إضافية من ردك. "
        else:
            opener = _CONTINUATION_OPENERS[self._call_count % len(_CONTINUATION_OPENERS)]
            self._call_count += 1

        hint_suffix = ""
        if hint:
            hint_suffix = f"\n({hint})"

        return f"{opener}{template}{hint_suffix}"

    @staticmethod
    def _keyword_fallback(field_name: str) -> str:
        for keyword, pattern in _KEYWORD_TEMPLATES:
            if keyword in field_name:
                return pattern.format(field=field_name)
        return f"ممكن تزوّدني بـ «{field_name}»؟"
