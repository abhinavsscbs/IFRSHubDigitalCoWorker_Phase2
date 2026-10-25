"""Simple API smoke test helpers for HubDigitalCoWorker backend.

This version validates:
- Ask:        POST /api/ask
- Follow-up:  POST /api/followup
- Poll:       POST /api/updatestatus
- Translate:  POST /api/translate

It writes all JSON artifacts using UTF-8 encoding to avoid platform-default
encoding issues (notably cp1252 on Windows).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict

import requests


TERMINAL_STATES = {"completed", "failed", "error", "cancelled"}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _safe_json(resp: requests.Response) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception as exc:
        raise RuntimeError(
            f"Expected JSON response but got non-JSON.\n"
            f"Status: {resp.status_code}\n"
            f"Body: {resp.text}"
        ) from exc


def _raise_for_error(resp: requests.Response, step_name: str) -> None:
    if resp.status_code < 400:
        return

    try:
        body = resp.json()
    except Exception:
        body = resp.text

    raise RuntimeError(
        f"{step_name} failed.\n"
        f"HTTP {resp.status_code}\n"
        f"Response: {body}"
    )


def _extract_prompt_payload(resp_json: Dict[str, Any]) -> Dict[str, Any]:
    payload = resp_json.get("payload")
    if not isinstance(payload, dict):
        raise RuntimeError(f"Response missing 'payload' object: {resp_json}")
    return payload


def _extract_prompt_id(resp_json: Dict[str, Any]) -> str:
    payload = _extract_prompt_payload(resp_json)
    prompt_id = payload.get("promptId") or payload.get("id")
    if not prompt_id:
        raise RuntimeError(f"Response missing promptId/id: {resp_json}")
    return str(prompt_id)


def _extract_prompt_status(resp_json: Dict[str, Any]) -> str:
    payload = _extract_prompt_payload(resp_json)
    return str(payload.get("promptStatus", "")).strip().lower()


def _poll_until_terminal(
    base_url: str,
    user_id: str,
    prompt_id: str,
    poll_interval_seconds: float,
    trace_file: Path,
) -> Dict[str, Any]:
    poll_history = []

    while True:
        response = requests.post(
            f"{base_url}/api/updatestatus",
            json={
                "userId": user_id,
                "promptId": prompt_id,
                "waitForTerminalMs": 0,
            },
        )
        _raise_for_error(response, "poll status")
        payload = _safe_json(response)
        poll_history.append(payload)

        status = _extract_prompt_status(payload)
        if status in TERMINAL_STATES:
            _write_json(
                trace_file,
                {"promptId": prompt_id, "pollHistory": poll_history},
            )
            return payload

        time.sleep(poll_interval_seconds)


def _post_json(
    url: str,
    payload: Dict[str, Any],
    step_name: str,
) -> Dict[str, Any]:
    response = requests.post(url, json=payload)
    _raise_for_error(response, step_name)
    return _safe_json(response)


def run_smoke(
    base_url: str,
    user_query: str,
    followup_query: str,
    poll_interval_seconds: float,
    results_dir: Path,
    user_id: str,
    clear_history_first: bool,
) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    base_url = base_url.rstrip("/")

    if clear_history_first:
        clear_payload = {"userId": user_id}
        clear_resp = _post_json(
            f"{base_url}/api/clear",
            clear_payload,
            "clear history",
        )
        _write_json(results_dir / "clear_response.json", clear_resp)

    # -------------------------
    # 1) ASK
    # -------------------------
    ask_payload = {
        "userId": user_id,
        "question": user_query,
    }
    ask_resp = _post_json(
        f"{base_url}/api/ask",
        ask_payload,
        "ask",
    )
    _write_json(results_dir / "ask_start_response.json", ask_resp)

    ask_prompt_id = _extract_prompt_id(ask_resp)

    ask_final = _poll_until_terminal(
        base_url=base_url,
        user_id=user_id,
        prompt_id=ask_prompt_id,
        poll_interval_seconds=poll_interval_seconds,
        trace_file=results_dir / "ask_poll_history.json",
    )
    _write_json(results_dir / "ask_final_response.json", ask_final)

    ask_final_status = _extract_prompt_status(ask_final)
    if ask_final_status != "completed":
        raise RuntimeError(
            f"Ask prompt ended in non-success terminal state: {ask_final_status}"
        )

    # -------------------------
    # 2) FOLLOW-UP
    # -------------------------
    followup_payload = {
        "userId": user_id,
        "promptId": ask_prompt_id,
        "question": "Now answer in tabular form.",
    }
    followup_resp = _post_json(
        f"{base_url}/api/followup",
        followup_payload,
        "followup",
    )
    _write_json(results_dir / "followup_start_response.json", followup_resp)

    followup_prompt_id = _extract_prompt_id(followup_resp)

    followup_final = _poll_until_terminal(
        base_url=base_url,
        user_id=user_id,
        prompt_id=followup_prompt_id,
        poll_interval_seconds=poll_interval_seconds,
        trace_file=results_dir / "followup_poll_history.json",
    )
    _write_json(results_dir / "followup_final_response.json", followup_final)

    followup_final_status = _extract_prompt_status(followup_final)
    if followup_final_status != "completed":
        raise RuntimeError(
            "Follow-up prompt ended in non-success terminal state: "
            f"{followup_final_status}"
        )

    # -------------------------
    # 3) TRANSLATE
    # -------------------------
    translate_payload = {
        "userId": user_id,
    }
    translate_resp = _post_json(
        f"{base_url}/api/translate",
        translate_payload,
        "translate",
    )
    _write_json(results_dir / "translate_response.json", translate_resp)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run API smoke test flow")
    parser.add_argument("--base-url", default="http://localhost:3000")
    parser.add_argument("--query", default="What is the difference between an operating lease and finance lease?")
    parser.add_argument(
        "--followup-query",
        default="Now answer in tabular form.",
    )
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--results-dir", default="smoke_results/api.tester2")
    parser.add_argument("--user-id", default="api.tester2")
    parser.add_argument(
        "--clear-history-first",
        action="store_true",
        help="Clear chat history for the smoke-test user before running.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    run_smoke(
        base_url=args.base_url,
        user_query=args.query,
        followup_query=args.followup_query,
        poll_interval_seconds=args.poll_interval_seconds,
        results_dir=Path(args.results_dir),
        user_id=args.user_id,
        clear_history_first=args.clear_history_first,
    )


if __name__ == "__main__":
    main()