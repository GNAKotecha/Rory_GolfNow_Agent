#!/bin/bash
#
# export_platform_core.sh
#
# Purpose: Create a clean, sanitized tarball of the platform core harness
# for distribution to clean environments. Removes all BRS-specific code and
# sensitive data while preserving the generic harness infrastructure.
#
# Usage: ./scripts/export_platform_core.sh
# Output: platform-core-export-TIMESTAMP.tar.gz
#
# Requirements:
#   - .exportignore file at repository root
#   - tar command with --exclude-from support
#   - Standard Unix utilities (grep, sed, sha256sum)
#

set -euo pipefail

# =============================================================================
# CONFIGURATION
# =============================================================================

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPORTIGNORE_FILE="${REPO_ROOT}/.exportignore"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EXPORT_DIR=$(mktemp -d)
OUTPUT_FILE="${REPO_ROOT}/platform-core-export-${TIMESTAMP}.tar.gz"
MANIFEST_FILE="${REPO_ROOT}/platform-core-export-${TIMESTAMP}.manifest"
CHECKSUM_FILE="${REPO_ROOT}/platform-core-export-${TIMESTAMP}.sha256"

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

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

cleanup() {
    log_info "Cleaning up temporary directory..."
    rm -rf "${EXPORT_DIR}"
}

trap cleanup EXIT

# =============================================================================
# VALIDATION
# =============================================================================

validate_prerequisites() {
    log_info "Validating prerequisites..."

    if [[ ! -f "${EXPORTIGNORE_FILE}" ]]; then
        log_error ".exportignore file not found at ${EXPORTIGNORE_FILE}"
        return 1
    fi

    # Check for required commands
    for cmd in tar grep sed sha256sum; do
        if ! command -v "$cmd" &> /dev/null; then
            log_error "Required command not found: $cmd"
            return 1
        fi
    done

    log_success "All prerequisites validated"
    return 0
}

# =============================================================================
# EXPORT PROCESS
# =============================================================================

copy_repo_files() {
    log_info "Copying repository files (excluding patterns from .exportignore)..."

    if ! tar -C "${REPO_ROOT}" \
        --exclude-from="${EXPORTIGNORE_FILE}" \
        -cf - . | tar -xf - -C "${EXPORT_DIR}"; then
        log_error "Failed to copy repository files"
        return 1
    fi

    log_success "Repository files copied"
    return 0
}

remove_pycache() {
    log_info "Removing Python cache directories..."
    find "${EXPORT_DIR}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "${EXPORT_DIR}" -type f -name "*.pyc" -delete 2>/dev/null || true
    log_success "Python cache removed"
    return 0
}

sanitize_env_files() {
    log_info "Sanitizing environment template files..."

    if [[ -f "${EXPORT_DIR}/.env.example" ]]; then
        # Keep only template variables, remove any actual values
        sed -i.bak \
            -e 's/=.*/=/g' \
            -e '/^#/b' \
            -e '/^$/b' \
            -e 's/=[^ ]*$/=/g' \
            "${EXPORT_DIR}/.env.example" || true
        rm -f "${EXPORT_DIR}/.env.example.bak"
        log_success ".env.example sanitized"
    fi

    # Remove any actual .env files that might have slipped through
    find "${EXPORT_DIR}" -name ".env" -not -name ".env.example" -delete 2>/dev/null || true

    return 0
}

generate_manifest() {
    log_info "Generating export manifest..."

    cat > "${MANIFEST_FILE}" <<EOF
Platform Core Export Manifest
Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
Export ID: ${TIMESTAMP}

=============================================================================
INCLUDED COMPONENTS
=============================================================================

Core Harness:
  - app/core/                     (Core agent logic)
  - app/services/                 (Generic services, BRS-specific excluded)
  - app/workflows/                (Generic workflows, BRS-specific excluded)
  - app/models/                   (Database models)
  - app/schemas/                  (Request/response schemas)
  - app/api/                       (REST API endpoints)
  - app/db/                        (Database utilities)
  - app/config/                    (Configuration)
  - app/workers/                   (Background workers)

Gateway MCP:
  - gateway_mcp/core/             (MCP server core)
  - gateway_mcp/tools/            (Generic tool implementations)
  - gateway_mcp/configs/          (MCP configurations)

Database:
  - alembic/                       (Migrations, generic only)
  - Generic tenant models
  - Generic skill/workflow models

Tests:
  - tests/                         (Generic tests only)

Documentation:
  - README.md
  - GATEWAY_MCP.md
  - Generic deployment guides

=============================================================================
EXCLUDED COMPONENTS (BRS-SPECIFIC)
=============================================================================

Excluded:
  - backend/app/services/brs_tools/
  - backend/gateway_mcp/tools/clubs.py
  - backend/gateway_mcp/tools/users.py
  - backend/gateway_mcp/tools/teesheet/
  - backend/gateway_mcp/core/brs_auth.py
  - backend/app/workflows/teesheet_onboarding.py
  - BRS-specific migrations
  - BRS-specific tests
  - BRS API reference documentation
  - Infrastructure and deployment configs
  - Project-specific planning documents

=============================================================================
DEPLOYMENT INSTRUCTIONS
=============================================================================

1. Extract the tarball:
   tar -xzf platform-core-export-${TIMESTAMP}.tar.gz -C /target/directory

2. Configure the environment:
   cp .env.example .env
   # Edit .env with your operator-specific values

3. Set up database:
   python -m alembic upgrade head

4. Configure MCP servers:
   Edit gateway_mcp/configs/ with your tool implementations

5. Start the service:
   python app/main.py

=============================================================================
NOTES
=============================================================================

- This export contains ONLY the generic harness infrastructure
- No BRS-specific code or configurations included
- No sensitive credentials or API keys
- Ready for deployment in clean environments
- Can be extended with operator-specific tools and workflows

=============================================================================
EOF

    log_success "Manifest generated: ${MANIFEST_FILE}"
    return 0
}

