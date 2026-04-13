from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol, Type


LLMMessage = dict[str, str]


class LLMClient(Protocol):
    provider: str

    @property
    def enabled(self) -> bool: ...

    async def generate_text(
        self,
        capability: str,
        instructions: str,
        user_input: Any,
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str | None: ...

    async def parse_structured(
        self,
        capability: str,
        instructions: str,
        user_input: Any,
        schema: Type[Any],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> Any | None: ...


def normalize_prompt_payload(instructions: str, user_input: Any) -> tuple[str, list[LLMMessage]]:
    system_parts = [instructions.strip()]
    messages: list[LLMMessage] = []

    if isinstance(user_input, list):
        for item in user_input:
            role = str(item.get("role", "user")).strip().lower()
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            if role == "system":
                system_parts.append(content)
                continue
            normalized_role = "assistant" if role in {"assistant", "model"} else "user"
            messages.append({"role": normalized_role, "content": content})
    elif user_input is not None:
        content = str(user_input).strip()
        if content:
            messages.append({"role": "user", "content": content})

    merged_instructions = "\n\n".join(part for part in system_parts if part)
    return merged_instructions, messages


def render_conversation_prompt(messages: list[LLMMessage]) -> str:
    if not messages:
        return ""

    rendered_blocks: list[str] = []
    for message in messages:
        label = "المساعد" if message["role"] == "assistant" else "المستخدم"
        rendered_blocks.append(f"{label}:\n{message['content']}")
    return "\n\n".join(rendered_blocks)


def build_gemini_json_schema(schema: Type[Any]) -> dict[str, Any]:
    raw_schema = deepcopy(schema.model_json_schema())
    definitions = raw_schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_name = str(node["$ref"]).split("/")[-1]
                return resolve(deepcopy(definitions.get(ref_name, {})))

            cleaned: dict[str, Any] = {}
            for key, value in node.items():
                if key in {"$defs", "$schema", "title", "default", "examples"}:
                    continue
                cleaned[key] = resolve(value)
            return cleaned

        if isinstance(node, list):
            return [resolve(item) for item in node]

        return node

    return resolve(raw_schema)
