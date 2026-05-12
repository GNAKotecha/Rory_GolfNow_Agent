"""
Unit tests for BRS tool handlers.

Tests each BRS tool with mock executor:
- create_club (docker exec: php app/console brs:tbs:create-installation)
- get_club_by_name (HTTP API: GET /api/admin/v1/clubs?keyword=...)
- verify_club_setup (HTTP API: composite)
- get_club_config (HTTP API: GET /{clubId}/api/v3/)
- create_admin_user (docker exec: php app/console brs:tbs:brs-superusers:update)
- call_internal_api (HTTP API: GET /{clubId}/api/v3/)
"""

import json
from datetime import datetime, timezone

import pytest

from gateway_mcp.core.errors import ToolExecutionError, UpstreamError
from gateway_mcp.core.executors.mock import MockExecutorBackend, MockResponse
from gateway_mcp.tools.base import Environment, ToolContext
from gateway_mcp.tools.clubs import (
    create_club_handler,
    get_club_by_name_handler,
    verify_club_setup_handler,
)
from gateway_mcp.tools.config import get_club_config_handler
from gateway_mcp.tools.users import create_admin_user_handler
from gateway_mcp.tools.api import call_internal_api_handler
from gateway_mcp.tools.schemas import (
    AdminRole,
    CallInternalApiInput,
    CreateAdminUserInput,
    CreateClubInput,
    GetClubByNameInput,
    GetClubConfigInput,
    InternalApiOperation,
    VerifyClubSetupInput,
)


# --------------------
# Fixtures
# --------------------

@pytest.fixture
def mock_executor():
    """Fresh mock executor for each test."""
    return MockExecutorBackend()


@pytest.fixture
def context(mock_executor):
    """Tool context with mock executor."""
    return ToolContext(
        user_id=1,
        correlation_id="test-corr-123",
        audit_id="test-audit-123",
        environment=Environment.LOCAL,
        _executor=mock_executor,
    )


# --------------------
# create_club tests
# --------------------

class TestCreateClub:
    """Tests for create_club handler (uses docker exec with Symfony console)."""
    
    @pytest.mark.asyncio
    async def test_create_club_success(self, context, mock_executor):
        """Test successful club creation via brs:tbs:create-installation."""
        # Mock the console command output
        mock_executor.set_response("teesheet", MockResponse(
            exit_code=0,
            stdout="SUCCESS\nYou can access the installation at: http://localhost/pebble_beach",
        ))
        
        input = CreateClubInput(
            name="Pebble Beach",
            country="US",
            timezone="America/Los_Angeles",
            currency="USD",
        )
        
        result = await create_club_handler(input, context)
        
        assert result.club_id == "pebble_beach"  # Derived from name
        assert result.club_name == "Pebble Beach"
        assert result.database_name == "brsgolf_pebble_beach"
        
        # Verify command was called correctly
        assert len(mock_executor.calls) == 1
        call = mock_executor.calls[0]
        assert call.service == "teesheet"
        assert "brs:tbs:create-installation" in " ".join(call.args["argv"])
        assert "--club-id=pebble_beach" in " ".join(call.args["argv"])
    
    @pytest.mark.asyncio
    async def test_create_club_failure(self, context, mock_executor):
        """Test club creation failure."""
        mock_executor.set_response("teesheet", MockResponse(
            exit_code=1,
            stderr="Database already exists",
        ))
        
        input = CreateClubInput(
            name="Test Club",
            country="IE",
            timezone="Europe/Dublin",
            currency="EUR",
        )
        
        with pytest.raises(UpstreamError) as exc_info:
            await create_club_handler(input, context)
        
        assert "teesheet" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_club_parses_minimal_output(self, context, mock_executor):
        """Test club creation with minimal SUCCESS output."""
        mock_executor.set_response("teesheet", MockResponse(
            exit_code=0,
            stdout="SUCCESS",
        ))
        
        input = CreateClubInput(
            name="Minimal Club",
            country="GB",
            timezone="Europe/London",
            currency="GBP",
        )
        
        result = await create_club_handler(input, context)
        
        assert result.club_id == "minimal_club"
        assert result.club_name == "Minimal Club"


