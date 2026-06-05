#!/bin/bash

# debug-rory.sh - Quick start script for debugging Rory API calls
#
# Usage:
#   ./debug-rory.sh              - Start with default debug logging
#   ./debug-rory.sh httpx        - Enable full httpx HTTP protocol logging
#   ./debug-rory.sh capture      - Capture all API calls to JSON files
#   ./debug-rory.sh watch        - Watch logs in real-time (in another terminal)

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
LOG_FILE="/tmp/rory.log"
API_CALLS_DIR="/tmp/rory_api_calls"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

show_help() {
    cat << 'EOF'
Rory Agent API Debugging Tool

USAGE:
  ./debug-rory.sh [MODE]

MODES:
  (default)     Start backend with debug logging enabled
  httpx         Enable full HTTP protocol logging (most detailed)
  capture       Capture all API calls to JSON files in /tmp/rory_api_calls/
  watch         Watch logs in real-time (run in separate terminal)
  clean         Clear log files and captured calls
  help          Show this help message

EXAMPLES:

  # Terminal 1: Start backend with debug logging
  ./debug-rory.sh

  # Terminal 2: Watch logs in real-time
  ./debug-rory.sh watch

  # Trigger agent action in frontend...

  # Terminal 1 will show all API calls with details

ENVIRONMENT VARIABLES:
  DEBUG=1          Enable debug logging
  HTTPX_LOG=1      Enable httpx HTTP protocol logging
  API_LOG_DIR      Directory for captured calls (default: /tmp/rory_api_calls)

OUTPUT FILES:
  Log file:        /tmp/rory.log
  API calls:       /tmp/rory_api_calls/call_*.json

QUICK DEBUGGING:
  # View last 50 log lines
  tail -50 /tmp/rory.log

  # Find failed requests (4xx, 5xx status)
  grep "status.*[4-9][0-9][0-9]" /tmp/rory.log

  # View specific captured call
  jq . /tmp/rory_api_calls/call_*.json

EOF
}

# Mode: Default debug logging
debug_mode() {
    print_header "Starting Rory Backend - Debug Mode"
    print_info "Log file: $LOG_FILE"
    print_info "To watch logs in another terminal, run: ./debug-rory.sh watch"
    echo ""

    cd "$BACKEND_DIR"
    DEBUG=1 uvicorn app.main:app --reload 2>&1 | tee "$LOG_FILE"
}

# Mode: Full httpx logging
httpx_mode() {
    print_header "Starting Rory Backend - Full HTTP Logging"
    print_warning "This will show raw HTTP protocol details (verbose!)"
    print_info "Log file: $LOG_FILE"
    echo ""

    cd "$BACKEND_DIR"
    DEBUG=1 HTTPX_LOG=1 python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('httpx').setLevel(logging.DEBUG)
" && DEBUG=1 uvicorn app.main:app --reload 2>&1 | tee "$LOG_FILE"
}

# Mode: API call capture
capture_mode() {
    print_header "Starting Rory Backend - API Call Capture"
    mkdir -p "$API_CALLS_DIR"
    print_success "Capturing API calls to: $API_CALLS_DIR"
    print_info "Calls will be saved as JSON files"
    echo ""
    print_warning "Note: This mode requires code modification (see guide)"
    echo "For now, check logs instead:"
    echo "  tail -f /tmp/rory.log | grep -i api"

    cd "$BACKEND_DIR"
    DEBUG=1 uvicorn app.main:app --reload 2>&1 | tee "$LOG_FILE"
}

# Mode: Watch logs
watch_mode() {
    if [ ! -f "$LOG_FILE" ]; then
        print_error "Log file not found: $LOG_FILE"
        print_info "Start backend in another terminal first: ./debug-rory.sh"
        exit 1
    fi

    print_header "Watching Rory Logs"
    print_info "Showing last 50 lines, then live updates..."
    echo ""

    tail -50f "$LOG_FILE"
}

# Mode: Watch API calls
watch_api_mode() {
    if [ ! -d "$API_CALLS_DIR" ]; then
        mkdir -p "$API_CALLS_DIR"
    fi

    print_header "Watching API Calls"
    print_info "Directory: $API_CALLS_DIR"
    echo ""

    # Watch for new files
    while true; do
        clear
        echo -e "${BLUE}=== API Calls (last 10) ===${NC}"
        ls -t "$API_CALLS_DIR"/call_*.json 2>/dev/null | head -10 | while read f; do
            url=$(jq -r '.url // "N/A"' "$f" 2>/dev/null)
            status=$(jq -r '.response.status // "N/A"' "$f" 2>/dev/null)
            elapsed=$(jq -r '.elapsed_ms // "N/A"' "$f" 2>/dev/null)
            echo "$status | $url | ${elapsed}ms | $(basename $f)"
        done

        echo ""
        echo "Refreshing every 2 seconds... (Ctrl+C to stop)"
        sleep 2
    done
}

# Mode: Clean
clean_mode() {
    print_header "Cleaning Debug Files"

    if [ -f "$LOG_FILE" ]; then
        rm "$LOG_FILE"
        print_success "Removed $LOG_FILE"
    fi

    if [ -d "$API_CALLS_DIR" ]; then
        rm -rf "$API_CALLS_DIR"
        print_success "Removed $API_CALLS_DIR"
    fi

    print_success "Cleaned up debug files"
}

# Main
MODE="${1:-debug}"

case "$MODE" in
    debug|"")
        debug_mode
        ;;
    httpx)
        httpx_mode
        ;;
    capture)
        capture_mode
        ;;
    watch)
        watch_mode
        ;;
    watch-api)
        watch_api_mode
        ;;
    clean)
        clean_mode
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown mode: $MODE"
        echo ""
        show_help
        exit 1
        ;;
esac
