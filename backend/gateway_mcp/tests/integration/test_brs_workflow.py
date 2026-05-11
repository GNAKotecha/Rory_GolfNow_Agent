"""
Integration tests for BRS tool workflow.

Tests the full club-setup workflow using the actual BRS API patterns:
- create_club: docker exec php app/console brs:tbs:create-installation
- get_club_by_name: HTTP GET /api/admin/v1/clubs?keyword=...
- create_admin_user: docker exec php app/console brs:tbs:brs-superusers:update
- call_internal_api: HTTP GET /{clubId}/api/v3/
- verify_club_setup: HTTP GET /{clubId}/api/v3/
"""

import json
from datetime import datetime, timezone

import pytest

from gateway_mcp.core.executors.mock import MockExecutorBackend, MockResponse
from gateway_mcp.tools.base import Environment, ToolContext
from gateway_mcp.tools.clubs import (
    create_club_handler,
    get_club_by_name_handler,
    verify_club_setup_handler,
)
from gateway_mcp.tools.users import create_admin_user_handler
from gateway_mcp.tools.api import call_internal_api_handler
from gateway_mcp.tools.schemas import (
    AdminRole,
    CallInternalApiInput,
    CreateAdminUserInput,
    CreateClubInput,
    GetClubByNameInput,
    InternalApiOperation,
    VerifyClubSetupInput,
)


