"""Bash script executor in sandboxed environment.

Reads script from stdin as JSON and executes it safely with resource limits.
"""
import json
import sys
import subprocess
import tempfile
import os
import resource
import shutil


def set_resource_limits():
    """
    Set resource limits for child processes.

    SECURITY: Prevents resource exhaustion attacks:
    - Limits CPU time to prevent infinite loops
    - Limits memory to prevent memory bombs
    - Limits number of processes to prevent fork bombs
    - Limits file sizes to prevent disk filling
    """
    try:
        # CPU time limit: 30 seconds of CPU time
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))

        # Memory limit: 256MB
        memory_limit = 256 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))

        # Process limit: 50 processes (prevents fork bombs)
        resource.setrlimit(resource.RLIMIT_NPROC, (50, 50))

        # File size limit: 100MB per file
        file_size_limit = 100 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (file_size_limit, file_size_limit))

        # Open files limit: 100 file descriptors
        resource.setrlimit(resource.RLIMIT_NOFILE, (100, 100))

    except (ValueError, OSError) as e:
        # Log but don't fail - container limits may already be in place
        print(f"Warning: Could not set resource limits: {e}", file=sys.stderr)


def run_bash_script(
    script: str,
    description: str,
    timeout: int = 30,
    workspace_path: str = "/workspace"
) -> dict:
    """
    Execute bash script safely with resource limits and workspace isolation.

    Safety measures:
    - No network access (worker container network isolation)
    - No access to host filesystem (isolated workspace)
    - Resource limits (CPU, memory, processes, file sizes)
    - Timeout enforcement
    - Process limits to prevent fork bombs
    - Atomic file creation to prevent TOCTOU races
    - Per-run workspace isolation (prevents cross-user/cross-run contamination)
    - Path traversal protection

    Args:
        script: Bash script to execute
        description: Description of what script does (for logging)
        timeout: Execution timeout in seconds
        workspace_path: Isolated workspace directory (defaults to /workspace)

    Returns:
        Dict with status, stdout, stderr, return_code
    """
    # Enforce maximum timeout
    timeout = min(timeout, 60)

    # Validate workspace_path for path traversal
    # Must be under /workspace/runs/ or be /workspace itself
    workspace_path_abs = os.path.abspath(workspace_path)
    if not (workspace_path_abs == "/workspace" or
            workspace_path_abs.startswith("/workspace/runs/")):
        return {
            "status": "error",
            "error": f"Invalid workspace path: {workspace_path}",
            "stdout": "",
            "stderr": "",
            "return_code": -1,
        }

    # Create workspace directory if it doesn't exist
    os.makedirs(workspace_path, mode=0o700, exist_ok=True)

    # Create temp file path
    temp_dir = tempfile.gettempdir()
    script_path = os.path.join(
        temp_dir,
        f"bash_script_{os.getpid()}_{os.urandom(8).hex()}.sh"
    )

    try:
        # Atomically create file with correct permissions (prevents TOCTOU race)
        # O_CREAT | O_EXCL ensures file doesn't exist and creates it
        # Mode 0o700 sets rwx for owner only, applied at creation time
        fd = os.open(script_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o700)

        try:
            # Write script content using file descriptor
            with os.fdopen(fd, 'w') as f:
                f.write("#!/bin/bash\n")
                f.write("set -e\n")  # Exit on error
                f.write("set -u\n")  # Error on undefined variables
                f.write("set -o pipefail\n")  # Fail on pipe errors
                f.write(script)
        except:
            # If write fails, clean up and re-raise
            os.remove(script_path)
            raise

        # Execute with timeout and resource limits in isolated workspace
        result = subprocess.run(
            ["/bin/bash", script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workspace_path,  # Use provided workspace (isolated per run)
            preexec_fn=set_resource_limits,  # Apply resource limits before exec
        )

        return {
            "status": "success" if result.returncode == 0 else "failed",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "error": f"Script timeout after {timeout}s",
            "stdout": "",
            "stderr": "",
            "return_code": -1,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "stdout": "",
            "stderr": "",
            "return_code": -1,
        }

    finally:
        # Cleanup script file
        if os.path.exists(script_path):
            try:
                os.remove(script_path)
            except OSError:
                pass  # File already removed or inaccessible

        # Cleanup workspace directory if under /workspace/runs/
        if workspace_path_abs.startswith("/workspace/runs/"):
            try:
                shutil.rmtree(workspace_path, ignore_errors=True)
            except Exception as e:
                # Log but don't fail
                print(f"Warning: Failed to cleanup workspace {workspace_path}: {e}", file=sys.stderr)


if __name__ == "__main__":
    try:
        # Read arguments from stdin
        args = json.loads(sys.stdin.read())

        # Validate required arguments
        if "script" not in args:
            raise ValueError("Missing required argument: script")

        # Get workspace_path from arguments (optional)
        workspace_path = args.get("workspace_path", "/workspace")

        # Run bash script
        result = run_bash_script(
            script=args["script"],
            description=args.get("description", "No description"),
            timeout=args.get("timeout", 30),
            workspace_path=workspace_path,  # Pass workspace path
        )

        # Write result to stdout
        print(json.dumps(result))

    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}), file=sys.stderr)
        sys.exit(1)

    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        print(json.dumps({"error": f"Unexpected error: {e}"}), file=sys.stderr)
        sys.exit(1)
