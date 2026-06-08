"""Agentic workflow orchestration with tool calling and full harness.

Task D1: Integrates EnhancedToolCatalog for workflow-aware filtering.
Task D2: Uses ToolExposurePolicy for workflow-scoped tool exposure.
Task E1: Uses HeadlessEventBuilder for stable event contract with run_id correlation.
Task E2: Integrates AskUserReason for structured HITL payloads.
"""
from typing import List, Dict, Any, Optional, Callable, TYPE_CHECKING, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import asyncio
import json
import time
import os

from sqlalchemy.orm import Session
from app.services.ollama import OllamaClient, OllamaError
from app.services.mcp_registry import MCPToolRegistry, ToolCatalog
from app.services.mcp_client import MCPTool, MCPToolResult
from app.services.agent_state import AgentState, ActionOutcome
from app.services.error_handler import (
    AgentErrorHandler,
    ErrorType,
    ErrorContext,
    ErrorRecoveryStrategy,
    ToolCallTelemetry,
    is_error_retryable,
)
from app.services.agent_planner import AgentPlanner, TaskPlan
from app.services.bash_tool import BashTool
from app.services.simple_tools import SimpleTool
from app.services.tool_catalog import (
    EnhancedToolCatalog,
    ToolMetadata,
    WorkflowType,
    ToolExposurePolicy,
    get_default_metadata_registry,
    get_policy_for_workflow,
)
from app.services.headless_events import (
    HeadlessEventBuilder,
    AskUserReason,
    RemediationOption,
    InputField,
    InputFieldType,
    create_auth_remediation_options,
    create_validation_remediation_options,
    create_semantic_error_remediation_options,
    create_rbac_remediation_options,
    create_approval_remediation_options,
    get_ask_user_reason_for_error_type,
    get_remediation_options_for_error_type,
    get_default_token_store,
)
from app.services.loop_budget_policy import LoopBudgetPolicy, BudgetProfile
from app.models.models import User
import re


def _format_semantic_error_message(tool_name: str, error: str) -> tuple[str, str, list]:
    """
    Format a semantic error into a user-friendly message.
    
    Returns: (title, message, remediation_options)
    """
    error_lower = error.lower()
    
    # Approval required errors
    if "requires approval" in error_lower or "approval_required" in error_lower:
        # Extract request ID if present
        request_id_match = re.search(r'request_id:\s*([a-f0-9-]+)', error)
        request_id = request_id_match.group(1) if request_id_match else None
        
        title = f"Approval Required: {tool_name}"
        message = (
            f"The **{tool_name}** tool requires approval before it can execute. "
            f"This is a security measure for operations that modify data.\n\n"
        )
        if request_id:
            message += f"**Request ID:** `{request_id}`\n\n"
        message += (
            "**What you can do:**\n"
            "- Ask an administrator to approve this request\n"
            "- Use a different approach that doesn't require this tool\n"
            "- Check if you have the required permissions for this operation"
        )
        return title, message, create_approval_remediation_options(tool_name)
    
    # Validation errors
    if "validation" in error_lower or "invalid" in error_lower:
        title = f"Invalid Input: {tool_name}"
        message = (
            f"The **{tool_name}** tool received invalid input.\n\n"
            f"**Error:** {error}\n\n"
            "Please check your parameters and try again with corrected values."
        )
        return title, message, create_validation_remediation_options()
    
    # Permission/authorization errors
    if "permission" in error_lower or "unauthorized" in error_lower or "forbidden" in error_lower:
        title = f"Permission Denied: {tool_name}"
        message = (
            f"You don't have permission to use **{tool_name}**.\n\n"
            f"**Error:** {error}\n\n"
            "Contact your administrator if you believe you should have access."
        )
        return title, message, create_rbac_remediation_options()
    
    # Not found errors
    if "not found" in error_lower:
        title = f"Not Found: {tool_name}"
        message = (
            f"The requested resource was not found.\n\n"
            f"**Error:** {error}\n\n"
            "Please verify the identifiers and try again."
        )
        return title, message, create_semantic_error_remediation_options()
    
    # Generic semantic error
    title = f"Tool Error: {tool_name}"
    message = (
        f"The **{tool_name}** tool encountered an error.\n\n"
        f"**Error:** {error}\n\n"
        "Please review the error message and try again with corrected input."
    )
    return title, message, create_semantic_error_remediation_options()

if TYPE_CHECKING:
    from app.services.rate_limiter import RateLimiter
    from app.services.mcp_health import MCPHealthChecker

logger = logging.getLogger(__name__)

# Global retry budget for agent-level retries (MCP client has its own)
AGENT_RETRY_BUDGET = int(os.environ.get("AGENT_RETRY_BUDGET", "3"))


@dataclass
class AgenticConfig:
    """Configuration for agentic loop.

    Task D1: Adds enhanced_catalog flag for EnhancedToolCatalog usage.
    Task D2: Adds workflow_type for workflow-scoped tool filtering.
    Task 5M2.2: Uses LoopBudgetPolicy for profile-driven loop limits.
    """
    max_steps: int = 10  # DEPRECATED: Use loop_budget_policy instead
    require_approval_for_write: bool = False
    timeout_seconds: int = 120
    enable_loop_detection: bool = True
    loop_window_size: int = 3
    enable_planning: bool = False  # Simplified for MVP
    verify_plan_steps: bool = False
    stream_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
    # Task B1: Enable run-scoped tool catalog for deterministic routing
    use_tool_catalog: bool = True
    tool_catalog_ttl_seconds: Optional[int] = None  # None = use default
    # Task D1: Enable enhanced catalog with metadata filtering
    use_enhanced_catalog: bool = True
    # Session-scoped approval cache checker
    # Signature: (session_id: int, tool_name: str, arguments: dict) -> bool
    # Returns True if already approved for this session
    session_approval_checker: Optional[Callable[[int, str, Dict[str, Any]], Awaitable[bool]]] = None
    # Task 5M2.2: Loop budget policy (replaces hardcoded max_steps)
    loop_budget_policy: Optional[LoopBudgetPolicy] = None
    # Tool approval policy lookup
    # Signature: (tool_name: str) -> Optional[str]  # Returns policy string or None
    tool_approval_policy_lookup: Optional[Callable[[str], Optional[str]]] = None
    # Task D2: Workflow type for scoped tool exposure
    workflow_type: Optional[WorkflowType] = None  # None = GENERAL


