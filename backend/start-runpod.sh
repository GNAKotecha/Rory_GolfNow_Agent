#!/bin/bash
set -e

echo "🚀 Starting Internal Agent on RunPod..."
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

# Pull Ollama model
echo "📦 Pulling Ollama model (this may take several minutes)..."
echo "   Starting Ollama service..."
docker compose -f docker-compose.runpod.yml up -d ollama

echo "   Waiting for Ollama to be ready..."
sleep 10

echo "   Pulling qwen2.5-coder:32b model..."
docker exec ollama ollama pull qwen2.5-coder:32b

echo ""
echo "✅ Model pulled successfully"
echo ""

# Start backend
echo "🔧 Starting backend..."
docker compose -f docker-compose.runpod.yml up -d backend

echo ""
echo "⏳ Waiting for backend to be ready..."
sleep 5

echo ""
echo "================================================"
echo "✅ All services started!"
echo "================================================"
echo ""
echo "Services:"
echo "  - Backend:  http://localhost:8000"
echo "  - Ollama:   http://localhost:11434"
echo ""
echo "Test health:"
echo "  curl http://localhost:8000/health"
echo ""
echo "View logs:"
echo "  docker compose -f docker-compose.runpod.yml logs -f"
echo ""
echo "Stop services:"
echo "  docker compose -f docker-compose.runpod.yml down"
echo ""
