#!/bin/bash
set -e

# Run Docker image locally for testing
# Usage: ./scripts/run-local-docker.sh [tag]

TAG=${1:-latest}
IMAGE_NAME="internal-agent-backend"
CONTAINER_NAME="agent-backend-test"

echo "🚀 Running Docker container: ${IMAGE_NAME}:${TAG}"
echo "================================================"

# Stop and remove existing container if running
docker rm -f ${CONTAINER_NAME} 2>/dev/null || true

# Run container
docker run \
  --name ${CONTAINER_NAME} \
  --rm \
  -p 8000:8000 \
  -e DATABASE_URL="${DATABASE_URL:-sqlite:///./data/agent.db}" \
  -e OLLAMA_URL="${OLLAMA_URL:-http://host.docker.internal:11434}" \
  -e SECRET_KEY="${SECRET_KEY:-dev-secret-key-change-in-production}" \
  ${IMAGE_NAME}:${TAG}

echo ""
echo "Container stopped"
