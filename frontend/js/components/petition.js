function buildSkeleton() {
  const wrapper = document.createElement("div");
  wrapper.className = "petition-loading";

  const spinner = document.createElement("div");
  spinner.className = "spinner";

  const label = document.createElement("p");
  label.className = "petition-loading-label";
  label.textContent = "جارٍ توليد هذا القسم...";

  const skeleton = document.createElement("div");
  skeleton.className = "skeleton-stack";
  for (let index = 0; index < 5; index += 1) {
    const line = document.createElement("div");
    line.className = `skeleton-line ${index === 4 ? "short" : ""}`.trim();
    skeleton.appendChild(line);
  }

  wrapper.append(spinner, label, skeleton);
  return wrapper;
}

function buildEditor({ value, section, disabled, readonly, onInput }) {
  const wrapper = document.createElement("div");
  wrapper.className = "petition-editor-shell";

  const note = document.createElement("div");
  note.className = "petition-editor-note";
  if (disabled) {
    note.textContent = "يتم تجهيز أو حفظ هذا القسم الآن...";
  } else if (readonly) {
    note.textContent = "القسم في وضع القراءة، انقر على 'تعديل الاختيار' لإجراء أي تغييرات.";
  } else {
    note.textContent = "وضع التعديل مفعل. لا تنسَ النقر على 'حفظ' بعد الانتهاء.";
  }

  const editor = document.createElement("textarea");
  editor.className = "petition-editor petition-text";
  editor.value = value;
  editor.disabled = disabled;
  editor.readOnly = readonly;
  editor.rows = 16;
  editor.spellcheck = false;
  editor.setAttribute("aria-label", sectionLabel(section));
  editor.placeholder = "سيظهر محتوى هذا القسم هنا عند اكتمال التوليد.";
  editor.addEventListener("input", () => onInput(section, editor.value));

  wrapper.append(note, editor);
  return wrapper;
}

function sectionLabel(tab) {
  if (tab === "facts") return "الوقائع";
  if (tab === "evidence") return "الأسانيد";
  return "الطلبات";
}

export function createPetitionComponent(elements, handlers) {
  const { panel, content, reviewButton, editButton, saveButton, statusLabel, tabButtons } = elements;

  tabButtons.forEach((button) => {
    button.addEventListener("click", () => handlers.onTabChange(button.dataset.tab));
  });

  reviewButton.addEventListener("click", handlers.onReview);
  editButton.addEventListener("click", handlers.onEditActive);
  saveButton.addEventListener("click", handlers.onSaveActive);

  return {
    render(state) {
      const activeTab = state.petition.activeTab;
      const hasPetition =
        Boolean(state.petition.facts) ||
        Boolean(state.petition.evidence) ||
        Boolean(state.petition.requests) ||
        state.petition.isGenerating;
      const isLoadingSection = state.petition.loadingSections[activeTab];
      const activeContent = state.petition[activeTab] || "";
      const hasDirtyActiveSection = state.petition.dirtySections[activeTab];

      panel.classList.toggle("hidden", !hasPetition && state.currentPhase < 2);
      reviewButton.disabled =
        !hasPetition || state.petition.isGenerating || state.petition.saveState === "saving" || state.petition.editMode;
      editButton.disabled =
        !hasPetition || state.petition.isGenerating || state.petition.saveState === "saving" || state.petition.editMode;
      saveButton.disabled =
        state.petition.isGenerating ||
        state.petition.saveState === "saving" ||
        !hasDirtyActiveSection ||
        !activeContent.trim();
        
      editButton.style.display = state.petition.editMode ? "none" : "inline-block";
      saveButton.style.display = state.petition.editMode ? "inline-block" : "none";

      tabButtons.forEach((button) => {
        const tab = button.dataset.tab;
        button.classList.toggle("active", tab === activeTab);
        button.classList.toggle("loading", state.petition.loadingSections[tab]);
        button.classList.toggle("dirty", state.petition.dirtySections[tab]);
      });

      if (state.petition.isGenerating) {
        statusLabel.textContent = `جارٍ توليد قسم ${sectionLabel(activeTab)}...`;
      } else if (state.petition.saveState === "saving") {
        statusLabel.textContent = "جارٍ حفظ التعديل...";
      } else if (state.petition.saveState === "saved") {
        statusLabel.textContent = state.petition.saveMessage || "تم حفظ التعديل.";
      } else if (state.petition.saveState === "error") {
        statusLabel.textContent = state.petition.saveMessage || "تعذر حفظ التعديل.";
      } else if (hasDirtyActiveSection) {
        statusLabel.textContent = "يوجد تعديل غير محفوظ في هذا القسم.";
      } else {
        statusLabel.textContent = `تحرير مباشر لقسم ${sectionLabel(activeTab)}.`;
      }

      content.setAttribute(
        "aria-busy",
        state.petition.isGenerating || state.petition.saveState === "saving" ? "true" : "false"
      );
      if (isLoadingSection && !activeContent.trim()) {
        content.replaceChildren();
        content.appendChild(buildSkeleton());
        return;
      }

      const existingEditor = content.querySelector(".petition-editor");
      const currentSection = existingEditor ? existingEditor.getAttribute("aria-label") : null;
      const expectedSectionLabel = sectionLabel(activeTab);
      const disabledState = state.petition.isGenerating || state.petition.saveState === "saving";
      const readonlyState = !state.petition.editMode;

      if (!existingEditor || currentSection !== expectedSectionLabel) {
        content.replaceChildren();
        content.appendChild(
          buildEditor({
            value: activeContent,
            section: activeTab,
            disabled: disabledState,
            readonly: readonlyState,
            onInput: handlers.onContentInput,
          })
        );
      } else {
        if (existingEditor.value !== activeContent) {
           existingEditor.value = activeContent;
        }
        existingEditor.disabled = disabledState;
        existingEditor.readOnly = readonlyState;
        
        const note = content.querySelector(".petition-editor-note");
        if (note) {
          if (disabledState) {
            note.textContent = "يتم تجهيز أو حفظ هذا القسم الآن...";
          } else if (readonlyState) {
            note.textContent = "القسم في وضع القراءة، انقر على 'تعديل الاختيار' لإجراء أي تغييرات.";
          } else {
            note.textContent = "وضع التعديل مفعل. لا تنسَ النقر على 'حفظ' بعد الانتهاء.";
          }
        }
      }
    },
  };
}
