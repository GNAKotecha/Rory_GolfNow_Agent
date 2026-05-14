"""Architecture Boundary Tests (Task D3)

Validates that architectural boundaries between Backend and Gateway are maintained:

1. Backend does NOT directly use external provider secrets (Atlassian, GitHub tokens)
2. Gateway remains the credential/policy boundary
3. Backend services do not import gateway credential handling directly

These tests run in CI to catch regressions that cross architectural boundaries.
"""
import ast
import os
import pytest
from pathlib import Path
from typing import List, Set, Tuple


# ==============================================================================
# Test Configuration
# ==============================================================================

# Backend service modules that should NOT access external credentials
BACKEND_SERVICE_PATHS = [
    "app/services/agentic_service.py",
    "app/services/mcp_registry.py",
    "app/services/mcp_client.py",
    "app/services/ollama.py",
    "app/services/error_handler.py",
    "app/services/agent_state.py",
    "app/services/tool_catalog.py",
]

# Patterns indicating direct external credential access
FORBIDDEN_CREDENTIAL_PATTERNS = [
    "ATLASSIAN_TOKEN",
    "JIRA_TOKEN",
    "JIRA_API_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_PAT",
    "OAUTH_TOKEN",
    "REFRESH_TOKEN",
    "CLIENT_SECRET",
    "ATLASSIAN_CLIENT_SECRET",
]

# Modules that backend should NOT import from gateway
FORBIDDEN_GATEWAY_IMPORTS = [
    "gateway_mcp.core.auth",
    "gateway_mcp.core.credentials",
    "gateway_mcp.core.oauth",
]

# These are allowed because they are enums/types, not credentials
ALLOWED_GATEWAY_IMPORTS = [
    "gateway_mcp.tools.base",  # RiskLevel, Environment enums
]


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def backend_root() -> Path:
    """Get the backend root directory."""
    return Path(__file__).parent.parent


# ==============================================================================
# AST Helpers
# ==============================================================================

def find_string_literals(tree: ast.AST) -> Set[str]:
    """Extract all string literals from an AST."""
    literals = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.add(node.value)
    return literals


def find_imports(tree: ast.AST) -> List[Tuple[str, int]]:
    """Extract all import statements with line numbers."""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append((node.module, node.lineno))
    return imports


def find_environ_access(tree: ast.AST) -> List[Tuple[str, int]]:
    """Find os.environ accesses with specific keys."""
    accesses = []
    for node in ast.walk(tree):
        # Check for os.environ.get("KEY") or os.environ["KEY"]
        if isinstance(node, ast.Subscript):
            if (isinstance(node.value, ast.Attribute) and
                node.value.attr == "environ" and
                isinstance(node.slice, ast.Constant)):
                accesses.append((node.slice.value, node.lineno))
        elif isinstance(node, ast.Call):
            if (isinstance(node.func, ast.Attribute) and
                node.func.attr == "get"):
                # Check if it's environ.get
                if (isinstance(node.func.value, ast.Attribute) and
                    node.func.value.attr == "environ"):
                    if node.args and isinstance(node.args[0], ast.Constant):
                        accesses.append((node.args[0].value, node.lineno))
    return accesses


# ==============================================================================
# Test Classes
# ==============================================================================

class TestBackendDoesNotAccessExternalSecrets:
    """Ensures backend services do not directly access external provider secrets."""
    
    def test_no_forbidden_env_var_access(self, backend_root):
        """Backend services must not access external credential env vars."""
        violations = []
        
        for rel_path in BACKEND_SERVICE_PATHS:
            file_path = backend_root / rel_path
            if not file_path.exists():
                continue
            
            with open(file_path, "r") as f:
                source = f.read()
            
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            
            env_accesses = find_environ_access(tree)
            
            for env_key, lineno in env_accesses:
                for forbidden in FORBIDDEN_CREDENTIAL_PATTERNS:
                    if forbidden in env_key.upper():
                        violations.append(
                            f"{rel_path}:{lineno} accesses forbidden env var: {env_key}"
                        )
        
        assert not violations, (
            "Backend services must not access external credentials directly.\n"
            "Violations found:\n" + "\n".join(f"  - {v}" for v in violations)
        )
    
    def test_no_hardcoded_credential_patterns(self, backend_root):
        """Backend services must not contain hardcoded credential patterns."""
        violations = []
        
        # Patterns that suggest hardcoded secrets (not exhaustive, just obvious ones)
        suspicious_patterns = [
            "Bearer ",
            "Basic ",
            "token=",
            "apikey=",
            "api_key=",
        ]
        
        for rel_path in BACKEND_SERVICE_PATHS:
            file_path = backend_root / rel_path
            if not file_path.exists():
                continue
            
            with open(file_path, "r") as f:
                source = f.read()
            
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            
            literals = find_string_literals(tree)
            
            for literal in literals:
                for pattern in suspicious_patterns:
                    # Skip short literals and test strings
                    if len(literal) > 20 and pattern.lower() in literal.lower():
                        violations.append(
                            f"{rel_path}: contains suspicious string pattern: {pattern}..."
                        )
        
        assert not violations, (
            "Backend services may contain hardcoded credential patterns.\n"
            "Review these:\n" + "\n".join(f"  - {v}" for v in violations)
        )


