#!/usr/bin/env bash
# =============================================================================
# infra.sh - Terraform infrastructure deployment for AG-UI demo
#
# Usage:
#   ./setup/infra.sh            # init -> plan -> apply
#   ./setup/infra.sh plan       # init -> plan only
#   ./setup/infra.sh apply      # init -> plan -> apply
#   ./setup/infra.sh destroy    # init -> destroy
#
# Env:
#   AUTO_APPROVE=true|false     # default: true (used for apply/destroy)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INFRA_DIR="$PROJECT_ROOT/infra"
TFVARS_FILE="$INFRA_DIR/terraform.tfvars"

ACTION="${1:-apply}"
AUTO_APPROVE="${AUTO_APPROVE:-true}"

log()  { echo "[infra] $*"; }
fail() { echo "[infra] ERROR: $*"; exit 1; }

command -v terraform >/dev/null 2>&1 || fail "terraform not found in PATH"
command -v az >/dev/null 2>&1 || fail "az CLI not found in PATH"

if ! az account show >/dev/null 2>&1; then
  fail "az CLI not logged in. Run: az login"
fi

if [[ -f "$TFVARS_FILE" ]]; then
  SUBSCRIPTION_ID=$(grep -E "^subscription_id" "$TFVARS_FILE" | sed -E 's/.*"([^"]+)".*/\1/' || true)
  if [[ -n "${SUBSCRIPTION_ID:-}" ]]; then
    log "Setting Azure subscription to ${SUBSCRIPTION_ID}"
    az account set -s "$SUBSCRIPTION_ID"
  fi
fi

log "Initializing Terraform"
terraform -chdir="$INFRA_DIR" init

case "$ACTION" in
  plan)
    log "Planning infrastructure"
    terraform -chdir="$INFRA_DIR" plan -var-file="$TFVARS_FILE" -out=tfplan
    ;;
  apply)
    log "Planning infrastructure"
    terraform -chdir="$INFRA_DIR" plan -var-file="$TFVARS_FILE" -out=tfplan
    log "Applying infrastructure"
    if [[ "$AUTO_APPROVE" == "true" ]]; then
      terraform -chdir="$INFRA_DIR" apply -auto-approve tfplan
    else
      terraform -chdir="$INFRA_DIR" apply tfplan
    fi
    ;;
  destroy)
    log "Destroying infrastructure"
    if [[ "$AUTO_APPROVE" == "true" ]]; then
      terraform -chdir="$INFRA_DIR" destroy -auto-approve -var-file="$TFVARS_FILE"
    else
      terraform -chdir="$INFRA_DIR" destroy -var-file="$TFVARS_FILE"
    fi
    ;;
  *)
    echo "Usage: $0 [plan|apply|destroy]"
    exit 1
    ;;
esac
