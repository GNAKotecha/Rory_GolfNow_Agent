"""Model selection utilities for manual and dynamic routing."""
from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.ollama import OllamaClient

logger = logging.getLogger(__name__)

AUTO_MODEL_ID = "auto"
AUTO_MODEL_LABEL = "Auto (dynamic)"
_AUTO_ALIASES = {"", AUTO_MODEL_ID, "default", "dynamic"}
_OPUS_47_PATTERNS = [
    r"opus[-_\s]?4[-_\s]?7",
    r"claude[-_\s]?opus[-_\s]?4[-_\s]?7",
]


@dataclass
class ModelSelection:
    """Selection output for routing and observability."""

    requested_model: Optional[str]
    resolved_model: Optional[str]
    strategy: str  # "manual" | "auto"
    complexity_tier: str  # "low" | "medium" | "high" | "fallback"
    reason: str
    available_models: List[str]
    coding_request: bool = False


def _is_blocked_model(model_name: str) -> bool:
    lower = model_name.lower()
    return any(re.search(pattern, lower) for pattern in _OPUS_47_PATTERNS)


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _fallback_catalog() -> List[str]:
    """Fallback models used if model discovery is unavailable."""
    if settings.use_api_key:
        return _dedupe_preserve_order(
            [
                os.getenv("ANTHROPIC_HAIKU_MODEL", "claude-haiku-4-5"),
                os.getenv("ANTHROPIC_SONNET_MODEL", "claude-sonnet-4-6"),
                os.getenv("ANTHROPIC_OPUS_46_MODEL", "claude-opus-4-6"),
                os.getenv("ANTHROPIC_OPUS_45_MODEL", "claude-opus-4-5"),
            ]
        )
    return _dedupe_preserve_order(
        [os.getenv("OLLAMA_MODEL", "qwen2.5-coder:32b")]
    )


def _filter_supported_models(models: List[str]) -> List[str]:
    filtered = [m for m in models if isinstance(m, str) and m.strip()]
    filtered = [m.strip() for m in filtered if not _is_blocked_model(m.strip())]
    return _dedupe_preserve_order(filtered)


def _contains_any(text: str, terms: List[str]) -> bool:
    return any(term in text for term in terms)


def _is_coding_request(messages: List[Dict[str, Any]]) -> bool:
    """Heuristic detection for coding-oriented tasks."""
    text = _get_latest_user_text(messages).lower()
    coding_terms = [
        "code",
        "debug",
        "bug",
        "refactor",
        "function",
        "class",
        "typescript",
        "javascript",
        "python",
        "java",
        "go",
        "rust",
        "api",
        "endpoint",
        "test",
        "unit test",
        "integration test",
        "compile",
        "stack trace",
        "exception",
        "traceback",
        "sql",
        "docker",
        "mcp",
    ]
    if "```" in text:
        return True
    return _contains_any(text, coding_terms)


