"""Bash escape hatch for dynamic tool creation via worker sandbox."""
from typing import Dict, Any, Optional, List
import logging
import re
from app.services.worker_client import WorkerClient, WorkerConfig
from app.services.mcp_client import MCPToolResult

logger = logging.getLogger(__name__)


class BashScriptValidator:
    """
    Validates bash scripts before execution to prevent injection attacks.

    SECURITY: Uses allowlist approach - only known-safe commands are permitted.
    This prevents bypass via command variants (ncat, wget2, socat) and
    interpreters with network capabilities (python -c "import urllib").
    """

    # Maximum script size (100KB)
    MAX_SCRIPT_SIZE = 100 * 1024

    # Allowlist: Safe commands for file operations, text processing, calculations
    ALLOWED_COMMANDS = {
        # File operations
        "ls", "cat", "head", "tail", "mkdir", "touch", "cp", "mv", "rm",
        "find", "file", "stat", "readlink", "realpath", "basename", "dirname",
        # Text processing
        "grep", "egrep", "fgrep", "sed", "awk", "sort", "uniq", "wc", "cut",
        "tr", "diff", "patch", "comm", "join", "paste", "column", "fold",
        # Calculations
        "bc", "expr", "calc",
        # Compression (read-only modes)
        "gzip", "gunzip", "bzip2", "bunzip2", "xz", "unxz", "tar", "zip", "unzip",
        # Output
        "echo", "printf",
        # Time/Date
        "date", "sleep",
        # Utilities
        "pwd", "test", "true", "false", "yes", "seq", "shuf", "rev", "tac",
        "nl", "od", "hexdump", "strings", "base64", "md5sum", "sha256sum",
        # Shell builtins (safe subset)
        "cd", "export", "set", "unset", "read", "shift", "getopts",
    }

    # Blocked patterns that could bypass allowlist via shell features
    BLOCKED_PATTERNS = [
        r"/dev/tcp",  # Network pseudo-devices
        r"/dev/udp",
        r">\s*/dev/",  # Writing to devices
        r"<\s*/dev/(?!null|zero|stdin)",  # Reading from devices (except safe ones)
        r"eval\s",  # Code evaluation
        r"\$\(\(.*\bimport\b",  # Python import in command substitution
        r":\(\)\{",  # Fork bomb
        r"while\s+true\s*;",  # Infinite loop
        r"ulimit\s+-u\s+unlimited",  # Remove process limits
        r"chmod\s+[+]?[4567][0-7]{2,3}",  # SUID/SGID bits
        r"dd\s+if=/dev/zero",  # Disk fill
        r">\s*/dev/random",  # Random device abuse
        r"\|\s*bash",  # Pipe to bash (code injection vector)
        r"\|\s*sh",  # Pipe to sh
    ]

    @classmethod
    def validate(cls, script: str, description: str) -> Optional[str]:
        """
        Validate bash script before execution using allowlist approach.

        Args:
            script: Script content to validate
            description: Description of what script does

        Returns:
            Error message if validation fails, None if valid
        """
        # Check size limit
        if len(script) > cls.MAX_SCRIPT_SIZE:
            return f"Script exceeds maximum size of {cls.MAX_SCRIPT_SIZE} bytes"

        # Check for empty script
        if not script.strip():
            return "Script is empty"

        # Check for blocked patterns
        script_lower = script.lower()
        for pattern in cls.BLOCKED_PATTERNS:
            if re.search(pattern, script, re.IGNORECASE):
                logger.warning(
                    f"Blocked pattern detected: {pattern}",
                    extra={"description": description}
                )
                return f"Script contains blocked pattern (potential security risk)"

        # Extract all commands from script (simple token extraction)
        # This catches commands in various positions: start of line, after pipes, semicolons
        commands_used = set()

        # Split by common delimiters and extract first word of each segment
        for line in script.split('\n'):
            # Remove comments
            line = re.sub(r'#.*$', '', line)

            # Split by shell operators, but handle redirects specially
            # Remove redirect targets (anything after > or <)
            line = re.sub(r'[<>]+\s*\S+', '', line)

            # Split by command separators
            tokens = re.split(r'[;&|]', line)

            for token in tokens:
                token = token.strip()
                if not token:
                    continue

                # Get first word (command name)
                words = token.split()
                if not words:
                    continue

                cmd = words[0]

                # Skip variable assignments (contains =)
                if '=' in cmd:
                    continue

                # Skip variable references and special chars
                if cmd.startswith('$') or cmd.startswith('(') or cmd.startswith('{'):
                    continue

                # Skip quotes and other non-command tokens
                if cmd.startswith('"') or cmd.startswith("'"):
                    continue

                commands_used.add(cmd)

        # Check if all commands are in allowlist
        for cmd in commands_used:
            # Skip shell control structures
            if cmd in ('if', 'then', 'else', 'elif', 'fi', 'for', 'while', 'do',
                       'done', 'case', 'esac', 'function', 'in', 'until'):
                continue

            # Skip assignments and variable references
            if '=' in cmd or cmd.startswith('$'):
                continue

            # Check allowlist
            if cmd not in cls.ALLOWED_COMMANDS:
                logger.warning(
                    f"Disallowed command: {cmd}",
                    extra={"description": description, "all_commands": list(commands_used)}
                )
                return f"Script uses disallowed command: {cmd}"

        # Check for excessive command chaining (potential obfuscation)
        semicolon_count = script.count(";")
        pipe_count = script.count("|")
        if semicolon_count > 50 or pipe_count > 30:
            return "Script has excessive command chaining (possible obfuscation)"

        # Warn about potentially risky patterns but allow (with logging)
        if "rm -rf" in script or "rm -fr" in script:
            logger.warning(
                "Script contains 'rm -rf' - potential data deletion",
                extra={"description": description}
            )

        return None  # Valid


