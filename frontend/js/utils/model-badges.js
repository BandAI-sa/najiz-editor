export const UNKNOWN_MODEL_KEY = "unknown";

export const MODEL_COLORS = {
  o3: { bg: "#E7F0F8", text: "#14476C" },
  "gpt-5.4": { bg: "#E4F4E8", text: "#1D5B29" },
  "gpt-5.2": { bg: "#EEF2DA", text: "#4A5A0E" },
  "gemini-3-pro-preview": { bg: "#FBE7E2", text: "#7B321D" },
  "gemini-2.5-pro": { bg: "#E9E8FB", text: "#3E338A" },
  "gpt-5.2-chat-latest": { bg: "#E5F2F1", text: "#0F5351" },
  "gpt-5.4-mini": { bg: "#FAEEDA", text: "#633806" },
  "gpt-5.4-nano": { bg: "#F9E2DA", text: "#7A331A" },
  "gemini-3-flash-preview": { bg: "#FDE4EA", text: "#8A2444" },
  "gemini-2.5-flash": { bg: "#E5F0FD", text: "#164A89" },
  "gemini-2.5-flash-lite": { bg: "#FFF0D9", text: "#8A5200" },
  unknown: { bg: "#F1EFE8", text: "#444441" },
};

export function getModelBadgeTheme(model) {
  const normalizedModel = typeof model === "string" ? model.trim() : "";
  if (!normalizedModel) {
    return {
      key: UNKNOWN_MODEL_KEY,
      label: "نموذج غير معروف",
      colors: MODEL_COLORS[UNKNOWN_MODEL_KEY],
      isUnknown: true,
    };
  }

  const modelKey = Object.hasOwn(MODEL_COLORS, normalizedModel)
    ? normalizedModel
    : UNKNOWN_MODEL_KEY;

  return {
    key: modelKey,
    label: normalizedModel,
    colors: MODEL_COLORS[modelKey],
    isUnknown: modelKey === UNKNOWN_MODEL_KEY,
  };
}
