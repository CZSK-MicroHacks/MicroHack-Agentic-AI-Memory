#!/usr/bin/env bash
# =============================================================================
# deploy.sh – Build & deploy backend + frontend to Azure Container Apps
#
# Usage:
#   ./setup/deploy.sh               # deploy both
#   ./setup/deploy.sh backend       # deploy backend only
#   ./setup/deploy.sh frontend      # deploy frontend only
#
# Prerequisites:
#   - az CLI logged in
#   - Terraform infrastructure already provisioned (infra/)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Configuration (derived from Terraform outputs) ──────────────────────────
RESOURCE_GROUP="rg-mhaimemk-001"
PROJECT_NAME="mhaimemk001"
SUBSCRIPTION_ID="6766574f-da48-496f-b65a-18d9e5f726a4"

echo "Starting deployment of projet ${PROJECT_NAME} into RG: ${RESOURCE_GROUP} (sub: ${SUBSCRIPTION_ID})..."

# Ensure correct subscription
az account set -s "$SUBSCRIPTION_ID"

BACKEND_APP="ca-backend-${PROJECT_NAME}"
FRONTEND_APP="ca-frontend-${PROJECT_NAME}"

# ACR – auto-detect from resource group
ACR_LOGIN_SERVER=$(az acr list -g "$RESOURCE_GROUP" --query "[0].loginServer" -o tsv)
ACR_NAME=$(az acr list -g "$RESOURCE_GROUP" --query "[0].name" -o tsv)

if [[ -z "$ACR_LOGIN_SERVER" ]]; then
  echo "❌ No ACR found in resource group $RESOURCE_GROUP"
  exit 1
fi

# Managed Identity
IDENTITY_CLIENT_ID=$(az identity show -n "id-${PROJECT_NAME}" -g "$RESOURCE_GROUP" --query clientId -o tsv)
IDENTITY_RESOURCE_ID=$(az identity show -n "id-${PROJECT_NAME}" -g "$RESOURCE_GROUP" --query id -o tsv)

# Image tags – default to git short hash + timestamp to avoid stale-tag rollouts
TAG="${DEPLOY_TAG:-$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo local)-$(date +%Y%m%d%H%M%S)}"
BUILD_ID="${DEPLOY_BUILD_ID:-$(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo "")}"

