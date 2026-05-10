"""
Audit Logger & Langfuse Integration

Provides structured audit logging for all tool invocations:
- JSON-formatted audit records with correlation IDs
- Langfuse span creation for observability
- Request/response capture (sanitized - no secrets)
- Duration and outcome tracking

All tool calls are logged regardless of success/failure.
Sensitive data (passwords, tokens, secrets) is redacted.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("gateway_mcp.audit")


class AuditOutcome(str, Enum):
    """Outcome of a tool invocation."""
    
    SUCCESS = "success"
    VALIDATION_ERROR = "validation_error"
    AUTH_ERROR = "auth_error"
    PERMISSION_DENIED = "permission_denied"
    ENV_RESTRICTED = "env_restricted"
    SCOPE_ERROR = "scope_error"
    APPROVAL_REQUIRED = "approval_required"
    EXECUTION_ERROR = "execution_error"
    TIMEOUT = "timeout"
    INTERNAL_ERROR = "internal_error"


@dataclass
class AuditRecord:
    """
    Structured audit record for a tool invocation.
    
    Captures the full lifecycle of a tool call from request
    through validation, execution, and response.
    """
    
    audit_id: str
    tool_name: str
    user_id: int
    environment: str
    
    # Request data (sanitized)
    input_data: dict = field(default_factory=dict)
    
    # Execution metadata
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    duration_ms: int = 0
    
    # Outcome
    outcome: AuditOutcome = AuditOutcome.SUCCESS
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    
    # Response data (sanitized)
    output_data: Optional[dict] = None
    
    # Tracing
    correlation_id: Optional[str] = None
    langfuse_trace_id: Optional[str] = None
    langfuse_span_id: Optional[str] = None
    
    def finish(
        self,
        outcome: AuditOutcome,
        output_data: Optional[dict] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Mark record as finished with outcome."""
        self.finished_at = datetime.now(timezone.utc)
        self.duration_ms = int(
            (self.finished_at - self.started_at).total_seconds() * 1000
        )
        self.outcome = outcome
        self.output_data = output_data
        self.error_code = error_code
        self.error_message = error_message
    
    def to_dict(self) -> dict:
        """Serialize for JSON logging."""
        return {
            "audit_id": self.audit_id,
            "tool_name": self.tool_name,
            "user_id": self.user_id,
            "environment": self.environment,
            "input_data": self.input_data,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": self.duration_ms,
            "outcome": self.outcome.value,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "output_data": self.output_data,
            "correlation_id": self.correlation_id,
            "langfuse_trace_id": self.langfuse_trace_id,
            "langfuse_span_id": self.langfuse_span_id,
        }


# Fields to redact from audit logs
SENSITIVE_FIELDS = {
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "credential",
    "private_key",
    "access_token",
    "refresh_token",
}


def sanitize_data(data: Any, depth: int = 0, max_depth: int = 10) -> Any:
    """
    Recursively sanitize sensitive data from audit records.
    
    Redacts values of fields whose names contain sensitive keywords.
    """
    if depth > max_depth:
        return "[TRUNCATED]"
    
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(s in key_lower for s in SENSITIVE_FIELDS):
                result[key] = "[REDACTED]"
            else:
                result[key] = sanitize_data(value, depth + 1, max_depth)
        return result
    
    if isinstance(data, list):
        return [sanitize_data(item, depth + 1, max_depth) for item in data]
    
    if isinstance(data, str) and len(data) > 1000:
        return data[:1000] + "...[TRUNCATED]"
    
    return data


