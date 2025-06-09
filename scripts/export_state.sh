#!/bin/bash
# Enhanced DRP Export Script with Grafana Dashboard Snapshots
# Exports all critical state including metrics, logs, and dashboards

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
EXPORT_DIR="${EXPORT_DIR:-export}"
EXPORT_LOG_FILE="${EXPORT_LOG_FILE:-logs/export_state.json}"
DRP_ENC_KEY="${DRP_ENC_KEY:-}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
GRAFANA_API_KEY="${GRAFANA_API_KEY:-}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"

# Create timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EXPORT_NAME="mev_og_export_${TIMESTAMP}"
EXPORT_PATH="${EXPORT_DIR}/${EXPORT_NAME}"

# Logging function
log_event() {
    local event="$1"
    local status="$2"
    local details="${3:-}"
    
    local log_entry=$(cat <<EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "event": "${event}",
    "status": "${status}",
    "export_name": "${EXPORT_NAME}",
    "details": ${details:-null}
}
EOF
)
    
    echo "${log_entry}" >> "${EXPORT_LOG_FILE}"
}

# Create export directory structure
create_export_structure() {
    echo -e "${YELLOW}Creating export structure...${NC}"
    
    mkdir -p "${EXPORT_PATH}"/{logs,state,config,telemetry,grafana,prometheus,strategies,archive}
    mkdir -p "${EXPORT_PATH}/telemetry"/{drp,ai_votes,metrics}
    
    # Create manifest
    cat > "${EXPORT_PATH}/manifest.json" <<EOF
{
    "export_version": "2.0",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "hostname": "$(hostname)",
    "components": {
        "logs": true,
        "state": true,
        "config": true,
        "telemetry": true,
        "grafana": ${GRAFANA_API_KEY:+true},
        "prometheus": true,
        "strategies": true
    }
}
EOF
    
    log_event "export_structure_created" "success"
}

# Export logs with validation
export_logs() {
    echo -e "${YELLOW}Exporting logs...${NC}"
    
    local log_count=0
    
    # Copy all JSON logs
    for log_file in logs/*.json; do
        if [[ -f "$log_file" ]]; then
            # Validate JSON before copying
            if jq empty "$log_file" 2>/dev/null; then
                cp "$log_file" "${EXPORT_PATH}/logs/"
                ((log_count++))
            else
                echo -e "${RED}Warning: Invalid JSON in $log_file${NC}"
                log_event "invalid_json_log" "warning" "{\"file\": \"$log_file\"}"
            fi
        fi
    done
    
    # Copy error logs
    if [[ -f "logs/errors.log" ]]; then
        cp "logs/errors.log" "${EXPORT_PATH}/logs/"
        ((log_count++))
    fi
    
    echo -e "${GREEN}Exported ${log_count} log files${NC}"
    log_event "logs_exported" "success" "{\"count\": ${log_count}}"
}

# Export state files
export_state() {
    echo -e "${YELLOW}Exporting state files...${NC}"
    
    local state_count=0
    
    # Copy all state files
    for state_file in state/*.json; do
        if [[ -f "$state_file" ]]; then
            cp "$state_file" "${EXPORT_PATH}/state/"
            ((state_count++))
        fi
    done
    
    # Export nonce cache
    if [[ -f "state/nonce_cache.json" ]]; then
        cp "state/nonce_cache.json" "${EXPORT_PATH}/state/"
    fi
    
    # Export capital lock state
    if [[ -f "state/capital_lock.json" ]]; then
        cp "state/capital_lock.json" "${EXPORT_PATH}/state/"
    fi
    
    echo -e "${GREEN}Exported ${state_count} state files${NC}"
    log_event "state_exported" "success" "{\"count\": ${state_count}}"
}

# Export configuration
export_config() {
    echo -e "${YELLOW}Exporting configuration...${NC}"
    
    # Copy config files (sanitize sensitive data)
    if [[ -f "config.yaml" ]]; then
        # Remove sensitive keys
        yq eval 'del(.api_keys, .private_keys, .webhook_urls)' config.yaml > "${EXPORT_PATH}/config/config_sanitized.yaml"
    fi
    
    # Export environment variables (sanitized)
    env | grep -E '^(POOL_|BRIDGE_|ARB_|CROSS_|L3_|NFT_|RWA_|METRICS_|KILL_)' | \
        sed 's/=.*_KEY=.*/=<REDACTED>/' | \
        sed 's/=.*_TOKEN=.*/=<REDACTED>/' | \
        sed 's/=.*_SECRET=.*/=<REDACTED>/' \
        > "${EXPORT_PATH}/config/env_vars.txt"
    
    log_event "config_exported" "success"
}

