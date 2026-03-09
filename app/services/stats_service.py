from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
STATS_PATH = DATA_DIR / "observability_stats.json"
FAILED_RESPONSES_PATH = DATA_DIR / "failed_responses.jsonl"


class StatsService:
    """Application observability counters and summaries."""

    def __init__(self) -> None:
        self._lock = Lock()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not STATS_PATH.exists():
            self._write_stats(self._default_stats())
        if not FAILED_RESPONSES_PATH.exists():
            FAILED_RESPONSES_PATH.touch()

    def record_request(self, *, method: str, path: str, endpoint: str, status_code: int, latency_ms: float, intent: str | None = None) -> None:
        with self._lock:
            stats = self._read_stats()
            stats["http"]["total_requests"] += 1
            if status_code >= 400:
                stats["http"]["error_requests"] += 1
            endpoint_key = endpoint or path
            endpoint_stats = stats["http"]["by_endpoint"].setdefault(
                endpoint_key,
                {
                    "method": method,
                    "path": path,
                    "count": 0,
                    "errors": 0,
                    "avg_latency_ms": 0.0,
                    "last_intent": None,
                    "last_status": None,
                },
            )
            endpoint_stats["count"] += 1
            endpoint_stats["last_status"] = status_code
            endpoint_stats["last_intent"] = intent
            if status_code >= 400:
                endpoint_stats["errors"] += 1
            current_avg = endpoint_stats["avg_latency_ms"]
            total_count = endpoint_stats["count"]
            endpoint_stats["avg_latency_ms"] = round(((current_avg * (total_count - 1)) + latency_ms) / total_count, 2)
            stats["http"]["recent_requests"].append(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "method": method,
                    "path": path,
                    "endpoint": endpoint,
                    "status_code": status_code,
                    "latency_ms": round(latency_ms, 2),
                    "intent": intent,
                }
            )
            stats["http"]["recent_requests"] = stats["http"]["recent_requests"][-50:]
            self._write_stats(stats)

    def record_http_error(self, *, method: str, path: str, status_code: int, body_preview: str, intent: str | None = None) -> None:
        with self._lock:
            stats = self._read_stats()
            stats["http"]["recent_errors"].append(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "intent": intent,
                    "body_preview": body_preview,
                }
            )
            stats["http"]["recent_errors"] = stats["http"]["recent_errors"][-20:]
            self._write_stats(stats)

    def record_intent(self, intent: str) -> None:
        with self._lock:
            stats = self._read_stats()
            stats["intent_counts"][intent] = stats["intent_counts"].get(intent, 0) + 1
            self._write_stats(stats)

    def record_failed_response(self, *, intent: str | None, user_message: str, response_text: str, reason: str) -> None:
        item = {
            "timestamp": datetime.utcnow().isoformat(),
            "intent": intent,
            "user_message": user_message,
            "response_text": response_text,
            "reason": reason,
        }
        with self._lock:
            with FAILED_RESPONSES_PATH.open("a", encoding="utf-8") as file:
                file.write(json.dumps(item, ensure_ascii=False) + "\n")

    def record_ai_usage(self, *, operation: str, model: str, input_tokens: int, output_tokens: int) -> None:
        with self._lock:
            stats = self._read_stats()
            stats["ai"]["calls"] += 1
            stats["ai"]["input_tokens"] += max(input_tokens, 0)
            stats["ai"]["output_tokens"] += max(output_tokens, 0)
            stats["ai"]["by_operation"][operation] = stats["ai"]["by_operation"].get(operation, 0) + 1
            stats["ai"]["last_model"] = model
            self._write_stats(stats)

    def record_ai_error(self, *, error_type: str, detail: str) -> None:
        with self._lock:
            stats = self._read_stats()
            stats["ai"]["errors"][error_type] = stats["ai"]["errors"].get(error_type, 0) + 1
            stats["ai"]["recent_errors"].append(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "error_type": error_type,
                    "detail": detail,
                }
            )
            stats["ai"]["recent_errors"] = stats["ai"]["recent_errors"][-20:]
            self._write_stats(stats)

    def record_fallback(self, *, reason: str, operation: str) -> None:
        with self._lock:
            stats = self._read_stats()
            key = f"{operation}:{reason}"
            stats["ai"]["fallbacks"][key] = stats["ai"]["fallbacks"].get(key, 0) + 1
            self._write_stats(stats)

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            stats = self._read_stats()
        intent_counter = Counter(stats["intent_counts"])
        stats["top_intents"] = [{"intent": key, "count": value} for key, value in intent_counter.most_common(8)]
        stats["failed_responses"] = self._read_failed_examples(limit=20)
        return stats

    def _read_failed_examples(self, limit: int = 20) -> list[dict[str, Any]]:
        if not FAILED_RESPONSES_PATH.exists():
            return []
        lines = FAILED_RESPONSES_PATH.read_text(encoding="utf-8").splitlines()
        items: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(items))

    def _read_stats(self) -> dict[str, Any]:
        with STATS_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _write_stats(self, stats: dict[str, Any]) -> None:
        with STATS_PATH.open("w", encoding="utf-8") as file:
            json.dump(stats, file, ensure_ascii=False, indent=2)

    @staticmethod
    def _default_stats() -> dict[str, Any]:
        return {
            "intent_counts": {},
            "http": {"total_requests": 0, "error_requests": 0, "by_endpoint": {}, "recent_requests": [], "recent_errors": []},
            "ai": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "last_model": None, "by_operation": {}, "errors": {}, "fallbacks": {}, "recent_errors": []},
        }


_stats_service: StatsService | None = None


def get_stats_service() -> StatsService:
    global _stats_service
    if _stats_service is None:
        _stats_service = StatsService()
    return _stats_service
