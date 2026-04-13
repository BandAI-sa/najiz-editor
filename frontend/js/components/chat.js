function buildMessageCard(message) {
  const wrapper = document.createElement("article");
  wrapper.className = `message-card ${message.role}`;

  const meta = document.createElement("div");
  meta.className = "message-meta";

  const role = document.createElement("strong");
  role.textContent = message.role === "user" ? "أنت" : "الوكيل";

  const time = document.createElement("span");
  time.textContent = new Date(message.timestamp).toLocaleTimeString("ar-SA", {
    hour: "2-digit",
    minute: "2-digit",
  });

  meta.append(role, time);

  const content = document.createElement("div");
  content.textContent = message.content;

  wrapper.append(meta, content);
  return wrapper;
}

export function createChatComponent({ container, form, input, onSubmit }) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = input.value.trim();
    if (!value) {
      return;
    }
    input.value = "";
    await onSubmit(value);
  });

  return {
    render(state) {
      container.replaceChildren();
      state.chat.forEach((message) => {
        container.appendChild(buildMessageCard(message));
      });
      container.scrollTop = container.scrollHeight;
    },
  };
}
