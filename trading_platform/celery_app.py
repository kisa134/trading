"""
Celery app: Redis broker, tasks for Outcome Worker and Self-Reflection.
Run worker: celery -A celery_app worker -l info
Run beat:   celery -A celery_app beat -l info
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
COLD_STORAGE_URL = os.environ.get("COLD_STORAGE_URL", "")

app = Celery(
    "trading_platform",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["services.ai.tasks"],
)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_retry_delay=60,
    beat_schedule={
        "outcome-evaluator": {
            "task": "services.ai.tasks.evaluate_outcomes",
            "schedule": 900.0,  # every 15 min
        },
        "refresh-gemini-cache": {
            "task": "services.ai.tasks.refresh_gemini_cache",
            "schedule": 3000.0,  # every 50 min so cache TTL 1h stays valid
        },
    },
)