class TestClubSetupWorkflow:
    """
    Integration test for the full club setup workflow.
    
    This test simulates the complete onboarding workflow:
    1. Create a new club (docker exec: brs:tbs:create-installation)
    2. Verify the club exists (HTTP: GET /api/admin/v1/clubs)
    3. Create admin user (docker exec: brs:tbs:brs-superusers:update)
    4. Check enabled features (HTTP: GET /{clubId}/api/v3/)
    5. Verify setup is complete (HTTP: GET /{clubId}/api/v3/)
    """
    
    @pytest.fixture
    def mock_executor(self):
        """Create mock executor with workflow-specific responses."""
        executor = MockExecutorBackend()
        
        # Setup response callback for dynamic responses
        def workflow_responses(method: str, service: str, args: dict) -> MockResponse:
            """Dynamic responses based on workflow state."""
            
            if method == "run_command" and service == "teesheet":
                argv = args.get("argv", [])
                cmd_str = " ".join(argv)
                
                if "brs:tbs:create-installation" in cmd_str:
                    return MockResponse(
                        exit_code=0,
                        stdout="SUCCESS\nYou can access the installation at: http://localhost/integration_test_club",
                    )
                
                elif "brs:tbs:brs-superusers:update" in cmd_str:
                    return MockResponse(
                        exit_code=0,
                        stdout="Superusers synced successfully",
                    )
            
            elif method == "call_http" and service == "teesheet":
                path = args.get("path", "")
                
                # GET /api/admin/v1/clubs?keyword=...
                if "/api/admin/v1/clubs" in path:
                    return MockResponse(
                        status_code=200,
                        body={
                            "data": [
                                {
                                    "club_id": "integration_test_club",
                                    "name": "Integration Test Club",
                                    "country": "US",
                                    "timezone": "America/New_York",
                                    "currency": "USD",
                                }
                            ],
                            "total": 1,
                        },
                    )
                
                # GET /{clubId}/api/v3/ for configuration
                elif "/api/v3/" in path:
                    return MockResponse(
                        status_code=200,
                        body={
                            "configurations": {
                                "member_booking_feature_supported": "yes",
                                "visitor_booking_feature_supported": "yes",
                                "mobile_enabled": "yes",
                                "facility_booking_feature_supported": "yes",
                            },
                        },
                    )
            
            # Default response
            return MockResponse()
        
        executor.set_response_callback(workflow_responses)
        return executor
    
    @pytest.fixture
    def context(self, mock_executor):
        """Create tool context with mock executor."""
        return ToolContext(
            user_id=1,
            correlation_id="workflow-test-123",
            audit_id="audit-workflow-123",
            environment=Environment.LOCAL,
            _executor=mock_executor,
        )
    
    @pytest.mark.asyncio
    async def test_full_club_setup_workflow(self, context, mock_executor):
        """
        Test complete club setup workflow end-to-end.
        
        Workflow steps:
        1. Create club → returns club_id (derived from name)
        2. Get club by name → verifies creation via API
        3. Create admin user → syncs superusers via console
        4. Check features → queries config API
        5. Verify setup → confirms everything is ready
        """
        
        # Step 1: Create club (docker exec)
        create_input = CreateClubInput(
            name="Integration Test Club",
            country="US",
            timezone="America/New_York",
            currency="USD",
        )
        
        create_result = await create_club_handler(create_input, context)
        
        assert create_result.club_id == "integration_test_club"
        assert create_result.club_name == "Integration Test Club"
        assert create_result.database_name == "brsgolf_integration_test_club"
        
        # Step 2: Verify club exists by looking it up (HTTP)
        get_input = GetClubByNameInput(name="Integration Test Club")
        
        get_result = await get_club_by_name_handler(get_input, context)
        
        assert get_result.found is True
        assert get_result.club_id == create_result.club_id
        assert get_result.name == "Integration Test Club"
        
        # Step 3: Create admin user (docker exec)
        admin_input = CreateAdminUserInput(
            club_id=create_result.club_id,
            email="admin@testclub.com",
            role=AdminRole.ADMIN,
        )
        
        admin_result = await create_admin_user_handler(admin_input, context)
        
        assert admin_result.club_id == create_result.club_id
        assert admin_result.role == AdminRole.ADMIN
        
        # Step 4: Check enabled features (HTTP)
        features_input = CallInternalApiInput(
            club_id=create_result.club_id,
            operation=InternalApiOperation.ENABLE_REQUIRED_FEATURES,
        )
        
        features_result = await call_internal_api_handler(features_input, context)
        
        assert features_result.club_id == create_result.club_id
        assert "member_booking_feature_supported" in features_result.enabled_features
        
        # Step 5: Verify setup is complete (HTTP)
        verify_input = VerifyClubSetupInput(club_id=create_result.club_id)
        
        verify_result = await verify_club_setup_handler(verify_input, context)
        
        assert verify_result.club_exists is True
        assert verify_result.config_valid is True
        assert len(verify_result.issues) == 0
        
        # Verify workflow made expected calls
        # 1. run_command: create-installation
        # 2. call_http: /api/admin/v1/clubs (get_club_by_name)
        # 3. run_command: brs-superusers:update
        # 4. call_http: /{clubId}/api/v3/ (call_internal_api)
        # 5. call_http: /api/admin/v1/clubs (verify_club_setup - existence)
        # 6. call_http: /{clubId}/api/v3/ (verify_club_setup - config)
        assert len(mock_executor.calls) == 6
        
        # Verify call methods
        call_methods = [c.method for c in mock_executor.calls]
        assert call_methods == ["run_command", "call_http", "run_command", "call_http", "call_http", "call_http"]
    
    @pytest.mark.asyncio
    async def test_workflow_with_existing_admin(self, context, mock_executor):
        """Test workflow when admin sync is re-run (idempotent)."""
        
        # Override admin creation to return success (re-sync is always okay)
        def idempotent_responses(method: str, service: str, args: dict) -> MockResponse:
            if method == "run_command" and service == "teesheet":
                argv = args.get("argv", [])
                cmd_str = " ".join(argv)
                
                if "brs:tbs:brs-superusers:update" in cmd_str:
                    return MockResponse(
                        exit_code=0,
                        stdout="Superusers already up to date",
                    )
                
                return MockResponse(exit_code=0, stdout="SUCCESS")
            
            return MockResponse()
        
        mock_executor.set_response_callback(idempotent_responses)
        
        admin_input = CreateAdminUserInput(
            club_id="test_club",
            email="admin@testclub.com",
        )
        
        result = await create_admin_user_handler(admin_input, context)
        
        # Re-sync is always successful
        assert result.club_id == "test_club"
    
    @pytest.mark.asyncio
    async def test_workflow_verification_with_issues(self, context, mock_executor):
        """Test workflow when verification finds issues (club not found)."""
        
        def incomplete_setup_responses(method: str, service: str, args: dict) -> MockResponse:
            if method == "call_http" and service == "teesheet":
                # Return 404 for config API
                return MockResponse(
                    status_code=404,
                    body={"error": "Club not found"},
                )
            
            return MockResponse()
        
        mock_executor.set_response_callback(incomplete_setup_responses)
        
        verify_input = VerifyClubSetupInput(club_id=999)
        
        result = await verify_club_setup_handler(verify_input, context)
        
        assert result.club_exists is False
        assert len(result.issues) > 0
