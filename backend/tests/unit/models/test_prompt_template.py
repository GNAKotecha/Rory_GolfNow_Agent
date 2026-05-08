import pytest
from datetime import datetime, timezone
from app.models.prompt_template import PromptTemplate, PromptTemplateVersion


def test_create_prompt_template(db_session):
    """Should create prompt template with initial version."""
    template = PromptTemplate(
        name="teesheet_config_generation",
        description="Generate club configuration for teesheet onboarding",
        current_version_id=None,
        created_at=datetime.now(timezone.utc)
    )

    db_session.add(template)
    db_session.commit()

    assert template.id is not None
    assert template.name == "teesheet_config_generation"


def test_create_prompt_template_version(db_session):
    """Should create version of prompt template."""
    template = PromptTemplate(
        name="test_template",
        description="Test template",
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(template)
    db_session.commit()

    version = PromptTemplateVersion(
        template_id=template.id,
        version_number=1,
        prompt_text="You are a helpful assistant. Generate config for {{club_name}}.",
        variables={"club_name": "string", "club_id": "string"},
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(version)
    db_session.commit()

    assert version.id is not None
    assert version.version_number == 1
    assert "{{club_name}}" in version.prompt_text


def test_prompt_template_version_metrics(db_session):
    """Should track metrics for prompt template version."""
    template = PromptTemplate(
        name="test_template",
        description="Test",
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(template)
    db_session.commit()

    version = PromptTemplateVersion(
        template_id=template.id,
        version_number=1,
        prompt_text="Test prompt",
        variables={},
        is_active=True,
        usage_count=10,
        success_count=8,
        avg_latency_ms=250.5,
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(version)
    db_session.commit()

    success_rate = version.success_count / version.usage_count
    assert success_rate == 0.8
    assert version.avg_latency_ms == 250.5


def test_get_active_version(db_session):
    """Should retrieve active version of template."""
    template = PromptTemplate(
        name="test_template",
        description="Test",
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(template)
    db_session.commit()

    old_version = PromptTemplateVersion(
        template_id=template.id,
        version_number=1,
        prompt_text="Old prompt",
        variables={},
        is_active=False,
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(old_version)

    new_version = PromptTemplateVersion(
        template_id=template.id,
        version_number=2,
        prompt_text="New prompt",
        variables={},
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(new_version)
    db_session.commit()

    active = db_session.query(PromptTemplateVersion).filter(
        PromptTemplateVersion.template_id == template.id,
        PromptTemplateVersion.is_active == True
    ).first()

    assert active.version_number == 2
    assert active.prompt_text == "New prompt"


def test_update_metrics_and_success_rate(db_session):
    """Should update metrics correctly and calculate success rate via public methods."""
    template = PromptTemplate(
        name="metrics_test_template",
        description="Test",
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(template)
    db_session.commit()

    version = PromptTemplateVersion(
        template_id=template.id,
        version_number=1,
        prompt_text="Test prompt",
        variables={},
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(version)
    db_session.commit()

    # Initial state: no usage
    assert version.calculate_success_rate() is None

    # First call: success=True, latency=100.0 — initializes avg_latency_ms
    version.update_metrics(success=True, latency_ms=100.0)
    assert version.usage_count == 1
    assert version.success_count == 1
    assert version.avg_latency_ms == 100.0
    assert version.calculate_success_rate() == 1.0

    # Second call: success=False, latency=200.0 — weighted avg = 100*0.9 + 200*0.1 = 110.0
    version.update_metrics(success=False, latency_ms=200.0)
    assert version.usage_count == 2
    assert version.success_count == 1
    assert version.avg_latency_ms == pytest.approx(110.0)
    assert version.calculate_success_rate() == 0.5
