function buildChip(label, value) {
  const chip = document.createElement("div");
  chip.className = "chip";
  chip.textContent = `${label}: ${value}`;
  return chip;
}

function severityClass(severity) {
  if (severity === "حرج") return "critical";
  if (severity === "تنبيه") return "warning";
  return "suggestion";
}

export function createProgressComponent(elements) {
  const { label, bar, value, count, extractedFields, guardAlerts } = elements;

  return {
    render(state) {
      label.textContent = state.interview.currentPrompt || "ابدأ بذكر الوقائع الأساسية.";
      bar.style.width = `${state.interview.completion}%`;
      value.textContent = `${state.interview.completion}%`;
      count.textContent = `${state.interview.missingFields.length} حقول متبقية`;

      extractedFields.replaceChildren();
      Object.entries(state.interview.extractedData).forEach(([field, fieldValue]) => {
        extractedFields.appendChild(buildChip(field, fieldValue));
      });

      guardAlerts.replaceChildren();
      state.flags.guardIssues.forEach((issue) => {
        const alert = document.createElement("article");
        alert.className = `alert-card ${severityClass(issue.severity)}`;
        const title = document.createElement("strong");
        title.textContent = issue.title;
        const desc = document.createElement("p");
        desc.textContent = `${issue.description} ${issue.recommendation}`;
        alert.append(title, desc);
        guardAlerts.appendChild(alert);
      });
    },
  };
}
