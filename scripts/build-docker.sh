#!/bin/bash
set -e

# Build Docker image for backend service
# Usage: ./scripts/build-docker.sh [tag]

TAG=${1:-latest}
IMAGE_NAME="internal-agent-backend"

echo "🔨 Building Docker image: ${IMAGE_NAME}:${TAG}"
echo "================================================"

cd backend

docker build \
  -t ${IMAGE_NAME}:${TAG} \
  -f Dockerfile \
  .

echo ""
echo "✅ Build complete!"
echo "   Image: ${IMAGE_NAME}:${TAG}"
echo ""
echo "To run locally:"
echo "  ./scripts/run-local-docker.sh ${TAG}"
echo ""
echo "To push to registry:"
echo "  ./scripts/push-docker.sh ${TAG}"
