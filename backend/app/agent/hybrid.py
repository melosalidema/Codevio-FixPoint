"""Hybrid parser/planner: LLM when configured, deterministic fallback always.

The wrappers keep the engine's simple callable interface. They record which
source actually produced the facts/action so the run detail can show whether the
LLM was used or the deterministic planner stepped in.
"""

from __future__ import annotations

from typing import Any

from app.agent.llm import LLMClient, parse_with_llm, propose_with_llm
from app.agent.parser import parse
from app.agent.planner import Resolution, propose
from app.safety.models import ParsedFacts, ProposedAction, RunContext


class HybridParser:
    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client
        self.last_source = "deterministic"
        self.last_error = ""

    def __call__(self, text: str) -> ParsedFacts:
        if self.client is None:
            self.last_source = "deterministic"
            return parse(text)
        try:
            facts = parse_with_llm(self.client, text)
            self.last_source = "llm"
            self.last_error = ""
            return facts
        except Exception as error:  # noqa: BLE001 - any failure must fall back safely
            self.last_source = "deterministic_fallback"
            self.last_error = str(error)[:200]
            return parse(text)


class HybridPlanner:
    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client
        self.last_source = "deterministic"
        self.last_error = ""
        self.meta: dict[str, Any] = {}

    def __call__(
        self,
        facts: ParsedFacts,
        resolution: Resolution,
        ctx: RunContext,
    ) -> ProposedAction | None:
        if self.client is None:
            self.last_source = "deterministic"
            return propose(facts, resolution, ctx)
        try:
            action = propose_with_llm(self.client, facts, resolution, ctx)
            self.last_source = "llm"
            self.last_error = ""
            self.meta = dict(getattr(self.client, "last_meta", {}) or {})
            return action
        except Exception as error:  # noqa: BLE001 - fall back, never fail closed-open
            self.last_source = "deterministic_fallback"
            self.last_error = str(error)[:200]
            meta = dict(getattr(self.client, "last_meta", {}) or {})
            meta["fallback_reason"] = self.last_error
            self.meta = meta
            return propose(facts, resolution, ctx)


def build_client(settings: Any) -> LLMClient | None:
    if not settings.llm_enabled or not settings.llm_configured:
        return None
    try:
        return LLMClient(
            settings.llm_base_url,
            settings.llm_api_key,
            settings.llm_model,
            settings.llm_timeout_seconds,
        )
    except Exception:  # noqa: BLE001 - misconfiguration disables the LLM, not the app
        return None


def build_hybrid(settings: Any) -> tuple[HybridParser, HybridPlanner]:
    client = build_client(settings)
    return HybridParser(client), HybridPlanner(client)


def source_label(parser: HybridParser, planner: HybridPlanner) -> str:
    llm_configured = (
        getattr(parser, "client", None) is not None or getattr(planner, "client", None) is not None
    )
    if not llm_configured:
        return "deterministic"
    if parser.last_source == "llm" and planner.last_source == "llm":
        return "llm"
    return "llm_fallback"
