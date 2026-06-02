"""Tests for loop budget policy.

Verifies profile-based loop limits and warning threshold calculations.
"""
import pytest

from app.services.loop_budget_policy import LoopBudgetPolicy, BudgetProfile


class TestLoopBudgetPolicy:
    """Test loop budget policy configuration."""

    def test_default_profile(self):
        """Test default profile returns 50 steps."""
        policy = LoopBudgetPolicy.resolve(BudgetProfile.DEFAULT.value)
        assert policy.profile == BudgetProfile.DEFAULT
        assert policy.max_steps == 50
        assert policy.warning_threshold == 0.8

    def test_browser_heavy_profile(self):
        """Test browser-heavy profile returns 90 steps."""
        policy = LoopBudgetPolicy.resolve(BudgetProfile.BROWSER_HEAVY.value)
        assert policy.profile == BudgetProfile.BROWSER_HEAVY
        assert policy.max_steps == 90

    def test_api_heavy_profile(self):
        """Test API-heavy profile returns 70 steps."""
        policy = LoopBudgetPolicy.resolve(BudgetProfile.API_HEAVY.value)
        assert policy.profile == BudgetProfile.API_HEAVY
        assert policy.max_steps == 70

    def test_custom_profile_with_limit(self):
        """Test custom profile accepts custom limit."""
        policy = LoopBudgetPolicy.resolve(BudgetProfile.CUSTOM.value, custom_limit=100)
        assert policy.profile == BudgetProfile.CUSTOM
        assert policy.max_steps == 100

    def test_custom_profile_without_limit_raises(self):
        """Test custom profile without limit raises ValueError."""
        with pytest.raises(ValueError, match="custom_limit required"):
            LoopBudgetPolicy.resolve(BudgetProfile.CUSTOM.value)

    def test_warning_step_calculation(self):
        """Test warning step is calculated at 80% of max."""
        policy = LoopBudgetPolicy.resolve(BudgetProfile.BROWSER_HEAVY.value)
        # 90 * 0.8 = 72
        assert policy.get_warning_step() == 72

    def test_warning_step_default_profile(self):
        """Test warning step for default profile."""
        policy = LoopBudgetPolicy.resolve(BudgetProfile.DEFAULT.value)
        # 50 * 0.8 = 40
        assert policy.get_warning_step() == 40

    def test_warning_step_custom_threshold(self):
        """Test warning step with custom threshold."""
        policy = LoopBudgetPolicy(
            profile=BudgetProfile.DEFAULT,
            max_steps=100,
            warning_threshold=0.9
        )
        # 100 * 0.9 = 90
        assert policy.get_warning_step() == 90

    def test_invalid_profile_defaults_to_50(self):
        """Test unknown profile defaults to 50 steps."""
        policy = LoopBudgetPolicy.resolve("unknown_profile")
        assert policy.max_steps == 50