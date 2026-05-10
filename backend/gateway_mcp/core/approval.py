"""
Approval Gate Bridge

Bridges Gateway MCP tool invocations to Phase 3's ApprovalService.

When a tool requires approval (via requires_approval flag or HIGH_WRITE risk),
this module creates an approval request and raises ApprovalRequiredError.

The caller (agent) must then poll for approval status or wait for callback.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from gateway_mcp.core.errors import ApprovalRequiredError
from gateway_mcp.tools.base import Tool


@dataclass
class ApprovalRequest:
    """
    Approval request created for a tool invocation.
    
    Used to track pending approvals without requiring
    a database connection in the middleware.
    """
    
    request_id: str
    tool_name: str
    user_id: int
    input_data: dict
    approval_prompt: str
    created_at: datetime
    workflow_run_id: Optional[int] = None  # Set if linked to workflow
    
    def to_dict(self) -> dict:
        """Serialize for storage or API response."""
        return {
            "request_id": self.request_id,
            "tool_name": self.tool_name,
            "user_id": self.user_id,
            "input_data": self.input_data,
            "approval_prompt": self.approval_prompt,
            "created_at": self.created_at.isoformat(),
            "workflow_run_id": self.workflow_run_id,
        }


class ApprovalBridge:
    """
    Bridge between Gateway middleware and Phase 3 ApprovalService.
    
    Handles creating approval requests and checking approval status
    without directly coupling to the workflow database.
    """
    
    def __init__(
        self,
        approval_service=None,  # Optional Phase 3 ApprovalService
        db_session=None,  # Optional SQLAlchemy session
    ):
        """
        Initialize approval bridge.
        
        Args:
            approval_service: Phase 3 ApprovalService instance (optional)
            db_session: Database session for ApprovalService (optional)
        """
        self._approval_service = approval_service
        self._db_session = db_session
        
        # In-memory pending approvals (fallback when no DB)
        self._pending: dict[str, ApprovalRequest] = {}
    
    def request_approval(
        self,
        tool: Tool,
        user_id: int,
        input_data: dict,
        audit_id: Optional[str] = None,
        workflow_run_id: Optional[int] = None,
    ) -> ApprovalRequest:
        """
        Create an approval request for a tool invocation.
        
        If connected to Phase 3 ApprovalService, creates a real
        approval record. Otherwise, stores in memory.
        
        Args:
            tool: Tool requiring approval
            user_id: User requesting the action
            input_data: Tool input data to be reviewed
            audit_id: Correlation ID
            workflow_run_id: Optional linked workflow run
            
        Returns:
            ApprovalRequest with request_id for tracking
        """
        request_id = str(uuid.uuid4())
        approval_prompt = self._generate_approval_prompt(tool, input_data)
        
        request = ApprovalRequest(
            request_id=request_id,
            tool_name=tool.name,
            user_id=user_id,
            input_data=input_data,
            approval_prompt=approval_prompt,
            created_at=datetime.now(timezone.utc),
            workflow_run_id=workflow_run_id,
        )
        
        # Store in Phase 3 ApprovalService if available
        if self._approval_service and self._db_session and workflow_run_id:
            try:
                self._approval_service.request_approval(
                    workflow_run_id=workflow_run_id,
                    approval_data=request.to_dict(),
                    approval_prompt=approval_prompt,
                )
            except Exception:
                # Fall back to in-memory if ApprovalService fails
                pass
        
        # Always store in local cache for middleware checks
        self._pending[request_id] = request
        
        return request
    
    def require_approval(
        self,
        tool: Tool,
        user_id: int,
        input_data: dict,
        audit_id: Optional[str] = None,
        workflow_run_id: Optional[int] = None,
    ) -> None:
        """
        Create approval request and raise ApprovalRequiredError.
        
        This is the main middleware entry point - always raises.
        
        Args:
            tool: Tool requiring approval
            user_id: User requesting the action
            input_data: Tool input data to be reviewed
            audit_id: Correlation ID
            workflow_run_id: Optional linked workflow run
            
        Raises:
            ApprovalRequiredError: Always raised with request_id
        """
        request = self.request_approval(
            tool=tool,
            user_id=user_id,
            input_data=input_data,
            audit_id=audit_id,
            workflow_run_id=workflow_run_id,
        )
        
        raise ApprovalRequiredError(
            tool=tool.name,
            approval_request_id=request.request_id,
            audit_id=audit_id,
        )
    
    def check_approval_status(
        self,
        request_id: str,
    ) -> Optional[str]:
        """
        Check status of an approval request.
        
        Returns:
            "pending", "approved", "rejected", or None if not found
        """
        if request_id not in self._pending:
            return None
        
        request = self._pending[request_id]
        
        # Check Phase 3 ApprovalService if connected
        if self._approval_service and self._db_session and request.workflow_run_id:
            try:
                history = self._approval_service.get_approval_history(
                    workflow_run_id=request.workflow_run_id
                )
                if history.get("approved_at"):
                    # Approved or rejected
                    return "approved" if history.get("approved") else "rejected"
            except Exception:
                pass
        
        return "pending"
    
    def is_approved(self, request_id: str) -> bool:
        """Check if a request has been approved."""
        return self.check_approval_status(request_id) == "approved"
    
    def get_pending_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get a pending approval request by ID."""
        return self._pending.get(request_id)
    
    def _generate_approval_prompt(
        self,
        tool: Tool,
        input_data: dict,
    ) -> str:
        """Generate human-readable approval prompt."""
        # Format input data for review
        input_summary = "\n".join(
            f"  - {k}: {v}" for k, v in input_data.items()
        )
        
        return f"""Approval Required: {tool.name}

Description: {tool.description}

Risk Level: {tool.risk_level.value}

Input Data:
{input_summary}

Please review and approve or reject this action."""


def create_approval_bridge_from_settings(
    settings,
    db_session=None,
) -> ApprovalBridge:
    """
    Factory to create ApprovalBridge from gateway settings.
    
    Optionally connects to Phase 3 ApprovalService if db_session provided.
    """
    approval_service = None
    
    if db_session:
        try:
            from app.services.approval_service import ApprovalService
            approval_service = ApprovalService(db_session)
        except ImportError:
            # Phase 3 not available
            pass
    
    return ApprovalBridge(
        approval_service=approval_service,
        db_session=db_session,
    )