# --------------------
# get_club_by_name tests (HTTP API)
# --------------------

class TestGetClubByName:
    """Tests for get_club_by_name handler (uses HTTP API)."""
    
    @pytest.mark.asyncio
    async def test_get_club_found(self, context, mock_executor):
        """Test finding an existing club via API."""
        # Mock HTTP response for GET /api/admin/v1/clubs?keyword=Augusta
        mock_executor.set_response("teesheet", MockResponse(
            status_code=200,
            body={
                "data": [
                    {
                        "club_id": "augusta",
                        "name": "Augusta National",
                        "country": "US",
                        "timezone": "America/New_York",
                        "currency": "USD",
                    }
                ],
                "total": 1,
            },
        ))
        
        input = GetClubByNameInput(name="Augusta National")
        result = await get_club_by_name_handler(input, context)
        
        assert result.found is True
        assert result.club_id == "augusta"
        assert result.name == "Augusta National"
        assert result.country == "US"
        
        # Verify HTTP call was made
        assert len(mock_executor.calls) == 1
        call = mock_executor.calls[0]
        assert call.method == "call_http"
        assert call.service == "teesheet"
    
    @pytest.mark.asyncio
    async def test_get_club_not_found_exit_code(self, context, mock_executor):
        """Test club not found via HTTP 404."""
        mock_executor.set_response("teesheet", MockResponse(
            status_code=404,
            body={"error": "Not found"},
        ))
        
        input = GetClubByNameInput(name="Nonexistent Club")
        result = await get_club_by_name_handler(input, context)
        
        assert result.found is False
        assert result.club_id is None
    
    @pytest.mark.asyncio
    async def test_get_club_not_found_json_response(self, context, mock_executor):
        """Test club not found via empty data array."""
        mock_executor.set_response("teesheet", MockResponse(
            status_code=200,
            body={"data": [], "total": 0},
        ))
        
        input = GetClubByNameInput(name="Nonexistent Club")
        result = await get_club_by_name_handler(input, context)
        
        assert result.found is False


# --------------------
# verify_club_setup tests (HTTP API)
# --------------------

class TestVerifyClubSetup:
    """Tests for verify_club_setup handler (uses HTTP API)."""
    
    @pytest.mark.asyncio
    async def test_verify_complete_setup(self, context, mock_executor):
        """Test verification of a complete setup."""
        # verify_club_setup makes two HTTP calls:
        # 1. GET /api/admin/v1/clubs?keyword={club_id} - to check existence
        # 2. GET /{clubId}/api/v3/ - to get configuration
        
        def multi_endpoint_response(method: str, service: str, args: dict) -> MockResponse:
            path = args.get("path", "")
            if "/api/admin/v1/clubs" in path:
                return MockResponse(
                    status_code=200,
                    body={"data": [{"clubId": 42, "name": "Test Club"}], "total": 1},
                )
            elif "/api/v3/" in path:
                return MockResponse(
                    status_code=200,
                    body={
                        "configurations": {
                            "member_booking_feature_supported": "yes",
                            "visitor_booking_feature_supported": "yes",
                            "mobile_enabled": "yes",
                        },
                    },
                )
            return MockResponse()
        
        mock_executor.set_response_callback(multi_endpoint_response)
        
        input = VerifyClubSetupInput(club_id=42)
        result = await verify_club_setup_handler(input, context)
        
        assert result.club_exists is True
        assert result.config_valid is True
        assert "member_booking_feature_supported" in result.features_enabled
    
    @pytest.mark.asyncio
    async def test_verify_incomplete_setup(self, context, mock_executor):
        """Test verification with missing features."""
        def multi_endpoint_response(method: str, service: str, args: dict) -> MockResponse:
            path = args.get("path", "")
            if "/api/admin/v1/clubs" in path:
                return MockResponse(
                    status_code=200,
                    body={"data": [{"clubId": 42, "name": "Test Club"}], "total": 1},
                )
            elif "/api/v3/" in path:
                return MockResponse(
                    status_code=200,
                    body={"configurations": {}},  # No features enabled
                )
            return MockResponse()
        
        mock_executor.set_response_callback(multi_endpoint_response)
        
        input = VerifyClubSetupInput(club_id=42)
        result = await verify_club_setup_handler(input, context)
        
        assert result.club_exists is True
        assert result.features_enabled == []
    
    @pytest.mark.asyncio
    async def test_verify_nonexistent_club(self, context, mock_executor):
        """Test verification of nonexistent club."""
        mock_executor.set_response("teesheet", MockResponse(
            status_code=200,
            body={"data": [], "total": 0},  # No clubs found
        ))
        
        input = VerifyClubSetupInput(club_id=999)
        result = await verify_club_setup_handler(input, context)
        
        assert result.club_exists is False
        assert len(result.issues) > 0