@dataclass
class AgenticStep:
    """Single step in agentic loop."""
    step_number: int
    llm_response: Dict[str, Any]  # {"type": "text"/"tool_calls", ...}
    tool_executions: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AgenticResult:
    """Result from agentic workflow."""
    final_response: str
    steps: List[AgenticStep]
    total_steps: int
    stopped_reason: str  # "completed", "max_steps", "error", "approval_needed", "loop_detected", "timeout", "ask_user", "rate_limited", "tool_unavailable", "budget_exhausted"
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AgenticService:
    """Orchestrates agentic workflow with full harness.
    
    Task B1: Supports run-scoped tool catalog for deterministic routing.
    Task D1: Supports EnhancedToolCatalog with metadata filtering.
    Task D2: Supports workflow-scoped tool exposure policy.
    Task E1: Uses HeadlessEventBuilder for stable event contract with run_id correlation.
    Task E2: Supports structured HITL payloads for ask_user scenarios.
    """

    def __init__(
        self,
        ollama_client: OllamaClient,
        mcp_registry: MCPToolRegistry,
        config: AgenticConfig,
        rate_limiter: Optional["RateLimiter"] = None,
        health_checker: Optional["MCPHealthChecker"] = None,
        run_id: Optional[str] = None,
        session: Optional[Session] = None,
        tenant_id: Optional[int] = None,
        workflow_name: Optional[str] = None,
    ):
        """
        Initialize agentic service.

        Args:
            ollama_client: Ollama LLM client
            mcp_registry: MCP tool registry
            config: Agentic configuration
            rate_limiter: Optional rate limiter for tool calls
            health_checker: Optional health checker for MCP servers
            run_id: Optional run ID for tracking
            session: Optional database session for workflow loading
            tenant_id: Optional tenant ID for workflow context
            workflow_name: Optional workflow name to load
        """
        self.ollama = ollama_client
        self.mcp = mcp_registry
        self.config = config
        self.rate_limiter = rate_limiter
        self.health_checker = health_checker
        self.run_id = run_id
        self.session = session
        self.tenant_id = tenant_id
        self.workflow_name = workflow_name
        self.workflow_context: Dict[str, Any] = {}
        self.skills_context: Dict[str, Any] = {}
        self.error_handler = AgentErrorHandler(max_retries=3)
        self.bash_tool = BashTool(run_id=run_id)  # Initialize bash escape hatch with run_id
        self.simple_tools = SimpleTool()  # Initialize simple built-in tools
        self.logger = logging.getLogger(__name__)

        # Task 5M2.2: Resolve loop budget policy (fallback to default if not provided)
        if self.config.loop_budget_policy is None:
            self.config.loop_budget_policy = LoopBudgetPolicy.resolve(BudgetProfile.DEFAULT.value)

        # Session context (set during execute)
        self._session_id: Optional[int] = None

        # Task B1: Run-scoped tool catalog (created fresh for each run)
        self._run_catalog: Optional[ToolCatalog] = None
        self._catalog_initialized: bool = False  # Track if catalog was ever set

        # Task D1: Enhanced tool catalog with metadata
        self._enhanced_catalog: Optional[EnhancedToolCatalog] = None

        # Task E1: Headless event builder for run-correlated events
        # Wire in the default token store for durable resume token persistence
        self._event_builder: HeadlessEventBuilder = HeadlessEventBuilder(
            run_id=run_id,
            token_store=get_default_token_store(),
        )

    def _load_workflow_context(self) -> None:
        """Load tenant workflow if provided.

        Task 3 (Phase 5): Runtime integration for tenant-managed workflows.
        Loads active workflow and skills for the tenant and extracts runtime context.

        Contract:
        - Session must remain valid for entire workflow duration
        - Workflow lookup occurs once before first tool call
        - None results are logged but execution continues gracefully
        """
        if not (self.session and self.tenant_id and self.workflow_name):
            return

        from app.services.workflow_runtime_service import WorkflowRuntimeService

        workflow = WorkflowRuntimeService.load_active_workflow(
            self.session, self.tenant_id, self.workflow_name
        )

        if workflow:
            self.workflow_context = WorkflowRuntimeService.get_workflow_context(workflow)
            self.logger.info(f"Loaded workflow: {self.workflow_name} v{workflow.version}")
        else:
            self.logger.warning(f"Workflow not found: {self.workflow_name} for tenant {self.tenant_id}")

    def _load_skills_context(self) -> None:
        """Load and extract skills context before execution.

        Task 2 (Phase 5): Skill runtime integration.
        Task 4 (Phase 5): Enhanced to load skills from SkillRepository.

        Loads active skills for the tenant and makes them available to the agent.
        Skills are loaded from both WorkflowRuntimeService (legacy) and SkillRepository.

        Contract:
        - Gracefully handles missing session or tenant_id
        - Returns empty dict if no skills found (does not raise)
        - Logs skill count for observability
        - Captures errors and logs but continues execution
        """
        if not (self.session and self.tenant_id):
            return

        from app.services.workflow_runtime_service import WorkflowRuntimeService
        from app.repositories.skill_repository import SkillRepository

        try:
            # Load skills from WorkflowRuntimeService (legacy)
            workflow_skills = WorkflowRuntimeService.load_active_skills(
                session=self.session,
                tenant_id=self.tenant_id
            )

            # Load skills from SkillRepository (new skill system)
            repository_skills = SkillRepository.get_active_skills(
                db=self.session,
                tenant_id=self.tenant_id
            )

            # Merge skills from both sources
            all_skills = list(workflow_skills) if workflow_skills else []

            # Add repository skills if not already present
            workflow_skill_names = {skill.skill_name for skill in workflow_skills} if workflow_skills else set()
            for repo_skill in repository_skills:
                if repo_skill.skill_name not in workflow_skill_names:
                    all_skills.append(repo_skill)

            if all_skills:
                # Build combined context
                self.skills_context = WorkflowRuntimeService.get_skills_context(all_skills)

                # Add additional metadata for repository skills
                repo_skill_data = []
                for skill in repository_skills:
                    skill_info = {
                        "name": skill.skill_name,
                        "description": skill.description or "No description available",
                        "version": skill.version,
                        "intent_patterns": skill.intent_patterns or [],
                    }
                    # Include skill_data if it has useful information
                    if skill.skill_data:
                        skill_info["config"] = skill.skill_data
                    repo_skill_data.append(skill_info)

                # Merge repository skills into context
                if "skills" not in self.skills_context:
                    self.skills_context["skills"] = []
                self.skills_context["skills"].extend(repo_skill_data)

                # Update skill names list
                if "skill_names" not in self.skills_context:
                    self.skills_context["skill_names"] = []
                self.skills_context["skill_names"].extend([s["name"] for s in repo_skill_data])

                self.logger.info(
                    f"Loaded {len(all_skills)} active skills for tenant {self.tenant_id} "
                    f"({len(workflow_skills or [])} from workflow, {len(repository_skills)} from repository)",
                    extra={
                        "tenant_id": self.tenant_id,
                        "total_skill_count": len(all_skills),
                        "workflow_skill_count": len(workflow_skills or []),
                        "repository_skill_count": len(repository_skills),
                        "skill_names": self.skills_context.get("skill_names", [])
                    }
                )
            else:
                self.logger.debug(f"No active skills for tenant {self.tenant_id}")
                self.skills_context = {}
        except Exception as e:
            self.logger.error(
                f"Error loading skills for tenant {self.tenant_id}: {e}",
                extra={"tenant_id": self.tenant_id, "error": str(e)},
                exc_info=True
            )
            self.skills_context = {}

    def _is_catalog_valid(self) -> bool:
        """Check if run catalog is valid with proper type checking.

        Guards against mocked/malformed catalog objects that would derail control flow.
        """
        if self._run_catalog is None:
            return False
        # Type guard: ensure is_valid() returns an actual bool, not a coroutine/mock
        if not isinstance(self._run_catalog, ToolCatalog):
            logger.warning(
                f"_run_catalog is not a ToolCatalog instance: {type(self._run_catalog)}",
                extra={"catalog_type": str(type(self._run_catalog))}
            )
            return False
        result = self._run_catalog.is_valid()
        if not isinstance(result, bool):
            logger.warning(
                f"is_valid() returned non-bool: {type(result)}",
                extra={"result_type": str(type(result))}
            )
            return False
        return result

    async def ensure_run_catalog_initialized(self, user: User) -> bool:
        """
        Ensure run catalog is initialized (lazy initialization).
        
        Returns True if catalog is valid, False if initialization failed.
        
        Contract:
        - If catalog was never initialized, initializes it once.
        - If catalog was initialized but expired, returns False (catalog_stale).
        """
        if not self.config.use_tool_catalog:
            return True  # Legacy mode, no catalog needed
        
        # If already initialized and valid, we're good
        if self._catalog_initialized and self._is_catalog_valid():
            return True
        
        # If was initialized but now invalid, that's catalog_stale
        if self._catalog_initialized and not self._is_catalog_valid():
            return False  # Caller should emit CATALOG_STALE error
        
        # Never initialized - initialize now
        self._run_catalog = await self.mcp.create_run_catalog(
            ttl_seconds=self.config.tool_catalog_ttl_seconds,
        )
        # Validate that we got a proper ToolCatalog
        if not isinstance(self._run_catalog, ToolCatalog):
            logger.error(
                f"create_run_catalog returned invalid type: {type(self._run_catalog)}",
                extra={"catalog_type": str(type(self._run_catalog))}
            )
            return False
        self._catalog_initialized = True
        return True

    async def execute(
        self,
        messages: List[Dict[str, Any]],
        user: User,
        session_id: int,
        model: Optional[str] = None,
    ) -> AgenticResult:
        """
        Execute agentic workflow with timeout wrapper.

        Args:
            messages: Conversation history
            user: Current user (for role-based tool access)
            session_id: Session ID for state tracking
            model: Ollama model to use

        Returns:
            AgenticResult with final response and execution trace
        """
        try:
            return await asyncio.wait_for(
                self._execute_internal(messages, user, session_id, model),
                timeout=self.config.timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.error(
                f"Agentic workflow timeout after {self.config.timeout_seconds}s",
                extra={"user_id": user.id, "session_id": session_id}
            )
            return AgenticResult(
                final_response="",
                steps=[],
                total_steps=0,
                stopped_reason="timeout",
                error=f"Workflow timeout after {self.config.timeout_seconds}s",
            )

    async def _execute_internal(
        self,
        messages: List[Dict[str, Any]],
        user: User,
        session_id: int,
        model: Optional[str] = None,
    ) -> AgenticResult:
        """
        Internal execution logic for agentic workflow.

        Args:
            messages: Conversation history
            user: Current user
            session_id: Session ID
            model: Ollama model

        Returns:
            AgenticResult
        """
        # Store session context for approval checks
        self._session_id = session_id
        
        steps: List[AgenticStep] = []
        current_messages = messages.copy()
        # Retry tracking is now run-scoped via AgentState._fingerprint_retry_counts
        # (removed step-scoped retry_count dict per Task A1)

        # Initialize state management
        state = AgentState(session_id=session_id, current_step=0)

        # Get available tools for user's role
        available_tools = await self._get_tool_definitions(user)

        # Add system prompt for tool usage (required for qwen2.5-coder and similar models)
        if available_tools and not any(msg.get("role") == "system" for msg in current_messages):
            tool_names = [tool["function"]["name"] for tool in available_tools]
            system_prompt = f"""You are a helpful AI assistant with access to tools and skills. When the user's request requires external actions, data retrieval, or computation, you MUST use the available tools by making function calls.

Available tools: {', '.join(tool_names)}

IMPORTANT RULES:
1. If a tool requires parameters the user has not provided, ASK THE USER for those values. Do NOT make up data like names, IDs, or other specific values.
2. When you receive tool results, use them to formulate your final response.
3. If a tool call fails, explain the error to the user and ask how to proceed.
4. Do NOT repeatedly call the same tool with the same arguments - if it fails once, investigate why.
5. After successfully completing a task, provide a clear confirmation to the user.

To use a tool, respond with a function call in the format expected by the API."""

            current_messages.insert(0, {
                "role": "system",
                "content": system_prompt
            })

        # Task 3 (Phase 5): Load workflow context before execution
        self._load_workflow_context()

        # Task 2 (Phase 5): Load skills context before execution
        self._load_skills_context()
        logger.info(f"🔍 Skills loaded: {len(self.skills_context.get('skills', []))} skills in context")
        if self.skills_context.get('skills'):
            logger.info(f"🔍 Skill names: {[s.get('name') for s in self.skills_context['skills']]}")

        # Task 4 (Phase 5): Check if user message matches a skill intent pattern
        skill_match_result = await self._check_skill_match(messages, user)
        if skill_match_result:
            # Skill matched and executed - format and return the result
            logger.info(
                f"Skill '{skill_match_result['skill_name']}' matched and executed",
                extra={
                    "skill_name": skill_match_result["skill_name"],
                    "success": skill_match_result.get("success", False),
                    "tenant_id": self.tenant_id,
                    "tools_used": len(skill_match_result.get("tool_calls", [])),
                }
            )

            # Format skill response for user display
            formatted_response = self._format_skill_response(skill_match_result)

            return AgenticResult(
                final_response=formatted_response,
                steps=[],
                total_steps=0,
                stopped_reason="skill_executed",
                metadata={
                    "skill_name": skill_match_result["skill_name"],
                    "skill_executed": True,
                    "skill_success": skill_match_result.get("success", False),
                    "tool_calls": skill_match_result.get("tool_calls", []),
                    "run_id": self.run_id,
                },
            )

        # Enhance system prompt with skills context if available
        if self.skills_context and self.skills_context.get("skill_names"):
            # Find the system message and append skills info
            system_msg = next((msg for msg in current_messages if msg.get("role") == "system"), None)
            if system_msg:
                # Build a concise skills description for the system prompt
                skills_list = self.skills_context.get("skills", [])
                if skills_list:
                    skills_description = "\n\nAvailable Skills (invoke by intent):\n"
                    for skill in skills_list:
                        skills_description += f"  - {skill['name']}: {skill.get('description', 'No description')}\n"
                        if skill.get('intent_patterns'):
                            skills_description += f"    Triggers: {', '.join(skill['intent_patterns'][:3])}\n"
                    system_msg["content"] += skills_description

        # Log workflow start if workflow loaded
        if self.workflow_name and self.workflow_context:
            from app.services.workflow_runtime_service import WorkflowRuntimeService
            WorkflowRuntimeService.log_workflow_execution(
                self.run_id,
                self.tenant_id,
                self.workflow_name,
                self.workflow_context.get("version"),
                "started"
            )

        # Task 5M2.2: Use policy-driven loop budget
        loop_budget = self.config.loop_budget_policy
        max_steps = loop_budget.max_steps

        logger.info(
            "Starting agentic workflow",
            extra={
                "user_id": user.id,
                "user_role": user.role.value,
                "session_id": session_id,
                "available_tools": len(available_tools),
                "max_steps": max_steps,
                "budget_profile": loop_budget.profile.value,
                "workflow_name": self.workflow_name,
                "workflow_version": self.workflow_context.get("version") if self.workflow_context else None,
            }
        )

        # Create plan if enabled
        plan: Optional[TaskPlan] = None
        if self.config.enable_planning and messages:
            planner = AgentPlanner()

            # Extract task from last user message
            task_description = next(
                (msg["content"] for msg in reversed(messages) if msg.get("role") == "user"),
                "Complete the requested task"
            )

            # Get available tool names
            available_tool_names = [tool["function"]["name"] for tool in available_tools]

            # Create plan
            plan = await planner.create_plan(
                task_description=task_description,
                ollama_client=self.ollama,
                available_tools=available_tool_names,
            )

            logger.info(
                f"Created plan with {len(plan.steps)} steps",
                extra={"session_id": session_id, "steps": len(plan.steps)}
            )

            # Stream plan to user
            if self.config.stream_callback:
                event = self._event_builder.plan_created([s.description for s in plan.steps])
                await self.config.stream_callback(event.to_dict())

        # Emit start event (Task E1: use HeadlessEventBuilder for run_id correlation)
        if self.config.stream_callback:
            workflow_type_str = self.config.workflow_type.value if self.config.workflow_type else None
            event = self._event_builder.workflow_start(
                available_tools=len(available_tools),
                max_steps=max_steps,
                workflow_type=workflow_type_str,
                model=model,
            )
            await self.config.stream_callback(event.to_dict())

        # Main control loop (Task 5M2.2: Use policy-driven max_steps)
        for step_num in range(1, max_steps + 1):
            state.current_step = step_num
            step_start = datetime.now(timezone.utc)

            # Task 5M2.3: Emit budget warning at 80% threshold
            warning_step = loop_budget.get_warning_step()
            if step_num == warning_step:
                logger.warning(
                    f"Budget warning: {step_num}/{max_steps} steps used ({loop_budget.profile.value} profile)",
                    extra={"session_id": session_id, "step": step_num, "profile": loop_budget.profile.value}
                )
                if self.config.stream_callback:
                    event = self._event_builder.budget_warning(
                        current_step=step_num,
                        budget_limit=max_steps,
                        remaining=max_steps - step_num,
                        profile=loop_budget.profile.value,
                    )
                    await self.config.stream_callback(event.to_dict())

            # Check plan progress if planning enabled
            if plan:
                next_step = plan.get_next_step()
                if next_step is None:
                    if plan.is_complete():
                        logger.info("Plan completed successfully")
                        return AgenticResult(
                            final_response="All planned steps completed successfully.",
                            steps=steps,
                            total_steps=step_num - 1,
                            stopped_reason="completed",
                        )
                    else:
                        logger.warning("No more steps available but plan not complete")
                else:
                    logger.info(
                        f"Executing plan step {next_step.step_number}: {next_step.description}",
                        extra={"session_id": session_id, "step": next_step.step_number}
                    )

            # Check for loops
            if self.config.enable_loop_detection and state.detect_loop(self.config.loop_window_size):
                logger.warning(
                    f"Loop detected at step {step_num}",
                    extra={"session_id": session_id, "step": step_num}
                )

                if self.config.stream_callback:
                    event = self._event_builder.loop_detected(step_number=step_num)
                    await self.config.stream_callback(event.to_dict())

                return AgenticResult(
                    final_response="Agent loop detected. Stopping execution to prevent infinite loop.",
                    steps=steps,
                    total_steps=step_num,
                    stopped_reason="loop_detected",
                )

            # Call Ollama with tool definitions
            try:
                llm_response = await self.ollama.generate_chat_completion_with_tools(
                    messages=current_messages,
                    tools=available_tools if available_tools else None,
                    model=model,
                )
            except OllamaError as e:
                logger.error(f"Ollama error at step {step_num}: {e}")
                return AgenticResult(
                    final_response="",
                    steps=steps,
                    total_steps=step_num - 1,
                    stopped_reason="error",
                    error=str(e),
                )

            # Handle response based on type
            if llm_response["type"] == "text":
                # Final response - no more tool calls
                final_text = llm_response["content"]

                # Check confidence
                confidence = self.error_handler.parse_confidence(final_text)

                if confidence < 0.5:  # Low confidence threshold
                    logger.warning(
                        f"Low confidence response: {confidence}",
                        extra={"session_id": session_id, "confidence": confidence}
                    )

                    if self.config.stream_callback:
                        event = self._event_builder.low_confidence(confidence=confidence, step_number=step_num)
                        await self.config.stream_callback(event.to_dict())

                    # For MVP, continue anyway but log it
                    # In production, might want to ask user for confirmation

                steps.append(AgenticStep(
                    step_number=step_num,
                    llm_response=llm_response,
                    tool_executions=[],
                    timestamp=step_start,
                ))

                logger.info(
                    "Agentic workflow completed",
                    extra={
                        "user_id": user.id,
                        "session_id": session_id,
                        "total_steps": step_num,
                        "reason": "completed",
                    }
                )

                if self.config.stream_callback:
                    event = self._event_builder.workflow_complete(
                        total_steps=step_num,
                        stopped_reason="completed",
                    )
                    await self.config.stream_callback(event.to_dict())

                return AgenticResult(
                    final_response=final_text,
                    steps=steps,
                    total_steps=step_num,
                    stopped_reason="completed",
                    metadata={"confidence": confidence},
                )

            elif llm_response["type"] == "tool_calls":
                # Execute tool calls
                tool_calls = llm_response["tool_calls"]
                tool_executions = []

                # Extract tool names for logging and events
                tool_names = [tc.get("function", {}).get("name") for tc in tool_calls]

                logger.info(
                    f"Step {step_num}: Executing {len(tool_calls)} tool calls: {tool_names}",
                    extra={
                        "step": step_num,
                        "tool_count": len(tool_calls),
                        "tools": tool_names,
                    }
                )

                if self.config.stream_callback:
                    event = self._event_builder.step(
                        step_number=step_num,
                        action="tool_calls",
                        tool_names=tool_names,
                        tool_count=len(tool_calls),
                        max_steps=max_steps,
                    )
                    await self.config.stream_callback(event.to_dict())

                should_retry_step = False  # Flag to break out of tool loop for retry

                for tool_call in tool_calls:
                    tool_name = tool_call.get("function", {}).get("name")
                    tool_args = tool_call.get("function", {}).get("arguments", {})
                    tool_id = tool_call.get("id", "unknown")

                    # Normalize tool arguments across model variants.
                    # Some models return arguments as a JSON string instead of an object.
                    if isinstance(tool_args, str):
                        try:
                            parsed_args = json.loads(tool_args)
                            tool_args = parsed_args if isinstance(parsed_args, dict) else {}
                        except json.JSONDecodeError:
                            logger.warning(
                                f"Tool arguments were non-JSON string for {tool_name}; defaulting to empty args",
                                extra={"tool_name": tool_name, "tool_id": tool_id, "raw_args": tool_args[:200]},
                            )
                            tool_args = {}
                    elif not isinstance(tool_args, dict):
                        logger.warning(
                            f"Tool arguments were not an object for {tool_name}; defaulting to empty args",
                            extra={"tool_name": tool_name, "tool_id": tool_id, "args_type": type(tool_args).__name__},
                        )
                        tool_args = {}

                    # Emit tool_executing event BEFORE execution (Task E1: use builder)
                    if self.config.stream_callback:
                        event = self._event_builder.tool_executing(
                            tool_name=tool_name,
                            tool_index=tool_calls.index(tool_call) + 1,
                            tool_total=len(tool_calls),
                            step_number=step_num,
                            arguments=tool_args,
                        )
                        await self.config.stream_callback(event.to_dict())

                    logger.debug(
                        f"Executing tool: {tool_name}",
                        extra={
                            "tool_name": tool_name,
                            "tool_id": tool_id,
                            "step": step_num,
                            "args_keys": list(tool_args.keys()) if tool_args else [],
                        }
                    )

                    # Check if approval needed for write operations
                    if self.config.require_approval_for_write and await self._requires_approval(tool_name, tool_args):
                        logger.info(f"Approval required for tool: {tool_name}")

                        if self.config.stream_callback:
                            event = self._event_builder.approval_request(
                                tool_name=tool_name,
                                arguments=tool_args,
                                step_number=step_num,
                            )
                            await self.config.stream_callback(event.to_dict())

                        return AgenticResult(
                            final_response="",
                            steps=steps,
                            total_steps=step_num,
                            stopped_reason="approval_needed",
                            metadata={
                                "pending_tool_call": {
                                    "tool_name": tool_name,
                                    "arguments": tool_args,
                                    "tool_call_id": tool_id,
                                },
                                "run_id": self._event_builder.run_id,  # Task E1: Include run_id in metadata
                            },
                        )

                    # Check if action already completed (deduplication)
                    if state.has_action_been_completed("tool_call", {"name": tool_name, "args": tool_args}):
                        logger.info(f"Skipping duplicate tool call: {tool_name}")
                        continue

                    # Rate limiting check for tool calls
                    if self.rate_limiter:
                        allowed, msg = await self.rate_limiter.check_tool_call_limit(user.id)
                        if not allowed:
                            logger.warning(f"Tool call rate limit reached: {msg}")
                            return AgenticResult(
                                final_response="Rate limit reached. Please wait before making more requests.",
                                steps=steps,
                                total_steps=step_num,
                                stopped_reason="rate_limited",
                                error=msg,
                            )
                        
                        # Check circuit breaker for the MCP server
                        server_name = await self._get_server_for_tool(tool_name)
                        if server_name:
                            circuit_ok, circuit_msg = await self.rate_limiter.check_circuit(server_name)
                            if not circuit_ok:
                                logger.warning(f"Circuit breaker open for {server_name}: {circuit_msg}")
                                
                                # Record circuit breaker skip
                                action_data_circuit = {"name": tool_name, "args": tool_args}
                                state.record_action(
                                    action_type="tool_call",
                                    action_data=action_data_circuit,
                                    result=circuit_msg,
                                    success=False,
                                    outcome=ActionOutcome.SKIPPED,
                                    error_type="circuit_breaker",
                                )
                                
                                tool_executions.append({
                                    "tool_call_id": tool_id,
                                    "tool_name": tool_name,
                                    "arguments": tool_args,
                                    "result": None,
                                    "error": circuit_msg,
                                    "circuit_open": True,
                                })
                                continue

                    # Health check for tool availability
                    if self.health_checker:
                        is_write = self.health_checker.is_write_tool(tool_name)
                        tool_ok, tool_msg = self.health_checker.check_tool_for_execution(
                            tool_name, is_write=is_write
                        )
                        if not tool_ok:
                            logger.warning(f"Tool unavailable: {tool_msg}")
                            if is_write:
                                # Fail closed for write tools
                                return AgenticResult(
                                    final_response="",
                                    steps=steps,
                                    total_steps=step_num,
                                    stopped_reason="tool_unavailable",
                                    error=f"Write tool unavailable: {tool_msg}",
                                )
                            else:
                                # Skip read tools in degraded mode
                                action_data_degraded = {"name": tool_name, "args": tool_args}
                                state.record_action(
                                    action_type="tool_call",
                                    action_data=action_data_degraded,
                                    result=tool_msg,
                                    success=False,
                                    outcome=ActionOutcome.SKIPPED,
                                    error_type="degraded_mode",
                                )
                                
                                tool_executions.append({
                                    "tool_call_id": tool_id,
                                    "tool_name": tool_name,
                                    "arguments": tool_args,
                                    "result": None,
                                    "error": tool_msg,
                                    "degraded": True,
                                })
                                continue

                    # Check if this tool has already failed terminally (non-retryable)
                    action_data = {"name": tool_name, "args": tool_args}
                    if state.has_action_failed_terminally("tool_call", action_data):
                        logger.warning(f"Tool {tool_name} previously failed with terminal error - stopping for user intervention")
                        state.record_action(
                            action_type="tool_call",
                            action_data=action_data,
                            result=None,
                            success=False,
                            outcome=ActionOutcome.ABORTED,
                            error_type="previously_failed_terminal",
                        )
                        # P1 Fix: Emit ask_user event BEFORE returning
                        terminal_error_msg = (
                            f"Tool '{tool_name}' previously failed with a non-retryable error and cannot be retried. "
                            f"Please review the error and provide alternative instructions."
                        )
                        if self.config.stream_callback:
                            event = self._event_builder.ask_user(
                                reason=AskUserReason.TERMINAL_ERROR,
                                title="Previous Tool Failure",
                                message=terminal_error_msg,
                                options=get_remediation_options_for_error_type("previously_failed_terminal"),
                                context={
                                    "tool_name": tool_name,
                                    "error_type": "previously_failed_terminal",
                                },
                                step_number=step_num,
                            )
                            await self.config.stream_callback(event.to_dict())
                            # Persist token for durable resume
                            await self._event_builder.persist_resume_token(event.payload.get("resume_token"))
                        
                        return AgenticResult(
                            final_response=terminal_error_msg,
                            steps=steps,
                            total_steps=step_num,
                            stopped_reason="ask_user",
                            error=f"Terminal tool failure: {tool_name}",
                            metadata={"run_id": self._event_builder.run_id},
                        )
                    
                    # Check global budget
                    if state.is_budget_exhausted():
                        logger.error("Global attempt budget exhausted")
                        return AgenticResult(
                            final_response="",
                            steps=steps,
                            total_steps=step_num,
                            stopped_reason="error",
                            error="Maximum total tool attempts exceeded",
                        )

                    # Task A1: Use run-scoped retry tracking via canonical fingerprint
                    # The fingerprint is based on {tool_name, tool_args} so same call
                    # across different steps shares retry budget
                    current_retries = state.get_fingerprint_retry_count(tool_name, tool_args)
                    attempt_budget = min(AGENT_RETRY_BUDGET, self.error_handler.max_retries)

                    # Track tool execution time
                    tool_start_time = time.time()

                    try:
                        # Record tool call for rate limiting
                        if self.rate_limiter:
                            await self.rate_limiter.record_tool_call(user.id)

                        # Handle simple built-in tools first
                        simple_tool_names = ["store_memory", "retrieve_memory", "list_memory_keys", "calculate", "retrieve_historical_context"]
                        if tool_name in simple_tool_names:
                            from app.services.mcp_client import MCPToolResult
                            # Set context for tools that need database access
                            self.simple_tools.set_context(
                                db_session=self.session,
                                tenant_id=self.tenant_id,
                                session_id=self._session_id or 0
                            )
                            simple_result = await self.simple_tools.execute_tool(tool_name, tool_args)
                            result = MCPToolResult(
                                success=simple_result["success"],
                                result=simple_result.get("result"),
                                error=simple_result.get("error"),
                            )
                        # Handle bash escape hatch
                        elif tool_name == "execute_bash":
                            result = await self.bash_tool.execute_bash(
                                script=tool_args.get("script", ""),
                                description=tool_args.get("description", "No description"),
                                timeout_seconds=30,
                            )
                        # Handle MCP tools
                        else:
                            # Refactor: When use_tool_catalog=true, catalog is authoritative.
                            # No fallback to legacy discovery path mid-run.
                            if self.config.use_tool_catalog:
                                # Ensure catalog is initialized (lazy init on first tool call)
                                catalog_ready = await self.ensure_run_catalog_initialized(user)
                                
                                if catalog_ready and self._is_catalog_valid():
                                    result = await self.mcp.execute_tool_with_catalog(
                                        tool_name=tool_name,
                                        arguments=tool_args,
                                        user=user,
                                        catalog=self._run_catalog,
                                    )
                                else:
                                    # catalog_stale: was initialized then expired (not "never initialized")
                                    result = MCPToolResult(
                                        success=False,
                                        error="Tool catalog expired during run. Please retry the operation.",
                                        error_category="catalog_stale",
                                        is_semantic_error=True,
                                    )
                            else:
                                # Legacy mode: direct tool execution
                                result = await self.mcp.execute_tool(
                                    tool_name=tool_name,
                                    arguments=tool_args,
                                    user=user,
                                )
                            
                            # Contract validation: ensure result is MCPToolResult-like
                            if not hasattr(result, 'success') or not isinstance(result.success, bool):
                                logger.error(
                                    f"Tool execution returned malformed result: {type(result)}",
                                    extra={"tool": tool_name, "result_type": str(type(result))}
                                )
                                result = MCPToolResult(
                                    success=False,
                                    error=f"Internal error: malformed tool result from {tool_name}",
                                    error_category="internal_error",
                                    is_semantic_error=True,
                                )

                        # Calculate execution duration
                        tool_duration_ms = int((time.time() - tool_start_time) * 1000)

                        # Update circuit breaker on success/failure
                        if self.rate_limiter and server_name:
                            if result.success:
                                await self.rate_limiter.record_circuit_success(server_name)
                            else:
                                await self.rate_limiter.record_circuit_failure(server_name)

                        # Handle tool failure with recovery strategy
                        if not result.success:
                            # Classify the error type
                            # Task C2: Use structured envelope fields (upstream_status, terminal_hint)
                            error_type = self.error_handler.classify_from_result(result)
                            
                            # Extract envelope fields for context and telemetry
                            http_status = getattr(result, 'http_status', None)
                            error_category = getattr(result, 'error_category', None)
                            
                            # Check if error is retryable
                            retryable = is_error_retryable(error_type)
                            
                            context = ErrorContext(
                                error_type=error_type,
                                step_number=step_num,
                                tool_name=tool_name,
                                error_message=result.error or "Unknown error",
                                retry_count=current_retries,
                                metadata={"tool_args": tool_args, "error_category": error_category},
                                http_status=http_status,
                                attempt_budget=attempt_budget,
                            )

                            action = self.error_handler.decide_recovery(context)
                            
                            # Build telemetry
                            telemetry = ToolCallTelemetry(
                                tool_name=tool_name,
                                error_type=error_type.value,
                                http_status=http_status,
                                retryable=retryable,
                                attempt_index=current_retries,
                                attempt_budget=attempt_budget,
                                recovery_strategy=action.strategy.value,
                                terminal=action.terminal,
                                duration_ms=tool_duration_ms,
                            )
                            
                            logger.warning(
                                f"Tool failure: {tool_name}",
                                extra=telemetry.to_dict(),
                            )
                            
                            # Emit telemetry event (Task E1: use builder for run_id correlation)
                            if self.config.stream_callback:
                                event = self._event_builder.tool_error(
                                    tool_name=tool_name,
                                    step_number=step_num,
                                    error=result.error,
                                    error_type=error_type.value,
                                    http_status=http_status,
                                    retryable=retryable,
                                    attempt_index=current_retries,
                                    attempt_budget=attempt_budget,
                                    recovery_strategy=action.strategy.value,
                                    terminal=action.terminal,
                                    duration_ms=tool_duration_ms,
                                )
                                await self.config.stream_callback(event.to_dict())

                            # Task A2: Check retry ownership before proceeding
                            # If MCP client exhausted transport retries, don't retry at agent level
                            transport_exhausted = getattr(result, 'transport_retries_exhausted', False)
                            is_semantic = getattr(result, 'is_semantic_error', False)

                            if action.strategy == ErrorRecoveryStrategy.RETRY:
                                # Task A2: Semantic errors should never be retried as transient failures.
                                # However, we should let the agent SEE the error and try alternative approaches.
                                if is_semantic:
                                    error_lower = (result.error or "").lower()
                                    
                                    # Check if this is an agent-blocking error that requires USER action
                                    # Note: 401 from external services (BRS) is NOT blocking - agent can authenticate
                                    # Only truly blocking are approval workflow and user-level auth issues
                                    is_agent_blocking = (
                                        "requires approval" in error_lower or
                                        "approval_required" in error_lower or
                                        "pending approval" in error_lower
                                        # Removed: "not authenticated" - agent can try authenticate_club tool
                                        # Removed: "unauthorized" - agent can recover by authenticating
                                    )
                                    
                                    if is_agent_blocking:
                                        # These errors need user action - escalate immediately
                                        logger.warning(
                                            f"Agent-blocking error for {tool_name}; escalating to ASK_USER",
                                            extra={
                                                "tool_name": tool_name,
                                                "reason": "agent_blocking_error",
                                                "error_type": error_type.value,
                                            }
                                        )
                                        state.record_action(
                                            action_type="tool_call",
                                            action_data=action_data,
                                            result=result.error,
                                            success=False,
                                            outcome=ActionOutcome.NON_RETRYABLE_FAILURE,
                                            error_type=error_type.value,
                                            http_status=http_status,
                                            duration_ms=tool_duration_ms,
                                        )

                                        # Format error into user-friendly message
                                        error_title, error_message, remediation_options = _format_semantic_error_message(
                                            tool_name, result.error
                                        )

                                        if self.config.stream_callback:
                                            event = self._event_builder.ask_user(
                                                reason=AskUserReason.SEMANTIC_ERROR,
                                                title=error_title,
                                                message=error_message,
                                                options=remediation_options,
                                                context={
                                                    "tool_name": tool_name,
                                                    "error": result.error,
                                                    "error_type": error_type.value,
                                                },
                                                step_number=step_num,
                                            )
                                            await self.config.stream_callback(event.to_dict())
                                            await self._event_builder.persist_resume_token(event.payload.get("resume_token"))

                                        return AgenticResult(
                                            final_response=error_message,
                                            steps=steps,
                                            total_steps=step_num,
                                            stopped_reason="ask_user",
                                            error=None,  # Don't set error - ask_user is a controlled pause, not a failure
                                            metadata={
                                                "tool_name": tool_name,
                                                "error_type": error_type.value,
                                                "semantic_error": True,
                                                "error_detail": result.error,  # Store original error here for reference
                                                "run_id": self._event_builder.run_id,
                                            },
                                        )
                                    
                                    # Recoverable semantic error - let agent see it and try alternatives
                                    logger.info(
                                        f"Semantic error for {tool_name}; feeding back to agent for recovery",
                                        extra={
                                            "tool_name": tool_name,
                                            "reason": "agent_recovery_attempt",
                                            "error_type": error_type.value,
                                        }
                                    )
                                    
                                    state.record_action(
                                        action_type="tool_call",
                                        action_data=action_data,
                                        result=result.error,
                                        success=False,
                                        outcome=ActionOutcome.RETRYABLE_FAILURE,
                                        error_type=error_type.value,
                                        http_status=http_status,
                                        duration_ms=tool_duration_ms,
                                    )
                                    
                                    # Add tool result with error to message history so agent can reason about it
                                    tool_executions.append({
                                        "tool_call_id": tool_id,
                                        "tool_name": tool_name,
                                        "arguments": tool_args,
                                        "result": result,  # Includes error info
                                        "error": result.error,
                                    })
                                    
                                    # Emit error event for streaming UI
                                    if self.config.stream_callback:
                                        event = self._event_builder.tool_result(
                                            tool_name=tool_name,
                                            tool_index=tool_calls.index(tool_call) + 1,
                                            tool_total=len(tool_calls),
                                            success=False,
                                            error=result.error,
                                            duration_ms=tool_duration_ms,
                                        )
                                        await self.config.stream_callback(event.to_dict())
                                    
                                    # Continue with next tool in this step (or next step)
                                    continue

                                # Task A2: Guard against retry amplification
                                if transport_exhausted:
                                    logger.warning(
                                        f"Transport retries exhausted for {tool_name}, escalating to ASK_USER",
                                        extra={
                                            "tool_name": tool_name,
                                            "transport_retries": result.retry_count,
                                            "reason": "retry_ownership_guard",
                                        }
                                    )
                                    # Record the failure and escalate
                                    state.record_action(
                                        action_type="tool_call",
                                        action_data=action_data,
                                        result=result.error,
                                        success=False,
                                        outcome=ActionOutcome.NON_RETRYABLE_FAILURE,
                                        error_type=error_type.value,
                                        http_status=http_status,
                                        duration_ms=tool_duration_ms,
                                    )
                                    
                                    # Task E2: Emit structured ask_user event
                                    if self.config.stream_callback:
                                        event = self._event_builder.ask_user(
                                            reason=AskUserReason.TRANSPORT_EXHAUSTED,
                                            title="Transport Retries Exhausted",
                                            message=f"Tool '{tool_name}' failed after {result.retry_count} transport retries. Error: {result.error}",
                                            options=[
                                                RemediationOption(
                                                    id="retry",
                                                    label="Retry",
                                                    description="Try the tool again",
                                                    action="retry",
                                                ),
                                                RemediationOption(
                                                    id="skip",
                                                    label="Skip",
                                                    description="Skip this tool and continue",
                                                    action="skip",
                                                ),
                                                RemediationOption(
                                                    id="abort",
                                                    label="Cancel",
                                                    description="Stop the workflow",
                                                    action="abort",
                                                ),
                                            ],
                                            context={
                                                "tool_name": tool_name,
                                                "error": result.error,
                                                "error_type": error_type.value,
                                                "retry_count": result.retry_count,
                                            },
                                            step_number=step_num,
                                        )
                                        await self.config.stream_callback(event.to_dict())
                                        # Persist token for durable resume
                                        await self._event_builder.persist_resume_token(event.payload.get("resume_token"))
                                    
                                    return AgenticResult(
                                        final_response=f"Tool '{tool_name}' failed after exhausting transport retries. Error: {result.error}",
                                        steps=steps,
                                        total_steps=step_num,
                                        stopped_reason="ask_user",
                                        error=f"Transport retries exhausted for {tool_name}",
                                        metadata={
                                            "tool_name": tool_name,
                                            "error_type": error_type.value,
                                            "transport_retries": result.retry_count,
                                            "run_id": self._event_builder.run_id,
                                        },
                                    )
                                
                                # Record retry attempt
                                state.record_action(
                                    action_type="tool_call",
                                    action_data=action_data,
                                    result=result.error,
                                    success=False,
                                    outcome=ActionOutcome.RETRYABLE_FAILURE,
                                    error_type=error_type.value,
                                    http_status=http_status,
                                    duration_ms=tool_duration_ms,
                                )
                                
                                # Use rate limiter's backoff if available
                                if self.rate_limiter and self.rate_limiter.should_retry(current_retries):
                                    delay = await self.rate_limiter.wait_with_backoff(current_retries)
                                    logger.info(f"Retrying tool: {tool_name} (attempt {current_retries + 1}/{attempt_budget}, delay {delay:.2f}s)")
                                elif action.retry_delay_seconds:
                                    await asyncio.sleep(action.retry_delay_seconds)
                                    logger.info(f"Retrying tool: {tool_name} (attempt {current_retries + 1}/{attempt_budget})")
                                else:
                                    logger.info(f"Retrying tool: {tool_name} (attempt {current_retries + 1}/{attempt_budget})")

                                # Task A1: Use run-scoped fingerprint retry tracking
                                state.increment_fingerprint_retry(tool_name, tool_args)

                                # Set flag to retry entire step (break out of tool loop)
                                should_retry_step = True
                                break

                            elif action.strategy == ErrorRecoveryStrategy.FALLBACK:
                                logger.info(f"Using fallback tool: {action.fallback_tool}")
                                
                                # Record fallback attempt
                                state.record_action(
                                    action_type="tool_call",
                                    action_data=action_data,
                                    result=result.error,
                                    success=False,
                                    outcome=ActionOutcome.RETRYABLE_FAILURE,
                                    error_type=error_type.value,
                                    duration_ms=tool_duration_ms,
                                )

                                # Execute fallback tool (same routing logic as primary)
                                if self.config.use_tool_catalog:
                                    catalog_ready = await self.ensure_run_catalog_initialized(user)
                                    if catalog_ready and self._is_catalog_valid():
                                        result = await self.mcp.execute_tool_with_catalog(
                                            tool_name=action.fallback_tool,
                                            arguments=tool_args,
                                            user=user,
                                            catalog=self._run_catalog,
                                        )
                                    else:
                                        from app.services.mcp_client import MCPToolResult
                                        result = MCPToolResult(
                                            success=False,
                                            error="Tool catalog expired during run. Please retry the operation.",
                                            error_category="catalog_stale",
                                            is_semantic_error=True,
                                        )
                                else:
                                    result = await self.mcp.execute_tool(
                                        tool_name=action.fallback_tool,
                                        arguments=tool_args,
                                        user=user,
                                    )

                            elif action.strategy == ErrorRecoveryStrategy.ASK_USER:
                                # Task A3: Check if model should get a reflection turn first
                                # For recoverable errors (validation, missing args), allow one corrective turn
                                recoverable_for_reflection = error_type in {
                                    ErrorType.VALIDATION_ERROR,
                                    ErrorType.MALFORMED_OUTPUT,
                                }
                                
                                if recoverable_for_reflection and state.can_reflect(tool_name, tool_args):
                                    # Allow model one corrective turn
                                    logger.info(
                                        f"Allowing reflection turn for {tool_name} ({error_type.value})",
                                        extra={
                                            "tool_name": tool_name,
                                            "error_type": error_type.value,
                                            "reflection_attempt": state.get_reflection_attempts(tool_name, tool_args) + 1,
                                        }
                                    )
                                    
                                    # Record the error for tracking
                                    state.record_action(
                                        action_type="tool_call",
                                        action_data=action_data,
                                        result=result.error,
                                        success=False,
                                        outcome=ActionOutcome.RETRYABLE_FAILURE,
                                        error_type=error_type.value,
                                        http_status=http_status,
                                        duration_ms=tool_duration_ms,
                                    )
                                    
                                    # Increment reflection counter
                                    state.increment_reflection_attempt(tool_name, tool_args)
                                    
                                    # Inject error into conversation for model correction
                                    # Add the tool call and its error result to messages
                                    current_messages.append({
                                        "role": "assistant",
                                        "content": "",
                                        "tool_calls": [{
                                            "id": tool_id,
                                            "type": "function",
                                            "function": {
                                                "name": tool_name,
                                                "arguments": json.dumps(tool_args) if tool_args else "{}",
                                            },
                                        }],
                                    })
                                    current_messages.append({
                                        "role": "tool",
                                        "tool_call_id": tool_id,
                                        "tool_name": tool_name,
                                        "content": f"Error: {result.error}\n\nPlease correct the parameters and try again.",
                                    })
                                    
                                    # Emit reflection event
                                    if self.config.stream_callback:
                                        await self.config.stream_callback({
                                            "type": "reflection_turn",
                                            "tool_name": tool_name,
                                            "error_type": error_type.value,
                                            "error": result.error,
                                            "step_number": step_num,
                                        })
                                    
                                    # Continue to next iteration of main loop (model will see error and try again)
                                    # Break out of this step so we don't append duplicate synthetic tool result entries.
                                    should_retry_step = True
                                    break
                                
                                # No reflection available - escalate to user
                                # Record the failure
                                state.record_action(
                                    action_type="tool_call",
                                    action_data=action_data,
                                    result=result.error,
                                    success=False,
                                    outcome=ActionOutcome.NON_RETRYABLE_FAILURE if action.terminal else ActionOutcome.RETRYABLE_FAILURE,
                                    error_type=error_type.value,
                                    http_status=http_status,
                                    duration_ms=tool_duration_ms,
                                )
                                
                                logger.info(f"Requesting user intervention for tool: {tool_name}")
                                
                                # P1 Fix: Use error-specific AskUserReason for targeted UI rendering
                                ask_reason = get_ask_user_reason_for_error_type(error_type.value)
                                remediation_options = get_remediation_options_for_error_type(
                                    error_type.value,
                                    tool_name=tool_name,
                                )
                                
                                if self.config.stream_callback:
                                    event = self._event_builder.ask_user(
                                        reason=ask_reason,
                                        title=f"Tool Error: {error_type.value.replace('_', ' ').title()}",
                                        message=action.remediation_prompt or action.reason,
                                        options=remediation_options,
                                        context={
                                            "tool_name": tool_name,
                                            "error": result.error,
                                            "error_type": error_type.value,
                                        },
                                        step_number=step_num,
                                    )
                                    await self.config.stream_callback(event.to_dict())
                                    # Persist token for durable resume
                                    await self._event_builder.persist_resume_token(event.payload.get("resume_token"))
                                
                                return AgenticResult(
                                    final_response=action.remediation_prompt or action.reason,
                                    steps=steps,
                                    total_steps=step_num,
                                    stopped_reason="ask_user",
                                    error=action.reason,
                                    metadata={
                                        "tool_name": tool_name,
                                        "remediation_prompt": action.remediation_prompt,
                                        "error_type": error_type.value,
                                        "run_id": self._event_builder.run_id,
                                    },
                                )

                            elif action.strategy == ErrorRecoveryStrategy.ABORT:
                                # Record terminal failure
                                state.record_action(
                                    action_type="tool_call",
                                    action_data=action_data,
                                    result=result.error,
                                    success=False,
                                    outcome=ActionOutcome.ABORTED,
                                    error_type=error_type.value,
                                    http_status=http_status,
                                    duration_ms=tool_duration_ms,
                                )
                                
                                logger.error(f"Aborting due to tool failure: {tool_name} - {action.reason}")
                                return AgenticResult(
                                    final_response=action.reason,
                                    steps=steps,
                                    total_steps=step_num,
                                    stopped_reason="error",
                                    error=action.reason,
                                    metadata={
                                        "error_type": error_type.value,
                                        "http_status": http_status,
                                        "action_history": state.get_action_history_summary(),
                                    },
                                )
                            
                            # SKIP strategy is no longer used for tool failures
                            # (only for circuit breaker/degraded mode, handled above)

                        # Record successful action
                        state.record_action(
                            action_type="tool_call",
                            action_data=action_data,
                            result=result.result,
                            success=result.success,
                            outcome=ActionOutcome.SUCCESS if result.success else ActionOutcome.RETRYABLE_FAILURE,
                            duration_ms=tool_duration_ms,
                        )

                        tool_executions.append({
                            "tool_call_id": tool_id,
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "result": result,
                            "duration_ms": tool_duration_ms,
                        })

                        logger.info(
                            f"Tool completed: {tool_name} (success={result.success}, duration={tool_duration_ms}ms)",
                            extra={
                                "tool_name": tool_name,
                                "success": result.success,
                                "duration_ms": tool_duration_ms,
                                "step": step_num,
                            }
                        )

                        # Task E1: Emit tool_result event with run_id correlation
                        if self.config.stream_callback:
                            # Prepare a safe preview of the result
                            result_preview = None
                            if result.result:
                                result_str = str(result.result)
                                result_preview = result_str[:200] + "..." if len(result_str) > 200 else result_str

                            event = self._event_builder.tool_result(
                                tool_name=tool_name,
                                step_number=step_num,
                                success=result.success,
                                duration_ms=tool_duration_ms,
                                result_preview=result_preview,
                                error=result.error if not result.success else None,
                            )
                            await self.config.stream_callback(event.to_dict())

                    except Exception as e:
                        tool_duration_ms = int((time.time() - tool_start_time) * 1000)
                        
                        # Classify the exception
                        error_type = self.error_handler.classify_error(str(e))
                        
                        logger.error(
                            f"Tool execution exception: {tool_name} - {e}",
                            extra={
                                "tool_name": tool_name,
                                "error": str(e),
                                "error_type": error_type.value,
                                "duration_ms": tool_duration_ms,
                                "step": step_num,
                            },
                            exc_info=True
                        )
                        
                        # Record the exception as a failure
                        state.record_action(
                            action_type="tool_call",
                            action_data=action_data,
                            result=str(e),
                            success=False,
                            outcome=ActionOutcome.NON_RETRYABLE_FAILURE if not is_error_retryable(error_type) else ActionOutcome.RETRYABLE_FAILURE,
                            error_type=error_type.value,
                            duration_ms=tool_duration_ms,
                        )
                        
                        tool_executions.append({
                            "tool_call_id": tool_id,
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "result": None,
                            "error": str(e),
                            "error_type": error_type.value,
                            "duration_ms": tool_duration_ms,
                        })

                        # Emit error event for tool execution failure
                        # P1 Fix: Use event builder for exception path to maintain contract
                        if self.config.stream_callback:
                            event = self._event_builder.tool_error(
                                tool_name=tool_name,
                                step_number=step_num,
                                error=str(e),
                                error_type=error_type.value,
                                retryable=is_error_retryable(error_type),
                                duration_ms=tool_duration_ms,
                                terminal=not is_error_retryable(error_type),
                            )
                            await self.config.stream_callback(event.to_dict())
                        
                        # For exceptions, check if we should abort
                        if not is_error_retryable(error_type):
                            return AgenticResult(
                                final_response="",
                                steps=steps,
                                total_steps=step_num,
                                stopped_reason="error",
                                error=f"Non-retryable error in tool {tool_name}: {e}",
                                metadata={
                                    "error_type": error_type.value,
                                    "action_history": state.get_action_history_summary(),
                                    "run_id": self._event_builder.run_id,
                                },
                            )

                # If retry flag set, repeat this step without recording
                if should_retry_step:
                    continue

                # Add tool execution step
                steps.append(AgenticStep(
                    step_number=step_num,
                    llm_response=llm_response,
                    tool_executions=tool_executions,
                    timestamp=step_start,
                ))

                # Verify plan step if planning enabled
                if plan and self.config.verify_plan_steps:
                    next_step = plan.get_next_step()
                    if next_step and next_step.step_number == step_num:
                        planner = AgentPlanner()

                        # Collect results from tool executions
                        step_result = {
                            "tools_executed": [ex["tool_name"] for ex in tool_executions],
                            "results": [
                                ex.get("result", {}).get("result") if ex.get("result") else ex.get("error")
                                for ex in tool_executions
                            ],
                        }

                        verified = await planner.verify_step(
                            step=next_step,
                            execution_result=step_result,
                            ollama_client=self.ollama,
                        )

                        if verified:
                            plan.mark_step_completed(next_step.step_number, step_result)
                            logger.info(
                                f"Plan step {next_step.step_number} verified as completed",
                                extra={"session_id": session_id, "step": next_step.step_number}
                            )
                        else:
                            plan.mark_step_failed(next_step.step_number, "Verification failed")
                            logger.warning(
                                f"Plan step {next_step.step_number} verification failed",
                                extra={"session_id": session_id, "step": next_step.step_number}
                            )

                        # Stream progress (Task E1: use builder for canonical contract)
                        if self.config.stream_callback:
                            event = self._event_builder.plan_progress(
                                progress=plan.get_progress(),
                                current_step=next_step.step_number,
                                current_step_description=next_step.description,
                                verified=verified,
                            )
                            await self.config.stream_callback(event.to_dict())

                # Add assistant message with tool calls to history
                current_messages.append({
                    "role": "assistant",
                    "content": "",  # Empty content when using tool calls
                    "tool_calls": tool_calls,
                })

                # Add tool results to message history
                for execution in tool_executions:
                    result = execution.get("result")
                    tool_content = self._format_tool_result(result)

                    current_messages.append({
                        "role": "tool",
                        # Ollama's tool protocol expects tool_name on tool-result messages.
                        # Keep tool_call_id too for compatibility with OpenAI-style tracing/validation.
                        "tool_name": execution["tool_name"],
                        "tool_call_id": execution["tool_call_id"],
                        "content": tool_content,
                    })

                # Continue loop - next iteration will call Ollama with updated messages
                continue

        # Max steps reached (Task 5M2.2: Use policy-driven max_steps)
        logger.warning(
            "Agentic workflow hit max steps",
            extra={
                "user_id": user.id,
                "session_id": session_id,
                "max_steps": max_steps,
                "budget_profile": loop_budget.profile.value,
            }
        )

        if self.config.stream_callback:
            event = self._event_builder.max_steps_reached(
                max_steps=max_steps,
                step_number=max_steps,
            )
            await self.config.stream_callback(event.to_dict())

            # Ask user if they want to continue
            continue_event = self._event_builder.ask_user(
                reason=AskUserReason.USER_INPUT_NEEDED,
                title="Maximum Steps Reached",
                message=(
                    f"The workflow has reached the maximum of {max_steps} steps "
                    f"(budget profile: {loop_budget.profile.value}) but hasn't completed yet.\n\n"
                    "Would you like to continue for more steps?"
                ),
                options=[
                    RemediationOption(
                        id="continue",
                        label="Continue",
                        description=f"Run for another {max_steps} steps",
                        action="continue",
                    ),
                    RemediationOption(
                        id="stop",
                        label="Stop here",
                        description="End the workflow with current progress",
                        action="abort",
                    ),
                ],
                context={
                    "completed_steps": max_steps,
                    "progress_so_far": steps[-1] if steps else None,
                },
                step_number=max_steps,
            )
            await self.config.stream_callback(continue_event.to_dict())
            await self._event_builder.persist_resume_token(continue_event.payload.get("resume_token"))

        # Task 2 (Phase 5): Log agent execution completion with skills context
        logger.info(
            "Agent execution completed",
            extra={
                "run_id": self.run_id,
                "session_id": session_id,
                "total_steps": max_steps,
                "skills_loaded": len(self.skills_context.get("skill_names", [])),
                "skill_names": self.skills_context.get("skill_names", []),
                "workflow_name": self.workflow_name,
            }
        )

        return AgenticResult(
            final_response=(
                f"Maximum steps ({max_steps}) reached (budget profile: {loop_budget.profile.value}). "
                f"Would you like me to continue? Reply 'continue' or 'yes' to proceed with more steps."
            ),
            steps=steps,
            total_steps=max_steps,
            stopped_reason="ask_user",  # Ask user to continue (budget_exhausted event already emitted at warning threshold)
            metadata={
                "run_id": self._event_builder.run_id,
                "can_continue": True,
                "budget_exhausted": True,  # Task 5M2.3: Mark budget exhaustion in telemetry
                "budget_profile": loop_budget.profile.value,
            },
        )

    async def _get_tool_definitions(self, user: User) -> List[Dict[str, Any]]:
        """
        Get tool definitions for user's role in Ollama format.
        
        Task B1: If use_tool_catalog is enabled, creates a run-scoped catalog
        for deterministic tool routing throughout the workflow.
        
        Task D1: If use_enhanced_catalog is enabled, uses EnhancedToolCatalog
        for workflow-aware filtering with rich metadata.
        
        Task D2: Applies workflow_type filter to reduce context overload.
        
        Refactor: Each run gets its own immutable catalog copy.

        Args:
            user: Current user

        Returns:
            List of tool definitions in OpenAI/Ollama format
        """
        # Task D1 + D2: Use enhanced catalog with workflow filtering
        if self.config.use_enhanced_catalog and self.config.use_tool_catalog:
            # Create fresh immutable catalog for this run
            self._run_catalog = await self.mcp.create_run_catalog(
                ttl_seconds=self.config.tool_catalog_ttl_seconds,
            )
            self._catalog_initialized = True

            # DEBUG: Check what tools the catalog has
            logger.info(
                f"[DEBUG MCP CATALOG] Run catalog created with {len(self._run_catalog.tools)} tools",
                extra={
                    "total_tools": len(self._run_catalog.tools),
                    "tool_names": [t.name for t in self._run_catalog.tools],
                    "servers": list(self._run_catalog.server_to_tools.keys()),
                    "server_health": self._run_catalog.server_health,
                }
            )

            # Create enhanced catalog from MCP tools with metadata enrichment
            self._enhanced_catalog = EnhancedToolCatalog.from_mcp_tools(
                self._run_catalog.tools,
                metadata_registry=get_default_metadata_registry(),
            )
            
            # Apply workflow exposure policy (Task D2)
            workflow = self.config.workflow_type or WorkflowType.GENERAL
            policy = get_policy_for_workflow(workflow)
            policy_filtered = policy.apply(self._enhanced_catalog)

            # Filter by role permissions (RBAC layer)
            allowed_tool_names = self.mcp.get_available_tools(user.role.value)

            # Handle wildcard: if "*" in allowlist, skip role filtering
            if "*" in allowed_tool_names:
                role_filtered = policy_filtered
            else:
                role_filtered = policy_filtered.include_only(allowed_tool_names)
            
            # Convert to Ollama format
            tool_definitions = role_filtered.to_ollama_format()

            # DEBUG: Check what we got from enhanced catalog
            logger.warning(
                f"[DEBUG ENHANCED] tool_definitions from enhanced catalog: {len(tool_definitions)} tools",
                extra={
                    "tool_count": len(tool_definitions),
                    "tool_names": [t["function"]["name"] for t in tool_definitions][:10] if tool_definitions else [],
                }
            )

            logger.info(
                f"Created enhanced catalog: {role_filtered.tool_count}/{self._enhanced_catalog.tool_count} tools "
                f"for role={user.role.value} workflow={workflow.value}",
                extra={
                    "total_tools": self._enhanced_catalog.tool_count,
                    "policy_filtered": policy_filtered.tool_count,
                    "role_filtered": role_filtered.tool_count,
                    "user_role": user.role.value,
                    "workflow_type": workflow.value,
                    "policy": policy.to_dict(),
                    "catalog_summary": role_filtered.to_summary_dict(),
                }
            )
        
        # Task B1: Use basic catalog (legacy path)
        elif self.config.use_tool_catalog:
            # Create fresh immutable catalog for this run
            self._run_catalog = await self.mcp.create_run_catalog(
                ttl_seconds=self.config.tool_catalog_ttl_seconds,
            )
            self._catalog_initialized = True  # Mark as initialized
            
            # Filter tools by role from catalog
            all_tools = self._run_catalog.tools
            allowed_tool_names = self.mcp.get_available_tools(user.role.value)

            # Handle wildcard: if "*" in allowlist, allow all tools
            if "*" in allowed_tool_names:
                allowed_tools = all_tools
            else:
                allowed_tools = [t for t in all_tools if t.name in allowed_tool_names]

            # DEBUG: Log tool filtering details
            logger.info(
                f"[DEBUG RBAC] Tool filtering for admin user:",
                extra={
                    "user_role": user.role.value,
                    "total_tools_in_catalog": len(all_tools),
                    "allowed_tool_names_count": len(allowed_tool_names),
                    "allowed_tool_names": allowed_tool_names[:10] if len(allowed_tool_names) < 100 else f"{allowed_tool_names[:10]}... (truncated, total: {len(allowed_tool_names)})",
                    "is_wildcard": "*" in allowed_tool_names,
                    "catalog_tool_names": [t.name for t in all_tools][:10],
                    "after_filter_count": len(allowed_tools),
                }
            )

            logger.info(
                f"Created run-scoped catalog: {len(allowed_tools)}/{len(all_tools)} tools for role {user.role.value}",
                extra={
                    "total_tools": len(all_tools),
                    "allowed_tools": len(allowed_tools),
                    "user_role": user.role.value,
                    "catalog_id": id(self._run_catalog),
                    "catalog_metrics": self.mcp.get_catalog_metrics(),
                }
            )
            
            # Convert to Ollama format
            tool_definitions = []
            for tool in allowed_tools:
                tool_definitions.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    }
                })
        else:
            # Legacy: Discover all tools (per-call)
            tools_by_server = await self.mcp.discover_all_tools()

            # Flatten and filter by user role
            all_tools: List[MCPTool] = []
            for tools in tools_by_server.values():
                all_tools.extend(tools)

            # Filter by role
            allowed_tool_names = self.mcp.get_available_tools(user.role.value)

            # Handle wildcard: if "*" in allowlist, allow all tools
            if "*" in allowed_tool_names:
                allowed_tools = all_tools
            else:
                allowed_tools = [t for t in all_tools if t.name in allowed_tool_names]
            
            # Convert to Ollama format
            tool_definitions = []
            for tool in allowed_tools:
                tool_definitions.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    }
                })

        # Add bash escape hatch tool only when explicitly enabled.
        # In native/Runpod modes without a worker service, probing worker DNS can
        # add latency and noisy failures on every chat turn.
        bash_tool_enabled = os.environ.get("ENABLE_BASH_TOOL", "false").lower() == "true"
        if bash_tool_enabled and await self.bash_tool.is_available():
            tool_definitions.append(BashTool.get_tool_definition())
            logger.info("Bash tool added to available tools (ENABLE_BASH_TOOL=true)")
        elif bash_tool_enabled:
            logger.warning("Bash tool enabled but worker service not reachable")
        else:
            logger.info("Bash tool disabled (set ENABLE_BASH_TOOL=true to enable)")

        # DEBUG: Check tool_definitions before adding SimpleTool
        logger.warning(
            f"[DEBUG BEFORE SIMPLE] tool_definitions count before SimpleTool: {len(tool_definitions)}",
            extra={
                "count_before_simple": len(tool_definitions),
                "tool_names_before": [t["function"]["name"] for t in tool_definitions][:10] if tool_definitions else [],
            }
        )

        # Add simple built-in tools (always available)
        tool_definitions.extend(SimpleTool.get_tool_definitions())
        logger.info(f"Added {len(SimpleTool.get_tool_definitions())} simple built-in tools")

        # DEBUG: Check final count
        final_tool_names = [t["function"]["name"] for t in tool_definitions]
        logger.warning(f"[DEBUG FINAL] Final tool_definitions count: {len(tool_definitions)}")
        logger.warning(f"[DEBUG FINAL] Tool names: {final_tool_names}")

        return tool_definitions

    async def _requires_approval(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """
        Check if tool requires user approval.

        Uses a multi-tier system:
        1. Check tool's approval policy (SAFE, SENSITIVE, DANGEROUS, CONTEXTUAL)
        2. For SAFE: always return False
        3. For SENSITIVE: check session approval cache, return False if cached
        4. For DANGEROUS: always return True
        5. For CONTEXTUAL: evaluate based on arguments, then apply logic
        6. Fallback: use legacy write pattern matching

        Args:
            tool_name: Name of tool
            arguments: Tool arguments

        Returns:
            True if approval required
        """
        # 1. Check tool's approval policy if lookup function provided
        if self.config.tool_approval_policy_lookup:
            policy = self.config.tool_approval_policy_lookup(tool_name)
            
            if policy == "safe":
                return False
            
            if policy == "dangerous":
                return True
            
            if policy in ("sensitive", "contextual"):
                # Check session approval cache if checker provided
                if self.config.session_approval_checker and self._session_id:
                    is_approved = await self.config.session_approval_checker(
                        self._session_id, tool_name, arguments
                    )
                    if is_approved:
                        logger.debug(
                            f"Tool {tool_name} already approved for session {self._session_id}"
                        )
                        return False
                # Not in cache, approval required
                return True
        
        # 2. Legacy fallback: pattern-based detection for write operations
        write_patterns = [
            "create", "update", "delete", "write", "modify",
            "insert", "remove", "drop", "set", "patch"
        ]

        tool_lower = tool_name.lower()
        return any(pattern in tool_lower for pattern in write_patterns)

    def _format_tool_result(self, result: Any) -> str:
        """
        Format tool result for Ollama.

        Args:
            result: MCPToolResult or None

        Returns:
            Formatted string for Ollama
        """
        if result is None:
            return json.dumps({"error": "No result", "success": False})

        if result.success:
            # Format successful result
            if isinstance(result.result, dict):
                return json.dumps(result.result)
            else:
                return str(result.result)
        else:
            # Format error
            return json.dumps({
                "error": result.error,
                "success": False
            })

    async def _get_server_for_tool(self, tool_name: str) -> Optional[str]:
        """
        Get the MCP server name that provides a given tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Server name or None if not found
        """
        try:
            server_name, _ = await self.mcp._find_tool(tool_name)
            return server_name
        except Exception:
            return None

    async def _check_skill_match(
        self, messages: List[Dict[str, Any]], user: User
    ) -> Optional[Dict[str, Any]]:
        """
        Check if the user's message matches any skill intent pattern and execute if matched.

        Task 4 (Phase 5): Skill detection and invocation integration.

        Args:
            messages: Conversation history
            user: Current user

        Returns:
            Skill execution result if matched and executed, None if no match
        """
        self.logger.info("=== 🎯 SKILL CHECK START ===")
        self.logger.info(f"Session exists: {self.session is not None}, Tenant ID: {self.tenant_id}")
        self.logger.info(f"Skills context: {list(self.skills_context.keys()) if self.skills_context else 'None'}")

        # Skip if no session or tenant_id
        if not (self.session and self.tenant_id):
            self.logger.warning("⚠️ Skill check skipped: no session or tenant_id")
            return None

        # Skip if no skills loaded
        if not self.skills_context or not self.skills_context.get("skills"):
            self.logger.warning(f"⚠️ Skill check skipped: no skills in context (context={self.skills_context})")
            return None

        # Get the last user message
        last_user_message = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content")
                break

        if not last_user_message:
            return None

        # Try to match the message to a skill
        from app.services.skill_discovery import SkillDiscoveryService
        from app.utils.skill_invoker import invoke_skill

        try:
            self.logger.info(f"🔍 Attempting to match message: '{last_user_message[:100]}'")
            discovery_service = SkillDiscoveryService(self.session)
            matched_skill = discovery_service.match_skill_by_intent(
                user_message=last_user_message,
                tenant_id=self.tenant_id
            )

            if not matched_skill:
                self.logger.info("❌ No skill matched")
                return None

            self.logger.info(f"✅ Skill matched: {matched_skill.skill_name} (id={matched_skill.id})")

            # Skill matched - execute it
            self.logger.info(
                f"Skill matched: {matched_skill.skill_name}",
                extra={
                    "skill_name": matched_skill.skill_name,
                    "skill_id": matched_skill.id,
                    "tenant_id": self.tenant_id,
                    "user_message": last_user_message[:100],
                }
            )

            # Stream skill execution event if callback available
            if self.config.stream_callback:
                event = self._event_builder.workflow_start(
                    available_tools=0,
                    max_steps=1,
                    workflow_type=f"skill:{matched_skill.skill_name}",
                    model=None,
                )
                await self.config.stream_callback(event.to_dict())

            # Build execution context
            execution_context = {
                "user_message": last_user_message,
                "user_id": user.id,
                "session_id": self._session_id,
                "run_id": self.run_id,
                "skill_id": matched_skill.id,
                "skill_config": matched_skill.skill_data or {},
            }

            # Build isolated skill execution context
            skill_instructions = self._build_skill_instructions(matched_skill, execution_context)

            # Create isolated context: ONLY skill instructions + user message
            skill_execution_messages = [
                {"role": "system", "content": skill_instructions},
                {"role": "user", "content": last_user_message}
            ]

            # Get available MCP tools
            available_tools = self._get_mcp_tools()
            self.logger.info(f"Skill execution with {len(available_tools)} available tools")

            # Execute skill in isolated mode (no conversation history)
            skill_result = await self._execute_skill_workflow(
                messages=skill_execution_messages,
                available_tools=available_tools,
                skill_name=matched_skill.skill_name
            )

            self.logger.info(
                f"✅ Skill execution completed: {matched_skill.skill_name}",
                extra={
                    "skill_id": matched_skill.id,
                    "success": skill_result["success"],
                    "tools_used": len(skill_result.get("tool_calls", []))
                }
            )

            # Return skill execution result (not None)
            return skill_result

        except Exception as e:
            self.logger.error(
                f"Error checking skill match: {e}",
                extra={
                    "tenant_id": self.tenant_id,
                    "error": str(e),
                    "last_user_message": last_user_message[:100] if last_user_message else None,
                },
                exc_info=True
            )
            return None

    def _build_skill_instructions(self, skill, context: dict) -> str:
        """
        Build execution instructions for a matched skill.

        The instructions tell the LLM how to execute the skill using available MCP tools.

        Args:
            skill: The matched TenantSkill object
            context: Execution context with user_message, user_id, etc.

        Returns:
            String containing execution instructions for the LLM
        """
        import json

        skill_data = skill.skill_data or {}
        user_message = context.get("user_message", "")

        instructions = f"""
# MANDATORY SKILL EXECUTION: {skill.skill_name}

⚠️ **CRITICAL**: You MUST execute this skill immediately. Do NOT ask clarifying questions first. Start execution NOW.

**Matched Skill:** {skill.skill_name}
**Description:** {skill.description or 'No description provided'}
**User Request:** {user_message}

**Skill Configuration:**
```json
{json.dumps(skill_data, indent=2)}
```

## 🚀 IMMEDIATE EXECUTION REQUIRED

You have been matched to this skill based on the user's intent. You MUST begin execution immediately using the available MCP tools.

**Available MCP Tools:**
- `run_sql` - Execute SELECT queries on BRS database
- `call_api` - Make HTTP requests to BRS API endpoints
- `call_internal_api` - Call internal agent API endpoints
- Other registered MCP tools

## 📋 REINSTATE_USER Workflow (Execute These Steps NOW)

**Step 1: Extract Username**
- Parse the user message: "{user_message}"
- Extract the username (look for text after "reinstate user" or "reinstate")
- The username is the account to be reinstated (currently has _deleted suffix or needs to be restored)

**Step 2: Query User Details**
- IMMEDIATELY execute: `run_sql` with query:
  ```sql
  SELECT uid, username, email, name, usergroup FROM fe_users WHERE username LIKE '%extracted_username%' OR username = 'extracted_username_deleted' LIMIT 5;
  ```
- If no results, query for similar usernames to help user identify the correct account

**Step 3: Identify Target User**
- From query results, identify the user to reinstate
- If username already has "_deleted" suffix, that's the one to restore
- If username doesn't exist, check if there's a "username_deleted" version

**Step 4: Check if Username is Available**
- Execute: `run_sql` with query:
  ```sql
  SELECT uid, username FROM fe_users WHERE username = 'target_username_without_deleted';
  ```
- If username IS available (no results): Proceed to rename step
- If username NOT available (user exists): The account is already active, inform user

**Step 5: Rename Deleted User (Restore Original Username)**
- Use `call_api` tool to update the username from "username_deleted" back to "username"
- Request details:
  - method: "PATCH"
  - endpoint: "/api/admin/users/{{uid}}"
  - body: {{"username": "original_username"}}
- IMPORTANT: Use call_api, NOT run_sql (writes must go through API)

**Step 6: Verify Restoration**
- Execute: `run_sql` query:
  ```sql
  SELECT uid, username, email, name FROM fe_users WHERE uid = {{restored_uid}};
  ```
- Confirm username no longer has "_deleted" suffix
- Report success to user with restored user details

## ⚠️ EXECUTION RULES

1. **DO NOT ask for clarification** - Extract parameters from the user message and begin execution
2. **DO use error handling** - If a step fails, report the error and suggest solutions
3. **DO verify each step** - After each MCP tool call, confirm the result before proceeding
4. **DO report progress** - Keep user informed of each step as you execute it
5. **DO use call_api for writes** - Never use run_sql for UPDATE/INSERT/DELETE operations

## 🎯 START EXECUTION NOW

Begin with Step 1 immediately. Do not respond with questions or requests for more information first.

## 🎯 START EXECUTION NOW

Begin with Step 1 immediately. Do not respond with questions or requests for more information first.
"""

        return instructions.strip()

    async def _execute_skill_workflow(
        self,
        messages: List[Dict[str, Any]],
        available_tools: List[Dict[str, Any]],
        skill_name: str,
        max_iterations: int = 10
    ) -> Dict[str, Any]:
        """
        Execute skill workflow with isolated context (no conversation history).

        This method forces deterministic skill execution by:
        1. Calling LLM with only skill instructions and user message
        2. Processing tool calls via MCP registry
        3. Handling multi-turn execution (LLM → tool → LLM → tool...)

        Args:
            messages: Isolated context [system instruction, user message]
            available_tools: MCP tools in Ollama format
            skill_name: Name of the skill being executed
            max_iterations: Maximum tool execution loops (default 10)

        Returns:
            {
                "success": bool,
                "skill_name": str,
                "message": str,  # Final LLM response
                "tool_calls": List[Dict],  # All tool calls made
                "tool_results": List[Dict]  # Results from all tools
            }
        """
        self.logger.info(f"🚀 Starting skill execution: {skill_name} (isolated context)")

        iteration = 0
        tool_call_history = []
        tool_results_history = []

        while iteration < max_iterations:
            try:
                self.logger.info(f"Skill execution iteration {iteration + 1}/{max_iterations}")

                # Call LLM with current context
                llm_response = await self.ollama.generate_chat_completion_with_tools(
                    messages=messages,
                    tools=available_tools if available_tools else None,
                    model="haiku"  # Use fast model for skill execution
                )

                # Extract tool calls from response
                # Response format: {"type": "tool_calls", "tool_calls": [...]} or {"type": "text", "content": "..."}
                if llm_response.get("type") == "text":
                    # No tool calls - final response
                    final_content = llm_response.get("content", "")
                    self.logger.info(f"✅ Skill execution complete: {skill_name}")
                    return {
                        "success": True,
                        "skill_name": skill_name,
                        "message": final_content,
                        "tool_calls": tool_call_history,
                        "tool_results": tool_results_history
                    }

                tool_calls = llm_response.get("tool_calls", [])

                self.logger.info(f"Processing {len(tool_calls)} tool calls")

                # Execute each tool call via MCP
                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool_args_str = tool_call["function"]["arguments"]

                    try:
                        tool_args = json.loads(tool_args_str)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Failed to parse tool arguments: {tool_args_str}", exc_info=True)
                        tool_call_history.append({
                            "tool": tool_name,
                            "arguments": tool_args_str
                        })
                        tool_results_history.append({
                            "tool": tool_name,
                            "success": False,
                            "result": f"Invalid JSON arguments: {str(e)}"
                        })
                        continue

                    self.logger.info(f"Calling tool: {tool_name} with args: {tool_args}")

                    # Call MCP tool
                    try:
                        mcp_result = await self.mcp.execute_tool(
                            tool_name=tool_name,
                            arguments=tool_args,
                            user=self.user
                        )

                        tool_call_history.append({
                            "tool": tool_name,
                            "arguments": tool_args
                        })

                        if mcp_result.success:
                            self.logger.info(f"✅ Tool {tool_name} succeeded")
                            tool_results_history.append({
                                "tool": tool_name,
                                "success": True,
                                "result": mcp_result.result
                            })
                            tool_result_content = json.dumps(mcp_result.result)
                        else:
                            self.logger.warning(f"⚠️ Tool {tool_name} failed: {mcp_result.error}")
                            tool_results_history.append({
                                "tool": tool_name,
                                "success": False,
                                "result": mcp_result.error
                            })
                            tool_result_content = mcp_result.error

                        # Add tool result to conversation for next LLM call
                        messages.append({
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [tool_call]
                        })
                        messages.append({
                            "role": "tool",
                            "content": tool_result_content
                        })

                    except Exception as e:
                        self.logger.error(f"Exception calling tool {tool_name}: {e}", exc_info=True)
                        tool_call_history.append({
                            "tool": tool_name,
                            "arguments": tool_args
                        })
                        tool_results_history.append({
                            "tool": tool_name,
                            "success": False,
                            "result": f"Tool execution error: {str(e)}"
                        })
                        # Still add to messages so LLM can see the error
                        messages.append({
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [tool_call]
                        })
                        messages.append({
                            "role": "tool",
                            "content": f"Error: {str(e)}"
                        })

                iteration += 1

            except Exception as e:
                self.logger.error(f"Error in skill execution loop: {e}", exc_info=True)
                return {
                    "success": False,
                    "skill_name": skill_name,
                    "message": f"Skill execution error: {str(e)}",
                    "tool_calls": tool_call_history,
                    "tool_results": tool_results_history
                }

        # Max iterations reached
        self.logger.warning(f"⚠️ Skill execution exceeded max iterations ({max_iterations})")
        return {
            "success": False,
            "skill_name": skill_name,
            "message": f"Skill execution exceeded maximum iterations ({max_iterations}). Partial results returned.",
            "tool_calls": tool_call_history,
            "tool_results": tool_results_history
        }

    def _format_skill_response(self, skill_result: Dict[str, Any]) -> str:
        """
        Format skill execution result as user-facing message.

        Args:
            skill_result: Result from _execute_skill_workflow()

        Returns:
            Formatted markdown string for display to user
        """
        if not skill_result["success"]:
            response = f"❌ **Skill execution failed: {skill_result['skill_name']}**\n\n"
            response += f"{skill_result['message']}\n\n"

            if skill_result.get("tool_calls"):
                response += "### Tools Attempted:\n"
                for i, tool_call in enumerate(skill_result['tool_calls'], 1):
                    tool_name = tool_call['tool']
                    response += f"{i}. `{tool_name}`\n"

            return response

        # Success case
        response_parts = [
            f"✅ **Executed skill: {skill_result['skill_name']}**",
            "",
            skill_result['message'],
            ""
        ]

        if skill_result.get("tool_calls"):
            response_parts.append("### Tools Used:")
            for i, tool_call in enumerate(skill_result['tool_calls'], 1):
                tool_name = tool_call['tool']
                response_parts.append(f"{i}. `{tool_name}`")

        return "\n".join(response_parts)

    def _get_mcp_tools(self) -> List[Dict[str, Any]]:
        """
        Get list of available MCP tools in Ollama tool format.

        Returns:
            List of tool definitions compatible with Ollama chat API
        """
        try:
            # Get tools from MCP registry (stored as self.mcp)
            if not hasattr(self, 'mcp') or self.mcp is None:
                self.logger.warning("No MCP registry available for skill execution")
                return []

            # Get the tool catalog
            if hasattr(self, '_run_catalog') and self._run_catalog is not None:
                tools = self._run_catalog.tools
                self.logger.info(f"Retrieved {len(tools)} tools from run catalog")

                # Convert MCPTool objects to dicts for Ollama API
                tool_dicts = []
                for tool in tools:
                    if isinstance(tool, dict):
                        tool_dicts.append(tool)
                    else:
                        # Convert dataclass to dict
                        tool_dicts.append({
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description,
                                "parameters": tool.input_schema
                            }
                        })

                return tool_dicts

            self.logger.warning("No run catalog available, tools may be empty")
            return []

        except Exception as e:
            self.logger.error(f"Error getting MCP tools: {e}", exc_info=True)
            return []
