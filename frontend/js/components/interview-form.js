function groupFields(fields) {
  const groups = [];
  const indexById = new Map();

  fields.forEach((field) => {
    if (!indexById.has(field.group_id)) {
      indexById.set(field.group_id, groups.length);
      groups.push({
        id: field.group_id,
        label: field.group_label,
        fields: [],
      });
    }

    groups[indexById.get(field.group_id)].fields.push(field);
  });

  return groups;
}

function fieldDomIds(fieldKey) {
  return {
    inputId: `interview-field-${fieldKey}`,
    hintId: `interview-hint-${fieldKey}`,
    errorId: `interview-error-${fieldKey}`,
  };
}

function buildFieldInput(field, value, error, handlers) {
  const { inputId, hintId, errorId } = fieldDomIds(field.key);
  const describedBy = [field.hint ? hintId : "", error ? errorId : ""].filter(Boolean).join(" ");

  if (field.input_type === "textarea") {
    const textarea = document.createElement("textarea");
    textarea.id = inputId;
    textarea.className = "interview-form-input interview-form-textarea";
    textarea.rows = 4;
    textarea.value = value;
    textarea.placeholder = field.placeholder || "";
    textarea.setAttribute("aria-label", field.aria_label);
    textarea.setAttribute("aria-invalid", String(Boolean(error)));
    if (describedBy) {
      textarea.setAttribute("aria-describedby", describedBy);
    }
    textarea.addEventListener("input", () => handlers.onFieldInput(field.key, textarea.value));
    return textarea;
  }

  if (field.input_type === "radio") {
    const wrapper = document.createElement("div");
    wrapper.className = "interview-form-radio-group";
    wrapper.setAttribute("role", "radiogroup");
    wrapper.setAttribute("aria-label", field.aria_label);
    wrapper.setAttribute("aria-invalid", String(Boolean(error)));
    if (describedBy) {
      wrapper.setAttribute("aria-describedby", describedBy);
    }

    field.options.forEach((option, optionIndex) => {
      const label = document.createElement("label");
      label.className = "interview-form-radio";

      const input = document.createElement("input");
      input.id = `${inputId}-${optionIndex + 1}`;
      input.type = "radio";
      input.name = field.key;
      input.value = option.value;
      input.checked = value === option.value;
      input.addEventListener("change", () => handlers.onFieldInput(field.key, option.value));

      const text = document.createElement("span");
      text.textContent = option.label;

      label.append(input, text);
      wrapper.appendChild(label);
    });

    return wrapper;
  }

  const input = document.createElement("input");
  input.id = inputId;
  input.className = "interview-form-input";
  input.type = field.input_type === "date" ? "date" : "text";
  input.value = value;
  input.placeholder = field.placeholder || "";
  input.setAttribute("aria-label", field.aria_label);
  input.setAttribute("aria-invalid", String(Boolean(error)));
  if (describedBy) {
    input.setAttribute("aria-describedby", describedBy);
  }
  input.addEventListener("input", () => handlers.onFieldInput(field.key, input.value));
  return input;
}

function buildFieldCard(field, value, error, handlers) {
  const { inputId, hintId, errorId } = fieldDomIds(field.key);
  const card = document.createElement("div");
  card.className = "interview-form-field";

  const header = document.createElement("div");
  header.className = "interview-form-field-head";

  const label = document.createElement("label");
  label.className = "interview-form-label";
  label.textContent = field.label;
  if (field.input_type !== "radio") {
    label.htmlFor = inputId;
  }

  if (field.required) {
    const required = document.createElement("span");
    required.className = "interview-form-required";
    required.textContent = "إلزامي";
    label.appendChild(required);
  }

  header.appendChild(label);

  if (field.badge_label) {
    const badge = document.createElement("span");
    badge.className = "interview-form-badge";
    badge.textContent = field.badge_label;
    header.appendChild(badge);
  }

  const hint = document.createElement("p");
  hint.id = hintId;
  hint.className = "interview-form-hint";
  hint.textContent = field.hint || "";
  hint.classList.toggle("hidden", !field.hint);

  const input = buildFieldInput(field, value, error, handlers);

  const errorText = document.createElement("p");
  errorText.id = errorId;
  errorText.className = "interview-form-error";
  errorText.textContent = error || "";
  errorText.classList.toggle("hidden", !error);

  card.append(header, hint, input, errorText);
  return card;
}

