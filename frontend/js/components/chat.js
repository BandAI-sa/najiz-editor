import { renderMarkdownToHtml } from "../utils/markdown.js";

function buildMessageCard(message) {
  const wrapper = document.createElement("article");
  wrapper.className = `message-card ${message.role}`;

  const meta = document.createElement("div");
  meta.className = "message-meta";

  const role = document.createElement("strong");
  role.textContent = message.role === "user" ? "أنت" : "المساعد القانوني";

  const time = document.createElement("span");
  time.textContent = new Date(message.timestamp).toLocaleTimeString("ar-SA", {
    hour: "2-digit",
    minute: "2-digit",
  });

  meta.append(role, time);

  const content = document.createElement("div");
  content.className = message.role === "assistant" ? "message-body markdown-content" : "message-body";
  if (message.role === "assistant") {
    content.innerHTML = renderMarkdownToHtml(message.content);
  } else {
    content.textContent = message.content;
  }

  wrapper.append(meta, content);
  return wrapper;
}

function buildPendingCard(message) {
  const wrapper = document.createElement("article");
  wrapper.className = "message-card assistant pending";
  wrapper.setAttribute("aria-live", "polite");

  const meta = document.createElement("div");
  meta.className = "message-meta";

  const role = document.createElement("strong");
  role.textContent = "المساعد القانوني";

  const status = document.createElement("span");
  status.textContent = "قيد المعالجة";

  meta.append(role, status);

  const content = document.createElement("div");
  content.className = "pending-message";

  const spinner = document.createElement("span");
  spinner.className = "pending-spinner";
  spinner.setAttribute("aria-hidden", "true");

  const text = document.createElement("span");
  text.textContent = message;

  content.append(spinner, text);
  wrapper.append(meta, content);
  return wrapper;
}

export function createChatComponent({ container, form, input, submitButton, onSubmit }) {
  const defaultPlaceholder = input.getAttribute("placeholder") || "";

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitButton?.disabled) {
      return;
    }
    const value = input.value.trim();
    if (!value) {
      return;
    }
    input.value = "";
    await onSubmit(value);
  });

  return {
    render(state) {
      const formMode = state.currentStep === "fill_form" || state.currentStep === "select_petition_role";
      container.replaceChildren();
      state.chat.forEach((message) => {
        container.appendChild(buildMessageCard(message));
      });
      if (state.loading && state.loadingMessage) {
        container.appendChild(buildPendingCard(state.loadingMessage));
      }
      const awaitingDraftRole = state.currentStep === "select_petition_role";
      const disabled = state.loading || awaitingDraftRole || state.currentStep === "fill_form";
      container.classList.toggle("hidden", formMode);
      form.classList.toggle("hidden", formMode);
      form.setAttribute("aria-busy", state.loading ? "true" : "false");
      input.disabled = disabled;
      input.placeholder = awaitingDraftRole
        ? "اختر الصيغة (أصيل أو وكيل) للمتابعة إلى الصياغة."
        : defaultPlaceholder;
      if (submitButton) {
        submitButton.disabled = disabled;
      }
      container.scrollTop = container.scrollHeight;
    },
  };
}
