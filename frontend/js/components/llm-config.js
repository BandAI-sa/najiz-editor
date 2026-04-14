function buildProviderCard(provider, activeProvider, onSelect) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "llm-provider-card";
  if (provider.id === activeProvider) {
    button.classList.add("is-active");
  }
  if (!provider.enabled) {
    button.classList.add("is-disabled");
    button.disabled = true;
  }

  const title = document.createElement("strong");
  title.textContent = provider.label;

  const meta = document.createElement("span");
  meta.className = "llm-provider-meta";
  meta.textContent = provider.enabled ? `الافتراضي: ${provider.default_model}` : "غير متاح حالياً";

  const tag = document.createElement("span");
  tag.className = "llm-provider-tag";
  tag.textContent = provider.enabled ? provider.id.toUpperCase() : "غير مفعّل";

  button.addEventListener("click", () => onSelect(provider.id));
  button.append(title, meta, tag);
  return button;
}

function fillSuggestions(listElement, suggestions) {
  listElement.replaceChildren();
  suggestions.forEach((model) => {
    const option = document.createElement("option");
    option.value = model;
    listElement.appendChild(option);
  });
}

export function createLLMConfigComponent(elements, handlers) {
  const {
    statusBar,
    statusProvider,
    statusModel,
    changeButton,
    overlay,
    providerOptions,
    modelInput,
    modelSuggestions,
    hint,
    saveButton,
    cancelButton,
  } = elements;

  changeButton.addEventListener("click", handlers.onOpen);
  cancelButton.addEventListener("click", handlers.onCancel);
  saveButton.addEventListener("click", () => handlers.onSave(modelInput.value));
  modelInput.addEventListener("input", () => handlers.onModelInput(modelInput.value));

  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      handlers.onCancel();
    }
  });

  return {
    render(state) {
      const { llm } = state;
      const activeProvider = llm.providers.find((provider) => provider.id === llm.draftProvider) || null;
      const shownProvider = llm.providers.find((provider) => provider.id === llm.selectedProvider) || activeProvider;

      statusBar.classList.toggle("hidden", !llm.hasSavedSelection);
      if (shownProvider) {
        statusProvider.textContent = shownProvider.label;
      }
      statusModel.textContent = llm.selectedModel || activeProvider?.default_model || "—";

      overlay.classList.toggle("hidden", !llm.chooserOpen);
      overlay.setAttribute("aria-hidden", String(!llm.chooserOpen));
      document.body.classList.toggle("overlay-open", llm.chooserOpen);

      providerOptions.replaceChildren(
        ...llm.providers.map((provider) =>
          buildProviderCard(provider, llm.draftProvider, handlers.onProviderSelect)
        )
      );

      fillSuggestions(modelSuggestions, activeProvider?.suggested_models || []);
      if (modelInput.value !== llm.draftModel) {
        modelInput.value = llm.draftModel;
      }

      hint.textContent = activeProvider
        ? `سيُستخدم ${activeProvider.label} مع النموذج ${activeProvider.default_model} افتراضياً، ويمكنك كتابة اسم مختلف إذا رغبت.`
        : "اختر مزوداً أولاً لعرض النماذج المقترحة.";

      saveButton.disabled = !activeProvider?.enabled || !llm.draftModel.trim();
      cancelButton.classList.toggle("hidden", !llm.canDismissChooser);
      cancelButton.disabled = !llm.canDismissChooser;
    },
  };
}