# Export Grafana dashboards
export_grafana() {
    echo -e "${YELLOW}Exporting Grafana dashboards...${NC}"
    
    if [[ -z "$GRAFANA_API_KEY" ]]; then
        echo -e "${YELLOW}Grafana API key not set, skipping dashboard export${NC}"
        return
    fi
    
    # Get list of dashboards
    local dashboards=$(curl -s -H "Authorization: Bearer ${GRAFANA_API_KEY}" \
        "${GRAFANA_URL}/api/search?type=dash-db" || echo "[]")
    
    if [[ "$dashboards" == "[]" ]]; then
        echo -e "${YELLOW}No dashboards found or API error${NC}"
        return
    fi
    
    local dashboard_count=0
    
    # Export each dashboard
    echo "$dashboards" | jq -r '.[] | @base64' | while read -r dashboard_b64; do
        local dashboard=$(echo "$dashboard_b64" | base64 -d)
        local uid=$(echo "$dashboard" | jq -r '.uid')
        local title=$(echo "$dashboard" | jq -r '.title')
        
        echo "Exporting dashboard: $title"
        
        # Get dashboard JSON
        local dashboard_json=$(curl -s -H "Authorization: Bearer ${GRAFANA_API_KEY}" \
            "${GRAFANA_URL}/api/dashboards/uid/${uid}")
        
        if [[ -n "$dashboard_json" ]]; then
            echo "$dashboard_json" | jq '.' > "${EXPORT_PATH}/grafana/${uid}.json"
            ((dashboard_count++))
        fi
        
        # Create dashboard snapshot
        local snapshot_response=$(curl -s -X POST \
            -H "Authorization: Bearer ${GRAFANA_API_KEY}" \
            -H "Content-Type: application/json" \
            -d "{\"dashboard\": $(echo "$dashboard_json" | jq '.dashboard'), \"expires\": 3600}" \
            "${GRAFANA_URL}/api/snapshots")
        
        if [[ -n "$snapshot_response" ]]; then
            local snapshot_url=$(echo "$snapshot_response" | jq -r '.url // empty')
            if [[ -n "$snapshot_url" ]]; then
                echo "$snapshot_url" >> "${EXPORT_PATH}/grafana/snapshots.txt"
            fi
        fi
    done
    
    echo -e "${GREEN}Exported Grafana dashboards${NC}"
    log_event "grafana_exported" "success" "{\"dashboard_count\": ${dashboard_count}}"
}

# Export Prometheus metrics
export_prometheus() {
    echo -e "${YELLOW}Exporting Prometheus metrics...${NC}"
    
    # Query important metrics
    local metrics=(
        "arb_opportunities_found"
        "arb_profit_eth"
        "arb_latency"
        "arb_error_count"
        "arb_abort_count"
    )
    
    for metric in "${metrics[@]}"; do
        # Get last 24h of data
        local query_result=$(curl -s -G \
            --data-urlencode "query=${metric}[24h]" \
            "${PROMETHEUS_URL}/api/v1/query" || echo "{}")
        
        if [[ -n "$query_result" ]] && [[ "$query_result" != "{}" ]]; then
            echo "$query_result" | jq '.' > "${EXPORT_PATH}/prometheus/${metric}.json"
        fi
    done
    
    # Export recording rules
    curl -s "${PROMETHEUS_URL}/api/v1/rules" | jq '.' > "${EXPORT_PATH}/prometheus/rules.json" || true
    
    # Export active alerts
    curl -s "${PROMETHEUS_URL}/api/v1/alerts" | jq '.' > "${EXPORT_PATH}/prometheus/alerts.json" || true
    
    log_event "prometheus_exported" "success"
}

# Export telemetry data
export_telemetry() {
    echo -e "${YELLOW}Exporting telemetry data...${NC}"
    
    # Copy DRP snapshots
    if [[ -d "/telemetry/drp" ]]; then
        cp -r /telemetry/drp/* "${EXPORT_PATH}/telemetry/drp/" 2>/dev/null || true
    fi
    
    # Copy AI votes
    if [[ -d "telemetry/ai_votes" ]]; then
        cp -r telemetry/ai_votes/* "${EXPORT_PATH}/telemetry/ai_votes/" 2>/dev/null || true
    fi
    
    # Export current metrics snapshot
    if command -v curl &> /dev/null; then
        curl -s "http://localhost:${METRICS_PORT:-8000}/metrics" > \
            "${EXPORT_PATH}/telemetry/metrics/current_metrics.txt" 2>/dev/null || true
    fi
    
    log_event "telemetry_exported" "success"
}

# Export strategies
export_strategies() {
    echo -e "${YELLOW}Exporting strategies...${NC}"
    
    local strategy_count=0
    
    # Copy active strategies
    if [[ -d "strategies" ]]; then
        for strategy_dir in strategies/*/; do
            if [[ -d "$strategy_dir" ]]; then
                local strategy_name=$(basename "$strategy_dir")
                mkdir -p "${EXPORT_PATH}/strategies/${strategy_name}"
                
                # Copy Python files
                cp "${strategy_dir}"*.py "${EXPORT_PATH}/strategies/${strategy_name}/" 2>/dev/null || true
                
                # Copy any config files
                cp "${strategy_dir}"*.yaml "${EXPORT_PATH}/strategies/${strategy_name}/" 2>/dev/null || true
                cp "${strategy_dir}"*.json "${EXPORT_PATH}/strategies/${strategy_name}/" 2>/dev/null || true
                
                ((strategy_count++))
            fi
        done
    fi
    
    # Copy archived strategies metadata
    if [[ -d "archive" ]]; then
        find archive -name "archive_metadata.json" -exec cp --parents {} "${EXPORT_PATH}/" \; 2>/dev/null || true
    fi
    
    echo -e "${GREEN}Exported ${strategy_count} strategies${NC}"
    log_event "strategies_exported" "success" "{\"count\": ${strategy_count}}"
}