# --------------------
# get_club_config tests
# --------------------

class TestGetClubConfig:
    """Tests for get_club_config handler."""
    
    @pytest.mark.asyncio
    async def test_get_config_success(self, context, mock_executor):
        """Test successful config retrieval."""
        mock_executor.set_response("config_api", MockResponse(
            exit_code=0,
            stdout=json.dumps({
                "club_id": 42,
                "modules": ["teesheet", "memberships", "payments"],
                "settings": {"max_booking_days": 14, "currency": "USD"},
                "version": 5,
            }),
        ))
        
        input = GetClubConfigInput(club_id=42)
        result = await get_club_config_handler(input, context)
        
        assert result.club_id == 42
        assert "teesheet" in result.modules
        assert result.settings["max_booking_days"] == 14
        assert result.version == 5
    
    @pytest.mark.asyncio
    async def test_get_config_not_found(self, context, mock_executor):
        """Test config retrieval for nonexistent club."""
        mock_executor.set_response("config_api", MockResponse(
            exit_code=1,
            stderr="Club not found",
        ))
        
        input = GetClubConfigInput(club_id=999)
        
        with pytest.raises(ToolExecutionError) as exc_info:
            await get_club_config_handler(input, context)
        
        assert "not found" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_get_config_minimal_response(self, context, mock_executor):
        """Test config with minimal response fields."""
        mock_executor.set_response("config_api", MockResponse(
            exit_code=0,
            stdout=json.dumps({
                "config_version": 1,
            }),
        ))
        
        input = GetClubConfigInput(club_id=42)
        result = await get_club_config_handler(input, context)
        
        assert result.club_id == 42  # Falls back to input
        assert result.modules == []  # Defaults
        assert result.version == 1


# --------------------
# create_admin_user tests (docker exec: brs:tbs:brs-superusers:update)
# --------------------

class TestCreateAdminUser:
    """Tests for create_admin_user handler (uses brs:tbs:brs-superusers:update)."""
    
    @pytest.mark.asyncio
    async def test_create_admin_success(self, context, mock_executor):
        """Test successful superuser sync."""
        mock_executor.set_response("teesheet", MockResponse(
            exit_code=0,
            stdout="Superusers synced successfully for club_42",
        ))
        
        input = CreateAdminUserInput(
            club_id=42,
            email="admin@example.com",
            role=AdminRole.ADMIN,
        )
        
        result = await create_admin_user_handler(input, context)
        
        assert result.club_id == "42"  # club_id is string after validation
        assert result.role == AdminRole.ADMIN
        assert result.already_existed is False
        
        # Verify command was called correctly
        call = mock_executor.calls[0]
        assert "brs:tbs:brs-superusers:update" in " ".join(call.args["argv"])
        assert "--club-id=42" in " ".join(call.args["argv"])
    
    @pytest.mark.asyncio
    async def test_create_admin_idempotent(self, context, mock_executor):
        """Test admin creation is idempotent (re-sync is okay)."""
        mock_executor.set_response("teesheet", MockResponse(
            exit_code=0,
            stdout="Superusers already up to date",
        ))
        
        input = CreateAdminUserInput(
            club_id=42,
            email="admin@example.com",
        )
        
        result = await create_admin_user_handler(input, context)
        
        # Even if already synced, the command succeeds
        assert result.club_id == "42"  # club_id is string after validation
    
    @pytest.mark.asyncio
    async def test_create_superuser(self, context, mock_executor):
        """Test superuser creation (same command, role is informational)."""
        mock_executor.set_response("teesheet", MockResponse(
            exit_code=0,
            stdout="Superusers synced",
        ))
        
        input = CreateAdminUserInput(
            club_id=42,
            email="superadmin@example.com",
            role=AdminRole.SUPERUSER,
        )
        
        result = await create_admin_user_handler(input, context)
        
        # Role is determined by the config, not the command
        assert result.role == AdminRole.SUPERUSER
        
        # Verify command was called with club-id
        call = mock_executor.calls[0]
        assert "--club-id=42" in " ".join(call.args["argv"])


