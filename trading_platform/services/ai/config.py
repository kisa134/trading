"""
Model config for LLM router: provider, role, model_id, fallbacks.
Env: OPENROUTER_API_KEY, GOOGLE_API_KEY (or VERTEX_* for Vertex AI).
"""
import os
from typing import TypedDict


class ModelEntry(TypedDict):
    model_id: str
    provider: str  # "openrouter" | "google" | "local"
    role: str  # "multimodal_live" | "text_analyst" | "aggregator" | "tick_anomaly" | "reflection"
    endpoint: str | None


# Default model mapping (OpenRouter model ids: https://openrouter.ai/docs#models)
MODELS: list[ModelEntry] = [
    {"model_id": "google/gemini-2.0-flash-exp:free", "provider": "openrouter", "role": "multimodal_live", "endpoint": None},
    {"model_id": "deepseek/deepseek-chat-v3-0324", "provider": "openrouter", "role": "text_analyst", "endpoint": None},
    {"model_id": "qwen/qwen-2.5-72b-instruct", "provider": "openrouter", "role": "aggregator", "endpoint": None},
    {"model_id": "deepseek/deepseek-r1", "provider": "openrouter", "role": "reflection", "endpoint": None},
    {"model_id": "local/visual-mamba", "provider": "local", "role": "tick_anomaly", "endpoint": None},
]

# Fallback for multimodal when primary fails (e.g. Gemini -> GPT-4o vision)
MULTIMODAL_FALLBACK_MODEL = "openai/gpt-4o"

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")


def get_model_for_role(role: str, use_fallback: bool = False) -> ModelEntry | None:
    for m in MODELS:
        if m["role"] == role:
            return m
    return None


def get_multimodal_model(fallback: bool = False) -> ModelEntry | None:
    for m in MODELS:
        if m["role"] == "multimodal_live":
            return m
    return None
