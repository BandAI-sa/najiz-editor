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

function buildModelCard(model, activeModel, onSelect) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "llm-model-card";
  if (model.id === activeModel) {
    button.classList.add("is-active");
  }

  const title = document.createElement("strong");
  title.textContent = model.label;

  const summary = document.createElement("p");
  summary.className = "llm-model-summary";
  summary.textContent = model.summary;

  const badges = document.createElement("div");
  badges.className = "llm-model-badges";

  const tier = document.createElement("span");
  tier.className = "llm-model-badge";
  tier.textContent = model.tier;
  badges.appendChild(tier);

  if (model.recommended) {
    const recommended = document.createElement("span");
    recommended.className = "llm-model-badge";
    recommended.textContent = "recommended";
    badges.appendChild(recommended);
  }

  if (model.stage && model.stage !== "stable" && model.stage !== "custom") {
    const stage = document.createElement("span");
    stage.className = "llm-model-badge preview";
    stage.textContent = model.stage;
    badges.appendChild(stage);
  }

  const note = document.createElement("p");
  note.className = "llm-model-note";
  note.textContent = model.notes || "";
  note.classList.toggle("hidden", !model.notes);

  button.addEventListener("click", () => onSelect(model.id));
  button.append(title, summary, badges, note);
  return button;
}

function fillSuggestions(listElement, models) {
  listElement.replaceChildren();
  models.forEach((model) => {
    const option = document.createElement("option");
    option.value = model.id;
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
    modelOptions,
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
      const providerModels = activeProvider?.models || [];
      const activeModel =
        providerModels.find((model) => model.id === llm.draftModel) ||
        providerModels.find((model) => model.id === activeProvider?.default_model) ||
        null;

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

      modelOptions.replaceChildren(
        ...providerModels.map((model) => buildModelCard(model, llm.draftModel, handlers.onModelSelect))
      );

      fillSuggestions(modelSuggestions, providerModels);
      if (modelInput.value !== llm.draftModel) {
        modelInput.value = llm.draftModel;
      }

      hint.textContent = activeModel
        ? `${activeModel.summary}${activeModel.notes ? ` ${activeModel.notes}` : ""}`
        : "يمكنك اختيار بطاقة من النماذج المقترحة أو كتابة معرف نموذج مخصص إذا لزم.";

      saveButton.disabled = !activeProvider?.enabled || !llm.draftModel.trim();
      cancelButton.classList.toggle("hidden", !llm.canDismissChooser);
      cancelButton.disabled = !llm.canDismissChooser;
    },
  };
}