# --------------------
# call_internal_api tests (HTTP API: GET /{clubId}/api/v3/)
# --------------------

class TestCallInternalApi:
    """Tests for call_internal_api handler (uses BRS config API)."""
    
    @pytest.mark.asyncio
    async def test_enable_features_success(self, context, mock_executor):
        """Test successful feature check from BRS config API."""
        mock_executor.set_response("teesheet", MockResponse(
            status_code=200,
            body={
                "configurations": {
                    "member_booking_feature_supported": "yes",
                    "visitor_booking_feature_supported": "yes",
                    "mobile_enabled": "yes",
                    "facility_booking_feature_supported": "no",
                },
            },
        ))
        
        input = CallInternalApiInput(
            club_id=42,
            operation=InternalApiOperation.ENABLE_REQUIRED_FEATURES,
        )
        
        result = await call_internal_api_handler(input, context)
        
        assert result.club_id == 42
        assert "member_booking_feature_supported" in result.enabled_features
        assert "visitor_booking_feature_supported" in result.enabled_features
        assert "mobile_enabled" in result.enabled_features
        # facility_booking is "no", so not in enabled
        assert "facility_booking_feature_supported" not in result.enabled_features
    
    @pytest.mark.asyncio
    async def test_enable_features_fallback_response(self, context, mock_executor):
        """Test feature enablement with minimal response."""
        mock_executor.set_response("teesheet", MockResponse(
            status_code=200,
            body={"success": True},
        ))
        
        input = CallInternalApiInput(
            club_id=42,
            operation=InternalApiOperation.ENABLE_REQUIRED_FEATURES,
        )
        
        result = await call_internal_api_handler(input, context)
        
        # With empty configs, no features are enabled
        assert len(result.enabled_features) == 0
    
    @pytest.mark.asyncio
    async def test_api_failure(self, context, mock_executor):
        """Test internal API failure (non-200 status)."""
        mock_executor.set_response("teesheet", MockResponse(
            status_code=500,
            body={"error": "Internal server error"},
        ))
        
        input = CallInternalApiInput(
            club_id=42,
            operation=InternalApiOperation.ENABLE_REQUIRED_FEATURES,
        )
        
        with pytest.raises(UpstreamError) as exc_info:
            await call_internal_api_handler(input, context)
        
        assert "teesheet" in str(exc_info.value).lower()


# --------------------
# Tool registration tests
# --------------------

class TestBRSToolRegistration:
    """Tests for BRS tool registration."""
    
    def test_all_brs_tools_registered(self):
        """Test that all 7 BRS tools are registered."""
        from gateway_mcp.tools import create_brs_registry
        
        registry = create_brs_registry()
        
        assert len(registry) == 7
        assert "create_club" in registry
        assert "get_club_by_name" in registry
        assert "verify_club_setup" in registry
        assert "get_club_config" in registry
        assert "create_admin_user" in registry
        assert "call_internal_api" in registry
        assert "authenticate_club" in registry
    
    def test_brs_tools_have_handlers(self):
        """Test that all BRS tools have handlers set."""
        from gateway_mcp.tools import create_brs_registry
        
        registry = create_brs_registry()
        
        for tool in registry:
            assert tool.handler is not None, f"Tool {tool.name} missing handler"
    
    def test_brs_tools_risk_levels(self):
        """Test that BRS tools have appropriate risk levels."""
        from gateway_mcp.tools import create_brs_registry, RiskLevel
        
        registry = create_brs_registry()
        
        # Read-only tools
        assert registry.get("get_club_by_name").risk_level == RiskLevel.READ
        assert registry.get("verify_club_setup").risk_level == RiskLevel.READ
        assert registry.get("get_club_config").risk_level == RiskLevel.READ
        
        # Write tools
        assert registry.get("create_club").risk_level == RiskLevel.LOW_WRITE
        assert registry.get("create_admin_user").risk_level == RiskLevel.MEDIUM_WRITE
        assert registry.get("call_internal_api").risk_level == RiskLevel.MEDIUM_WRITE


