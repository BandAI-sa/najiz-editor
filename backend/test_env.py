import os
from app.core.config import get_settings

settings = get_settings()
print("OS LLM_PROVIDER:", os.environ.get("LLM_PROVIDER"))
print("OS LLM_ENABLE:", os.environ.get("LLM_ENABLE"))
print("OS OPENAI_API_KEY:", bool(os.environ.get("OPENAI_API_KEY")))
print("OS GEMINI_API_KEY:", bool(os.environ.get("GEMINI_API_KEY")))
print("Settings LLM provider:", settings.llm_provider)
print("Settings LLM enabled:", settings.llm_is_enabled)
print("Settings selected api key bool:", bool(settings.llm_provider_api_key))

with open('env_debug.txt', 'w') as f:
    f.write(f"OS LLM_PROVIDER: {os.environ.get('LLM_PROVIDER')}\n")
    f.write(f"OS LLM_ENABLE: {os.environ.get('LLM_ENABLE')}\n")
    f.write(f"OS OPENAI_API_KEY: {bool(os.environ.get('OPENAI_API_KEY'))}\n")
    f.write(f"OS GEMINI_API_KEY: {bool(os.environ.get('GEMINI_API_KEY'))}\n")
    f.write(f"Settings LLM provider: {settings.llm_provider}\n")
    f.write(f"Settings LLM enabled: {settings.llm_is_enabled}\n")
    f.write(f"Settings selected api key bool: {bool(settings.llm_provider_api_key)}\n")
