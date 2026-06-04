#!/bin/bash
set -e

echo "🚀 Starting Gateway MCP Server..."
echo "================================================"

# Ensure venv is activated
VENV_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/venv"
if [ ! -d "$VENV_PATH" ]; then
  echo "❌ ERROR: Virtual environment not found at $VENV_PATH"
  echo "   Create it with: python3 -m venv venv"
  exit 1
fi

source "$VENV_PATH/bin/activate"

# Set defaults if not provided (but don't override if already set by parent shell)
export GATEWAY_PORT=${GATEWAY_PORT:-8090}
export GATEWAY_HOST=${GATEWAY_HOST:-0.0.0.0}
export GATEWAY_ENV=${GATEWAY_ENV:-local}
export GATEWAY_CREDENTIAL_ENCRYPTION_KEY=${GATEWAY_CREDENTIAL_ENCRYPTION_KEY:-"test-key-32-chars-minimum-1234567"}
# IMPORTANT: Do not set default for GATEWAY_SERVICE_TOKEN - it MUST come from environment
if [ -z "$GATEWAY_SERVICE_TOKEN" ]; then
  echo "⚠️  WARNING: GATEWAY_SERVICE_TOKEN not set - auth will fail"
  export GATEWAY_SERVICE_TOKEN="invalid-token-please-set-env-var"
fi

echo "✅ Environment Configuration:"
echo "   Port: $GATEWAY_PORT"
echo "   Host: $GATEWAY_HOST"
echo "   Environment: $GATEWAY_ENV"
echo "   Executor Backend: ${EXECUTOR_BACKEND:-mock}"
echo ""

# Navigate to backend directory
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BACKEND_DIR"

echo "Starting server from: $BACKEND_DIR"
echo "================================================"
echo ""

# Start the server
python -m gateway_mcp.main