# Scan for secrets
scan_for_secrets() {
    echo -e "${YELLOW}Scanning for secrets...${NC}"
    
    local secret_patterns=(
        "api[_-]?key"
        "secret[_-]?key"
        "private[_-]?key"
        "auth[_-]?token"
        "bearer[_-]?token"
        "webhook[_-]?url"
        "0x[a-fA-F0-9]{64}"  # Private keys
    )
    
    local found_secrets=0
    local scan_report="${EXPORT_PATH}/secret_scan_report.txt"
    
    echo "Secret Scan Report - $(date)" > "$scan_report"
    echo "================================" >> "$scan_report"
    
    for pattern in "${secret_patterns[@]}"; do
        echo "Scanning for pattern: $pattern" >> "$scan_report"
        
        # Use grep with context to find potential secrets
        if grep -r -i -E "$pattern" "${EXPORT_PATH}" --exclude="secret_scan_report.txt" >> "$scan_report" 2>/dev/null; then
            ((found_secrets++))
        fi
    done
    
    if [[ $found_secrets -gt 0 ]]; then
        echo -e "${RED}WARNING: Found ${found_secrets} potential secrets in export!${NC}"
        echo -e "${RED}Review ${scan_report} and remove sensitive data${NC}"
        log_event "secrets_found" "warning" "{\"count\": ${found_secrets}}"
    else
        echo -e "${GREEN}No secrets detected${NC}"
        log_event "secrets_scan_clean" "success"
    fi
}

# Create archive
create_archive() {
    echo -e "${YELLOW}Creating archive...${NC}"
    
    cd "${EXPORT_DIR}"
    
    # Create tar archive
    tar -czf "${EXPORT_NAME}.tar.gz" "${EXPORT_NAME}/"
    
    # Calculate checksum
    local checksum=$(sha256sum "${EXPORT_NAME}.tar.gz" | cut -d' ' -f1)
    echo "$checksum" > "${EXPORT_NAME}.tar.gz.sha256"
    
    # Encrypt if key provided
    if [[ -n "$DRP_ENC_KEY" ]]; then
        echo -e "${YELLOW}Encrypting archive...${NC}"
        openssl enc -aes-256-cbc -salt -pbkdf2 \
            -in "${EXPORT_NAME}.tar.gz" \
            -out "${EXPORT_NAME}.tar.gz.enc" \
            -k "$DRP_ENC_KEY"
        
        # Remove unencrypted archive
        rm "${EXPORT_NAME}.tar.gz"
        
        echo -e "${GREEN}Archive encrypted${NC}"
        log_event "archive_encrypted" "success"
    fi
    
    # Clean up directory
    rm -rf "${EXPORT_NAME}/"
    
    cd - > /dev/null
    
    echo -e "${GREEN}Archive created: ${EXPORT_DIR}/${EXPORT_NAME}.tar.gz${DRP_ENC_KEY:+.enc}${NC}"
    log_event "archive_created" "success" "{\"path\": \"${EXPORT_DIR}/${EXPORT_NAME}.tar.gz${DRP_ENC_KEY:+.enc}\", \"checksum\": \"$checksum\"}"
}

# Cleanup old exports
cleanup_old_exports() {
    echo -e "${YELLOW}Cleaning up old exports...${NC}"
    
    # Keep only last 10 exports
    cd "${EXPORT_DIR}"
    ls -t mev_og_export_*.tar.gz* 2>/dev/null | tail -n +11 | xargs -r rm
    cd - > /dev/null
    
    log_event "cleanup_complete" "success"
}

# Main execution
main() {
    echo -e "${GREEN}Starting MEV-OG DRP Export...${NC}"
    log_event "export_started" "info"
    
    # Check dependencies
    for cmd in jq tar; do
        if ! command -v $cmd &> /dev/null; then
            echo -e "${RED}Error: $cmd is required but not installed${NC}"
            exit 1
        fi
    done
    
    # Optional dependencies
    if ! command -v yq &> /dev/null; then
        echo -e "${YELLOW}Warning: yq not found, config export will be limited${NC}"
    fi
    
    # Create export
    create_export_structure
    export_logs
    export_state
    export_config
    export_grafana
    export_prometheus
    export_telemetry
    export_strategies
    scan_for_secrets
    create_archive
    cleanup_old_exports
    
    echo -e "${GREEN}Export completed successfully!${NC}"
    echo -e "${GREEN}Location: ${EXPORT_DIR}/${EXPORT_NAME}.tar.gz${DRP_ENC_KEY:+.enc}${NC}"
    
    log_event "export_completed" "success" "{\"duration_seconds\": $SECONDS}"
}

# Run main function
main "$@"