function buildSupportItem(item, expanded, handlers) {
  const article = document.createElement("article");
  article.className = "support-item";

  const top = document.createElement("div");
  top.className = "support-item-top";

  const copy = document.createElement("div");
  copy.className = "support-item-copy";

  const title = document.createElement("strong");
  title.textContent = item.title;

  const summary = document.createElement("p");
  summary.className = "support-item-summary";
  summary.textContent = item.summary;

  copy.append(title, summary);

  const detailsId = `support-details-${item.support_id}`;
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "btn btn-ghost support-toggle-btn";
  toggle.textContent = expanded ? "إخفاء التفاصيل" : "عرض التفاصيل";
  toggle.setAttribute("aria-label", item.aria_label);
  toggle.setAttribute("aria-expanded", String(expanded));
  toggle.setAttribute("aria-controls", detailsId);
  toggle.addEventListener("click", () => handlers.onToggleSupport(item.support_id, !expanded));

  top.append(copy, toggle);

  const details = document.createElement("div");
  details.id = detailsId;
  details.className = expanded ? "support-item-details is-open" : "support-item-details";
  details.setAttribute("aria-hidden", String(!expanded));

  const detailsInner = document.createElement("div");
  detailsInner.className = "support-item-details-inner";
  detailsInner.textContent = item.details;

  details.appendChild(detailsInner);
  article.append(top, details);
  return article;
}

export function createInterviewFormComponent(elements, handlers) {
  const {
    panel,
    path,
    title,
    description,
    status,
    groupsContainer,
    submitButton,
    supportsPanel,
    supportsList,
    expandAllButton,
    collapseAllButton,
  } = elements;

  submitButton.addEventListener("click", handlers.onSubmit);
  expandAllButton.addEventListener("click", () => handlers.onExpandAllSupports(true));
  collapseAllButton.addEventListener("click", () => handlers.onExpandAllSupports(false));

  return {
    render(state) {
      const showForm = state.currentStep === "fill_form" && Boolean(state.interview.form);
      panel.classList.toggle("hidden", !showForm);
      supportsPanel.classList.toggle("hidden", !showForm);
      if (!showForm || !state.interview.form) {
        return;
      }

      const { form, formValues, formErrors, supportState } = state.interview;
      const groups = groupFields(form.fields || []);
      path.textContent = state.classification.selectedPath || "لم يتم اعتماد نوع الدعوى بعد.";
      title.textContent = form.title;
      description.textContent = form.description;

      if (state.interview.submitState === "error") {
        status.className = "interview-form-status warning";
      } else if (state.interview.submitState === "success") {
        status.className = "interview-form-status success";
      } else {
        status.className = "interview-form-status";
      }
      status.textContent =
        state.interview.submitMessage || "أكمل جميع الحقول الإلزامية ثم اعتمد البيانات للمتابعة.";

      groupsContainer.replaceChildren();
      groups.forEach((group) => {
        const section = document.createElement("section");
        section.className = "interview-form-group";

        const heading = document.createElement("h3");
        heading.textContent = group.label;

        const grid = document.createElement("div");
        grid.className = "interview-form-grid";

        group.fields.forEach((field) => {
          const value = formValues[field.key] || "";
          const error = formErrors[field.key] || "";
          grid.appendChild(buildFieldCard(field, value, error, handlers));
        });

        section.append(heading, grid);
        groupsContainer.appendChild(section);
      });

      supportsList.replaceChildren();
      (form.support_items || []).forEach((item) => {
        const expanded = Boolean(supportState.expandedById[item.support_id]);
        supportsList.appendChild(buildSupportItem(item, expanded, handlers));
      });

      const expandedValues = Object.values(supportState.expandedById || {});
      const allExpanded = expandedValues.length > 0 && expandedValues.every(Boolean);
      const anyExpanded = expandedValues.some(Boolean);

      expandAllButton.disabled = state.loading || allExpanded;
      collapseAllButton.disabled = state.loading || !anyExpanded;

      const hasBlockingErrors = Object.values(formErrors).some(Boolean);
      submitButton.textContent = form.submit_label;
      submitButton.disabled = state.loading || hasBlockingErrors;
    },
  };
}
