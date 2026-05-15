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

function resolveRadioOptions(field) {
  if (Array.isArray(field.options) && field.options.length > 0) {
    return field.options;
  }

  return [
    { label: "نعم", value: "نعم" },
    { label: "لا", value: "لا" },
  ];
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

    resolveRadioOptions(field).forEach((option, optionIndex) => {
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
  input.type = field.input_type === "date" ? "date" : field.input_type === "number" ? "number" : "text";
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

  if (!field.required) {
    const optional = document.createElement("span");
    optional.className = "interview-form-optional";
    optional.textContent = "اختياري";
    label.appendChild(optional);
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
  card.classList.toggle("has-error", Boolean(error));

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
  toggle.addEventListener("click", () => {
    if (typeof handlers.onToggleSupport === "function") {
      handlers.onToggleSupport(item.support_id, !expanded);
      return;
    }
    if (typeof handlers.onSupportToggle === "function") {
      handlers.onSupportToggle(item.support_id, !expanded);
    }
  });

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

function captureFieldFocus(container) {
  const activeElement = document.activeElement;
  if (!activeElement || !container.contains(activeElement) || !activeElement.id) {
    return null;
  }

  const focusState = {
    id: activeElement.id,
  };

  if (
    typeof activeElement.selectionStart === "number" &&
    typeof activeElement.selectionEnd === "number"
  ) {
    focusState.selectionStart = activeElement.selectionStart;
    focusState.selectionEnd = activeElement.selectionEnd;
    focusState.selectionDirection = activeElement.selectionDirection || "none";
  }

  return focusState;
}

function restoreFieldFocus(container, focusState) {
  if (!focusState?.id) {
    return;
  }

  const selector = `#${CSS.escape(focusState.id)}`;
  const nextActiveElement = container.querySelector(selector);
  if (!(nextActiveElement instanceof HTMLElement)) {
    return;
  }

  nextActiveElement.focus({ preventScroll: true });

  if (
    typeof focusState.selectionStart === "number" &&
    typeof focusState.selectionEnd === "number" &&
    typeof nextActiveElement.setSelectionRange === "function"
  ) {
    nextActiveElement.setSelectionRange(
      focusState.selectionStart,
      focusState.selectionEnd,
      focusState.selectionDirection || "none"
    );
  }
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
  expandAllButton.addEventListener("click", () => {
    if (typeof handlers.onExpandAllSupports === "function") {
      handlers.onExpandAllSupports(true);
      return;
    }
    if (typeof handlers.onExpandAll === "function") {
      handlers.onExpandAll();
    }
  });
  collapseAllButton.addEventListener("click", () => {
    if (typeof handlers.onExpandAllSupports === "function") {
      handlers.onExpandAllSupports(false);
      return;
    }
    if (typeof handlers.onCollapseAll === "function") {
      handlers.onCollapseAll();
    }
  });

  return {
    render(state) {
      const showForm =
        (state.currentStep === "fill_form" || state.currentStep === "fill_supplementary_form") &&
        Boolean(state.interview.form);
      panel.classList.toggle("hidden", !showForm);
      supportsPanel.classList.toggle("hidden", !showForm);
      if (!showForm || !state.interview.form) {
        return;
      }

      const { form, formValues, formErrors, supportState } = state.interview;
      const groups = groupFields(form.fields || []);
      path.textContent = state.classification.selectedPath || "لم يتم اعتماد نوع الدعوى بعد.";
      title.textContent = form.title;
      description.textContent = form.helper_text || form.description;

      if (state.interview.submitState === "error") {
        status.className = "interview-form-status warning";
      } else if (state.interview.submitState === "success") {
        status.className = "interview-form-status success";
      } else {
        status.className = "interview-form-status";
      }
      status.textContent =
        state.interview.submitMessage ||
        (form.variant === "supplementary_optional"
          ? "هذه البيانات اختيارية بالكامل. يمكنك تعبئة ما يتوفر لديك ثم المتابعة."
          : "أكمل البيانات الأساسية المطلوبة، ثم تابع إلى الصياغة.");

      const focusState = captureFieldFocus(panel);

      groupsContainer.replaceChildren();
      const coreGroups = groups.filter((group) => group.fields.some((field) => field.required));
      const optionalGroups = groups.filter((group) => group.fields.every((field) => !field.required));
      const orderedGroups = form.variant === "supplementary_optional" ? groups : [...coreGroups, ...optionalGroups];

      orderedGroups.forEach((group) => {
        const section = document.createElement("section");
        section.className = "interview-form-group";
        if (group.fields.every((field) => !field.required)) {
          section.classList.add("optional");
        }

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

      restoreFieldFocus(panel, focusState);

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
