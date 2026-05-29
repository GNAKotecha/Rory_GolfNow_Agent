"""Tests for dynamic model selection and policy filtering."""

import pytest

from app.services.model_selector import (
    AUTO_MODEL_ID,
    get_available_models,
    resolve_model_selection,
)


class _FakeClient:
    def __init__(self, models):
        self._models = models

    async def list_models(self):
        return self._models


@pytest.mark.asyncio
async def test_manual_model_selection_uses_requested_model():
    client = _FakeClient(["claude-haiku-4-5", "claude-sonnet-4-6"])
    result = await resolve_model_selection(
        requested_model="claude-sonnet-4-6",
        messages=[{"role": "user", "content": "hello"}],
        client=client,
    )
    assert result.strategy == "manual"
    assert result.resolved_model == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_blocked_opus_47_is_never_selected():
    client = _FakeClient(
        ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7", "claude-opus-4-6"]
    )
    result = await resolve_model_selection(
        requested_model="claude-opus-4-7",
        messages=[{"role": "user", "content": "perform deep architecture analysis"}],
        client=client,
    )
    assert result.strategy == "auto"
    assert result.resolved_model != "claude-opus-4-7"
    assert "4-7" not in (result.resolved_model or "")


@pytest.mark.asyncio
async def test_auto_low_complexity_prefers_haiku():
    client = _FakeClient(["claude-sonnet-4-6", "claude-haiku-4-5", "claude-opus-4-6"])
    result = await resolve_model_selection(
        requested_model=AUTO_MODEL_ID,
        messages=[{"role": "user", "content": "quick summary of this text"}],
        client=client,
    )
    assert result.strategy == "auto"
    assert result.complexity_tier == "low"
    assert "haiku" in (result.resolved_model or "").lower()


@pytest.mark.asyncio
async def test_auto_high_complexity_prefers_opus46_or45():
    client = _FakeClient(["claude-haiku-4-5", "claude-opus-4-5", "claude-sonnet-4-6"])
    result = await resolve_model_selection(
        requested_model=None,
        messages=[{"role": "user", "content": "multi-step architecture migration with security review and deep analysis"}],
        client=client,
    )
    assert result.strategy == "auto"
    assert result.complexity_tier == "high"
    assert result.resolved_model == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_auto_coding_prefers_sonnet():
    client = _FakeClient(["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-6"])
    result = await resolve_model_selection(
        requested_model=AUTO_MODEL_ID,
        messages=[{"role": "user", "content": "debug this python function and refactor it"}],
        client=client,
    )
    assert result.strategy == "auto"
    assert result.coding_request is True
    assert result.resolved_model == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_manual_opus_requires_permission_and_justification():
    client = _FakeClient(["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-6"])
    result = await resolve_model_selection(
        requested_model="claude-opus-4-6",
        messages=[{"role": "user", "content": "run a deep analysis"}],
        client=client,
        allow_opus=False,
        opus_justification="",
    )
    assert result.strategy == "auto"
    assert result.resolved_model == "claude-haiku-4-5"
    assert "requires explicit permission" in result.reason.lower()


@pytest.mark.asyncio
async def test_auto_high_complexity_uses_opus_when_approved():
    client = _FakeClient(["claude-haiku-4-5", "claude-opus-4-6", "claude-sonnet-4-6"])
    result = await resolve_model_selection(
        requested_model=AUTO_MODEL_ID,
        messages=[{"role": "user", "content": "multi-step architecture migration with security review and deep analysis"}],
        client=client,
        allow_opus=True,
        opus_justification="Critical production incident requiring deeper reasoning",
    )
    assert result.strategy == "auto"
    assert result.complexity_tier == "high"
    assert result.resolved_model == "claude-opus-4-6"


@pytest.mark.asyncio
async def test_get_available_models_filters_blocked():
    client = _FakeClient(["claude-opus-4-7", "claude-sonnet-4-6"])
    models = await get_available_models(client)
    assert "claude-opus-4-7" not in models
    assert "claude-sonnet-4-6" in models
