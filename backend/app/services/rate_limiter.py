"""Rate limiting infrastructure with multiple strategies.

Provides:
- Per-user active run limit
- Per-tool call limit
- Model request limit
- Exponential backoff with jitter
- Max retry count
- Circuit breaker per MCP server
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
import asyncio
import random
import threading
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    # Per-user limits
    max_active_runs_per_user: int = 3
    max_tool_calls_per_minute: int = 60
    max_model_requests_per_minute: int = 30
    
    # Retry configuration
    max_retries: int = 3
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 30.0
    backoff_multiplier: float = 2.0
    jitter_range: float = 0.5  # ±50% jitter
    
    # Circuit breaker configuration
    circuit_failure_threshold: int = 5  # Failures before opening
    circuit_recovery_timeout_seconds: int = 60  # Time before half-open
    circuit_success_threshold: int = 3  # Successes to close from half-open


@dataclass
class CircuitBreaker:
    """Circuit breaker for an MCP server."""
    server_name: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_state_change: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def record_success(self, config: RateLimitConfig):
        """Record a successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= config.circuit_success_threshold:
                self._transition_to(CircuitState.CLOSED)
                logger.info(f"Circuit breaker CLOSED for {self.server_name} after recovery")
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0
    
    def record_failure(self, config: RateLimitConfig):
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)
        
        if self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open reopens circuit
            self._transition_to(CircuitState.OPEN)
            logger.warning(f"Circuit breaker OPEN for {self.server_name} (failed in half-open)")
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= config.circuit_failure_threshold:
                self._transition_to(CircuitState.OPEN)
                logger.warning(
                    f"Circuit breaker OPEN for {self.server_name} "
                    f"(threshold {config.circuit_failure_threshold} reached)"
                )
    
    def is_available(self, config: RateLimitConfig) -> bool:
        """Check if requests can proceed (pure check, no state mutation)."""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout elapsed
            elapsed = datetime.now(timezone.utc) - self.last_state_change
            return elapsed.total_seconds() >= config.circuit_recovery_timeout_seconds
        
        # Half-open: allow limited requests
        return True
    
    def maybe_transition_to_half_open(self, config: RateLimitConfig) -> bool:
        """
        Transition from OPEN to HALF_OPEN if timeout elapsed.
        
        Returns True if transitioned or already in testable state.
        Must be called under lock.
        """
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            elapsed = datetime.now(timezone.utc) - self.last_state_change
            if elapsed.total_seconds() >= config.circuit_recovery_timeout_seconds:
                self._transition_to(CircuitState.HALF_OPEN)
                logger.info(f"Circuit breaker HALF_OPEN for {self.server_name} (testing recovery)")
                return True
            return False
        
        # Already half-open
        return True
    
    def _transition_to(self, new_state: CircuitState):
        """Transition to a new state."""
        self.state = new_state
        self.last_state_change = datetime.now(timezone.utc)
        if new_state == CircuitState.CLOSED:
            self.failure_count = 0
            self.success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self.success_count = 0


@dataclass
class UserRateLimitState:
    """Track rate limit state for a single user."""
    user_id: int
    active_runs: int = 0
    tool_calls: List[datetime] = field(default_factory=list)
    model_requests: List[datetime] = field(default_factory=list)
    tool_calls: list = field(default_factory=list)  # List of timestamps
    model_requests: list = field(default_factory=list)  # List of timestamps


