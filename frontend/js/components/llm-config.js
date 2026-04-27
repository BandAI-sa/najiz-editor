function formatTier(tier) {
  if (tier === "flagship") return "استدلال عميق";
  if (tier === "advanced") return "صياغة متقدمة";
  if (tier === "balanced") return "استخدام عام";
  if (tier === "chat") return "محادثة";
  return "نموذج معتمد";
}

function formatStage(stage) {
  if (stage === "preview") return "معاينة";
  if (stage === "alias") return "إحالة";
  return "";
}

function buildProviderCard(provider, activeProvider, onSelect) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "llm-provider-card";
  button.setAttribute("dir", "rtl");
  button.setAttribute("lang", "ar");

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
  meta.textContent = provider.enabled ? `النموذج الافتراضي: ${provider.default_label || provider.default_model}` : "غير متاح حالياً";

  const tag = document.createElement("span");
  tag.className = "llm-provider-tag";
  tag.textContent = provider.enabled ? "مزود متاح" : "غير مفعّل";

  button.addEventListener("click", () => onSelect(provider.id));
  button.append(title, meta, tag);
  return button;
}

function buildModelCard(model, activeModel, onSelect) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "llm-model-card";
  button.setAttribute("dir", "rtl");
  button.setAttribute("lang", "ar");
  button.title = [model.summary, model.notes].filter(Boolean).join(" ");

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
  tier.textContent = formatTier(model.tier);
  badges.appendChild(tier);

  if (model.recommended) {
    const recommended = document.createElement("span");
    recommended.className = "llm-model-badge";
    recommended.textContent = "الافتراضي";
    badges.appendChild(recommended);
  }

  const stageLabel = formatStage(model.stage);
  if (stageLabel) {
    const stage = document.createElement("span");
    stage.className = "llm-model-badge preview";
    stage.textContent = stageLabel;
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

export function createLLMConfigComponent(elements, handlers) {
  const {
    statusBar,
    statusProvider,
    statusModel,
    changeButton,
    overlay,
    providerOptions,
    modelInput,
    modelOptions,
    hint,
    saveButton,
    cancelButton,
  } = elements;

  changeButton.addEventListener("click", handlers.onOpen);
  cancelButton.addEventListener("click", handlers.onCancel);
  saveButton.addEventListener("click", handlers.onSave);

  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      handlers.onCancel();
    }
  });

  if (modelInput) {
    modelInput.readOnly = true;
  }

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
      const shownModel =
        shownProvider?.models?.find((model) => model.id === llm.selectedModel) ||
        shownProvider?.models?.find((model) => model.id === shownProvider?.default_model) ||
        activeModel;

      statusBar.classList.toggle("hidden", !llm.hasSavedSelection);
      if (shownProvider) {
        statusProvider.textContent = shownProvider.label;
      }
      statusModel.textContent = shownModel?.label || activeModel?.label || "—";

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

      if (modelInput) {
        modelInput.value = activeModel?.label || "";
      }

      hint.textContent = activeModel
        ? `${activeModel.summary}${activeModel.notes ? ` ${activeModel.notes}` : ""}`
        : "اختر نموذجاً معتمداً من البطاقات الظاهرة فقط.";

      saveButton.disabled = !activeProvider?.enabled || !activeModel;
      cancelButton.classList.toggle("hidden", !llm.canDismissChooser);
      cancelButton.disabled = !llm.canDismissChooser;
    },
  };
}
