const DRAFT_ROLE_OPTIONS = [
  {
    id: "principal",
    title: "أصيل",
    description: "تصاغ الصحيفة منسوبة مباشرة إلى صاحب الحق نفسه دون عبارات وكالة أو نيابة.",
  },
  {
    id: "agent",
    title: "وكيل",
    description: "تصاغ الصحيفة بصيغة وكيل عن المدعي وبعبارات تمثيل محايدة مثل: بالنيابة عن موكلي.",
  },
];

function buildOption(option, selectedRole, onSelect) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "draft-role-card";
  button.dataset.role = option.id;
  button.setAttribute("aria-pressed", option.id === selectedRole ? "true" : "false");
  button.classList.toggle("is-active", option.id === selectedRole);

  const title = document.createElement("strong");
  title.textContent = option.title;

  const description = document.createElement("span");
  description.textContent = option.description;

  button.append(title, description);
  button.addEventListener("click", () => onSelect(option.id));
  return button;
}

export function createDraftRoleComponent(elements, handlers) {
  const { panel, options, hint } = elements;
  const defaultHint = hint?.textContent || "";

  return {
    render(state) {
      const visible = state.currentStep === "select_petition_role";
      panel.classList.toggle("hidden", !visible);

      if (!visible) {
        if (hint) {
          hint.textContent = defaultHint;
        }
        return;
      }

      if (hint) {
        hint.textContent =
          state.petition.roleSelection === "agent"
            ? "سيتم توجيه الصياغة بصيغة تمثيل عن المدعي مع منع أي تعريف مهني زائد."
            : state.petition.roleSelection === "principal"
              ? "سيتم توجيه الصياغة بصيغة أصيل عن نفسه دون وكالة أو نيابة."
              : defaultHint;
      }

      options.replaceChildren(
        ...DRAFT_ROLE_OPTIONS.map((option) =>
          buildOption(option, state.petition.roleSelection, handlers.onSelect)
        )
      );
    },
  };
}
