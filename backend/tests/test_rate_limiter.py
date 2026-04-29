"""Tests for rate limiter."""
import pytest
import asyncio
from datetime import datetime, timezone

from app.services.rate_limiter import (
    RateLimiter,
    RateLimitConfig,
    CircuitBreaker,
    CircuitState,
    get_rate_limiter,
    reset_rate_limiter,
)


class TestRateLimiter:
    """Test rate limiting functionality."""

    @pytest.fixture(autouse=True)
    def reset(self):
        """Reset global rate limiter before each test."""
        reset_rate_limiter()
        yield
        reset_rate_limiter()

    @pytest.fixture
    def rate_limiter(self):
        """Create a rate limiter with test config."""
        config = RateLimitConfig(
            max_active_runs_per_user=2,
            max_tool_calls_per_minute=5,
            max_model_requests_per_minute=3,
            max_retries=3,
            initial_backoff_seconds=0.1,
            max_backoff_seconds=1.0,
            circuit_failure_threshold=3,
            circuit_recovery_timeout_seconds=1,
        )
        return RateLimiter(config)

    @pytest.mark.asyncio
    async def test_active_run_limit(self, rate_limiter):
        """Test per-user active run limiting."""
        user_id = 1

        # First two runs should succeed
        assert await rate_limiter.acquire_run(user_id) is True
        assert await rate_limiter.acquire_run(user_id) is True

        # Third should fail
        assert await rate_limiter.acquire_run(user_id) is False

        # Check returns proper message
        allowed, msg = await rate_limiter.check_active_run_limit(user_id)
        assert allowed is False
        assert "max 2" in msg

        # Release one and try again
        await rate_limiter.release_run(user_id)
        assert await rate_limiter.acquire_run(user_id) is True

    @pytest.mark.asyncio
    async def test_tool_call_rate_limit(self, rate_limiter):
        """Test tool call rate limiting."""
        user_id = 1

        # First 5 calls should succeed
        for _ in range(5):
            allowed, _ = await rate_limiter.check_tool_call_limit(user_id)
            assert allowed is True
            await rate_limiter.record_tool_call(user_id)

        # 6th should fail
        allowed, msg = await rate_limiter.check_tool_call_limit(user_id)
        assert allowed is False
        assert "5 tool calls" in msg

    @pytest.mark.asyncio
    async def test_model_request_rate_limit(self, rate_limiter):
        """Test model request rate limiting."""
        user_id = 1

        # First 3 requests should succeed
        for _ in range(3):
            allowed, _ = await rate_limiter.check_model_request_limit(user_id)
            assert allowed is True
            await rate_limiter.record_model_request(user_id)

        # 4th should fail
        allowed, msg = await rate_limiter.check_model_request_limit(user_id)
        assert allowed is False
        assert "3 model requests" in msg

    def test_exponential_backoff(self, rate_limiter):
        """Test exponential backoff calculation."""
        # First retry: 0.1s (±jitter)
        delay0 = rate_limiter.calculate_backoff(0)
        assert 0.05 <= delay0 <= 0.15

        # Second retry: 0.2s (±jitter)
        delay1 = rate_limiter.calculate_backoff(1)
        assert 0.1 <= delay1 <= 0.3

        # Third retry: 0.4s (±jitter)
        delay2 = rate_limiter.calculate_backoff(2)
        assert 0.2 <= delay2 <= 0.6

    def test_should_retry(self, rate_limiter):
        """Test retry count checking."""
        assert rate_limiter.should_retry(0) is True
        assert rate_limiter.should_retry(1) is True
        assert rate_limiter.should_retry(2) is True
        assert rate_limiter.should_retry(3) is False


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    @pytest.fixture
    def config(self):
        return RateLimitConfig(
            circuit_failure_threshold=3,
            circuit_recovery_timeout_seconds=1,
            circuit_success_threshold=2,
        )

    def test_circuit_starts_closed(self, config):
        """Circuit should start closed."""
        cb = CircuitBreaker(server_name="test")
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available(config) is True

    def test_circuit_opens_after_failures(self, config):
        """Circuit should open after threshold failures."""
        cb = CircuitBreaker(server_name="test")

        # Record failures up to threshold
        cb.record_failure(config)
        assert cb.state == CircuitState.CLOSED

        cb.record_failure(config)
        assert cb.state == CircuitState.CLOSED

        cb.record_failure(config)
        assert cb.state == CircuitState.OPEN
        assert cb.is_available(config) is False

    def test_circuit_resets_on_success(self, config):
        """Failure count resets on success."""
        cb = CircuitBreaker(server_name="test")

        cb.record_failure(config)
        cb.record_failure(config)
        assert cb.failure_count == 2

        cb.record_success(config)
        assert cb.failure_count == 0

    def test_circuit_half_open_transition(self, config):
        """Circuit should transition to half-open after timeout."""
        cb = CircuitBreaker(server_name="test")

        # Open the circuit
        for _ in range(3):
            cb.record_failure(config)

        assert cb.state == CircuitState.OPEN

        # Simulate timeout elapsed
        from datetime import timedelta
        cb.last_state_change = datetime.now(timezone.utc) - timedelta(seconds=2)

        # is_available is pure check - should return True after timeout
        assert cb.is_available(config) is True
        # State hasn't changed yet (is_available is pure)
        assert cb.state == CircuitState.OPEN
        
        # maybe_transition_to_half_open actually mutates state
        assert cb.maybe_transition_to_half_open(config) is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_circuit_closes_after_successes(self, config):
        """Circuit should close after success threshold in half-open."""
        cb = CircuitBreaker(server_name="test")
        cb.state = CircuitState.HALF_OPEN
        cb.success_count = 0

        cb.record_success(config)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success(config)
        assert cb.state == CircuitState.CLOSED


class TestRateLimiterCircuitIntegration:
    """Test rate limiter with circuit breaker integration."""

    @pytest.fixture
    def rate_limiter(self):
        config = RateLimitConfig(
            circuit_failure_threshold=2,
            circuit_recovery_timeout_seconds=1,
        )
        return RateLimiter(config)

    @pytest.mark.asyncio
    async def test_circuit_opens_via_rate_limiter(self, rate_limiter):
        """Test circuit breaker via rate limiter interface."""
        server = "mcp-server-1"

        # Initially available
        available, _ = await rate_limiter.check_circuit(server)
        assert available is True

        # Record failures
        await rate_limiter.record_circuit_failure(server)
        await rate_limiter.record_circuit_failure(server)

        # Should now be unavailable
        available, msg = await rate_limiter.check_circuit(server)
        assert available is False
        assert "OPEN" in msg

    @pytest.mark.asyncio
    async def test_get_circuit_statuses(self, rate_limiter):
        """Test getting all circuit statuses."""
        await rate_limiter.record_circuit_success("server-1")
        await rate_limiter.record_circuit_failure("server-2")

        statuses = rate_limiter.get_all_circuit_statuses()
        assert "server-1" in statuses
        assert "server-2" in statuses
        assert statuses["server-1"]["state"] == "closed"


class TestGlobalRateLimiter:
    """Test global singleton rate limiter."""

    def test_singleton_pattern(self):
        """Test singleton creation and reset."""
        reset_rate_limiter()

        rl1 = get_rate_limiter()
        rl2 = get_rate_limiter()
        assert rl1 is rl2

        reset_rate_limiter()
        rl3 = get_rate_limiter()
        assert rl3 is not rl1
