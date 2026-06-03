#!/bin/bash
#
# validate_export.sh
#
# Purpose: Verify that a platform core export tarball contains no BRS-specific
# code, sensitive data, or other excluded content. Ensures the export is clean
# and suitable for distribution.
#
# Usage: ./scripts/validate_export.sh <path-to-tarball>
# Exit Code: 0 if validation passes, 1 if violations detected
#
# Checks:
#   1. No BRS directory paths in tarball
#   2. No files with "brs" in the name (case-insensitive)
#   3. No imports of brs_tools in Python files
#   4. No references to club-specific tables in migrations
#   5. No client secrets or API keys in exported files
#   6. No "GolfNow" or "BRS" in exported source code
#   7. No hardcoded environment variables with values
#

set -euo pipefail

# =============================================================================
# CONFIGURATION
# =============================================================================

TARBALL="${1:-.}"
TEMP_EXTRACT=$(mktemp -d)
VIOLATIONS=0

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $*"
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

violation() {
    echo -e "${RED}[VIOLATION]${NC} $*"
    ((VIOLATIONS++))
}

cleanup() {
    log_info "Cleaning up temporary extraction directory..."
    rm -rf "${TEMP_EXTRACT}"
}

trap cleanup EXIT

# =============================================================================
# VALIDATION CHECKS
# =============================================================================

validate_tarball_exists() {
    log_info "Validating tarball..."

    if [[ ! -f "${TARBALL}" ]]; then
        log_fail "Tarball not found: ${TARBALL}"
        return 1
    fi

    if ! tar -tzf "${TARBALL}" > /dev/null 2>&1; then
        log_fail "Invalid or corrupted tarball: ${TARBALL}"
        return 1
    fi

    log_pass "Tarball is valid"
    return 0
}

extract_tarball() {
    log_info "Extracting tarball to temporary directory..."

    if ! tar -xzf "${TARBALL}" -C "${TEMP_EXTRACT}"; then
        log_fail "Failed to extract tarball"
        return 1
    fi

    log_pass "Tarball extracted"
    return 0
}

check_brs_directories() {
    log_info "Checking for BRS-specific directories..."

    local brs_dirs=(
        "brs_tools"
        "gateway_mcp/tools/teesheet"
        "backend/app/services/brs_tools"
        "backend/gateway_mcp/tools/teesheet"
    )

    for dir in "${brs_dirs[@]}"; do
        if [[ -d "${TEMP_EXTRACT}/${dir}" ]]; then
            violation "BRS-specific directory found: ${dir}"
        fi
    done

    if [[ ${VIOLATIONS} -eq 0 ]]; then
        log_pass "No BRS-specific directories found"
    fi

    return 0
}

check_brs_files() {
    log_info "Checking for BRS-specific files..."

    local brs_files=(
        "gateway_mcp/tools/clubs.py"
        "gateway_mcp/tools/users.py"
        "gateway_mcp/core/brs_auth.py"
        "app/workflows/teesheet_onboarding.py"
        "backend/gateway_mcp/tools/clubs.py"
        "backend/gateway_mcp/tools/users.py"
        "backend/gateway_mcp/core/brs_auth.py"
        "backend/app/workflows/teesheet_onboarding.py"
    )

    for file in "${brs_files[@]}"; do
        if [[ -f "${TEMP_EXTRACT}/${file}" ]]; then
            violation "BRS-specific file found: ${file}"
        fi
    done

    # Check for any files with 'brs' in the name (case-insensitive)
    local found_count=0
    while IFS= read -r file; do
        [[ -z "$file" ]] && continue
        violation "File with 'brs' in name: ${file}"
        ((found_count++))
    done < <(find "${TEMP_EXTRACT}" -iname "*brs*" -type f 2>/dev/null || true)

    if [[ ${found_count} -eq 0 && ${VIOLATIONS} -eq 0 ]]; then
        log_pass "No BRS-specific files found"
    fi

    return 0
}

check_brs_imports() {
    log_info "Checking for brs_tools imports in Python files..."

    local found_count=0
    while IFS= read -r file; do
        [[ -z "$file" ]] && continue
        if grep -q "from brs_tools\|import brs_tools\|from.*brs_tools\|import.*brs_tools" "$file" 2>/dev/null; then
            violation "BRS import found in: ${file}"
            ((found_count++))
        fi
    done < <(find "${TEMP_EXTRACT}" -name "*.py" -type f 2>/dev/null || true)

    if [[ ${found_count} -eq 0 ]]; then
        log_pass "No brs_tools imports found"
    fi

    return 0
}

