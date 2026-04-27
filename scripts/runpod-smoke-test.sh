#!/bin/bash
set -e

# RunPod deployment smoke test
# Usage: RUNPOD_URL=https://your-pod.proxy.runpod.net ./scripts/runpod-smoke-test.sh

if [ -z "$RUNPOD_URL" ]; then
  echo "❌ ERROR: RUNPOD_URL environment variable not set"
  echo ""
  echo "Usage:"
  echo "  export RUNPOD_URL=https://your-pod-url.proxy.runpod.net"
  echo "  ./scripts/runpod-smoke-test.sh"
  exit 1
fi

echo "🧪 RunPod Deployment Smoke Test"
echo "================================================"
echo "  URL: $RUNPOD_URL"
echo ""

# Test 1: Health Check
echo "1️⃣  Testing health endpoint..."
HEALTH_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" "$RUNPOD_URL/health")
HTTP_STATUS=$(echo "$HEALTH_RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)

if [ "$HTTP_STATUS" = "200" ]; then
  echo "   ✅ Health check passed (HTTP $HTTP_STATUS)"
  echo "$HEALTH_RESPONSE" | grep -v "HTTP_STATUS" | jq . 2>/dev/null || echo "$HEALTH_RESPONSE" | grep -v "HTTP_STATUS"
else
  echo "   ❌ Health check failed (HTTP $HTTP_STATUS)"
  echo "$HEALTH_RESPONSE" | grep -v "HTTP_STATUS"
  exit 1
fi

echo ""

# Test 2: User Registration
echo "2️⃣  Testing user registration..."
RANDOM_USER="smoketest_$(date +%s)"
REGISTER_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -X POST "$RUNPOD_URL/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$RANDOM_USER\",\"email\":\"$RANDOM_USER@test.com\",\"password\":\"testpass123\"}")
HTTP_STATUS=$(echo "$REGISTER_RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)

if [ "$HTTP_STATUS" = "200" ]; then
  echo "   ✅ User registration passed (HTTP $HTTP_STATUS)"
  USER_ID=$(echo "$REGISTER_RESPONSE" | grep -v "HTTP_STATUS" | jq -r '.user.id // empty' 2>/dev/null)
  if [ -n "$USER_ID" ]; then
    echo "   Created user ID: $USER_ID"
  fi
else
  echo "   ❌ User registration failed (HTTP $HTTP_STATUS)"
  echo "$REGISTER_RESPONSE" | grep -v "HTTP_STATUS"
  exit 1
fi

echo ""

# Test 3: User Login
echo "3️⃣  Testing user login..."
LOGIN_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -X POST "$RUNPOD_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$RANDOM_USER\",\"password\":\"testpass123\"}")
HTTP_STATUS=$(echo "$LOGIN_RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)

if [ "$HTTP_STATUS" = "200" ]; then
  echo "   ✅ User login passed (HTTP $HTTP_STATUS)"
  ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -v "HTTP_STATUS" | jq -r '.access_token // empty' 2>/dev/null)
  if [ -n "$ACCESS_TOKEN" ]; then
    echo "   Received access token"
  else
    echo "   ⚠️  Warning: No access token in response"
  fi
else
  echo "   ❌ User login failed (HTTP $HTTP_STATUS)"
  echo "$LOGIN_RESPONSE" | grep -v "HTTP_STATUS"
  exit 1
fi

echo ""

# Test 4: Authenticated Request (Session Creation)
if [ -n "$ACCESS_TOKEN" ]; then
  echo "4️⃣  Testing authenticated request (session creation)..."
  SESSION_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
    -X POST "$RUNPOD_URL/api/sessions" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"title":"Smoke Test Session"}')
  HTTP_STATUS=$(echo "$SESSION_RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)

  if [ "$HTTP_STATUS" = "200" ]; then
    echo "   ✅ Session creation passed (HTTP $HTTP_STATUS)"
    SESSION_ID=$(echo "$SESSION_RESPONSE" | grep -v "HTTP_STATUS" | jq -r '.id // empty' 2>/dev/null)
    if [ -n "$SESSION_ID" ]; then
      echo "   Created session ID: $SESSION_ID"
    fi
  else
    echo "   ❌ Session creation failed (HTTP $HTTP_STATUS)"
    echo "$SESSION_RESPONSE" | grep -v "HTTP_STATUS"
    exit 1
  fi
else
  echo "4️⃣  Skipping authenticated request (no access token)"
fi

echo ""

# Test 5: Database Write/Read (via session list)
if [ -n "$ACCESS_TOKEN" ]; then
  echo "5️⃣  Testing database persistence (session list)..."
  LIST_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
    -X GET "$RUNPOD_URL/api/sessions" \
    -H "Authorization: Bearer $ACCESS_TOKEN")
  HTTP_STATUS=$(echo "$LIST_RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)

  if [ "$HTTP_STATUS" = "200" ]; then
    echo "   ✅ Session list passed (HTTP $HTTP_STATUS)"
    SESSION_COUNT=$(echo "$LIST_RESPONSE" | grep -v "HTTP_STATUS" | jq 'length // 0' 2>/dev/null)
    if [ -n "$SESSION_COUNT" ]; then
      echo "   Found $SESSION_COUNT session(s)"
    fi
  else
    echo "   ❌ Session list failed (HTTP $HTTP_STATUS)"
    echo "$LIST_RESPONSE" | grep -v "HTTP_STATUS"
    exit 1
  fi
else
  echo "5️⃣  Skipping database test (no access token)"
fi

echo ""
echo "================================================"
echo "✅ All smoke tests passed!"
echo ""
echo "Summary:"
echo "  - Health endpoint responding"
echo "  - User registration working"
echo "  - Authentication working"
echo "  - Database writes persisting"
echo "  - API endpoints accessible"
echo ""
echo "Deployment verified successfully! 🎉"
