from __future__ import annotations

from html import escape

from app.models.petition import PetitionDraft
from app.models.session import Session
from app.utils.markdown import render_markdown_html


def build_markdown(session: Session, petition: PetitionDraft) -> str:
    path = " > ".join(session.classification.case_path) if session.classification else ""
    return f"""# صحيفة دعوى

**رقم الجلسة:** {session.session_id}
**التصنيف:** {path}
**الإصدار:** {petition.version}

## {petition.facts.title}
{petition.facts.content}

## {petition.evidence.title}
{petition.evidence.content}

## {petition.requests.title}
{petition.requests.content}
"""


def build_pdf(session: Session, petition: PetitionDraft) -> bytes:
    from weasyprint import HTML

    html_content = render_markdown_html(build_markdown(session, petition))

    html_doc = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>صحيفة دعوى</title>
  <style>
    @page {{
      size: A4;
      margin: 2.5cm 2cm;
    }}
    body {{
      font-family: 'Amiri', serif;
      direction: rtl;
      font-size: 14pt;
      line-height: 1.8;
      color: #000;
    }}
    h1 {{ font-size: 20pt; text-align: center; border-bottom: 2px solid #073b3a; padding-bottom: 10px; margin-bottom: 30px; }}
    h2 {{ font-size: 16pt; color: #073b3a; margin-top: 25px; }}
    h3, h4, h5, h6 {{ color: #073b3a; margin-top: 18px; }}
    p {{ margin-bottom: 12px; }}
    ul, ol {{ padding-inline-start: 20px; }}
    li {{ margin-bottom: 8px; }}
    code {{ background: #f3eee6; padding: 2px 6px; border-radius: 6px; }}
  </style>
</head>
<body>
  {html_content}
</body>
</html>"""

    return HTML(string=html_doc).write_pdf()


def build_printable_html(session: Session, petition: PetitionDraft) -> str:
    facts_html = render_markdown_html(petition.facts.content)
    evidence_html = render_markdown_html(petition.evidence.content)
    requests_html = render_markdown_html(petition.requests.content)

    review_block = ""
    if petition.review_report:
        review_block = f"""
        <section class="review-box">
          <h2>تقرير المراجعة</h2>
          <p>درجة الاكتمال: {petition.review_report.completeness_score}</p>
          <div class="markdown-block">{render_markdown_html(petition.review_report.recommendation)}</div>
          <div class="markdown-block">{render_markdown_html(petition.review_report.summary)}</div>
        </section>
        """

    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <title>صحيفة دعوى - {escape(session.classification.case_title if session.classification else 'Najiz')}</title>
  <style>
    body {{ font-family: 'Amiri', serif; margin: 32px; color: #1d1b18; direction: rtl; }}
    h1, h2 {{ color: #073b3a; }}
    .meta, .review-box {{ background: #f6f2ea; padding: 16px; border-radius: 12px; margin-bottom: 20px; }}
    .section {{ margin-bottom: 24px; }}
    .section-content, .markdown-block {{ line-height: 2; }}
    .section-content > :first-child, .markdown-block > :first-child {{ margin-top: 0; }}
    .section-content > :last-child, .markdown-block > :last-child {{ margin-bottom: 0; }}
    ul, ol {{ padding-inline-start: 20px; }}
    li {{ margin-bottom: 8px; }}
    code {{ background: #f3eee6; padding: 2px 6px; border-radius: 6px; }}
    @media print {{ body {{ margin: 0; }} .no-print {{ display: none; }} }}
  </style>
</head>
<body>
  <div class="meta">
    <h1>صحيفة دعوى</h1>
    <p>رقم الجلسة: {escape(session.session_id)}</p>
    <p>التصنيف: {escape(' > '.join(session.classification.case_path) if session.classification else '')}</p>
    <p>الإصدار: {petition.version}</p>
  </div>
  <section class="section">
    <h2>{escape(petition.facts.title)}</h2>
    <div class="section-content">{facts_html}</div>
  </section>
  <section class="section">
    <h2>{escape(petition.evidence.title)}</h2>
    <div class="section-content">{evidence_html}</div>
  </section>
  <section class="section">
    <h2>{escape(petition.requests.title)}</h2>
    <div class="section-content">{requests_html}</div>
  </section>
  {review_block}
  <script>window.print()</script>
</body>
</html>
"""
