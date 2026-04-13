function fillSelect(select, items, placeholder) {
  select.replaceChildren();
  const initial = document.createElement("option");
  initial.value = "";
  initial.textContent = placeholder;
  select.appendChild(initial);
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.title;
    select.appendChild(option);
  });
}

function buildSuggestionCard(suggestion, index, onSelect) {
  const card = document.createElement("article");
  card.className = "suggestion-card";

  const title = document.createElement("strong");
  title.textContent = `${index + 1}. ${suggestion.case_title}`;

  const meta = document.createElement("div");
  meta.className = "suggestion-meta";
  meta.textContent = `${suggestion.main_title} > ${suggestion.sub_title} | ${Math.round(
    suggestion.confidence * 100
  )}%`;

  const reason = document.createElement("p");
  reason.textContent = suggestion.rationale;

  const button = document.createElement("button");
  button.className = "btn btn-secondary";
  button.textContent = "اعتماد هذا الاقتراح";
  button.addEventListener("click", () => onSelect(index + 1));

  card.append(title, meta, reason, button);
  return card;
}

export function createClassificationComponent(elements, handlers) {
  const { mainSelect, subSelect, caseSelect, manualButton, suggestionsPanel } = elements;

  mainSelect.addEventListener("change", async () => {
    await handlers.onMainChange(mainSelect.value);
  });

  subSelect.addEventListener("change", async () => {
    await handlers.onSubChange(subSelect.value);
  });

  caseSelect.addEventListener("change", () => {
    handlers.onCaseChange(caseSelect.value);
  });

  manualButton.addEventListener("click", handlers.onManualSubmit);

  return {
    render(state) {
      fillSelect(mainSelect, state.classification.mains, "اختر التصنيف الرئيسي");
      mainSelect.value = state.classification.mainId || "";

      fillSelect(subSelect, state.classification.subs, "اختر التصنيف الفرعي");
      subSelect.value = state.classification.subId || "";
      subSelect.disabled = state.classification.subs.length === 0;

      fillSelect(caseSelect, state.classification.cases, "اختر نوع الدعوى");
      caseSelect.value = state.classification.caseId || "";
      caseSelect.disabled = state.classification.cases.length === 0;

      manualButton.disabled = !state.classification.caseId;

      suggestionsPanel.replaceChildren();
      state.classification.suggestions.forEach((suggestion, index) => {
        suggestionsPanel.appendChild(buildSuggestionCard(suggestion, index, handlers.onSuggestionSelect));
      });
    },
  };
}
