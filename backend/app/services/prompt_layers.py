"""Prompt layering and context assembly service.

Based on openclaude architecture:
- User context: prepended to messages (static, cached)
- System prompt: base behavioral layer (static, cached)
- System context: appended to system (dynamic)
"""
from typing import Dict, List, Optional, Any
from datetime import datetime


# ==============================================================================
# Base System Layer
# ==============================================================================

BASE_SYSTEM_PROMPT = """You are an AI assistant integrated into a hosted agent platform.

Your role:
- Help users with their workflows
- Follow tool usage policies
- Respect approval and role-based access control
- Provide clear, actionable responses

Important constraints:
- Only use tools that are available to the current user's role
- Do not attempt to bypass approval or permission checks
- If a workflow requires admin privileges, inform the user clearly"""


# ==============================================================================
# Role/Environment Layer
# ==============================================================================

def get_role_layer(user: Any) -> str:
    """Generate role-specific context based on user permissions."""
    role_context = f"""
# User Profile
- Role: {user.role.value}
- Approval Status: {user.approval_status.value}
- User ID: {user.id}
- Email: {user.email}
"""

    if user.role.value == "admin":
        role_context += """
## Admin Capabilities
- Full access to all tools
- Can approve/reject users
- Can view all sessions
- Can modify system configuration
"""
    elif user.approval_status.value == "approved":
        role_context += """
## User Capabilities
- Access to chat and workflow tools
- Can create and manage own sessions
- Standard tool access
"""
    else:
        role_context += """
## Limited Access
- User is not yet approved
- Cannot access workflow tools
- Contact administrator for approval
"""

    return role_context.strip()


# ==============================================================================
# Workflow/Rule Layer
# ==============================================================================

def get_workflow_layer(workflow_type: Optional[str] = None) -> str:
    """Generate workflow-specific instructions and rules."""
    if not workflow_type:
        return """
# General Workflow
- Respond to user queries naturally
- Use available tools when appropriate
- Provide clear explanations
"""

    # Future: Add specific workflow types
    workflows = {
        "code_review": """
# Code Review Workflow
- Analyze code structure and patterns
- Identify potential issues
- Suggest improvements
- Follow best practices
""",
        "debugging": """
# Debugging Workflow
- Reproduce the issue
- Identify root cause
- Propose fix
- Verify solution
""",
    }

    return workflows.get(workflow_type, "# Workflow: " + workflow_type)


# ==============================================================================
# Tool Policy Layer
# ==============================================================================

def get_tool_policy_layer(user: Any, available_tools: List[str]) -> str:
    """Generate tool usage policies based on user role and available tools."""
    policy = """
# Tool Usage Policy
"""

    if not available_tools:
        policy += "- No tools currently available\n"
        return policy

    policy += f"- Available tools: {', '.join(available_tools)}\n"

    if user.role.value == "admin":
        policy += """- Full tool access granted
- Can execute administrative commands
- Can access sensitive operations
"""
    else:
        policy += """- Standard tool access
- Administrative tools restricted
- Sensitive operations require approval
"""

    return policy.strip()


# ==============================================================================
# Context Assembly
# ==============================================================================

def assemble_system_prompt(
    user: Any,
    workflow_type: Optional[str] = None,
    available_tools: Optional[List[str]] = None,
    additional_context: Optional[Dict[str, str]] = None,
) -> List[str]:
    """
    Assemble full system prompt with deterministic layer ordering.

    Layer order (following openclaude pattern):
    1. Base system prompt (static, cacheable)
    2. Role/environment layer
    3. Workflow/rule layer
    4. Tool policy layer
    5. Dynamic context (timestamp, session state)

    Args:
        user: Current authenticated user
        workflow_type: Optional workflow identifier
        available_tools: List of tool names available to user
        additional_context: Additional key-value context pairs

    Returns:
        List of system prompt sections
    """
    tools = available_tools or []

    # Static layers (cacheable)
    prompt_layers = [
        BASE_SYSTEM_PROMPT,
        get_role_layer(user),
        get_workflow_layer(workflow_type),
        get_tool_policy_layer(user, tools),
    ]

    # Dynamic context (changes per request)
    dynamic_context = _build_dynamic_context(additional_context)
    if dynamic_context:
        prompt_layers.append(dynamic_context)

    return [layer.strip() for layer in prompt_layers if layer.strip()]


def _build_dynamic_context(context: Optional[Dict[str, str]] = None) -> str:
    """Build dynamic context section with timestamp and custom fields."""
    # Only add dynamic context if there's actual context to add
    if not context:
        return ""

    parts = [
        "# Session Context",
        f"- Current Time: {datetime.utcnow().isoformat()}Z",
    ]

    for key, value in context.items():
        parts.append(f"- {key}: {value}")

    return "\n".join(parts)


# ==============================================================================
# User Context (prepended to messages)
# ==============================================================================

def get_user_context() -> Dict[str, str]:
    """
    Get user context to prepend to conversation messages.
    Following openclaude pattern of static, cacheable context.

    Returns:
        Dictionary of context key-value pairs
    """
    return {
        "currentDate": f"Today's date is {datetime.utcnow().strftime('%Y-%m-%d')}",
        # Future: Add project docs, memory, etc.
    }


# ==============================================================================
# System Context (appended to system prompt)
# ==============================================================================

def get_system_context(session_id: Optional[int] = None) -> Dict[str, str]:
    """
    Get system context to append to system prompt.
    Dynamic state that changes during conversation.

    Returns:
        Dictionary of context key-value pairs
    """
    context = {}

    if session_id:
        context["sessionId"] = str(session_id)

    # Future: Add git status, active workflows, etc.

    return context


# ==============================================================================
# Helper: Append context to system prompt
# ==============================================================================

def append_system_context(
    system_prompt: List[str],
    context: Dict[str, str],
) -> List[str]:
    """Append system context to system prompt."""
    if not context:
        return system_prompt

    context_str = "\n".join(
        f"{key}: {value}" for key, value in context.items()
    )

    return [*system_prompt, context_str]


# ==============================================================================
# Helper: Prepend context to messages
# ==============================================================================

def prepend_user_context(
    messages: List[Dict],
    context: Dict[str, str],
) -> List[Dict]:
    """Prepend user context as first user message."""
    if not context or not messages:
        return messages

    context_message = {
        "role": "user",
        "content": "\n".join(
            f"{key}: {value}" for key, value in context.items()
        ),
    }

    return [context_message, *messages]
