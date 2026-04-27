"""Tests for worker isolation configuration.

These tests verify that isolation configuration is properly defined.
Real isolation verification requires Docker inspection in running containers.
"""
import yaml
import os


def test_docker_compose_worker_defined():
    """Test that worker service is defined in docker-compose.yml."""
    compose_path = os.path.join(
        os.path.dirname(__file__),
        "../../infrastructure/docker-compose.yml"
    )

    if not os.path.exists(compose_path):
        # Skip if docker-compose.yml not found (e.g., in CI)
        return

    with open(compose_path, "r") as f:
        compose = yaml.safe_load(f)

    assert "services" in compose
    assert "worker" in compose["services"]


def test_docker_compose_worker_resource_limits():
    """Test that worker has resource limits configured."""
    compose_path = os.path.join(
        os.path.dirname(__file__),
        "../../infrastructure/docker-compose.yml"
    )

    if not os.path.exists(compose_path):
        return

    with open(compose_path, "r") as f:
        compose = yaml.safe_load(f)

    worker = compose["services"]["worker"]

    # Check resource limits
    assert "deploy" in worker
    assert "resources" in worker["deploy"]
    assert "limits" in worker["deploy"]["resources"]

    limits = worker["deploy"]["resources"]["limits"]
    assert "cpus" in limits
    assert "memory" in limits


def test_docker_compose_worker_read_only():
    """Test that worker filesystem is read-only."""
    compose_path = os.path.join(
        os.path.dirname(__file__),
        "../../infrastructure/docker-compose.yml"
    )

    if not os.path.exists(compose_path):
        return

    with open(compose_path, "r") as f:
        compose = yaml.safe_load(f)

    worker = compose["services"]["worker"]
    assert worker.get("read_only") is True


def test_docker_compose_worker_security():
    """Test that worker has security configurations."""
    compose_path = os.path.join(
        os.path.dirname(__file__),
        "../../infrastructure/docker-compose.yml"
    )

    if not os.path.exists(compose_path):
        return

    with open(compose_path, "r") as f:
        compose = yaml.safe_load(f)

    worker = compose["services"]["worker"]

    # Check capability drops
    assert "cap_drop" in worker
    assert "ALL" in worker["cap_drop"]

    # Check security options
    assert "security_opt" in worker
    assert "no-new-privileges:true" in worker["security_opt"]


def test_worker_dockerfile_exists():
    """Test that worker Dockerfile exists."""
    dockerfile_path = os.path.join(
        os.path.dirname(__file__),
        "../Dockerfile.worker"
    )

    assert os.path.exists(dockerfile_path)


def test_worker_dockerfile_uses_nonroot_user():
    """Test that worker Dockerfile creates and uses non-root user."""
    dockerfile_path = os.path.join(
        os.path.dirname(__file__),
        "../Dockerfile.worker"
    )

    if not os.path.exists(dockerfile_path):
        return

    with open(dockerfile_path, "r") as f:
        content = f.read()

    # Check for user creation
    assert "groupadd" in content
    assert "useradd" in content
    assert "worker" in content

    # Check for USER directive
    assert "USER worker" in content


def test_worker_requirements_minimal():
    """Test that worker requirements are minimal."""
    requirements_path = os.path.join(
        os.path.dirname(__file__),
        "../requirements-worker.txt"
    )

    if not os.path.exists(requirements_path):
        return

    with open(requirements_path, "r") as f:
        lines = f.readlines()

    packages = [line.strip() for line in lines if line.strip() and not line.startswith("#")]

    # Worker should only need minimal dependencies
    assert len(packages) <= 5

    # Should include FastAPI and Uvicorn
    package_names = [p.split("==")[0].lower() for p in packages]
    assert "fastapi" in package_names
    assert "uvicorn" in package_names
