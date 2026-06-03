"""Workflow runtime service for loading and managing tenant workflows at runtime.

This service provides runtime integration for tenant-managed workflows,
enabling AgenticService to load and execute custom tenant workflows.
"""
from typing import Optional, List, Dict, Any
import logging
from sqlalchemy.orm import Session
from app.models.models import TenantWorkflow, TenantSkill

logger = logging.getLogger(__name__)


class WorkflowRuntimeService:
    """Service for loading and managing tenant workflows at runtime."""

    @staticmethod
    def load_active_workflow(
        session: Session,
        tenant_id: int,
        workflow_name: str
    ) -> Optional[TenantWorkflow]:
        """
        Load active workflow for given tenant and workflow_name.

        Args:
            session: Database session
            tenant_id: ID of the tenant
            workflow_name: Name of the workflow to load

        Returns:
            TenantWorkflow object if found and active, None otherwise

        Example:
            workflow = WorkflowRuntimeService.load_active_workflow(
                session, tenant_id=1, workflow_name="club_creation"
            )
            if workflow:
                context = WorkflowRuntimeService.get_workflow_context(workflow)
        """
        try:
            workflow = session.query(TenantWorkflow).filter(
                TenantWorkflow.tenant_id == tenant_id,
                TenantWorkflow.workflow_name == workflow_name,
                TenantWorkflow.is_active == True
            ).first()

            if workflow:
                logger.debug(f"Loaded workflow '{workflow_name}' v{workflow.version} for tenant {tenant_id}")
            else:
                logger.debug(f"No active workflow '{workflow_name}' found for tenant {tenant_id}")

            return workflow
        except Exception as e:
            logger.error(
                f"Error loading workflow '{workflow_name}' for tenant {tenant_id}: {e}",
                extra={
                    "tenant_id": tenant_id,
                    "workflow_name": workflow_name,
                    "error": str(e),
                }
            )
            return None

    @staticmethod
    def load_active_skills(
        session: Session,
        tenant_id: int
    ) -> List[TenantSkill]:
        """
        Load all active skills for tenant.

        Args:
            session: Database session
            tenant_id: ID of the tenant

        Returns:
            List of active TenantSkill objects (empty list if none found)

        Example:
            skills = WorkflowRuntimeService.load_active_skills(session, tenant_id=1)
            context = WorkflowRuntimeService.get_skills_context(skills)
        """
        try:
            skills = session.query(TenantSkill).filter(
                TenantSkill.tenant_id == tenant_id,
                TenantSkill.is_active == True
            ).all()

            logger.info(f"Loaded {len(skills)} active skills for tenant {tenant_id}")
            return skills
        except Exception as e:
            logger.warning(f"Error loading skills for tenant {tenant_id}: {e}")
            return []

    @staticmethod
    def get_workflow_context(
        workflow: TenantWorkflow
    ) -> Dict[str, Any]:
        """
        Extract runtime context from workflow definition.

        Args:
            workflow: TenantWorkflow object

        Returns:
            Dictionary containing workflow runtime context with default values
            for missing fields

        Example:
            {
                "name": "club_creation",
                "version": 1,
                "approval_gates": ["manager"],
                "tools_required": ["github", "jira"],
                "max_retries": 3,
                "timeout_seconds": 300,
                "custom_rules": {}
            }
        """
        definition = workflow.workflow_definition or {}

        context = {
            "name": workflow.workflow_name,
            "version": workflow.version,
            "approval_gates": definition.get("approval_gates", []),
            "tools_required": definition.get("tools_required", []),
            "max_retries": definition.get("max_retries", 3),
            "timeout_seconds": definition.get("timeout_seconds", 300),
            "custom_rules": definition.get("custom_rules", {})
        }

        logger.debug(f"Extracted context for workflow '{workflow.workflow_name}' v{workflow.version}")
        return context

    @staticmethod
    def get_skills_context(
        skills: List[TenantSkill]
    ) -> Dict[str, Any]:
        """
        Extract runtime context from active skills.

        Args:
            skills: List of TenantSkill objects

        Returns:
            Dictionary containing skill names and their data

        Example:
            {
                "skill_names": ["github_pr_automation", "jira_ticket_creation"],
                "skill_data": {
                    "github_pr_automation": {"type": "workflow", "steps": [...]},
                    "jira_ticket_creation": {"type": "tool", "config": {...}}
                }
            }
        """
        context = {
            "skill_names": [skill.skill_name for skill in skills],
            "skill_data": {
                skill.skill_name: skill.skill_data or {}
                for skill in skills
            }
        }

        logger.debug(f"Extracted context for {len(skills)} skills")
        return context

    @staticmethod
    def log_workflow_execution(
        run_id: str,
        tenant_id: int,
        workflow_name: str,
        workflow_version: int,
        action: str
    ) -> None:
        """
        Log workflow execution provenance for analytics.

        Args:
            run_id: Unique run identifier
            tenant_id: ID of the tenant
            workflow_name: Name of the workflow
            workflow_version: Version of the workflow
            action: Action type ("started", "step_completed", "error", "finished")

        Example:
            WorkflowRuntimeService.log_workflow_execution(
                run_id="abc123",
                tenant_id=1,
                workflow_name="club_creation",
                workflow_version=1,
                action="started"
            )
        """
        log_message = (
            f"[{run_id}] tenant={tenant_id} workflow={workflow_name} "
            f"v{workflow_version} action={action}"
        )
        logger.info(log_message)