# --------------------
# Club ID propagation tests
# --------------------

class TestClubIdPropagation:
    """Tests that club-scoped HTTP calls pass club_id for auth token usage."""
    
    @pytest.mark.asyncio
    async def test_verify_club_setup_passes_club_id_to_config_api(self, context, mock_executor):
        """verify_club_setup passes club_id when calling club-scoped config API."""
        # Setup multi-endpoint response
        def multi_endpoint_response(method: str, service: str, args: dict) -> MockResponse:
            path = args.get("path", "")
            if "/api/admin/v1/clubs" in path:
                # Global admin API - no club_id needed
                return MockResponse(
                    status_code=200,
                    body={"data": [{"clubId": "test_club_42", "name": "Test Club"}], "total": 1},
                )
            elif "/api/v3/" in path:
                # Club-scoped API - should have club_id passed
                return MockResponse(
                    status_code=200,
                    body={"configurations": {"member_booking_feature_supported": "yes"}},
                )
            return MockResponse()
        
        mock_executor.set_response_callback(multi_endpoint_response)
        
        input = VerifyClubSetupInput(club_id="test_club_42")
        await verify_club_setup_handler(input, context)
        
        # Find the call to the club-scoped config endpoint
        config_api_calls = [c for c in mock_executor.calls if "/api/v3/" in c.args.get("path", "")]
        assert len(config_api_calls) == 1
        
        # Verify club_id was passed for the club-scoped call
        assert config_api_calls[0].args.get("club_id") == "test_club_42"
        
        # Verify admin API call does NOT have club_id (it's global)
        admin_api_calls = [c for c in mock_executor.calls if "/api/admin/" in c.args.get("path", "")]
        assert len(admin_api_calls) == 1
        assert admin_api_calls[0].args.get("club_id") is None
    
    @pytest.mark.asyncio
    async def test_call_internal_api_passes_club_id(self, context, mock_executor):
        """call_internal_api passes club_id for club-scoped HTTP calls."""
        mock_executor.set_response("teesheet", MockResponse(
            status_code=200,
            body={
                "configurations": {
                    "member_booking_feature_supported": "yes",
                },
            },
        ))
        
        input = CallInternalApiInput(
            club_id=99,
            operation=InternalApiOperation.ENABLE_REQUIRED_FEATURES,
        )
        
        await call_internal_api_handler(input, context)
        
        # Verify club_id was passed
        assert len(mock_executor.calls) == 1
        call = mock_executor.calls[0]
        assert call.method == "call_http"
        assert call.args.get("club_id") == "99"  # String form of club_id
    
    @pytest.mark.asyncio
    async def test_get_club_by_name_no_club_id_for_global_api(self, context, mock_executor):
        """get_club_by_name uses global admin API - no club_id needed."""
        mock_executor.set_response("teesheet", MockResponse(
            status_code=200,
            body={"data": [{"clubId": "augusta", "name": "Augusta National"}], "total": 1},
        ))
        
        input = GetClubByNameInput(name="Augusta National")
        await get_club_by_name_handler(input, context)
        
        # Global admin API should not have club_id
        assert len(mock_executor.calls) == 1
        call = mock_executor.calls[0]
        assert call.method == "call_http"
        assert "/api/admin/v1/clubs" in call.args.get("path", "")
        assert call.args.get("club_id") is None
