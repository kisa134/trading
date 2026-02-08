"""
Model config for LLM router: provider, role, model_id, fallbacks.
Env: OPENROUTER_API_KEY, GOOGLE_API_KEY (or VERTEX_* for Vertex AI).

Ensemble roles:
- multimodal_live (visual "eye"): Gemini via REST or OpenRouter; best for canvas/snapshot analysis.
- cognitive_analyst: DeepSeek R1 via OpenRouter; strategic reasoning with <think> and GraphRAG.
- text_analyst: DeepSeek V3 via OpenRouter; Delta, OI, Funding, liquidations JSON → trade plan.
- tick_anomaly (HFT predictor): Visual Mamba local service (VMAMBA_SERVICE_URL); O(n) on tick tape.
- reflection: DeepSeek R1 via OpenRouter; post-mortem on failed predictions, result to graph.
"""
import os
from typing import TypedDict


class ModelEntry(TypedDict):
    model_id: str
    provider: str  # "openrouter" | "google" | "local"
    role: str  # "multimodal_live" | "cognitive_analyst" | "text_analyst" | "aggregator" | "tick_anomaly" | "reflection"
    endpoint: str | None


# Default model mapping (OpenRouter model ids: https://openrouter.ai/docs#models)
MODELS: list[ModelEntry] = [
    {"model_id": "google/gemini-2.0-flash-exp:free", "provider": "openrouter", "role": "multimodal_live", "endpoint": None},
    {"model_id": "deepseek/deepseek-r1", "provider": "openrouter", "role": "cognitive_analyst", "endpoint": None},
    {"model_id": "deepseek/deepseek-chat-v3-0324", "provider": "openrouter", "role": "text_analyst", "endpoint": None},
    {"model_id": "qwen/qwen-2.5-72b-instruct", "provider": "openrouter", "role": "aggregator", "endpoint": None},
    {"model_id": "deepseek/deepseek-r1", "provider": "openrouter", "role": "reflection", "endpoint": None},
    {"model_id": "local/visual-mamba", "provider": "local", "role": "tick_anomaly", "endpoint": None},
]

# Fallback for multimodal when primary fails (e.g. Gemini -> GPT-4o vision)
MULTIMODAL_FALLBACK_MODEL = "openai/gpt-4o"

# DeepSeek V3 for metrics/trade plan (OpenRouter)
DEEPSEEK_METRICS_MODEL = os.environ.get("DEEPSEEK_METRICS_MODEL", "deepseek/deepseek-chat-v3-0324")

# DeepSeek R1 for self-reflection (why did prediction fail?)
DEEPSEEK_REFLECTION_MODEL = os.environ.get("DEEPSEEK_REFLECTION_MODEL", "deepseek/deepseek-r1")

# Optional: Visual Mamba service URL (Docker) for tick anomaly score; set when GPU/Vim available
VMAMBA_SERVICE_URL = os.environ.get("VMAMBA_SERVICE_URL", "")

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
