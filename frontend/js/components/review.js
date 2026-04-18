import { setMarkdownContent } from "../utils/markdown.js";

function severityClass(severity) {
  if (severity === "حرج") return "critical";
  if (severity === "تنبيه") return "warning";
  return "suggestion";
}

function scoreClass(score) {
  if (score === null || score === undefined) return "";
  if (score >= 85) return "good";
  if (score >= 65) return "medium";
  return "poor";
}

function buildIssueCard(issue, onAutoFix) {
  const card = document.createElement("article");
  card.className = `review-issue ${severityClass(issue.severity)}`;

  const title = document.createElement("strong");
  title.className = "review-issue-title";
  title.textContent = `${issue.severity} | ${issue.category}`;

  const description = document.createElement("div");
  description.className = "markdown-content";
  setMarkdownContent(description, issue.description, "لا يوجد وصف إضافي.");

  const suggestionLabel = document.createElement("strong");
  suggestionLabel.className = "review-issue-label";
  suggestionLabel.textContent = "الاقتراح";

  const suggestion = document.createElement("div");
  suggestion.className = "markdown-content";
  setMarkdownContent(suggestion, issue.suggestion, "لا توجد توصية إضافية.");

  card.append(title, description, suggestionLabel, suggestion);

  if (issue.auto_fixable) {
    const button = document.createElement("button");
    button.className = "btn btn-secondary";
    button.textContent = "إصلاح تلقائي";
    button.addEventListener("click", () => onAutoFix(issue));
    card.appendChild(button);
  }

  return card;
}

export function createReviewComponent(elements, handlers) {
  const { panel, scoreCircle, scoreNumber, recommendation, summary, issuesList, exportMdButton, exportPdfButton } = elements;
  if (exportMdButton) exportMdButton.addEventListener("click", () => handlers.onExport("md"));
  if (exportPdfButton) exportPdfButton.addEventListener("click", () => handlers.onExport("pdf"));

  return {
    render(state) {
      panel.classList.toggle("hidden", !state.review.isReady && state.currentPhase < 3);
      scoreCircle.className = `score-circle ${scoreClass(state.review.score)}`.trim();
      scoreNumber.textContent = state.review.score ?? "—";
      setMarkdownContent(recommendation, state.review.recommendation, "لم يبدأ التقييم بعد");
      setMarkdownContent(summary, state.review.summary, "سيظهر هنا ملخص المراجعة بعد تشغيلها.");
      if (exportMdButton) exportMdButton.disabled = !state.review.isReady;
      if (exportPdfButton) exportPdfButton.disabled = !state.review.isReady;

      issuesList.replaceChildren();
      state.review.issues.forEach((issue) => {
        issuesList.appendChild(buildIssueCard(issue, handlers.onAutoFix));
      });
    },
  };
}