def _get_latest_user_text(messages: List[Dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            return str(content) if content is not None else ""
    return ""


def _score_complexity(messages: List[Dict[str, Any]]) -> int:
    """Cheap complexity heuristic for auto model routing."""
    text = _get_latest_user_text(messages).lower()
    score = 0

    length = len(text)
    if length > 700:
        score += 1
    if length > 1800:
        score += 2

    if "```" in text:
        score += 1

    if len(messages) > 10:
        score += 1

    high_terms = [
        "architecture",
        "root cause",
        "multi-step",
        "migration",
        "performance",
        "scalability",
        "security review",
        "design spec",
        "incident",
        "long-running",
        "deep analysis",
        "research",
        "refactor",
    ]
    medium_terms = [
        "debug",
        "implement",
        "code review",
        "workflow",
        "integration",
        "tool call",
        "test plan",
    ]
    low_terms = [
        "quick",
        "brief",
        "summarize",
        "rewrite",
        "format",
        "extract",
        "classify",
        "one line",
    ]

    if _contains_any(text, high_terms):
        score += 3
    elif _contains_any(text, medium_terms):
        score += 1

    if _contains_any(text, low_terms):
        score -= 1

    return score


def _complexity_tier(messages: List[Dict[str, Any]]) -> str:
    score = _score_complexity(messages)
    if score <= 0:
        return "low"
    if score >= 3:
        return "high"
    return "medium"


def _first_match(models: List[str], patterns: List[str]) -> Optional[str]:
    for model in models:
        lower = model.lower()
        if any(re.search(p, lower) for p in patterns):
            return model
    return None


def _choose_haiku(models: List[str]) -> Optional[str]:
    return _first_match(models, [r"haiku[-_\s]?4[-_\s]?5", r"haiku"])


def _choose_sonnet(models: List[str]) -> Optional[str]:
    return _first_match(models, [r"sonnet[-_\s]?4[-_\s]?6", r"sonnet[-_\s]?4[-_\s]?5", r"sonnet"])


def _choose_opus(models: List[str]) -> Optional[str]:
    return (
        _first_match(models, [r"opus[-_\s]?4[-_\s]?6"])
        or _first_match(models, [r"opus[-_\s]?4[-_\s]?5"])
        or _first_match(models, [r"opus"])
    )


def _is_opus_model(model_name: str) -> bool:
    return bool(re.search(r"opus", model_name.lower()))


def is_manual_model_request(requested_model: Optional[str]) -> bool:
    """True when caller explicitly requested a concrete model (not auto aliases)."""
    requested = (requested_model or "").strip().lower()
    return requested not in _AUTO_ALIASES


def _has_opus_permission(allow_opus: bool, opus_justification: Optional[str]) -> bool:
    if not allow_opus:
        return False
    justification = (opus_justification or "").strip()
    return len(justification) >= 12


def _choose_for_tier(tier: str, models: List[str]) -> Optional[str]:
    """Prefer 4.6/4.5 families and avoid Opus 4.7 by pre-filtering."""
    if not models:
        return None

    if tier == "low":
        return (
            _first_match(models, [r"haiku[-_\s]?4[-_\s]?5", r"haiku"])
            or _first_match(models, [r"sonnet"])
            or models[0]
        )

    if tier == "high":
        return (
            _first_match(models, [r"opus[-_\s]?4[-_\s]?6"])
            or _first_match(models, [r"opus[-_\s]?4[-_\s]?5"])
            or _first_match(models, [r"sonnet[-_\s]?4[-_\s]?6", r"sonnet[-_\s]?4[-_\s]?5", r"sonnet"])
            or models[0]
        )

    # medium (default)
    return (
        _first_match(models, [r"sonnet[-_\s]?4[-_\s]?6", r"sonnet[-_\s]?4[-_\s]?5", r"sonnet"])
        or _first_match(models, [r"haiku"])
        or _first_match(models, [r"opus[-_\s]?4[-_\s]?6", r"opus[-_\s]?4[-_\s]?5", r"opus"])
        or models[0]
    )


async def get_available_models(client: OllamaClient) -> List[str]:
    """Discover models from backend, with fallback defaults."""
    try:
        discovered = await client.list_models()
        models = _filter_supported_models(discovered)
        if models:
            return models
    except Exception as exc:
        logger.warning(
            "Model discovery failed; falling back to defaults",
            extra={"error": str(exc)},
        )

    return _filter_supported_models(_fallback_catalog())


async def resolve_model_selection(
    requested_model: Optional[str],
    messages: List[Dict[str, Any]],
    client: OllamaClient,
    allow_opus: bool = False,
    opus_justification: Optional[str] = None,
) -> ModelSelection:
    """
    Resolve model selection for a request.

    - Manual mode: use requested model if not blocked.
    - Auto mode (`auto`/`default`/empty): route by complexity to haiku/sonnet/opus.
    """
    available = await get_available_models(client)
    requested = (requested_model or "").strip()
    coding_request = _is_coding_request(messages)
    complexity_tier = _complexity_tier(messages)
    opus_allowed = _has_opus_permission(allow_opus, opus_justification)

    def _default_non_opus_model() -> Optional[str]:
        if coding_request:
            return _choose_sonnet(available) or _choose_haiku(available) or (available[0] if available else None)
        return _choose_haiku(available) or _choose_sonnet(available) or (available[0] if available else None)

    if requested and requested.lower() not in _AUTO_ALIASES:
        if _is_blocked_model(requested):
            fallback = _default_non_opus_model()
            return ModelSelection(
                requested_model=requested_model,
                resolved_model=fallback,
                strategy="auto",
                complexity_tier=complexity_tier,
                reason=f"Requested model '{requested}' is blocked by policy (Opus 4.7 disabled).",
                available_models=available,
                coding_request=coding_request,
            )

        if _is_opus_model(requested) and not opus_allowed:
            fallback = _default_non_opus_model()
            return ModelSelection(
                requested_model=requested_model,
                resolved_model=fallback,
                strategy="auto",
                complexity_tier=complexity_tier,
                reason="Opus requires explicit permission and non-empty justification.",
                available_models=available,
                coding_request=coding_request,
            )

        return ModelSelection(
            requested_model=requested_model,
            resolved_model=requested,
            strategy="manual",
            complexity_tier="fallback",
            reason="Using explicitly requested model.",
            available_models=available,
            coding_request=coding_request,
        )

    # Auto strategy:
    # - Most tasks default to Haiku
    # - Coding tasks default to Sonnet
    # - Opus only when complexity is high AND permission/justification provided
    chosen = _default_non_opus_model()
    reason = "Auto-selected default model."
    if complexity_tier == "high" and opus_allowed:
        chosen = _choose_opus(available) or chosen
        reason = "Auto-selected Opus for high-complexity task with explicit permission."
    elif coding_request:
        reason = "Auto-selected Sonnet for coding-focused task."
    else:
        reason = "Auto-selected Haiku for general task."

    return ModelSelection(
        requested_model=requested_model or AUTO_MODEL_ID,
        resolved_model=chosen,
        strategy="auto",
        complexity_tier=complexity_tier,
        reason=reason,
        available_models=available,
        coding_request=coding_request,
    )
