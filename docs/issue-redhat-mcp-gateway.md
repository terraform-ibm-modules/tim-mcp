# Deploy TIM-MCP to Red Hat MCP Gateway on OpenShift

Parent: #17576

## Summary

Deploy TIM-MCP to an IBM Cloud OpenShift (ROKS) cluster behind the Red Hat MCP Gateway, replacing the IBM Code Engine deployment from PR #58.

## Investigation Findings

The **Red Hat MCP Gateway** ([Kuadrant/mcp-gateway](https://github.com/Kuadrant/mcp-gateway)) is an Envoy-based gateway that aggregates multiple MCP servers behind a single endpoint. It provides:

- **Authentication**: OAuth2/RBAC via Kuadrant + Keycloak (handled at gateway level, not by TIM-MCP)
- **Observability**: Envoy access logs, metrics (`:8082`), distributed tracing, audit trail
- **Tool federation**: Aggregates tools from multiple backends with configurable prefixes
- **Policy enforcement**: Rate limiting via Limitador, identity-based tool filtering

**TIM-MCP is already largely compatible.** It implements the MCP protocol over HTTP, is stateless, and has a health endpoint. Minimal code changes are needed.

## Implementation Tasks

### 1. Code Changes (Minimal)

- [ ] **`tim_mcp/main.py`**: Add `envvar="PORT"` to the `--port` Click option and change default to 8080 (OpenShift convention)
- [ ] **`tim_mcp/server.py`**: Add `@mcp.custom_route("/health")` endpoint that checks GitHub API and Terraform Registry connectivity, returning `{"status": "healthy|degraded", "checks": {...}}`

### 2. Container Image

- [ ] **`Dockerfile`**: Multi-stage build using `registry.access.redhat.com/ubi9/python-312` (UBI base for Red Hat compatibility). Runs as user 1001 (OpenShift arbitrary UID). Uses `SETUPTOOLS_SCM_PRETEND_VERSION` build arg for hatch-vcs.
- [ ] **`.dockerignore`**: Exclude `.git`, `.venv`, `test/`, `common-dev-assets/`, etc.

### 3. OpenShift Base Manifests (`deploy/openshift/base/`)

Kustomize-based deployment with:

- [ ] `deployment.yaml` — 1 replica, port 8080, liveness/readiness probes on `/health`, security context (runAsNonRoot, readOnlyRootFilesystem, drop ALL caps, seccomp RuntimeDefault), GITHUB_TOKEN from Secret, `/tmp` emptyDir volume
- [ ] `service.yaml` — ClusterIP on port 8080
- [ ] `configmap.yaml` — TIM_LOG_LEVEL, TIM_STRUCTURED_LOGGING, TIM_ALLOWED_NAMESPACES
- [ ] `secret.yaml` — Placeholder for github-token (replaced at deploy time)
- [ ] `kustomization.yaml` — Orchestrates all resources

### 4. MCP Gateway Overlay (`deploy/openshift/overlays/mcp-gateway/`)

- [ ] `httproute.yaml` — Gateway API HTTPRoute pointing to tim-mcp Service
- [ ] `mcpserverregistration.yaml` — MCP Gateway CRD with `toolPrefix: tim_`, references HTTPRoute, path defaults to `/mcp`
- [ ] `kustomization.yaml` — Extends base, adds gateway resources

Tools appear through the gateway as: `tim_search_modules`, `tim_get_module_details`, `tim_list_content`, `tim_get_content`

### 5. Standalone Overlay (`deploy/openshift/overlays/standalone/`)

- [ ] `route.yaml` — OpenShift Route with TLS edge termination (for testing without the gateway)
- [ ] `kustomization.yaml`

### 6. Documentation

- [ ] `docs/openshift-mcp-gateway.md` — Investigation findings, architecture overview, prerequisites, build instructions, deployment steps, auth explanation, observability, troubleshooting

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **No `credentialRef` in MCPServerRegistration** | GITHUB_TOKEN is a server-side secret for outbound API calls, not a client credential the gateway forwards |
| **`toolPrefix: tim_`** | Short, distinctive, matches project name |
| **UBI9 (not UBI8)** | Latest RHEL base, longer support lifecycle, better security defaults |
| **Port 8080** | OpenShift convention for non-root processes |
| **readOnlyRootFilesystem** | Security hardening; `/tmp` emptyDir + `PYTHONDONTWRITEBYTECODE=1` handles write needs |
| **Gateway handles client auth** | TIM-MCP doesn't implement OAuth; Kuadrant/Keycloak at gateway level handles this |

## Authentication Architecture

```
Client (with OAuth token)
  → MCP Gateway (Envoy + Kuadrant validates token, filters tools by identity)
    → HTTPRoute
      → TIM-MCP Service (no auth required, sits behind gateway)
        → GitHub API (uses GITHUB_TOKEN from K8s Secret)
        → Terraform Registry (public, no auth)
```

## Prerequisites

- IBM Cloud OpenShift (ROKS) cluster
- OpenShift Service Mesh (Istio) installed
- Gateway API CRDs installed
- MCP Gateway deployed ([install docs](https://github.com/Kuadrant/mcp-gateway/tree/main/config/openshift)) — install via `kubectl apply -k 'https://github.com/Kuadrant/mcp-gateway/config/install?ref=v0.5.0'`
- Container image registry (e.g., ICR, Quay.io)
- `oc` CLI access with cluster-admin

## Verification

```bash
# Build image
docker build --build-arg VERSION=0.1.0 -t tim-mcp:test .

# Test locally
docker run -p 8080:8080 -e GITHUB_TOKEN=<token> tim-mcp:test
curl http://localhost:8080/health
curl -X POST http://localhost:8080/mcp -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'

# Validate manifests
kubectl kustomize deploy/openshift/base
kubectl kustomize deploy/openshift/overlays/mcp-gateway

# Deploy to OpenShift
oc apply -k deploy/openshift/overlays/mcp-gateway
oc create secret generic tim-mcp-secrets --from-literal=github-token=<TOKEN> -n tim-mcp
oc get mcpserverregistration tim-mcp -o yaml  # Check status.discoveredTools = 4

# Run tests
uv run pytest test/unit/
```

## Acceptance Criteria

- [ ] Container builds successfully with UBI9 base image
- [ ] Health endpoint returns dependency status (GitHub API, Terraform Registry)
- [ ] Deploys to OpenShift via `oc apply -k`
- [ ] MCPServerRegistration discovers all 4 tools through the gateway
- [ ] All MCP tools function correctly through the gateway endpoint
- [ ] Documentation covers deployment, auth, observability, and troubleshooting
- [ ] Existing unit tests pass
