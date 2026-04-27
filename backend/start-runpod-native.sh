#!/bin/bash
set -e

echo "🚀 Starting Internal Agent on RunPod (Native)..."
echo "================================================"
echo ""

# Check environment variables
if [ -z "$DATABASE_URL" ]; then
  echo "❌ ERROR: DATABASE_URL not set"
  echo "   Set it with: export DATABASE_URL=\"postgresql://...\""
  exit 1
fi

if [ -z "$SECRET_KEY" ]; then
  echo "❌ ERROR: SECRET_KEY not set"
  echo "   Generate one: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
  exit 1
fi

echo "✅ Environment variables set"
echo ""

# Install Ollama if not present
if ! command -v ollama &> /dev/null; then
  echo "📦 Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
  echo ""
fi

# Start Ollama service in background
echo "🔧 Starting Ollama service..."
ollama serve > /tmp/ollama.log 2>&1 &
OLLAMA_PID=$!
echo "   Ollama PID: $OLLAMA_PID"
echo ""

# Wait for Ollama to be ready
echo "⏳ Waiting for Ollama to be ready..."
for i in {1..30}; do
  if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "   ✅ Ollama is ready"
    break
  fi
  if [ $i -eq 30 ]; then
    echo "   ❌ Ollama failed to start"
    exit 1
  fi
  sleep 1
done
echo ""

# Pull model
echo "📦 Pulling qwen2.5-coder:32b model (this will take 10-20 minutes)..."
ollama pull qwen2.5-coder:32b
echo ""
echo "✅ Model pulled successfully"
echo ""

# Install backend dependencies if needed
if [ ! -d "venv" ]; then
  echo "🔧 Creating Python virtual environment..."
  python3 -m venv venv
  source venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  echo ""
else
  source venv/bin/activate
fi

# Set backend environment
export OLLAMA_URL="http://localhost:11434"
export HOST="0.0.0.0"
export PORT="8000"

# Start backend
echo "🔧 Starting backend on port 8000..."
uvicorn app.main:app --host $HOST --port $PORT > /tmp/backend.log 2>&1 &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"
echo ""

# Wait for backend to be ready
echo "⏳ Waiting for backend to be ready..."
for i in {1..30}; do
  if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "   ✅ Backend is ready"
    break
  fi
  if [ $i -eq 30 ]; then
    echo "   ❌ Backend failed to start"
    echo "   Check logs: tail -f /tmp/backend.log"
    exit 1
  fi
  sleep 1
done
echo ""

echo "================================================"
echo "✅ All services started!"
echo "================================================"
echo ""
echo "Services:"
echo "  - Backend:  http://localhost:8000"
echo "  - Ollama:   http://localhost:11434"
echo ""
echo "Public URL (via RunPod):"
echo "  - Use RunPod's proxy URL for port 8000"
echo ""
echo "Test health:"
echo "  curl http://localhost:8000/health"
echo ""
echo "View logs:"
echo "  tail -f /tmp/backend.log"
echo "  tail -f /tmp/ollama.log"
echo ""
echo "PIDs:"
echo "  Ollama: $OLLAMA_PID"
echo "  Backend: $BACKEND_PID"
echo ""
echo "Stop services:"
echo "  kill $OLLAMA_PID $BACKEND_PID"
echo ""
