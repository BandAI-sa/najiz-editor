from __future__ import annotations

from app.models.classification import ClassificationSelection
from app.models.petition import (
    PetitionDraft,
    PetitionSection,
    PetitionSectionName,
    ReviewIssue,
    ReviewReport,
)
from app.models.session import Session
from app.utils.export import build_printable_html
from app.utils.markdown import render_markdown_html, strip_markdown_text


def build_petition() -> PetitionDraft:
    return PetitionDraft(
        session_id="session-123",
        version=2,
        facts=PetitionSection(
            name=PetitionSectionName.FACTS,
            title="الوقائع",
            content="## وقائع مرتبة\n\n**تفصيل** أول عن النزاع.",
        ),
        evidence=PetitionSection(
            name=PetitionSectionName.EVIDENCE,
            title="الأسانيد",
            content="- مستند أول\n- مستند ثانٍ",
        ),
        requests=PetitionSection(
            name=PetitionSectionName.REQUESTS,
            title="الطلبات",
            content="**إلزام** المدعى عليه بالتسليم.",
        ),
        full_text="## وقائع مرتبة\n\n**تفصيل** أول عن النزاع.",
        review_report=ReviewReport(
            completeness_score=88,
            recommendation="**جاهز للرفع**",
            summary="## ملخص\n\nيوجد **تنبيه** واحد.",
            issues=[
                ReviewIssue(
                    severity="تنبيه",
                    category="صياغة",
                    description="**أضف** تاريخ بداية النزاع.",
                    suggestion="## تحسين\n\nاذكر التاريخ صراحة.",
                )
            ],
        ),
    )


def build_session() -> Session:
    session = Session(session_id="session-123")
    session.classification = ClassificationSelection(
        main_id="main-1",
        sub_id="sub-1",
        case_id="case-1",
        main_title="أحوال شخصية",
        sub_title="التصنيف العام",
        case_title="إقامة حارس قضائي",
        case_path=["أحوال شخصية", "التصنيف العام", "إقامة حارس قضائي"],
    )
    return session


def test_render_markdown_html_supports_headings_and_bold():
    html = render_markdown_html("## عنوان\n\n**نص مهم**")

    assert "<h2>عنوان</h2>" in html
    assert "<strong>نص مهم</strong>" in html


def test_strip_markdown_text_removes_decorators():
    plain = strip_markdown_text("## عنوان\n\n**نص مهم**\n\n- بند")

    assert "عنوان" in plain
    assert "نص مهم" in plain
    assert "بند" in plain
    assert "#" not in plain
    assert "**" not in plain


def test_printable_html_renders_markdown_sections():
    html = build_printable_html(build_session(), build_petition())

    assert "<h2>وقائع مرتبة</h2>" in html
    assert "<strong>تفصيل</strong>" in html
    assert "<li>مستند أول</li>" in html
    assert "<strong>جاهز للرفع</strong>" in html
    assert "<h2>ملخص</h2>" in html
