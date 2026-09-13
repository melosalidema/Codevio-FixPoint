"""Local OpenAI-compatible mock for the Fixpoint LLM planner (dev only).

Lets you demo and test `planner_source=llm` with zero external keys or network.
It is NOT a language model: it reuses Fixpoint's own deterministic parser so the
responses are well-formed and schema-valid.

Run:
    cd backend
    python -m scripts.mock_llm_server --port 8123

Then start the API with:
    FIXPOINT_LLM_ENABLED=true
    FIXPOINT_LLM_BASE_URL=http://localhost:8123/v1
    FIXPOINT_LLM_API_KEY=mock
    FIXPOINT_LLM_MODEL=mock-llm
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from app.agent.parser import parse


def _facts_from_text(text: str) -> dict[str, Any]:
    return parse(text).model_dump(mode="json")


def _action_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    facts = payload.get("facts", {})
    charges = payload.get("charges", [])
    duplicates = set(payload.get("duplicate_charge_ids", []))
    if not charges:
        return None
    target = next((c for c in charges if c.get("id") in duplicates), charges[0])
    amount = facts.get("amount_cents") or target.get("amount_cents", 0)
    return {
        "action": {
            "tool": "stripe.refund",
            "params": {
                "charge_id": target["id"],
                "amount_cents": int(amount),
                "reason": "duplicate charge" if target["id"] in duplicates else "policy_exception",
            },
            "justification": "mock model proposal",
            "evidence_refs": [f"stripe:{target['id']}"],
        }
    }


def _reply(system: str, user: str) -> str:
    if "extract structured data" in system.lower():
        try:
            text = json.loads(user).get("text", "")
        except (json.JSONDecodeError, AttributeError):
            text = user
        return json.dumps(_facts_from_text(text))

    try:
        payload = json.loads(user)
    except json.JSONDecodeError:
        payload = {}
    return json.dumps(_action_from_payload(payload) or {"action": None})


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = {}
        messages = body.get("messages", [])
        system = messages[0].get("content", "") if messages else ""
        user = messages[1].get("content", "") if len(messages) > 1 else ""
        content = _reply(system, user)

        response = {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": 0,
            "model": body.get("model", "mock-llm"),
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 42, "completion_tokens": 24, "total_tokens": 66},
        }
        payload = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: Any) -> None:  # keep the console quiet
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock OpenAI-compatible server for Fixpoint")
    parser.add_argument("--port", type=int, default=8123)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"mock LLM listening on http://127.0.0.1:{args.port}/v1")
    server.serve_forever()


if __name__ == "__main__":
    main()
