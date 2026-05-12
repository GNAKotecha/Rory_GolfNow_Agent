#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${SCRIPT_DIR}"

echo "🚀 Starting Internal Agent on RunPod (Native)..."
echo "================================================"
echo ""

load_env_file() {
  local env_file="$1"
  if [ -f "${env_file}" ]; then
    echo "📄 Loading env: ${env_file}"
    set -a
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
  fi
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts="${3:-30}"
  local sleep_s="${4:-1}"
  local i
  for i in $(seq 1 "${attempts}"); do
    if curl -s "${url}" >/dev/null 2>&1; then
      echo "   ✅ ${label} is ready"
      return 0
    fi
    sleep "${sleep_s}"
  done
  return 1
}

require_env() {
  local var_name="$1"
  if [ -z "${!var_name:-}" ]; then
    echo "❌ ERROR: ${var_name} not set"
    exit 1
  fi
}

select_python_bin() {
  for candidate in python3.11 python3.10 python3; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      echo "${candidate}"
      return 0
    fi
  done
  return 1
}

load_env_file "${REPO_ROOT}/infrastructure/.env"
load_env_file "${SCRIPT_DIR}/.env"
echo ""

PYTHON_BIN="${PYTHON_BIN:-$(select_python_bin || true)}"
if [ -z "${PYTHON_BIN}" ]; then
  echo "❌ ERROR: No python3 interpreter found"
  exit 1
fi

PYTHON_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_MAJOR="${PYTHON_VERSION%%.*}"
PY_MINOR="${PYTHON_VERSION##*.}"
if [ "${PY_MAJOR}" -lt 3 ] || { [ "${PY_MAJOR}" -eq 3 ] && [ "${PY_MINOR}" -lt 10 ]; }; then
  echo "❌ ERROR: ${PYTHON_BIN} is Python ${PYTHON_VERSION}, but this stack requires Python 3.10+"
  exit 1
fi
echo "🐍 Using ${PYTHON_BIN} (Python ${PYTHON_VERSION})"

# Backward compatibility for legacy variable names
if [ -n "${BACKEND_MODE:-}" ] && [ -z "${BACKEND_ENV:-}" ]; then
  export BACKEND_ENV="${BACKEND_MODE}"
fi
if [ -n "${MCP_SERVER_URL:-}" ] && [ -z "${MCP_GATEWAY_URL:-}" ]; then
  export MCP_GATEWAY_URL="${MCP_SERVER_URL}"
fi

# Defaults (can be overridden in infrastructure/.env)
export HOST="${HOST:-0.0.0.0}"
export PORT="${BACKEND_PORT:-8000}"
export BACKEND_ENV="${BACKEND_ENV:-development}"
export GATEWAY_ENV="${GATEWAY_ENV:-local}"
export GATEWAY_PORT="${GATEWAY_PORT:-8090}"
export GATEWAY_HOST="${GATEWAY_HOST:-0.0.0.0}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5-coder:32b}"
export VENV_DIR="${VENV_DIR:-venv}"

# Runpod/native defaults: disable auxiliary MCP servers and bash tool
# (test-mcp and mock-search are not deployed in Runpod native mode)
export ENABLE_AUX_MCP_SERVERS="${ENABLE_AUX_MCP_SERVERS:-false}"
export ENABLE_BASH_TOOL="${ENABLE_BASH_TOOL:-false}"

# Native mode runs ollama locally, so normalize docker-compose URL if present.
if [ "${OLLAMA_URL:-}" = "http://ollama:11434" ]; then
  export OLLAMA_URL="http://localhost:11434"
fi
export OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"

# Decide whether this script should start a local gateway.
# If MCP_GATEWAY_URL points to ngrok/remote, default to skipping local gateway startup.
if [ -z "${START_GATEWAY_LOCAL:-}" ]; then
  case "${MCP_GATEWAY_URL:-}" in
    ""|"http://localhost:8090"|"http://127.0.0.1:8090")
      export START_GATEWAY_LOCAL="true"
      ;;
    *)
      export START_GATEWAY_LOCAL="false"
      ;;
  esac
fi

if [ "${START_GATEWAY_LOCAL}" = "true" ] && [ -z "${MCP_GATEWAY_URL:-}" ]; then
  export MCP_GATEWAY_URL="http://localhost:8090"
fi

if [ "${START_GATEWAY_LOCAL}" != "true" ] && [ -z "${MCP_GATEWAY_URL:-}" ]; then
  echo "❌ ERROR: MCP_GATEWAY_URL is required when START_GATEWAY_LOCAL=false"
  exit 1
fi

# Required environment variables
require_env "DATABASE_URL"
require_env "SECRET_KEY"
require_env "GATEWAY_SERVICE_TOKEN"
echo "✅ Required environment variables are set"
echo "   MCP_GATEWAY_URL: ${MCP_GATEWAY_URL:-http://localhost:8090}"
echo "   ENABLE_AUX_MCP_SERVERS: ${ENABLE_AUX_MCP_SERVERS}"
echo ""

