"""Loop budget policy for agentic workflows.

Provides profile-based loop step limits with configurable warning thresholds.
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class BudgetProfile(str, Enum):
    """Pre-defined budget profiles for different workflow types."""
    DEFAULT = "default"  # 50 steps
    BROWSER_HEAVY = "browser-heavy"  # 90 steps (Playwright automation)
    API_HEAVY = "api-heavy"  # 70 steps
    CUSTOM = "custom"  # Admin-configurable


@dataclass
class LoopBudgetPolicy:
    """Policy-driven loop budget configuration.

    Attributes:
        profile: The budget profile being used
        max_steps: Maximum number of loop iterations allowed
        warning_threshold: Percentage (0.0-1.0) at which to emit warning
    """
    profile: BudgetProfile
    max_steps: int
    warning_threshold: float = 0.8  # 80% = emit warning

    def get_warning_step(self) -> int:
        """Return step number when warning should fire (80% of max by default).

        Returns:
            The step number at which a warning should be emitted
        """
        return int(self.max_steps * self.warning_threshold)

    @staticmethod
    def resolve(profile: str, custom_limit: Optional[int] = None) -> "LoopBudgetPolicy":
        """Resolve policy based on profile name.

        Args:
            profile: Profile name (default, browser-heavy, api-heavy, custom)
            custom_limit: Custom step limit (required if profile is "custom")

        Returns:
            Resolved LoopBudgetPolicy instance

        Raises:
            ValueError: If custom profile specified without custom_limit
        """
        profiles = {
            BudgetProfile.DEFAULT: 50,
            BudgetProfile.BROWSER_HEAVY: 90,
            BudgetProfile.API_HEAVY: 70,
        }

        if profile == BudgetProfile.CUSTOM.value:
            if custom_limit is None:
                raise ValueError("custom_limit required when using CUSTOM profile")
            return LoopBudgetPolicy(BudgetProfile.CUSTOM, custom_limit)

        # Try to resolve profile, default to DEFAULT if invalid
        try:
            budget_profile = BudgetProfile(profile)
            max_steps = profiles.get(budget_profile, 50)
            return LoopBudgetPolicy(budget_profile, max_steps)
        except ValueError:
            # Invalid profile, use default
            return LoopBudgetPolicy(BudgetProfile.DEFAULT, 50)