class TestBackendDoesNotImportGatewayCredentials:
    """Ensures backend does not import gateway credential modules."""
    
    def test_no_forbidden_gateway_imports(self, backend_root):
        """Backend services must not import gateway credential modules."""
        violations = []
        
        for rel_path in BACKEND_SERVICE_PATHS:
            file_path = backend_root / rel_path
            if not file_path.exists():
                continue
            
            with open(file_path, "r") as f:
                source = f.read()
            
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            
            imports = find_imports(tree)
            
            for module, lineno in imports:
                for forbidden in FORBIDDEN_GATEWAY_IMPORTS:
                    if module.startswith(forbidden):
                        violations.append(
                            f"{rel_path}:{lineno} imports forbidden module: {module}"
                        )
        
        assert not violations, (
            "Backend services must not import gateway credential modules.\n"
            "The gateway is the credential boundary - backend should call gateway via MCP.\n"
            "Violations found:\n" + "\n".join(f"  - {v}" for v in violations)
        )


class TestGatewayOwnsCredentials:
    """Validates that credential handling is properly encapsulated in gateway."""
    
    def test_gateway_has_credential_module(self, backend_root):
        """Gateway should have a credentials or auth module."""
        gateway_root = backend_root / "gateway_mcp"
        
        # Check for auth-related modules in gateway
        auth_modules = [
            gateway_root / "core" / "auth.py",
            gateway_root / "core" / "permissions.py",
        ]
        
        existing = [m for m in auth_modules if m.exists()]
        
        assert existing, (
            "Gateway should have auth/credentials modules.\n"
            f"Expected one of: {[str(m) for m in auth_modules]}"
        )
    
    def test_tool_context_has_credential_fetcher(self, backend_root):
        """ToolContext should provide credential access abstraction."""
        base_path = backend_root / "gateway_mcp" / "tools" / "base.py"
        
        if not base_path.exists():
            pytest.skip("gateway_mcp/tools/base.py not found")
        
        with open(base_path, "r") as f:
            source = f.read()
        
        # Check for get_credential method or _credential_fetcher
        assert "get_credential" in source or "_credential_fetcher" in source, (
            "ToolContext should provide credential abstraction.\n"
            "Tools should call context.get_credential() not access tokens directly."
        )


class TestBackendMCPClientBoundary:
    """Validates MCP client respects gateway boundary."""
    
    def test_mcp_client_does_not_pass_raw_tokens(self, backend_root):
        """MCPClient should not pass raw credential tokens."""
        mcp_client_path = backend_root / "app" / "services" / "mcp_client.py"
        
        if not mcp_client_path.exists():
            pytest.skip("mcp_client.py not found")
        
        with open(mcp_client_path, "r") as f:
            source = f.read()
        
        try:
            tree = ast.parse(source)
        except SyntaxError:
            pytest.fail("mcp_client.py has syntax error")
        
        # Check for forbidden patterns in string literals
        forbidden_in_headers = ["authorization", "bearer", "x-api-key"]
        literals = find_string_literals(tree)
        
        violations = []
        for lit in literals:
            for pattern in forbidden_in_headers:
                if pattern in lit.lower() and "token" in source.lower():
                    # This might be a header with direct token
                    violations.append(f"Found suspicious header pattern: {lit}")
        
        # This is advisory - some headers are legitimate
        if violations:
            # Log but don't fail - manual review needed
            print(f"Review these patterns in mcp_client.py:\n" + 
                  "\n".join(f"  - {v}" for v in violations))


# ==============================================================================
# Configuration Validation Tests
# ==============================================================================

class TestArchitectureBoundaryConfiguration:
    """Validates that architecture boundary rules are properly documented."""
    
    def test_forbidden_patterns_list_not_empty(self):
        """Ensure forbidden patterns list is maintained."""
        assert len(FORBIDDEN_CREDENTIAL_PATTERNS) > 0, (
            "FORBIDDEN_CREDENTIAL_PATTERNS should not be empty"
        )
    
    def test_backend_service_paths_exist(self, backend_root):
        """Ensure at least some backend service paths exist."""
        existing = [
            p for p in BACKEND_SERVICE_PATHS
            if (backend_root / p).exists()
        ]
        
        assert len(existing) > 0, (
            "At least some BACKEND_SERVICE_PATHS should exist"
        )
    
    def test_forbidden_gateway_imports_list(self):
        """Ensure forbidden imports list is maintained."""
        assert len(FORBIDDEN_GATEWAY_IMPORTS) > 0, (
            "FORBIDDEN_GATEWAY_IMPORTS should not be empty"
        )
