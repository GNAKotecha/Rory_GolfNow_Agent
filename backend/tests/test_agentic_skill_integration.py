"""Integration tests for skill invocation in AgenticService.

Tests Task 4 (Phase 5): Skill detection, matching, and execution during chat.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from sqlalchemy.orm import Session

from app.services.agentic_service import AgenticService, AgenticConfig, AgenticResult
from app.services.ollama import OllamaClient
from app.services.mcp_registry import MCPToolRegistry
from app.models.models import User, UserRole
from app.models.skill_model import Skill


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = Mock(spec=Session)
    return session


@pytest.fixture
def mock_ollama_client():
    """Create a mock Ollama client."""
    client = Mock(spec=OllamaClient)
    return client


@pytest.fixture
def mock_mcp_registry():
    """Create a mock MCP registry."""
    registry = Mock(spec=MCPToolRegistry)
    registry.discover_all_tools = AsyncMock(return_value={})
    registry.get_available_tools = Mock(return_value=[])
    return registry


@pytest.fixture
def test_user():
    """Create a test user."""
    user = Mock(spec=User)
    user.id = 1
    user.role = UserRole.ADMIN
    return user


@pytest.fixture
def test_skill():
    """Create a test skill with intent patterns."""
    skill = Mock(spec=Skill)
    skill.id = 1
    skill.skill_name = "test_workflow"
    skill.description = "Test workflow skill"
    skill.version = 1
    skill.is_active = True
    skill.intent_patterns = [
        r"test workflow",
        r"run.*test",
        r"execute.*workflow"
    ]
    skill.skill_data = {"config": "test"}
    return skill


@pytest.fixture
def agentic_service(mock_ollama_client, mock_mcp_registry, mock_db_session):
    """Create an AgenticService instance for testing."""
    config = AgenticConfig(
        max_steps=5,
        use_tool_catalog=False,
        use_enhanced_catalog=False,
    )
    service = AgenticService(
        ollama_client=mock_ollama_client,
        mcp_registry=mock_mcp_registry,
        config=config,
        run_id="test-run-123",
        session=mock_db_session,
        tenant_id=1,
    )
    return service


class TestSkillLoadingIntegration:
    """Test skill loading from repository."""

    @patch('app.repositories.skill_repository.SkillRepository')
    @patch('app.services.workflow_runtime_service.WorkflowRuntimeService')
    def test_load_skills_from_repository(
        self, mock_workflow_service, mock_skill_repo, agentic_service, test_skill
    ):
        """Test that skills are loaded from SkillRepository."""
        # Arrange
        mock_workflow_service.load_active_skills.return_value = []
        mock_skill_repo.get_active_skills.return_value = [test_skill]
        mock_workflow_service.get_skills_context.return_value = {
            "skill_names": [],
            "skills": []
        }

        # Act
        agentic_service._load_skills_context()

        # Assert
        mock_skill_repo.get_active_skills.assert_called_once_with(
            db=agentic_service.session,
            tenant_id=1
        )
        assert "skills" in agentic_service.skills_context
        assert len(agentic_service.skills_context["skills"]) > 0
        assert agentic_service.skills_context["skills"][0]["name"] == "test_workflow"

    @patch('app.repositories.skill_repository.SkillRepository')
    @patch('app.services.workflow_runtime_service.WorkflowRuntimeService')
    def test_load_skills_merges_sources(
        self, mock_workflow_service, mock_skill_repo, agentic_service, test_skill
    ):
        """Test that skills from both sources are merged."""
        # Arrange
        workflow_skill = Mock(spec=Skill)
        workflow_skill.skill_name = "workflow_skill"
        workflow_skill.description = "Workflow skill"
        workflow_skill.version = 1
        workflow_skill.is_active = True
        workflow_skill.intent_patterns = []
        workflow_skill.skill_data = {}

        mock_workflow_service.load_active_skills.return_value = [workflow_skill]
        mock_skill_repo.get_active_skills.return_value = [test_skill]
        mock_workflow_service.get_skills_context.return_value = {
            "skill_names": ["workflow_skill"],
            "skills": []
        }

        # Act
        agentic_service._load_skills_context()

        # Assert
        assert len(agentic_service.skills_context["skill_names"]) >= 2
        assert "workflow_skill" in agentic_service.skills_context["skill_names"]
        assert "test_workflow" in agentic_service.skills_context["skill_names"]

    def test_load_skills_handles_missing_session(self, agentic_service):
        """Test that missing session is handled gracefully."""
        # Arrange
        agentic_service.session = None

        # Act
        agentic_service._load_skills_context()

        # Assert
        assert agentic_service.skills_context == {}

    def test_load_skills_handles_missing_tenant_id(self, agentic_service):
        """Test that missing tenant_id is handled gracefully."""
        # Arrange
        agentic_service.tenant_id = None

        # Act
        agentic_service._load_skills_context()

        # Assert
        assert agentic_service.skills_context == {}

    @patch('app.repositories.skill_repository.SkillRepository')
    @patch('app.services.workflow_runtime_service.WorkflowRuntimeService')
    def test_load_skills_handles_exception(
        self, mock_workflow_service, mock_skill_repo, agentic_service
    ):
        """Test that exceptions during skill loading are handled gracefully."""
        # Arrange
        mock_skill_repo.get_active_skills.side_effect = Exception("Database error")

        # Act
        agentic_service._load_skills_context()

        # Assert - should not raise, just log error
        assert agentic_service.skills_context == {}


class TestSkillMatchingIntegration:
    """Test skill intent matching and invocation."""

    @pytest.mark.asyncio
    @patch('app.services.skill_discovery.SkillDiscoveryService')
    @patch('app.utils.skill_invoker.invoke_skill')
    async def test_check_skill_match_executes_matched_skill(
        self, mock_invoke, mock_discovery_service_class, agentic_service, test_user, test_skill
    ):
        """Test that a matched skill is executed."""
        # Arrange
        messages = [
            {"role": "user", "content": "I want to run the test workflow"}
        ]

        mock_discovery = Mock()
        mock_discovery.match_skill_by_intent.return_value = test_skill
        mock_discovery_service_class.return_value = mock_discovery

        mock_invoke.return_value = {
            "success": True,
            "skill_name": "test_workflow",
            "message": "Skill executed successfully",
            "context": {}
        }

        agentic_service._session_id = 1
        agentic_service.skills_context = {"skills": [{"name": "test_workflow"}]}

        # Act
        result = await agentic_service._check_skill_match(messages, test_user)

        # Assert
        assert result is not None
        assert result["success"] is True
        assert result["skill_name"] == "test_workflow"
        mock_discovery.match_skill_by_intent.assert_called_once()
        mock_invoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_skill_match_returns_none_without_session(
        self, agentic_service, test_user
    ):
        """Test that None is returned when session is missing."""
        # Arrange
        agentic_service.session = None
        messages = [{"role": "user", "content": "test"}]

        # Act
        result = await agentic_service._check_skill_match(messages, test_user)

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_check_skill_match_returns_none_without_skills(
        self, agentic_service, test_user
    ):
        """Test that None is returned when no skills are loaded."""
        # Arrange
        agentic_service.skills_context = {}
        messages = [{"role": "user", "content": "test"}]

        # Act
        result = await agentic_service._check_skill_match(messages, test_user)

        # Assert
        assert result is None

    @pytest.mark.asyncio
    @patch('app.services.agentic_service.SkillDiscoveryService')
    async def test_check_skill_match_returns_none_for_no_match(
        self, mock_discovery_service_class, agentic_service, test_user
    ):
        """Test that None is returned when no skill matches."""
        # Arrange
        messages = [{"role": "user", "content": "unmatched message"}]

        mock_discovery = Mock()
        mock_discovery.match_skill_by_intent.return_value = None
        mock_discovery_service_class.return_value = mock_discovery

        agentic_service._session_id = 1
        agentic_service.skills_context = {"skills": [{"name": "test_workflow"}]}

        # Act
        result = await agentic_service._check_skill_match(messages, test_user)

        # Assert
        assert result is None

    @pytest.mark.asyncio
    @patch('app.services.agentic_service.SkillDiscoveryService')
    async def test_check_skill_match_handles_exception(
        self, mock_discovery_service_class, agentic_service, test_user
    ):
        """Test that exceptions during skill matching are handled gracefully."""
        # Arrange
        messages = [{"role": "user", "content": "test"}]

        mock_discovery_service_class.side_effect = Exception("Discovery error")

        agentic_service._session_id = 1
        agentic_service.skills_context = {"skills": [{"name": "test_workflow"}]}

        # Act
        result = await agentic_service._check_skill_match(messages, test_user)

        # Assert - should not raise, just log error and return None
        assert result is None


class TestSkillExecutionIntegration:
    """Test end-to-end skill execution in chat flow."""

    @pytest.mark.asyncio
    @patch('app.services.agentic_service.SkillDiscoveryService')
    @patch('app.repositories.skill_repository.SkillRepository')
    @patch('app.services.workflow_runtime_service.WorkflowRuntimeService')
    @patch('app.services.agentic_service.invoke_skill')
    async def test_execute_with_skill_match(
        self, mock_invoke, mock_workflow_service, mock_skill_repo,
        mock_discovery_service_class, agentic_service, test_user, test_skill
    ):
        """Test that execute() returns skill result when skill matches."""
        # Arrange
        messages = [{"role": "user", "content": "run the test workflow"}]

        # Mock skill loading
        mock_workflow_service.load_active_skills.return_value = []
        mock_skill_repo.get_active_skills.return_value = [test_skill]
        mock_workflow_service.get_skills_context.return_value = {
            "skill_names": ["test_workflow"],
            "skills": [{"name": "test_workflow", "description": "Test"}]
        }

        # Mock skill matching
        mock_discovery = Mock()
        mock_discovery.match_skill_by_intent.return_value = test_skill
        mock_discovery_service_class.return_value = mock_discovery

        # Mock skill execution
        mock_invoke.return_value = {
            "success": True,
            "skill_name": "test_workflow",
            "message": "Skill executed successfully",
            "context": {"result": "done"}
        }

        # Act
        result = await agentic_service.execute(
            messages=messages,
            user=test_user,
            session_id=1,
            model="qwen2.5-coder:7b"
        )

        # Assert
        assert isinstance(result, AgenticResult)
        assert result.stopped_reason == "skill_executed"
        assert result.metadata is not None
        assert result.metadata["skill_name"] == "test_workflow"
        assert result.final_response == "Skill executed successfully"

    @pytest.mark.asyncio
    @patch('app.services.agentic_service.SkillDiscoveryService')
    @patch('app.repositories.skill_repository.SkillRepository')
    @patch('app.services.workflow_runtime_service.WorkflowRuntimeService')
    async def test_execute_continues_without_skill_match(
        self, mock_workflow_service, mock_skill_repo, mock_discovery_service_class,
        agentic_service, test_user, test_skill, mock_ollama_client
    ):
        """Test that execute() continues normally when no skill matches."""
        # Arrange
        messages = [{"role": "user", "content": "unmatched message"}]

        # Mock skill loading
        mock_workflow_service.load_active_skills.return_value = []
        mock_skill_repo.get_active_skills.return_value = [test_skill]
        mock_workflow_service.get_skills_context.return_value = {
            "skill_names": ["test_workflow"],
            "skills": [{"name": "test_workflow", "description": "Test"}]
        }

        # Mock skill matching (no match)
        mock_discovery = Mock()
        mock_discovery.match_skill_by_intent.return_value = None
        mock_discovery_service_class.return_value = mock_discovery

        # Mock LLM response
        mock_ollama_client.generate_chat_completion_with_tools = AsyncMock(
            return_value={
                "type": "text",
                "content": "I don't understand that request."
            }
        )

        # Act
        result = await agentic_service.execute(
            messages=messages,
            user=test_user,
            session_id=1,
            model="qwen2.5-coder:7b"
        )

        # Assert
        assert isinstance(result, AgenticResult)
        assert result.stopped_reason == "completed"
        assert "skill" not in result.stopped_reason

    @pytest.mark.asyncio
    @patch('app.repositories.skill_repository.SkillRepository')
    @patch('app.services.workflow_runtime_service.WorkflowRuntimeService')
    async def test_system_prompt_includes_skills(
        self, mock_workflow_service, mock_skill_repo,
        agentic_service, test_user, test_skill, mock_ollama_client
    ):
        """Test that system prompt is enhanced with skill information."""
        # Arrange
        messages = [{"role": "user", "content": "hello"}]

        # Mock skill loading
        mock_workflow_service.load_active_skills.return_value = []
        mock_skill_repo.get_active_skills.return_value = [test_skill]
        mock_workflow_service.get_skills_context.return_value = {
            "skill_names": ["test_workflow"],
            "skills": [{
                "name": "test_workflow",
                "description": "Test workflow skill",
                "intent_patterns": ["test workflow"]
            }]
        }

        # Mock LLM response and capture the messages sent
        captured_messages = None
        async def capture_messages(messages, tools=None, model=None):
            nonlocal captured_messages
            captured_messages = messages
            return {"type": "text", "content": "Hello!"}

        mock_ollama_client.generate_chat_completion_with_tools = capture_messages

        # Act
        await agentic_service.execute(
            messages=messages,
            user=test_user,
            session_id=1,
            model="qwen2.5-coder:7b"
        )

        # Assert
        assert captured_messages is not None
        system_msg = next((m for m in captured_messages if m.get("role") == "system"), None)
        assert system_msg is not None
        assert "Available Skills" in system_msg["content"]
        assert "test_workflow" in system_msg["content"]
        assert "Test workflow skill" in system_msg["content"]
