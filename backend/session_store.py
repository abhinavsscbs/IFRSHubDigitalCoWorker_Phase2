import json
import os
import re
from typing import Any, Dict, List, Optional

from rag_engine.rag_config import CHAT_HISTORY_DIR, REDIS_URL, CONFIG

try:
    import redis
except Exception:
    redis = None


def _safe_user_id(user_id: str) -> str:
    if not user_id:
        return "unknown"
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", user_id.strip().lower())
    return safe.strip("_") or "unknown"


class SessionStore:
    def __init__(self) -> None:
        self._client = None
        if redis is not None and CONFIG.get("session", {}).get("provider") == "redis":
            try:
                self._client = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
                self._client.ping()
            except Exception:
                self._client = None
        os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)

    def _key(self, user_id: str) -> str:
        return f"ifrs:history:{user_id}"

    def load_history(self, user_id: str) -> List[Dict[str, Any]]:
        if self._client:
            try:
                raw = self._client.get(self._key(user_id))
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
        return self._load_file_history(user_id)

    def save_history(self, user_id: str, history: List[Dict[str, Any]]) -> None:
        payload = json.dumps(history, ensure_ascii=True)
        if self._client:
            try:
                self._client.set(self._key(user_id), payload)
            except Exception:
                pass
        self._write_file_history(user_id, payload)

    def _file_path(self, user_id: str) -> str:
        safe = _safe_user_id(user_id)
        return os.path.join(CHAT_HISTORY_DIR, f"{safe}.json")

    def _load_file_history(self, user_id: str) -> List[Dict[str, Any]]:
        path = self._file_path(user_id)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _write_file_history(self, user_id: str, payload: str) -> None:
        path = self._file_path(user_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(payload)
        except Exception:
            pass