# ── Service endpoints (from Terraform-provisioned resources) ────────────────
COSMOS_ENDPOINT=$(az cosmosdb show -n "cosmos-${PROJECT_NAME}" -g "$RESOURCE_GROUP" --query documentEndpoint -o tsv)
PG_FQDN=$(az postgres flexible-server show -n "pgflex-${PROJECT_NAME}-db" -g "$RESOURCE_GROUP" --query fullyQualifiedDomainName -o tsv)
BACKEND_FQDN=$(az containerapp show -n "$BACKEND_APP" -g "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv)
OPENAI_ENDPOINT=$(az cognitiveservices account show -n "aifoundry-${PROJECT_NAME}" -g "$RESOURCE_GROUP" --query "properties.endpoint" -o tsv)
SEARCH_ENDPOINT=$(az search service show -n "search-${PROJECT_NAME}" -g "$RESOURCE_GROUP" --query "endpoint" -o tsv 2>/dev/null || echo "")
REDIS_HOST=$(az redis show -n "redis-${PROJECT_NAME}" -g "$RESOURCE_GROUP" --query "hostName" -o tsv 2>/dev/null || echo "")
REDIS_PASSWORD=$(az redis list-keys -n "redis-${PROJECT_NAME}" -g "$RESOURCE_GROUP" --query "primaryKey" -o tsv 2>/dev/null || echo "")

# Auth settings (prefer Terraform outputs so deploy always matches infra state)
AUTH_MODE="${AUTH_MODE:-$(terraform -chdir="$PROJECT_ROOT/infra" output -raw auth_mode 2>/dev/null || echo entra)}"
ENTRA_TENANT_ID="$(terraform -chdir="$PROJECT_ROOT/infra" output -raw entra_tenant_id 2>/dev/null || echo "")"
BACKEND_API_CLIENT_ID="$(terraform -chdir="$PROJECT_ROOT/infra" output -raw backend_api_client_id 2>/dev/null || echo "")"
FRONTEND_SPA_CLIENT_ID="$(terraform -chdir="$PROJECT_ROOT/infra" output -raw frontend_spa_client_id 2>/dev/null || echo "")"
BACKEND_API_SCOPE="$(terraform -chdir="$PROJECT_ROOT/infra" output -raw backend_api_scope 2>/dev/null || echo "")"

# ── Helpers ─────────────────────────────────────────────────────────────────
log()  { echo "──▶ $*"; }
ok()   { echo "  ✅ $*"; }
fail() { echo "  ❌ $*"; exit 1; }

acr_build() {
  local image_name="$1"
  local context_dir="$2"

  log "Building ${image_name} in ACR (cloud build)…"
  az acr build \
    --registry "$ACR_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --image "$image_name" \
    --platform linux/amd64 \
    "$context_dir"
  ok "Image built & pushed: ${image_name}"
}

ensure_registry_configured() {
  local app_name="$1"
  local has_registry
  has_registry=$(az containerapp show -n "$app_name" -g "$RESOURCE_GROUP" \
    --query "length(properties.configuration.registries[?server=='${ACR_LOGIN_SERVER}'])" -o tsv 2>/dev/null || echo "0")

  if [[ "$has_registry" == "0" ]]; then
    log "Configuring ACR registry on ${app_name}…"
    az containerapp registry set -n "$app_name" -g "$RESOURCE_GROUP" \
      --server "$ACR_LOGIN_SERVER" \
      --identity "$IDENTITY_RESOURCE_ID"
    ok "Registry configured"
  else
    ok "Registry already configured on ${app_name}"
  fi
}

# ── Backend deploy ──────────────────────────────────────────────────────────
deploy_backend() {
  acr_build "${BACKEND_APP}:${TAG}" "$PROJECT_ROOT/backend"

  ensure_registry_configured "$BACKEND_APP"

  log "Updating container app ${BACKEND_APP}…"
  az containerapp update -n "$BACKEND_APP" -g "$RESOURCE_GROUP" \
    --image "${ACR_LOGIN_SERVER}/${BACKEND_APP}:${TAG}" \
    --set-env-vars \
      "AZURE_CLIENT_ID=${IDENTITY_CLIENT_ID}" \
      "AUTH_MODE=${AUTH_MODE}" \
      "ENTRA_TENANT_ID=${ENTRA_TENANT_ID}" \
      "ENTRA_AUDIENCE=${BACKEND_API_CLIENT_ID}" \
      "ENTRA_REQUIRED_SCOPES=access_as_user" \
      "COSMOS_ENDPOINT=${COSMOS_ENDPOINT}" \
      "COSMOS_DATABASE_NAME=ag-ui-db" \
      "COSMOS_CONTAINER_NAME=conversations" \
      "COSMOS_UPM_DATABASE_NAME=ag-ui-db" \
      "COSMOS_UPM_CONTAINER_NAME=user_profiles" \
      "PG_HOST=${PG_FQDN}" \
      "PG_PORT=5432" \
      "PG_DATABASE=appdb" \
      "PG_AUTH_MODE=managed_identity" \
      "PG_AAD_PRINCIPAL_NAME=id-${PROJECT_NAME}" \
      "AZURE_OPENAI_ENDPOINT=${OPENAI_ENDPOINT}" \
      "AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-mini" \
      "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME=text-embedding-3-large" \
      "AZURE_SEARCH_ENDPOINT=${SEARCH_ENDPOINT}" \
      "AZURE_SEARCH_KNOWLEDGE_BASE_NAME=customer-support-kb" \
      "AZURE_SEARCH_ORDERS_INDEX=orders" \
      "REDIS_HOST=${REDIS_HOST}" \
      "REDIS_PORT=6380" \
      "REDIS_PASSWORD=${REDIS_PASSWORD}" \
      "REDIS_SSL=true"
  ok "Backend container app updated"

  # Ensure ingress target port matches uvicorn
  az containerapp ingress update -n "$BACKEND_APP" -g "$RESOURCE_GROUP" \
    --target-port 8000 >/dev/null 2>&1
  ok "Backend ingress target port set to 8000"

  wait_for_revision "$BACKEND_APP"
}

# ── Frontend deploy ─────────────────────────────────────────────────────────
deploy_frontend() {
  acr_build "${FRONTEND_APP}:${TAG}" "$PROJECT_ROOT/frontend"

  ensure_registry_configured "$FRONTEND_APP"

  log "Updating container app ${FRONTEND_APP}…"
  az containerapp update -n "$FRONTEND_APP" -g "$RESOURCE_GROUP" \
    --image "${ACR_LOGIN_SERVER}/${FRONTEND_APP}:${TAG}" \
    --set-env-vars \
      "BACKEND_URL=https://${BACKEND_FQDN}" \
      "BUILD_ID=${BUILD_ID}" \
      "AUTH_MODE=${AUTH_MODE}" \
      "ENTRA_TENANT_ID=${ENTRA_TENANT_ID}" \
      "ENTRA_CLIENT_ID=${FRONTEND_SPA_CLIENT_ID}" \
      "ENTRA_API_SCOPE=${BACKEND_API_SCOPE}"
  ok "Frontend container app updated"

  # Ensure ingress target port matches nginx
  az containerapp ingress update -n "$FRONTEND_APP" -g "$RESOURCE_GROUP" \
    --target-port 8080 >/dev/null 2>&1
  ok "Frontend ingress target port set to 8080"

  wait_for_revision "$FRONTEND_APP"
}

# ── Wait for healthy revision ──────────────────────────────────────────────
wait_for_revision() {
  local app_name="$1"
  local max_wait=120
  local elapsed=0

  log "Waiting for ${app_name} to become healthy (max ${max_wait}s)…"

  while [[ $elapsed -lt $max_wait ]]; do
    local state
    state=$(az containerapp show -n "$app_name" -g "$RESOURCE_GROUP" \
      --query "properties.latestRevisionName" -o tsv)

    local health running
    health=$(az containerapp revision show -n "$app_name" -g "$RESOURCE_GROUP" \
      --revision "$state" --query "properties.healthState" -o tsv 2>/dev/null || echo "Unknown")
    running=$(az containerapp revision show -n "$app_name" -g "$RESOURCE_GROUP" \
      --revision "$state" --query "properties.runningState" -o tsv 2>/dev/null || echo "Unknown")

    if [[ "$health" == "Healthy" && "$running" != "Activating" ]]; then
      ok "${app_name} revision ${state} is Healthy / ${running}"
      return 0
    fi

    echo "    ⏳ ${state}: health=${health} running=${running} (${elapsed}s)"
    sleep 10
    elapsed=$((elapsed + 10))
  done

  echo "  ⚠️  Timeout waiting for ${app_name}. Fetching logs…"
  az containerapp logs show -n "$app_name" -g "$RESOURCE_GROUP" --tail 20
  return 1
}

# ── Smoke test ──────────────────────────────────────────────────────────────
smoke_test() {
  log "Running smoke tests…"
  local failures=0

  # Backend /me (unauthenticated must be rejected in entra mode)
  local backend_url="https://${BACKEND_FQDN}"
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" "${backend_url}/me" 2>/dev/null || echo "000")
  if [[ "$AUTH_MODE" == "entra" ]]; then
    if [[ "$status" == "401" ]]; then
      ok "Backend /me unauthenticated → 401"
    else
      echo "  ⚠️  Backend /me unauthenticated → ${status} (expected 401 in entra mode)"
      failures=$((failures + 1))
    fi
  else
    if [[ "$status" == "401" ]]; then
      ok "Backend /me without mock header → 401"
    else
      echo "  ⚠️  Backend /me without mock header → ${status} (expected 401 in mock mode)"
      failures=$((failures + 1))
    fi
  fi

  # Frontend index
  local frontend_fqdn
  frontend_fqdn=$(az containerapp show -n "$FRONTEND_APP" -g "$RESOURCE_GROUP" \
    --query "properties.configuration.ingress.fqdn" -o tsv)
  status=$(curl -s -o /dev/null -w "%{http_code}" "https://${frontend_fqdn}/" 2>/dev/null || echo "000")
  if [[ "$status" == "200" ]]; then
    ok "Frontend / → 200"
  else
    echo "  ⚠️  Frontend / → ${status}"
    failures=$((failures + 1))
  fi

  # Frontend config.js
  local config_body
  config_body=$(curl -s "https://${frontend_fqdn}/config.js" 2>/dev/null)
  if echo "$config_body" | grep -q "apiBaseUrl"; then
    ok "Frontend /config.js contains apiBaseUrl"
  else
    echo "  ⚠️  Frontend /config.js missing apiBaseUrl"
    failures=$((failures + 1))
  fi

  # CORS preflight
  status=$(curl -s -o /dev/null -w "%{http_code}" -X OPTIONS "${backend_url}/me" \
    -H "Origin: https://${frontend_fqdn}" \
    -H "Access-Control-Request-Method: GET" \
    -H "Access-Control-Request-Headers: Authorization" 2>/dev/null || echo "000")
  if [[ "$status" == "200" ]]; then
    ok "CORS preflight → 200"
  else
    echo "  ⚠️  CORS preflight → ${status}"
    failures=$((failures + 1))
  fi

  echo ""
  if [[ $failures -eq 0 ]]; then
    echo "  ✅ All smoke tests successful!"
  else
    echo "  ⚠️  ${failures} smoke test(s) failed"
  fi
  echo "  Frontend: https://${frontend_fqdn}"
  echo "  Backend:  ${backend_url}"
}

# ── Print .env variables for local development ─────────────────────────────
print_env_summary() {
  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║  backend/.env – copy the block below into your .env file   ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  cat <<EOF

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT=${OPENAI_ENDPOINT}
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-mini
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME=text-embedding-3-large

# ── Azure Cosmos DB (Conversation History) ──────────────────
COSMOS_ENDPOINT=${COSMOS_ENDPOINT}
COSMOS_DATABASE_NAME=ag-ui-db
COSMOS_CONTAINER_NAME=conversations

COSMOS_UPM_DATABASE_NAME=ag-ui-db
COSMOS_UPM_CONTAINER_NAME=user_profiles

# Local auth mode
AUTH_MODE=${AUTH_MODE}
# These variables are only needed for Entra authentication
# AZURE_CLIENT_ID=${IDENTITY_CLIENT_ID}
# ENTRA_TENANT_ID=${ENTRA_TENANT_ID}
# ENTRA_AUDIENCE=${BACKEND_API_CLIENT_ID}
# ENTRA_REQUIRED_SCOPES=access_as_user

# Postgres db
PG_HOST=${PG_FQDN}
PG_PORT=5432
PG_DATABASE=appdb
PG_AUTH_MODE=managed_identity
PG_AAD_PRINCIPAL_NAME=id-${PROJECT_NAME}

# Azure AI Search
AZURE_SEARCH_ENDPOINT=${SEARCH_ENDPOINT}
AZURE_SEARCH_KNOWLEDGE_BASE_NAME=customer-support-kb
AZURE_SEARCH_ORDERS_INDEX=orders

# Azure Cache for Redis (Session Memory)
REDIS_HOST=${REDIS_HOST}
REDIS_PORT=6380
REDIS_PASSWORD=${REDIS_PASSWORD}
REDIS_SSL=true
EOF
  echo ""
}

# ── Main ────────────────────────────────────────────────────────────────────
main() {
  local target="${1:-all}"

  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║  AG-UI Demo – Azure Container Apps Deploy                  ║"
  echo "║  Tag: ${TAG}                                       ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo ""

  case "$target" in
    backend)
      deploy_backend
      smoke_test
      print_env_summary
      ;;
    frontend)
      deploy_frontend
      smoke_test
      print_env_summary
      ;;
    all)
      deploy_backend
      deploy_frontend
      smoke_test
      print_env_summary
      ;;
    test)
      smoke_test
      ;;
    *)
      echo "Usage: $0 [backend|frontend|all|test]"
      exit 1
      ;;
  esac
}

main "$@"