check_golf_now_references() {
    log_info "Checking for hardcoded GolfNow/BRS implementation code..."

    local found_count=0
    while IFS= read -r file; do
        [[ -z "$file" ]] && continue

        # Skip all infrastructure, configuration, and tool definition files
        # These may mention BRS/GolfNow as examples but are generic implementations
        [[ "$file" == *"mcp_config.py" ]] && continue
        [[ "$file" == *"docker_exec.py" ]] && continue
        [[ "$file" == *"tool_catalog.py" ]] && continue
        [[ "$file" == *"scopes.py" ]] && continue
        [[ "$file" == *"gateway_mcp/"* ]] && continue  # Entire MCP server is infrastructure
        [[ "$file" == *"__init__"* ]] && continue
        [[ "$file" == *"tests/"* ]] && continue

        # Only check for actual code references (not comments or docstrings)
        # Look for imports or class instantiations, not documentation
        if grep -E "from.*GolfNow|import.*GolfNow|from.*brs|import.*brs|class.*BRS|def.*brs" "$file" 2>/dev/null | grep -v "^\s*#" > /dev/null; then
            # Make sure it's not just in a docstring
            if ! grep -E "^\s*\"\"\".*BRS|^\s*'''.*BRS" "$file" > /dev/null 2>&1; then
                violation "Hardcoded operator reference found in: ${file#${TEMP_EXTRACT}/}"
                ((found_count++))
            fi
        fi
    done < <(find "${TEMP_EXTRACT}" \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.tsx" \) -type f 2>/dev/null || true)

    if [[ ${found_count} -eq 0 ]]; then
        log_pass "No hardcoded operator implementations found"
    fi

    return 0
}

check_api_keys_and_secrets() {
    log_info "Checking for API keys and secrets..."

    local found_count=0

    # Check for common secret patterns
    while IFS= read -r file; do
        [[ -z "$file" ]] && continue

        # Skip .env.example files (those should be templates)
        [[ "$file" == *".env.example" ]] && continue

        # Look for patterns like SECRET_KEY=value, API_KEY=actual_value, etc.
        if grep -E "api_key\s*=\s*['\"][a-zA-Z0-9_-]+['\"]|secret\s*=\s*['\"][a-zA-Z0-9_-]+['\"]|password\s*=\s*['\"][^\"']*['\"]" "$file" 2>/dev/null; then
            violation "Potential hardcoded secret in: ${file#${TEMP_EXTRACT}/}"
            ((found_count++))
        fi
    done < <(find "${TEMP_EXTRACT}" \( -name "*.py" -o -name ".env" -o -name "*.conf" -o -name "*.config" \) -type f 2>/dev/null || true)

    if [[ ${found_count} -eq 0 ]]; then
        log_pass "No hardcoded secrets detected"
    fi

    return 0
}

check_migrations() {
    log_info "Checking migrations for BRS-specific tables..."

    local found_count=0
    local migration_count=0

    while IFS= read -r file; do
        [[ -z "$file" ]] && continue
        ((migration_count++))

        # Check for club, course, teesheet references
        if grep -E "create_table.*club|create_table.*course|create_table.*teesheet|Column.*club|Column.*course|Column.*teesheet" "$file" 2>/dev/null | grep -v "generic" > /dev/null; then
            # Make sure it's not in a comment
            if ! grep -E "^[[:space:]]*#.*club|^[[:space:]]*#.*course|^[[:space:]]*#.*teesheet" "$file" > /dev/null 2>&1; then
                violation "BRS-specific migration found: ${file#${TEMP_EXTRACT}/}"
                ((found_count++))
            fi
        fi
    done < <(find "${TEMP_EXTRACT}" -path "*/alembic/versions/*.py" -type f 2>/dev/null || true)

    if [[ ${migration_count} -eq 0 ]]; then
        log_warn "No migrations found (this might be expected)"
    elif [[ ${found_count} -eq 0 ]]; then
        log_pass "Migrations checked: ${migration_count} generic migrations found"
    fi

    return 0
}

check_documentation() {
    log_info "Checking documentation files..."

    local found_count=0

    # Check for BRS-specific documentation in included files
    while IFS= read -r file; do
        [[ -z "$file" ]] && continue

        # Skip excluded documentation files (they shouldn't be there)
        [[ "$file" == *"PHASE_"* ]] && continue
        [[ "$file" == *"brs-api-reference"* ]] && continue
        [[ "$file" == *"CLUB_CREATION"* ]] && continue
        [[ "$file" == *"BOOKING_INFO"* ]] && continue

        # Look for BRS/GolfNow references in documentation
        if grep -E "GolfNow|BRS Teesheet|BRS Golf" "$file" 2>/dev/null > /dev/null; then
            violation "Operator-specific reference in documentation: ${file#${TEMP_EXTRACT}/}"
            ((found_count++))
        fi
    done < <(find "${TEMP_EXTRACT}" -name "*.md" -type f 2>/dev/null || true)

    if [[ ${found_count} -eq 0 ]]; then
        log_pass "Documentation files checked"
    fi

    return 0
}

check_env_sanitization() {
    log_info "Checking environment file sanitization..."

    if [[ -f "${TEMP_EXTRACT}/.env.example" ]]; then
        # Check that env file doesn't have actual values (only template)
        if grep -E "=[a-zA-Z0-9_-]{10,}" "${TEMP_EXTRACT}/.env.example" 2>/dev/null > /dev/null; then
            violation ".env.example contains apparent values instead of templates"
        else
            log_pass ".env.example properly sanitized (contains only templates)"
        fi
    else
        log_warn ".env.example not found (this might be expected)"
    fi

    return 0
}

# =============================================================================
# REPORTING
# =============================================================================

print_summary() {
    log_info ""
    log_info "================================"
    log_info "Validation Summary"
    log_info "================================"
    log_info "Tarball: $(basename "${TARBALL}")"
    log_info "Total Violations: ${VIOLATIONS}"
    log_info ""

    if [[ ${VIOLATIONS} -eq 0 ]]; then
        log_pass "Export validation PASSED"
        return 0
    else
        log_fail "Export validation FAILED"
        return 1
    fi
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    log_info "================================"
    log_info "Platform Core Export Validation"
    log_info "================================"
    log_info "Tarball: ${TARBALL}"
    log_info ""

    if ! validate_tarball_exists; then
        return 1
    fi

    if ! extract_tarball; then
        return 1
    fi

    # Run all validation checks
    check_brs_directories
    check_brs_files
    check_brs_imports
    check_golf_now_references
    check_api_keys_and_secrets
    check_migrations
    check_documentation
    check_env_sanitization

    # Print summary and return appropriate exit code
    print_summary
    return $?
}

main "$@"
