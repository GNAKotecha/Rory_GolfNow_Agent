"""Tests for TestRun and TestScenarioResult models."""
import pytest
from datetime import datetime
from uuid import uuid4
from sqlalchemy import text

from app.models import TestRun, TestScenarioResult
from app.models.models import Tenant
from app.db.session import SessionLocal, Base, engine


@pytest.fixture(scope="session", autouse=True)
def setup_all_tables():
    """Create all tables once per test session."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def cleanup_tables(setup_all_tables):
    """Clean test data between test functions."""
    yield
    # Delete test data
    with SessionLocal() as session:
        try:
            session.execute(text("DELETE FROM test_scenario_results"))
            session.execute(text("DELETE FROM test_runs"))
            session.execute(text("DELETE FROM tenants"))
            session.commit()
        except Exception:
            session.rollback()


@pytest.fixture
def db_session():
    """Provide a database session."""
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def test_tenant(db_session):
    """Create a test tenant."""
    tenant = Tenant(
        name="test-tenant",
        slug="test-tenant"
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


class TestTestRunModel:
    """Tests for TestRun model."""

    def test_create_test_run_with_all_fields(self, db_session, test_tenant):
        """Test creating a TestRun with all required fields."""
        run_id = str(uuid4())
        test_run = TestRun(
            run_id=run_id,
            tenant_id=test_tenant.id,
            timestamp=datetime.utcnow(),
            environment="dev",
            total_scenarios=5,
            passed=3,
            failed=2,
            duration_seconds=45.5,
            tags=["core", "jira"]
        )
        db_session.add(test_run)
        db_session.commit()
        db_session.refresh(test_run)

        assert test_run.id is not None
        assert test_run.run_id == run_id
        assert test_run.tenant_id == test_tenant.id
        assert test_run.environment == "dev"
        assert test_run.total_scenarios == 5
        assert test_run.passed == 3
        assert test_run.failed == 2
        assert test_run.duration_seconds == 45.5
        assert test_run.tags == ["core", "jira"]
        assert test_run.created_at is not None

    def test_test_run_unique_run_id(self, db_session, test_tenant):
        """Test that run_id must be unique."""
        run_id = str(uuid4())
        test_run_1 = TestRun(
            run_id=run_id,
            tenant_id=test_tenant.id,
            timestamp=datetime.utcnow(),
            environment="dev",
            total_scenarios=1,
            passed=1,
            failed=0,
            duration_seconds=10.0
        )
        db_session.add(test_run_1)
        db_session.commit()

        # Try to create another with same run_id
        test_run_2 = TestRun(
            run_id=run_id,
            tenant_id=test_tenant.id,
            timestamp=datetime.utcnow(),
            environment="staging",
            total_scenarios=1,
            passed=1,
            failed=0,
            duration_seconds=10.0
        )
        db_session.add(test_run_2)

        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()

    def test_test_run_defaults(self, db_session, test_tenant):
        """Test TestRun model defaults."""
        run_id = str(uuid4())
        test_run = TestRun(
            run_id=run_id,
            tenant_id=test_tenant.id,
            timestamp=datetime.utcnow(),
            environment="prod",
            duration_seconds=30.0
        )
        db_session.add(test_run)
        db_session.commit()
        db_session.refresh(test_run)

        assert test_run.total_scenarios == 0
        assert test_run.passed == 0
        assert test_run.failed == 0
        assert test_run.tags == []
        assert test_run.created_at is not None

    def test_test_run_environment_values(self, db_session, test_tenant):
        """Test TestRun with different environment values."""
        environments = ["dev", "staging", "prod"]
        for env in environments:
            test_run = TestRun(
                run_id=str(uuid4()),
                tenant_id=test_tenant.id,
                timestamp=datetime.utcnow(),
                environment=env,
                duration_seconds=10.0
            )
            db_session.add(test_run)
        db_session.commit()

        # Verify all were created
        runs = db_session.query(TestRun).filter_by(tenant_id=test_tenant.id).all()
        assert len(runs) == 3
        assert {r.environment for r in runs} == set(environments)


class TestTestScenarioResultModel:
    """Tests for TestScenarioResult model."""

    def test_create_scenario_result_with_all_fields(self, db_session, test_tenant):
        """Test creating a TestScenarioResult with all fields."""
        test_run = TestRun(
            run_id=str(uuid4()),
            tenant_id=test_tenant.id,
            timestamp=datetime.utcnow(),
            environment="dev",
            total_scenarios=1,
            passed=1,
            failed=0,
            duration_seconds=30.0
        )
        db_session.add(test_run)
        db_session.commit()

        turn_results = [
            {"turn_num": 1, "status": "success", "tool_calls": 2},
            {"turn_num": 2, "status": "success", "tool_calls": 1}
        ]
        scenario_result = TestScenarioResult(
            test_run_id=test_run.id,
            scenario_name="booking_workflow",
            success=True,
            turn_count=2,
            tool_calls_count=3,
            turn_results=turn_results
        )
        db_session.add(scenario_result)
        db_session.commit()
        db_session.refresh(scenario_result)

        assert scenario_result.id is not None
        assert scenario_result.test_run_id == test_run.id
        assert scenario_result.scenario_name == "booking_workflow"
        assert scenario_result.success is True
        assert scenario_result.turn_count == 2
        assert scenario_result.tool_calls_count == 3
        assert scenario_result.turn_results == turn_results
        assert scenario_result.error_message is None
        assert scenario_result.created_at is not None

    def test_scenario_result_failed_with_error(self, db_session, test_tenant):
        """Test TestScenarioResult with failure status and error message."""
        test_run = TestRun(
            run_id=str(uuid4()),
            tenant_id=test_tenant.id,
            timestamp=datetime.utcnow(),
            environment="dev",
            total_scenarios=1,
            passed=0,
            failed=1,
            duration_seconds=15.0
        )
        db_session.add(test_run)
        db_session.commit()

        scenario_result = TestScenarioResult(
            test_run_id=test_run.id,
            scenario_name="payment_workflow",
            success=False,
            turn_count=2,
            tool_calls_count=2,
            error_message="Payment API returned 500"
        )
        db_session.add(scenario_result)
        db_session.commit()
        db_session.refresh(scenario_result)

        assert scenario_result.success is False
        assert scenario_result.error_message == "Payment API returned 500"

    def test_scenario_result_defaults(self, db_session, test_tenant):
        """Test TestScenarioResult model defaults."""
        test_run = TestRun(
            run_id=str(uuid4()),
            tenant_id=test_tenant.id,
            timestamp=datetime.utcnow(),
            environment="dev",
            duration_seconds=10.0
        )
        db_session.add(test_run)
        db_session.commit()

        scenario_result = TestScenarioResult(
            test_run_id=test_run.id,
            scenario_name="basic_test",
            success=True
        )
        db_session.add(scenario_result)
        db_session.commit()
        db_session.refresh(scenario_result)

        assert scenario_result.turn_count == 0
        assert scenario_result.tool_calls_count == 0
        assert scenario_result.error_message is None
        assert scenario_result.turn_results == []


class TestRelationships:
    """Tests for relationships between models."""

    def test_test_run_cascade_delete_scenarios(self, db_session, test_tenant):
        """Test that deleting TestRun cascades to TestScenarioResult."""
        test_run = TestRun(
            run_id=str(uuid4()),
            tenant_id=test_tenant.id,
            timestamp=datetime.utcnow(),
            environment="dev",
            total_scenarios=2,
            passed=2,
            failed=0,
            duration_seconds=25.0
        )
        db_session.add(test_run)
        db_session.commit()

        # Add multiple scenario results
        for i in range(3):
            scenario_result = TestScenarioResult(
                test_run_id=test_run.id,
                scenario_name=f"scenario_{i}",
                success=True,
                turn_count=1,
                tool_calls_count=1
            )
            db_session.add(scenario_result)
        db_session.commit()

        # Verify 3 scenario results exist
        scenario_count = db_session.query(TestScenarioResult).filter_by(
            test_run_id=test_run.id
        ).count()
        assert scenario_count == 3

        # Delete the test run
        test_run_id = test_run.id
        db_session.delete(test_run)
        db_session.commit()

        # Verify test_run is deleted
        deleted_run = db_session.query(TestRun).filter_by(id=test_run_id).first()
        assert deleted_run is None

        # Verify scenario results are also deleted
        remaining_scenarios = db_session.query(TestScenarioResult).filter_by(
            test_run_id=test_run_id
        ).count()
        assert remaining_scenarios == 0

    def test_test_run_relationship_to_tenant(self, db_session, test_tenant):
        """Test TestRun relationship to Tenant."""
        test_run = TestRun(
            run_id=str(uuid4()),
            tenant_id=test_tenant.id,
            timestamp=datetime.utcnow(),
            environment="dev",
            duration_seconds=10.0
        )
        db_session.add(test_run)
        db_session.commit()

        # Verify relationship works
        db_session.refresh(test_tenant)
        assert len(test_tenant.test_runs) == 1
        assert test_tenant.test_runs[0].run_id == test_run.run_id

    def test_scenario_result_relationship_to_test_run(self, db_session, test_tenant):
        """Test TestScenarioResult relationship to TestRun."""
        test_run = TestRun(
            run_id=str(uuid4()),
            tenant_id=test_tenant.id,
            timestamp=datetime.utcnow(),
            environment="dev",
            total_scenarios=2,
            passed=2,
            failed=0,
            duration_seconds=20.0
        )
        db_session.add(test_run)
        db_session.commit()

        scenarios = []
        for i in range(2):
            scenario = TestScenarioResult(
                test_run_id=test_run.id,
                scenario_name=f"scenario_{i}",
                success=True,
                turn_count=1,
                tool_calls_count=1
            )
            scenarios.append(scenario)
            db_session.add(scenario)
        db_session.commit()

        # Verify relationship
        db_session.refresh(test_run)
        assert len(test_run.scenario_results) == 2
        assert all(s.test_run_id == test_run.id for s in test_run.scenario_results)


class TestIndexes:
    """Tests for database indexes."""

    def test_scenario_results_indexed_by_scenario_name(self, db_session, test_tenant):
        """Test that scenario results can be queried by scenario_name (indexed)."""
        test_run = TestRun(
            run_id=str(uuid4()),
            tenant_id=test_tenant.id,
            timestamp=datetime.utcnow(),
            environment="dev",
            duration_seconds=10.0
        )
        db_session.add(test_run)
        db_session.commit()

        # Add multiple scenarios with same name
        for i in range(3):
            scenario = TestScenarioResult(
                test_run_id=test_run.id,
                scenario_name="common_scenario",
                success=True,
                turn_count=1,
                tool_calls_count=1
            )
            db_session.add(scenario)
        db_session.commit()

        # Query by scenario_name
        results = db_session.query(TestScenarioResult).filter_by(
            scenario_name="common_scenario"
        ).all()
        assert len(results) == 3

    def test_test_runs_indexed_by_created_at_environment(self, db_session, test_tenant):
        """Test that test runs can be queried by (created_at, environment) index."""
        # Create runs in different environments
        for env in ["dev", "staging", "prod"]:
            for i in range(2):
                test_run = TestRun(
                    run_id=str(uuid4()),
                    tenant_id=test_tenant.id,
                    timestamp=datetime.utcnow(),
                    environment=env,
                    duration_seconds=10.0
                )
                db_session.add(test_run)
        db_session.commit()

        # Query by environment
        dev_runs = db_session.query(TestRun).filter_by(
            environment="dev"
        ).all()
        assert len(dev_runs) == 2

    def test_test_runs_indexed_by_tenant_timestamp(self, db_session, test_tenant):
        """Test that test runs can be queried by (tenant_id, timestamp) index."""
        now = datetime.utcnow()
        for i in range(3):
            test_run = TestRun(
                run_id=str(uuid4()),
                tenant_id=test_tenant.id,
                timestamp=now,
                environment="dev",
                duration_seconds=10.0
            )
            db_session.add(test_run)
        db_session.commit()

        # Query by tenant_id and timestamp
        results = db_session.query(TestRun).filter(
            TestRun.tenant_id == test_tenant.id,
            TestRun.timestamp == now
        ).all()
        assert len(results) == 3
