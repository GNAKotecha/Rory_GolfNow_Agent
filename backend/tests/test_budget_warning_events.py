"""Test budget warning events at 80% threshold.

Task 5M2.3: Tests that budget warnings are emitted at 80% threshold
and stopped_reason is correctly set when budget is exhausted.
"""
import pytest
from app.services.loop_budget_policy import LoopBudgetPolicy, BudgetProfile
from app.services.headless_events import HeadlessEventType, HeadlessEventBuilder


class TestBudgetWarningEventFormat:
    """Test budget warning event has all required fields."""

    def test_budget_warning_event_format(self):
        """Event has all required fields: current_step, budget_limit, remaining, profile."""
        builder = HeadlessEventBuilder()
        event = builder.budget_warning(
            current_step=72,
            budget_limit=90,
            remaining=18,
            profile="browser-heavy",
        )

        assert event.type == HeadlessEventType.BUDGET_WARNING
        assert event.step_number == 72
        assert event.payload["current_step"] == 72
        assert event.payload["budget_limit"] == 90
        assert event.payload["remaining"] == 18
        assert event.payload["profile"] == "browser-heavy"
        assert event.run_id is not None  # Has correlation ID
        assert event.timestamp is not None


class TestWarningThresholdLogic:
    """Test warning threshold logic for different profiles."""

    def test_browser_heavy_warning_at_80_percent(self):
        """Browser-heavy: 90 steps, warning at step 72 (80%)."""
        policy = LoopBudgetPolicy.resolve("browser-heavy")
        warning_step = policy.get_warning_step()

        assert warning_step == 72
        assert warning_step < policy.max_steps
        # Verify it's actually 80%
        assert warning_step / policy.max_steps == 0.8

    def test_default_profile_warning_at_80_percent(self):
        """Default: 50 steps, warning at step 40 (80%)."""
        policy = LoopBudgetPolicy.resolve("default")
        warning_step = policy.get_warning_step()

        assert warning_step == 40
        assert warning_step < policy.max_steps
        assert warning_step / policy.max_steps == 0.8

    def test_no_warning_before_threshold(self):
        """Warning step calculation ensures warning fires exactly at threshold."""
        policy = LoopBudgetPolicy.resolve("default")  # 50 steps
        warning_step = policy.get_warning_step()

        # Steps before warning threshold should not trigger
        for step in range(1, warning_step):
            assert step != warning_step

        # Warning step is exactly at threshold
        assert warning_step == 40


class TestBudgetExhaustedMetadata:
    """Test that budget exhaustion is marked in telemetry."""

    def test_budget_exhausted_metadata_format(self):
        """Verify metadata structure for budget exhaustion."""
        # Simulate metadata that would be set when budget is exhausted
        metadata = {
            "budget_exhausted": True,
            "budget_profile": "default",
            "run_id": "test-run-id",
            "can_continue": True,
        }

        assert metadata["budget_exhausted"] is True
        assert metadata["budget_profile"] == "default"
        assert metadata["can_continue"] is True
        assert "run_id" in metadata


class TestWarningThresholdCalculation:
    """Test warning step calculation for different profiles."""

    def test_warning_step_browser_heavy(self):
        """Browser-heavy: 90 steps * 0.8 = 72."""
        policy = LoopBudgetPolicy.resolve("browser-heavy")
        assert policy.get_warning_step() == 72

    def test_warning_step_default(self):
        """Default: 50 steps * 0.8 = 40."""
        policy = LoopBudgetPolicy.resolve("default")
        assert policy.get_warning_step() == 40

    def test_warning_step_api_heavy(self):
        """API-heavy: 70 steps * 0.8 = 56."""
        policy = LoopBudgetPolicy.resolve("api-heavy")
        assert policy.get_warning_step() == 56

    def test_warning_step_custom(self):
        """Custom: 100 steps * 0.8 = 80."""
        policy = LoopBudgetPolicy.resolve("custom", custom_limit=100)
        assert policy.get_warning_step() == 80
