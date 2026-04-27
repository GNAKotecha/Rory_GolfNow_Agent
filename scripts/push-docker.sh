#!/bin/bash
set -e

# Push Docker image to registry
# Usage: ./scripts/push-docker.sh [tag] [registry]

TAG=${1:-latest}
REGISTRY=${2:-docker.io}  # Default to Docker Hub
IMAGE_NAME="internal-agent-backend"

# Prompt for registry username if using Docker Hub
if [ "$REGISTRY" = "docker.io" ]; then
  read -p "Docker Hub username: " DOCKER_USERNAME
  FULL_IMAGE_NAME="${DOCKER_USERNAME}/${IMAGE_NAME}"
else
  FULL_IMAGE_NAME="${REGISTRY}/${IMAGE_NAME}"
fi

echo "📤 Pushing Docker image to registry"
echo "================================================"
echo "  Image: ${FULL_IMAGE_NAME}:${TAG}"
echo ""

# Tag image for registry
docker tag ${IMAGE_NAME}:${TAG} ${FULL_IMAGE_NAME}:${TAG}

# Push to registry
docker push ${FULL_IMAGE_NAME}:${TAG}

echo ""
echo "✅ Push complete!"
echo "   Image: ${FULL_IMAGE_NAME}:${TAG}"
echo ""
echo "To use on RunPod:"
echo "  Set Container Image to: ${FULL_IMAGE_NAME}:${TAG}"
