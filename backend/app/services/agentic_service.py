"""Agentic workflow orchestration with tool calling and full harness."""
from typing import List, Dict, Any, Optional, Callable, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import asyncio
import json

from app.services.ollama import OllamaClient, OllamaError
from app.services.mcp_registry import MCPToolRegistry
from app.services.mcp_client import MCPTool
from app.services.agent_state import AgentState
from app.services.error_handler import (
    AgentErrorHandler,
    ErrorType,
    ErrorContext,
    ErrorRecoveryStrategy
)
from app.services.agent_planner import AgentPlanner, TaskPlan
from app.services.bash_tool import BashTool
from app.services.simple_tools import SimpleTool
from app.models.models import User

if TYPE_CHECKING:
    from app.services.rate_limiter import RateLimiter
    from app.services.mcp_health import MCPHealthChecker

logger = logging.getLogger(__name__)


@dataclass
class AgenticConfig:
    """Configuration for agentic loop."""
    max_steps: int = 10
    require_approval_for_write: bool = False
    timeout_seconds: int = 120
    enable_loop_detection: bool = True
    loop_window_size: int = 3
    enable_planning: bool = False  # Simplified for MVP
    verify_plan_steps: bool = False
    stream_callback: Optional[Callable[[Dict[str, Any]], Any]] = None


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
    stopped_reason: str  # "completed", "max_steps", "error", "approval_needed", "loop_detected", "timeout"
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AgenticService:
    """Orchestrates agentic workflow with full harness."""

    def __init__(
        self,
        ollama_client: OllamaClient,
        mcp_registry: MCPToolRegistry,
        config: AgenticConfig,
        rate_limiter: Optional["RateLimiter"] = None,
        health_checker: Optional["MCPHealthChecker"] = None,
        run_id: Optional[str] = None,
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
        """
        self.ollama = ollama_client
        self.mcp = mcp_registry
        self.config = config
        self.rate_limiter = rate_limiter
        self.health_checker = health_checker
        self.run_id = run_id
        self.error_handler = AgentErrorHandler(max_retries=3)
        self.bash_tool = BashTool(run_id=run_id)  # Initialize bash escape hatch with run_id
        self.simple_tools = SimpleTool()  # Initialize simple built-in tools

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
        steps: List[AgenticStep] = []
        current_messages = messages.copy()
        retry_count: Dict[str, int] = {}  # Track retries per tool

        # Initialize state management
        state = AgentState(session_id=session_id, current_step=0)

        # Get available tools for user's role
        available_tools = await self._get_tool_definitions(user)

        # Add system prompt for tool usage (required for qwen2.5-coder and similar models)
        if available_tools and not any(msg.get("role") == "system" for msg in current_messages):
            tool_names = [tool["function"]["name"] for tool in available_tools]
            system_prompt = f"""You are a helpful AI assistant with access to tools. When the user's request requires external actions, data retrieval, or computation, you MUST use the available tools by making function calls.

Available tools: {', '.join(tool_names)}

To use a tool, respond with a function call in the format expected by the API. Do NOT describe what you would do - actually call the tool.

When you receive tool results, use them to formulate your final response to the user."""

            current_messages.insert(0, {
                "role": "system",
                "content": system_prompt
            })

        logger.info(
            "Starting agentic workflow",
            extra={
                "user_id": user.id,
                "user_role": user.role.value,
                "session_id": session_id,
                "available_tools": len(available_tools),
                "max_steps": self.config.max_steps,
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
                await self.config.stream_callback({
                    "type": "plan_created",
                    "steps": [s.description for s in plan.steps],
                })

        # Emit start event
        if self.config.stream_callback:
            await self.config.stream_callback({
                "type": "workflow_start",
                "available_tools": len(available_tools),
                "max_steps": self.config.max_steps,
            })

        # Main control loop
        for step_num in range(1, self.config.max_steps + 1):
            state.current_step = step_num
            step_start = datetime.now(timezone.utc)

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
                    await self.config.stream_callback({
                        "type": "loop_detected",
                        "step": step_num,
                    })

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
                        await self.config.stream_callback({
                            "type": "low_confidence",
                            "confidence": confidence,
                        })

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
                    await self.config.stream_callback({
                        "type": "workflow_complete",
                        "total_steps": step_num,
                    })

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

                logger.info(
                    f"Step {step_num}: Executing {len(tool_calls)} tool calls",
                    extra={
                        "step": step_num,
                        "tool_count": len(tool_calls),
                        "tools": [tc.get("function", {}).get("name") for tc in tool_calls],
                    }
                )

                if self.config.stream_callback:
                    await self.config.stream_callback({
                        "type": "step",
                        "step_number": step_num,
                        "action": "tool_calls",
                        "tool_count": len(tool_calls),
                    })

                should_retry_step = False  # Flag to break out of tool loop for retry

                for tool_call in tool_calls:
                    tool_name = tool_call.get("function", {}).get("name")
                    tool_args = tool_call.get("function", {}).get("arguments", {})
                    tool_id = tool_call.get("id", "unknown")

                    # Check if approval needed for write operations
                    if self.config.require_approval_for_write and await self._requires_approval(tool_name, tool_args):
                        logger.info(f"Approval required for tool: {tool_name}")

                        if self.config.stream_callback:
                            await self.config.stream_callback({
                                "type": "approval_request",
                                "tool_name": tool_name,
                                "arguments": tool_args,
                            })

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
                                }
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
                                tool_executions.append({
                                    "tool_call_id": tool_id,
                                    "tool_name": tool_name,
                                    "arguments": tool_args,
                                    "result": None,
                                    "error": tool_msg,
                                    "degraded": True,
                                })
                                continue

                    # Execute tool via MCP registry with error handling
                    retry_key = f"{step_num}:{tool_name}"
                    current_retries = retry_count.get(retry_key, 0)

                    try:
                        # Record tool call for rate limiting
                        if self.rate_limiter:
                            await self.rate_limiter.record_tool_call(user.id)

                        # Handle simple built-in tools first
                        simple_tool_names = ["store_memory", "retrieve_memory", "list_memory_keys", "calculate"]
                        if tool_name in simple_tool_names:
                            from app.services.mcp_client import MCPToolResult
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
                            result = await self.mcp.execute_tool(
                                tool_name=tool_name,
                                arguments=tool_args,
                                user=user,
                            )

                        # Update circuit breaker on success/failure
                        if self.rate_limiter and server_name:
                            if result.success:
                                await self.rate_limiter.record_circuit_success(server_name)
                            else:
                                await self.rate_limiter.record_circuit_failure(server_name)

                        # Handle tool failure with recovery strategy
                        if not result.success:
                            context = ErrorContext(
                                error_type=ErrorType.TOOL_FAILURE,
                                step_number=step_num,
                                tool_name=tool_name,
                                error_message=result.error or "Unknown error",
                                retry_count=current_retries,
                                metadata={},
                            )

                            action = self.error_handler.decide_recovery(context)

                            if action.strategy == ErrorRecoveryStrategy.RETRY:
                                # Use rate limiter's backoff if available
                                if self.rate_limiter and self.rate_limiter.should_retry(current_retries):
                                    delay = await self.rate_limiter.wait_with_backoff(current_retries)
                                    logger.info(f"Retrying tool: {tool_name} (attempt {current_retries + 1}, delay {delay:.2f}s)")
                                elif action.retry_delay_seconds:
                                    await asyncio.sleep(action.retry_delay_seconds)
                                    logger.info(f"Retrying tool: {tool_name} (attempt {current_retries + 1})")
                                else:
                                    logger.info(f"Retrying tool: {tool_name} (attempt {current_retries + 1})")

                                retry_count[retry_key] = current_retries + 1

                                # Set flag to retry entire step (break out of tool loop)
                                should_retry_step = True
                                break

                            elif action.strategy == ErrorRecoveryStrategy.FALLBACK:
                                logger.info(f"Using fallback tool: {action.fallback_tool}")

                                # Execute fallback tool
                                result = await self.mcp.execute_tool(
                                    tool_name=action.fallback_tool,
                                    arguments=tool_args,
                                    user=user,
                                )

                            elif action.strategy == ErrorRecoveryStrategy.SKIP:
                                logger.warning(f"Skipping failed tool: {tool_name}")
                                tool_executions.append({
                                    "tool_call_id": tool_id,
                                    "tool_name": tool_name,
                                    "arguments": tool_args,
                                    "result": result,
                                    "skipped": True,
                                })
                                continue

                            elif action.strategy == ErrorRecoveryStrategy.ABORT:
                                logger.error(f"Aborting due to tool failure: {tool_name}")
                                return AgenticResult(
                                    final_response="",
                                    steps=steps,
                                    total_steps=step_num,
                                    stopped_reason="error",
                                    error=action.reason,
                                )

                        # Record successful action
                        state.record_action(
                            action_type="tool_call",
                            action_data={"name": tool_name, "args": tool_args},
                            result=result.result,
                            success=result.success,
                        )

                        tool_executions.append({
                            "tool_call_id": tool_id,
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "result": result,
                        })

                        if self.config.stream_callback:
                            await self.config.stream_callback({
                                "type": "tool_result",
                                "tool_name": tool_name,
                                "success": result.success,
                            })

                    except Exception as e:
                        logger.error(f"Tool execution exception: {e}")
                        tool_executions.append({
                            "tool_call_id": tool_id,
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "result": None,
                            "error": str(e),
                        })

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

                        # Stream progress
                        if self.config.stream_callback:
                            await self.config.stream_callback({
                                "type": "plan_progress",
                                "progress": plan.get_progress(),
                                "current_step": next_step.description,
                                "verified": verified,
                            })

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
                        "tool_call_id": execution["tool_call_id"],
                        "content": tool_content,
                    })

                # Continue loop - next iteration will call Ollama with updated messages
                continue

        # Max steps reached
        logger.warning(
            "Agentic workflow hit max steps",
            extra={
                "user_id": user.id,
                "session_id": session_id,
                "max_steps": self.config.max_steps,
            }
        )

        if self.config.stream_callback:
            await self.config.stream_callback({
                "type": "max_steps_reached",
                "max_steps": self.config.max_steps,
            })

        return AgenticResult(
            final_response="Maximum steps reached. Workflow incomplete.",
            steps=steps,
            total_steps=self.config.max_steps,
            stopped_reason="max_steps",
        )

    async def _get_tool_definitions(self, user: User) -> List[Dict[str, Any]]:
        """
        Get tool definitions for user's role in Ollama format.

        Args:
            user: Current user

        Returns:
            List of tool definitions in OpenAI/Ollama format
        """
        # Discover all tools (cached)
        tools_by_server = await self.mcp.discover_all_tools()

        # Flatten and filter by user role
        all_tools: List[MCPTool] = []
        for tools in tools_by_server.values():
            all_tools.extend(tools)

        # Filter by role
        allowed_tool_names = self.mcp.get_available_tools(user.role.value)
        allowed_tools = [t for t in all_tools if t.name in allowed_tool_names]

        # Convert to Ollama format (OpenAI function calling format)
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

        # Add bash escape hatch tool (only if worker available)
        if await self.bash_tool.is_available():
            tool_definitions.append(BashTool.get_tool_definition())
            logger.info("Bash tool added to available tools")
        else:
            logger.warning("Bash tool unavailable - worker service not reachable")

        # Add simple built-in tools (always available)
        tool_definitions.extend(SimpleTool.get_tool_definitions())
        logger.info(f"Added {len(SimpleTool.get_tool_definitions())} simple built-in tools")

        return tool_definitions

    async def _requires_approval(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """
        Check if tool requires user approval (write operations).

        Args:
            tool_name: Name of tool
            arguments: Tool arguments

        Returns:
            True if approval required
        """
        # Define write tool patterns
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