class RateLimiter:
    """
    Rate limiting infrastructure.
    
    Manages:
    - Per-user active run tracking
    - Per-tool call rate limiting
    - Model request rate limiting
    - Exponential backoff with jitter
    - Circuit breakers per MCP server
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._user_states: Dict[int, UserRateLimitState] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()  # Async lock for async operations
        self._sync_lock = threading.Lock()  # Sync lock for thread-safe reads
    
    # =========================================================================
    # User Rate Limiting
    # =========================================================================
    
    def _get_user_state(self, user_id: int) -> UserRateLimitState:
        """Get or create user rate limit state."""
        if user_id not in self._user_states:
            self._user_states[user_id] = UserRateLimitState(user_id=user_id)
        return self._user_states[user_id]
    
    def _prune_old_timestamps(self, timestamps: list, window_seconds: int = 60) -> list:
        """Remove timestamps older than window."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        return [ts for ts in timestamps if ts > cutoff]
    
    async def check_active_run_limit(self, user_id: int) -> tuple[bool, str]:
        """
        Check if user can start a new run.
        
        Returns:
            (allowed, message)
        """
        async with self._lock:
            state = self._get_user_state(user_id)
            
            if state.active_runs >= self.config.max_active_runs_per_user:
                return False, (
                    f"Rate limit: max {self.config.max_active_runs_per_user} "
                    f"concurrent runs per user (current: {state.active_runs})"
                )
            
            return True, ""
    
    async def acquire_run(self, user_id: int) -> bool:
        """
        Acquire a run slot for user.
        
        Returns:
            True if acquired, False if limit reached
        """
        async with self._lock:
            state = self._get_user_state(user_id)
            
            if state.active_runs >= self.config.max_active_runs_per_user:
                return False
            
            state.active_runs += 1
            logger.debug(f"User {user_id} acquired run slot ({state.active_runs} active)")
            return True
    
    async def release_run(self, user_id: int):
        """Release a run slot for user."""
        async with self._lock:
            state = self._get_user_state(user_id)
            state.active_runs = max(0, state.active_runs - 1)
            logger.debug(f"User {user_id} released run slot ({state.active_runs} active)")
    
    async def check_tool_call_limit(self, user_id: int) -> tuple[bool, str]:
        """
        Check if user can make a tool call.
        
        Returns:
            (allowed, message)
        """
        async with self._lock:
            state = self._get_user_state(user_id)
            state.tool_calls = self._prune_old_timestamps(state.tool_calls)
            
            if len(state.tool_calls) >= self.config.max_tool_calls_per_minute:
                return False, (
                    f"Rate limit: max {self.config.max_tool_calls_per_minute} "
                    f"tool calls per minute"
                )
            
            return True, ""
    
    async def record_tool_call(self, user_id: int):
        """Record a tool call for rate limiting."""
        async with self._lock:
            state = self._get_user_state(user_id)
            state.tool_calls.append(datetime.now(timezone.utc))
    
    async def check_model_request_limit(self, user_id: int) -> tuple[bool, str]:
        """
        Check if user can make a model request.
        
        Returns:
            (allowed, message)
        """
        async with self._lock:
            state = self._get_user_state(user_id)
            state.model_requests = self._prune_old_timestamps(state.model_requests)
            
            if len(state.model_requests) >= self.config.max_model_requests_per_minute:
                return False, (
                    f"Rate limit: max {self.config.max_model_requests_per_minute} "
                    f"model requests per minute"
                )
            
            return True, ""
    
    async def record_model_request(self, user_id: int):
        """Record a model request for rate limiting."""
        async with self._lock:
            state = self._get_user_state(user_id)
            state.model_requests.append(datetime.now(timezone.utc))
    
    # =========================================================================
    # Exponential Backoff with Jitter
    # =========================================================================
    
    def calculate_backoff(self, retry_count: int) -> float:
        """
        Calculate backoff delay with exponential increase and jitter.
        
        Args:
            retry_count: Current retry number (0-indexed)
        
        Returns:
            Delay in seconds
        """
        # Exponential backoff
        base_delay = self.config.initial_backoff_seconds * (
            self.config.backoff_multiplier ** retry_count
        )
        
        # Cap at max
        base_delay = min(base_delay, self.config.max_backoff_seconds)
        
        # Add jitter (±jitter_range)
        jitter = base_delay * self.config.jitter_range * (2 * random.random() - 1)
        delay = max(0, base_delay + jitter)
        
        return delay
    
    async def wait_with_backoff(self, retry_count: int) -> float:
        """
        Wait with exponential backoff and jitter.
        
        Args:
            retry_count: Current retry number
            
        Returns:
            Actual delay used
        """
        delay = self.calculate_backoff(retry_count)
        await asyncio.sleep(delay)
        return delay
    
    def should_retry(self, retry_count: int) -> bool:
        """Check if another retry is allowed."""
        return retry_count < self.config.max_retries
    
    # =========================================================================
    # Circuit Breaker
    # =========================================================================
    
    def _get_circuit_breaker(self, server_name: str) -> CircuitBreaker:
        """
        Get or create circuit breaker for server.
        
        Note: Caller must hold _sync_lock when calling this method.
        """
        if server_name not in self._circuit_breakers:
            self._circuit_breakers[server_name] = CircuitBreaker(server_name=server_name)
        return self._circuit_breakers[server_name]
    
    async def check_circuit(self, server_name: str) -> tuple[bool, str]:
        """
        Check if server circuit is available.
        
        State transitions happen under both async and sync locks
        to prevent race conditions with sync readers.
        
        Returns:
            (available, message)
        """
        async with self._lock:
            with self._sync_lock:
                cb = self._get_circuit_breaker(server_name)
                
                # Attempt state transition under lock
                if not cb.maybe_transition_to_half_open(self.config):
                    return False, (
                        f"Circuit breaker OPEN for {server_name}: "
                        f"service temporarily unavailable"
                    )
                
                return True, ""
    
    async def record_circuit_success(self, server_name: str):
        """Record successful call to server (thread-safe)."""
        async with self._lock:
            with self._sync_lock:
                cb = self._get_circuit_breaker(server_name)
                cb.record_success(self.config)
    
    async def record_circuit_failure(self, server_name: str):
        """Record failed call to server (thread-safe)."""
        async with self._lock:
            with self._sync_lock:
                cb = self._get_circuit_breaker(server_name)
                cb.record_failure(self.config)
    
    def get_circuit_status(self, server_name: str) -> Dict[str, Any]:
        """
        Get circuit breaker status for a server (thread-safe).
        
        Uses sync lock to ensure consistent reads across threads.
        """
        with self._sync_lock:
            if server_name not in self._circuit_breakers:
                return {"state": "closed", "failure_count": 0}
            
            cb = self._circuit_breakers[server_name]
            # Copy all values under lock to ensure consistency
            return {
                "state": cb.state.value,
                "failure_count": cb.failure_count,
                "success_count": cb.success_count,
                "last_failure": cb.last_failure_time.isoformat() if cb.last_failure_time else None,
                "last_state_change": cb.last_state_change.isoformat(),
            }
    
    def get_all_circuit_statuses(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all circuit breakers (thread-safe).
        
        Uses sync lock to ensure consistent reads across threads.
        """
        with self._sync_lock:
            # Copy server names under lock, then get each status
            server_names = list(self._circuit_breakers.keys())
        
        return {
            server: self.get_circuit_status(server)
            for server in server_names
        }


# Global rate limiter instance (thread-safe singleton pattern)
_rate_limiter: Optional[RateLimiter] = None
_rate_limiter_lock = threading.Lock()


def get_rate_limiter(config: Optional[RateLimitConfig] = None) -> RateLimiter:
    """Get or create the global rate limiter (thread-safe)."""
    global _rate_limiter
    
    # Fast path: already initialized
    if _rate_limiter is not None:
        return _rate_limiter
    
    # Slow path: double-checked locking
    with _rate_limiter_lock:
        if _rate_limiter is None:
            _rate_limiter = RateLimiter(config)
    return _rate_limiter


def reset_rate_limiter():
    """Reset the global rate limiter (for testing)."""
    global _rate_limiter
    with _rate_limiter_lock:
        _rate_limiter = None
