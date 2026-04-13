import asyncio
import traceback
import sys
import os

try:
    from app.core.config import get_settings
    from app.services.llm.openai_client import OpenAIResponseClient
    from pydantic import BaseModel
    class TestSchema(BaseModel):
        suggestions: list[str] = []
except Exception as e:
    with open('output.txt', 'w', encoding='utf-8') as f:
        f.write(f"Import Error: {e}\n{traceback.format_exc()}")
    sys.exit(1)

async def test():
    try:
        settings = get_settings()
        client = OpenAIResponseClient(settings)
        await client.parse_structured("classifier", "say hi", [{"role": "user", "content": "hi"}], TestSchema)
        with open('output.txt', 'w', encoding='utf-8') as f:
            f.write("Success!\n")
    except Exception as e:
        with open('output.txt', 'w', encoding='utf-8') as f:
            f.write(f"Parse Error: {e}\n{traceback.format_exc()}")

asyncio.run(test())
