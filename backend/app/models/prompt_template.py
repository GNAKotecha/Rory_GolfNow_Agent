from sqlalchemy import Column, Integer, String, Text, JSON, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from typing import Optional
from app.db.session import Base


class PromptTemplate(Base):
    """Prompt template for LLM interactions with versioning support.

    Attributes:
        id: Primary key
        name: Unique template identifier (e.g., 'teesheet_config_generation')
        description: Human-readable description
        current_version_id: ID of currently active version
        created_at: Creation timestamp
        versions: All versions of this template
    """

    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    current_version_id = Column(Integer, ForeignKey("prompt_template_versions.id", use_alter=True), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    versions = relationship("PromptTemplateVersion", back_populates="template", foreign_keys="PromptTemplateVersion.template_id")


class PromptTemplateVersion(Base):
    """Version of a prompt template with metrics tracking.

    Attributes:
        id: Primary key
        template_id: Foreign key to parent template
        version_number: Sequential version number (1, 2, 3, ...)
        prompt_text: Actual prompt with {{variable}} placeholders
        variables: Schema of variables (JSON dict)
        is_active: Whether this version is currently in use
        usage_count: Number of times this version was used
        success_count: Number of successful executions
        avg_latency_ms: Average LLM response latency
        created_at: Version creation timestamp
        created_by: User ID who created this version
        notes: Optional notes about this version
        template: Relationship to parent template
    """

    __tablename__ = "prompt_template_versions"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("prompt_templates.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    prompt_text = Column(Text, nullable=False)
    variables = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, default=False, nullable=False)
    usage_count = Column(Integer, default=0, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    avg_latency_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)

    template = relationship("PromptTemplate", back_populates="versions", foreign_keys=[template_id])

    def calculate_success_rate(self) -> Optional[float]:
        """Calculate success rate for this version.

        Returns:
            Success rate (0.0-1.0) or None if no usage
        """
        if self.usage_count == 0:
            return None
        return self.success_count / self.usage_count

    def update_metrics(self, success: bool, latency_ms: float):
        """Update metrics after prompt execution.

        Args:
            success: Whether execution succeeded
            latency_ms: LLM response latency in milliseconds
        """
        self.usage_count += 1
        if success:
            self.success_count += 1

        if self.avg_latency_ms is None:
            self.avg_latency_ms = latency_ms
        else:
            self.avg_latency_ms = (self.avg_latency_ms * 0.9) + (latency_ms * 0.1)