# Install Ollama if not present
if ! command -v ollama >/dev/null 2>&1; then
  echo "📦 Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
  echo ""
fi

OLLAMA_PID=""
if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "ℹ️  Ollama is already running"
else
  echo "🔧 Starting Ollama service..."
  ollama serve >/tmp/ollama.log 2>&1 &
  OLLAMA_PID="$!"
  echo "   Ollama PID: ${OLLAMA_PID}"
fi
echo "⏳ Waiting for Ollama to be ready..."
if ! wait_for_url "http://localhost:11434/api/tags" "Ollama"; then
  echo "   ❌ Ollama failed to start"
  exit 1
fi
echo ""

echo "📦 Pulling ${OLLAMA_MODEL} model (this can take several minutes)..."
ollama pull "${OLLAMA_MODEL}"
echo "✅ Model ready"
echo ""

if [ ! -x "${VENV_DIR}/bin/python" ]; then
  echo "🔧 Creating Python virtual environment..."
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi
source "${VENV_DIR}/bin/activate"

if [ "${SKIP_PIP_INSTALL:-false}" != "true" ]; then
  echo "📦 Installing Python dependencies..."
  pip install --upgrade pip
  pip install -r requirements.txt
  echo ""
fi

GATEWAY_PID=""
if [ "${START_GATEWAY_LOCAL}" = "true" ]; then
  echo "🔧 Starting Gateway MCP on port ${GATEWAY_PORT}..."
  export GATEWAY_ENV="local"
  "${VENV_DIR}/bin/python" -m gateway_mcp.main >/tmp/gateway.log 2>&1 &
  GATEWAY_PID="$!"
  echo "   Gateway PID: ${GATEWAY_PID}"
  echo "⏳ Waiting for Gateway MCP to be ready..."
  if ! wait_for_url "http://localhost:${GATEWAY_PORT}/health" "Gateway MCP"; then
    echo "   ❌ Gateway failed to start"
    echo "   Check logs: tail -f /tmp/gateway.log"
    exit 1
  fi
else
  echo "ℹ️  Using remote gateway: ${MCP_GATEWAY_URL}"
fi
echo ""

echo "🔧 Starting backend on port ${PORT}..."
uvicorn app.main:app --host "${HOST}" --port "${PORT}" >/tmp/backend.log 2>&1 &
BACKEND_PID="$!"
echo "   Backend PID: ${BACKEND_PID}"
echo "⏳ Waiting for backend to be ready..."
if ! wait_for_url "http://localhost:${PORT}/health" "Backend"; then
  echo "   ❌ Backend failed to start"
  echo "   Check logs: tail -f /tmp/backend.log"
  exit 1
fi
echo ""

echo "================================================"
echo "✅ All services started!"
echo "================================================"
echo ""
echo "Services:"
echo "  - Backend:      http://localhost:${PORT}"
if [ "${START_GATEWAY_LOCAL}" = "true" ]; then
  echo "  - Gateway MCP:  http://localhost:${GATEWAY_PORT}"
else
  echo "  - Gateway MCP:  ${MCP_GATEWAY_URL} (remote)"
fi
echo "  - Ollama:       http://localhost:11434"
echo ""
echo "Public URL (via RunPod):"
echo "  - Use your RunPod proxy URL for port ${PORT}"
echo ""
echo "Test health:"
echo "  curl http://localhost:${PORT}/health"
if [ "${START_GATEWAY_LOCAL}" = "true" ]; then
  echo "  curl http://localhost:${GATEWAY_PORT}/health"
fi
echo ""
echo "View logs:"
echo "  tail -f /tmp/backend.log"
echo "  tail -f /tmp/ollama.log"
if [ "${START_GATEWAY_LOCAL}" = "true" ]; then
  echo "  tail -f /tmp/gateway.log"
fi
echo ""
echo "PIDs:"
if [ -n "${OLLAMA_PID}" ]; then
  echo "  Ollama:  ${OLLAMA_PID}"
else
  echo "  Ollama:  (already running)"
fi
if [ -n "${GATEWAY_PID}" ]; then
  echo "  Gateway: ${GATEWAY_PID}"
fi
echo "  Backend: ${BACKEND_PID}"
echo ""
echo "Stop services started by this script:"
STOP_CMD="kill ${BACKEND_PID}"
if [ -n "${GATEWAY_PID}" ]; then
  STOP_CMD="${STOP_CMD} ${GATEWAY_PID}"
fi
if [ -n "${OLLAMA_PID}" ]; then
  STOP_CMD="${STOP_CMD} ${OLLAMA_PID}"
fi
echo "  ${STOP_CMD}"
echo ""