class BashTool:
    """
    Sandboxed Bash execution for dynamic tool creation.

    Allows agent to create and execute ad-hoc scripts when:
    - No existing tool fits the need
    - Task requires custom logic
    - One-off operations needed
    """

    def __init__(self, worker_url: str = "http://worker:8001", run_id: Optional[str] = None):
        """
        Initialize Bash tool with worker client.

        Args:
            worker_url: URL of worker service
            run_id: Optional run ID for workspace isolation
        """
        config = WorkerConfig(url=worker_url, timeout_seconds=120)
        self.worker = WorkerClient(config)
        self.run_id = run_id
        self._is_available = None  # Cache availability status

    async def is_available(self) -> bool:
        """
        Check if worker service is available.

        Returns:
            True if worker can be reached, False otherwise
        """
        if self._is_available is not None:
            return self._is_available

        try:
            # Try a simple health check by submitting a minimal job
            import asyncio
            result = await asyncio.wait_for(
                self.worker.submit_job(
                    script_name="bash_runner",
                    arguments={
                        "script": "echo 'test'",
                        "description": "Health check",
                        "workspace_path": "/workspace",
                    },
                    timeout_seconds=5,
                ),
                timeout=5.0
            )
            self._is_available = True
            logger.info("Worker service is available")
            return True
        except Exception as e:
            self._is_available = False
            logger.warning(f"Worker service unavailable: {e}")
            return False

    async def execute_bash(
        self,
        script: str,
        description: str,
        timeout_seconds: int = 30,
    ) -> MCPToolResult:
        """
        Execute bash script in sandboxed worker with isolated workspace.

        SECURITY: Scripts are validated before execution to prevent:
        - Network access attempts (curl, wget, nc, etc.)
        - Privilege escalation (sudo, su)
        - Fork bombs and resource exhaustion
        - Disk filling attacks
        - Script injection attacks

        Args:
            script: Bash script to execute
            description: Human-readable description of what script does
            timeout_seconds: Execution timeout (max 60 seconds)

        Returns:
            MCPToolResult with script output or error
        """
        # Enforce maximum timeout
        timeout_seconds = min(timeout_seconds, 60)

        # CRITICAL: Validate script before execution
        validation_error = BashScriptValidator.validate(script, description)
        if validation_error:
            logger.error(
                f"Script validation failed: {validation_error}",
                extra={"description": description}
            )
            return MCPToolResult(
                success=False,
                error=f"Script validation failed: {validation_error}",
            )

        # Determine workspace path
        if self.run_id:
            workspace_path = f"/workspace/runs/{self.run_id}/"
        else:
            workspace_path = "/workspace"  # Fallback to shared (backward compat)

        logger.info(
            "Executing validated Bash script",
            extra={
                "description": description,
                "script_length": len(script),
                "timeout": timeout_seconds,
                "workspace": workspace_path,
                "run_id": self.run_id,
            }
        )

        try:
            # Submit to worker sandbox with workspace path
            result = await self.worker.submit_job(
                script_name="bash_runner",
                arguments={
                    "script": script,
                    "description": description,
                    "workspace_path": workspace_path,  # NEW: pass workspace
                },
                timeout_seconds=timeout_seconds,
            )

            if result.get("status") == "success":
                output = result.get("output", {})
                return MCPToolResult(
                    success=True,
                    result={
                        "stdout": output.get("stdout", ""),
                        "stderr": output.get("stderr", ""),
                        "return_code": output.get("return_code", 0),
                    },
                    execution_time_ms=result.get("execution_time_ms", 0),
                )
            else:
                return MCPToolResult(
                    success=False,
                    error=result.get("error", "Unknown error"),
                    execution_time_ms=result.get("execution_time_ms", 0),
                )

        except Exception as e:
            logger.error(f"Bash execution failed: {e}", exc_info=True)
            return MCPToolResult(
                success=False,
                error=str(e),
            )

    async def close(self):
        """Close worker client."""
        await self.worker.close()

    @staticmethod
    def get_tool_definition() -> Dict[str, Any]:
        """
        Get tool definition for Ollama.

        Returns:
            Tool definition in OpenAI function calling format
        """
        return {
            "type": "function",
            "function": {
                "name": "execute_bash",
                "description": """Execute a bash script in a sandboxed environment.
Use this when no existing tool fits your needs. The script runs in an
isolated container with no network access and resource limits.
Best for: file operations, data processing, ad-hoc calculations, text manipulation.
The workspace directory is /workspace and is isolated from the host system.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "script": {
                            "type": "string",
                            "description": "Bash script to execute. Use #!/bin/bash shebang and set -e for safety."
                        },
                        "description": {
                            "type": "string",
                            "description": "What this script does (for logging and auditing)"
                        }
                    },
                    "required": ["script", "description"]
                }
            }
        }