create_tarball() {
    log_info "Creating compressed tarball..."

    if ! tar -czf "${OUTPUT_FILE}" -C "$(dirname "${EXPORT_DIR}")" "$(basename "${EXPORT_DIR}")"; then
        log_error "Failed to create tarball"
        return 1
    fi

    local size_bytes=$(stat -f%z "${OUTPUT_FILE}" 2>/dev/null || stat -c%s "${OUTPUT_FILE}" 2>/dev/null)
    if [[ -z "$size_bytes" ]]; then
        log_error "Unable to determine file size - stat command not available on this platform"
        return 1
    fi
    local size_mb=$(echo "scale=2; $size_bytes / 1048576" | bc)

    log_success "Tarball created: ${OUTPUT_FILE} (${size_mb} MB)"
    return 0
}

generate_checksums() {
    log_info "Generating checksums..."

    cd "$(dirname "${OUTPUT_FILE}")"
    sha256sum "$(basename "${OUTPUT_FILE}")" > "${CHECKSUM_FILE}"
    cd - > /dev/null

    log_success "Checksum generated: ${CHECKSUM_FILE}"
    return 0
}

# =============================================================================
# VALIDATION
# =============================================================================

run_validation() {
    log_info "Running validation script..."

    local validation_script="${REPO_ROOT}/scripts/validate_export.sh"

    if [[ ! -f "${validation_script}" ]]; then
        log_warn "Validation script not found: ${validation_script}"
        return 0
    fi

    if bash "${validation_script}" "${OUTPUT_FILE}"; then
        log_success "Export validation passed"
        return 0
    else
        log_error "Export validation failed"
        return 1
    fi
}

# =============================================================================
# REPORTING
# =============================================================================

generate_report() {
    log_info "Generating export report..."

    local report_file="${REPO_ROOT}/platform-core-export-${TIMESTAMP}.report"

    # Get file size with proper error handling
    local size_bytes=$(stat -f%z "${OUTPUT_FILE}" 2>/dev/null || stat -c%s "${OUTPUT_FILE}" 2>/dev/null)
    if [[ -z "$size_bytes" ]]; then
        log_error "Unable to determine file size - stat command not available on this platform"
        return 1
    fi

    cat > "${report_file}" <<EOF
Platform Core Export Report
Generated: $(date)
Export ID: ${TIMESTAMP}

=============================================================================
EXPORT SUMMARY
=============================================================================

Tarball: $(basename "${OUTPUT_FILE}")
Location: ${OUTPUT_FILE}
Size: ${size_bytes} bytes
Compressed Size: $(du -h "${OUTPUT_FILE}" | cut -f1)

Checksum (SHA256):
$(cat "${CHECKSUM_FILE}")

=============================================================================
MANIFEST
=============================================================================

$(cat "${MANIFEST_FILE}" | tail -n +2)

=============================================================================
FILES INCLUDED
=============================================================================

$(tar -tzf "${OUTPUT_FILE}" | head -50)
... (and $(tar -tzf "${OUTPUT_FILE}" | wc -l) total files)

=============================================================================
QUICK VERIFICATION
=============================================================================

To verify the export:
  1. Check checksum: sha256sum -c platform-core-export-${TIMESTAMP}.sha256
  2. Extract to temp: tar -xzf platform-core-export-${TIMESTAMP}.tar.gz -C /tmp
  3. Run validation: ./scripts/validate_export.sh platform-core-export-${TIMESTAMP}.tar.gz
  4. Review manifest: cat platform-core-export-${TIMESTAMP}.manifest

=============================================================================
EOF

    log_success "Report generated: ${report_file}"
    return 0
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    log_info "================================"
    log_info "Platform Core Export Process"
    log_info "================================"
    log_info "Repository: ${REPO_ROOT}"
    log_info "Timestamp: ${TIMESTAMP}"
    log_info ""

    # Step 1: Validate prerequisites
    if ! validate_prerequisites; then
        log_error "Prerequisites validation failed"
        return 1
    fi

    # Step 2: Copy files
    if ! copy_repo_files; then
        log_error "File copy failed"
        return 1
    fi

    # Step 3: Remove cache
    if ! remove_pycache; then
        log_error "Cache removal failed"
        return 1
    fi

    # Step 4: Sanitize sensitive files
    if ! sanitize_env_files; then
        log_error "Environment sanitization failed"
        return 1
    fi

    # Step 5: Generate manifest
    if ! generate_manifest; then
        log_error "Manifest generation failed"
        return 1
    fi

    # Step 6: Create tarball
    if ! create_tarball; then
        log_error "Tarball creation failed"
        return 1
    fi

    # Step 7: Generate checksums
    if ! generate_checksums; then
        log_error "Checksum generation failed"
        return 1
    fi

    # Step 8: Run validation
    if ! run_validation; then
        log_error "Validation failed - export may contain BRS-specific code"
        return 1
    fi

    # Step 9: Generate report
    if ! generate_report; then
        log_error "Report generation failed"
        return 1
    fi

    log_info ""
    log_success "================================"
    log_success "Export completed successfully!"
    log_success "================================"
    log_success "Output: ${OUTPUT_FILE}"
    log_success "Manifest: ${MANIFEST_FILE}"
    log_success "Report: ${REPO_ROOT}/platform-core-export-${TIMESTAMP}.report"
    log_success "Checksum: ${CHECKSUM_FILE}"
    log_info ""

    return 0
}

main "$@"