class AuditLogger:
    """
    Structured audit logger with optional Langfuse integration.
    
    Creates audit records for tool invocations and logs them
    as structured JSON. Optionally creates Langfuse spans for
    distributed tracing.
    """
    
    def __init__(
        self,
        environment: str,
        langfuse_client=None,
        log_level: int = logging.INFO,
    ):
        """
        Initialize audit logger.
        
        Args:
            environment: Current deployment environment
            langfuse_client: Optional Langfuse client for tracing
            log_level: Logging level for audit records
        """
        self.environment = environment
        self._langfuse = langfuse_client
        self._log_level = log_level
        
        # Configure JSON formatter for audit logger
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(log_level)
    
    def start_audit(
        self,
        tool_name: str,
        user_id: int,
        input_data: dict,
        correlation_id: Optional[str] = None,
    ) -> AuditRecord:
        """
        Start an audit record for a tool invocation.
        
        Creates a unique audit_id and optionally a Langfuse span.
        
        Args:
            tool_name: Name of tool being invoked
            user_id: ID of calling user
            input_data: Tool input (will be sanitized)
            correlation_id: Optional correlation ID from caller
            
        Returns:
            AuditRecord to track the invocation
        """
        audit_id = str(uuid.uuid4())
        
        record = AuditRecord(
            audit_id=audit_id,
            tool_name=tool_name,
            user_id=user_id,
            environment=self.environment,
            input_data=sanitize_data(input_data),
            correlation_id=correlation_id or audit_id,
        )
        
        # Create Langfuse span if client available
        if self._langfuse:
            try:
                trace = self._langfuse.trace(
                    name=f"gateway.{tool_name}",
                    id=audit_id,
                    user_id=str(user_id),
                    metadata={
                        "environment": self.environment,
                        "correlation_id": record.correlation_id,
                    },
                )
                span = trace.span(
                    name=f"tool.{tool_name}",
                    input=record.input_data,
                )
                record.langfuse_trace_id = trace.id
                record.langfuse_span_id = span.id
            except Exception as e:
                logger.warning(f"Langfuse span creation failed: {e}")
        
        return record
    
    def finish_audit(
        self,
        record: AuditRecord,
        outcome: AuditOutcome,
        output_data: Optional[dict] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Finish an audit record and write to log.
        
        Updates Langfuse span if available.
        """
        record.finish(
            outcome=outcome,
            output_data=sanitize_data(output_data) if output_data else None,
            error_code=error_code,
            error_message=error_message,
        )
        
        # Update Langfuse span
        if self._langfuse and record.langfuse_span_id:
            try:
                # Langfuse span update
                self._langfuse.span(
                    id=record.langfuse_span_id,
                    trace_id=record.langfuse_trace_id,
                    output=record.output_data,
                    level="ERROR" if outcome != AuditOutcome.SUCCESS else "DEFAULT",
                    status_message=error_message if error_message else None,
                )
            except Exception as e:
                logger.warning(f"Langfuse span update failed: {e}")
        
        # Write structured log
        self._write_log(record)
    
    def _write_log(self, record: AuditRecord) -> None:
        """Write audit record as structured JSON log."""
        log_entry = {
            "type": "gateway_audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **record.to_dict(),
        }
        
        log_json = json.dumps(log_entry, default=str)
        
        if record.outcome == AuditOutcome.SUCCESS:
            logger.info(log_json)
        elif record.outcome in (
            AuditOutcome.AUTH_ERROR,
            AuditOutcome.PERMISSION_DENIED,
            AuditOutcome.ENV_RESTRICTED,
        ):
            logger.warning(log_json)
        else:
            logger.error(log_json)


def create_audit_logger_from_settings(settings) -> AuditLogger:
    """
    Factory to create AuditLogger from gateway settings.
    
    Optionally initializes Langfuse client if configured.
    """
    environment = getattr(settings, "env", "local")
    
    # Initialize Langfuse if configured
    langfuse_client = None
    langfuse_enabled = getattr(settings, "langfuse_enabled", False)
    
    if langfuse_enabled:
        try:
            from langfuse import Langfuse
            
            langfuse_client = Langfuse(
                public_key=getattr(settings, "langfuse_public_key", None),
                secret_key=getattr(settings, "langfuse_secret_key", None),
                host=getattr(settings, "langfuse_host", "https://cloud.langfuse.com"),
            )
        except ImportError:
            logger.warning("Langfuse not installed, tracing disabled")
        except Exception as e:
            logger.warning(f"Langfuse initialization failed: {e}")
    
    return AuditLogger(
        environment=environment,
        langfuse_client=langfuse_client,
    )
