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

  const description = document.createElement("p");
  description.textContent = issue.description;

  const suggestion = document.createElement("p");
  suggestion.textContent = `الاقتراح: ${issue.suggestion}`;

  card.append(title, description, suggestion);

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
  if(exportMdButton) exportMdButton.addEventListener("click", () => handlers.onExport("md"));
  if(exportPdfButton) exportPdfButton.addEventListener("click", () => handlers.onExport("pdf"));

  return {
    render(state) {
      panel.classList.toggle("hidden", !state.review.isReady && state.currentPhase < 3);
      scoreCircle.className = `score-circle ${scoreClass(state.review.score)}`.trim();
      scoreNumber.textContent = state.review.score ?? "—";
      recommendation.textContent = state.review.recommendation || "لم يبدأ التقييم بعد";
      summary.textContent = state.review.summary || "سيظهر هنا ملخص المراجعة بعد تشغيلها.";
      if(exportMdButton) exportMdButton.disabled = !state.review.isReady;
      if(exportPdfButton) exportPdfButton.disabled = !state.review.isReady;

      issuesList.replaceChildren();
      state.review.issues.forEach((issue) => {
        issuesList.appendChild(buildIssueCard(issue, handlers.onAutoFix));
      });
    },
  };
}
