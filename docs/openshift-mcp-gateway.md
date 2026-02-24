# Deploy TIM-MCP to Red Hat MCP Gateway on OpenShift

Parent: #17576

## Summary

Deploy TIM-MCP to an IBM Cloud OpenShift (ROKS) cluster behind the
[Red Hat MCP Gateway](https://github.com/Kuadrant/mcp-gateway), an Envoy-based
aggregation gateway that federates multiple MCP servers behind a single endpoint.

## What the Red Hat MCP Gateway Is

The **Red Hat MCP Gateway** ([Kuadrant/mcp-gateway](https://github.com/Kuadrant/mcp-gateway))
consists of three components:

1. **MCP Router** (Envoy ext_proc) — parses JSON-RPC requests, sets routing headers,
   manages sessions
2. **MCP Broker** — aggregates tool lists from backends, handles initialization,
   proxies SSE streams
3. **Discovery Controller** — watches `MCPServerRegistration` CRDs, auto-discovers
   backends

## Investigation Findings

| Area | Finding |
|------|---------|
| **What it provides** | Envoy-based gateway: tool aggregation, OAuth2 auth, rate limiting (Limitador), observability (OTEL), K8s-native discovery via CRDs |
| **Access** | Open source, install via `kubectl apply -k` from repo. Needs: ROKS cluster, Service Mesh (Istio), Gateway API CRDs |
| **TIM MCP modifications** | Minimal — health endpoint + PORT envvar. No protocol changes needed; TIM MCP already speaks MCP/HTTP at `/mcp` |
| **Authentication** | Gateway handles all client auth (OAuth2/Kuadrant/Authorino). TIM MCP needs no client auth. GITHUB_TOKEN is server-side only, stored as K8s Secret |
| **Build/Update** | GitHub Actions workflow builds container images → GHCR. Triggered on tag push (`v*`) |
| **Observability** | Structured JSON logging already compatible with Loki. Future: add OpenTelemetry tracing + Prometheus metrics (separate issue) |

## Authentication Architecture

```
Client (OAuth token) → MCP Gateway (Kuadrant validates, filters tools)
  → HTTPRoute → TIM MCP Service (no auth, behind gateway)
    → GitHub API (GITHUB_TOKEN from K8s Secret)
    → Terraform Registry (public)
```

- **Client authentication** is handled entirely by the MCP Gateway via
  Kuadrant + Keycloak/Authorino. TIM MCP does not implement any client auth.
- **GITHUB_TOKEN** is a server-side secret for outbound API calls to GitHub.
  It is stored as a Kubernetes Secret and injected via environment variable.
  It is _not_ a client credential and is not referenced in the
  `MCPServerRegistration` CRD.
- **Terraform Registry** access is public and requires no authentication.

## Code Changes

### Health Endpoint (`tim_mcp/server.py`)

Added `GET /health` endpoint using `@mcp.custom_route` that checks:
- **GitHub API** — calls `/rate_limit`, reports remaining quota, warns if < 10
- **Terraform Registry** — calls a known module endpoint to verify connectivity

Returns:
- `200` with `{"status": "healthy"}` when all dependencies are reachable
- `200` with `{"status": "degraded"}` when one or more dependencies are down
- `503` only for internal server errors

### PORT Environment Variable (`tim_mcp/main.py`)

The `--port` CLI option now reads from the `PORT` environment variable
(`envvar="PORT"`), allowing container orchestration platforms to configure the
port without modifying the command.

### Container Image (`Dockerfile`)

Multi-stage build on `registry.access.redhat.com/ubi9/python-312:latest`:
- Stage 1 (builder): installs `uv`, syncs dependencies
- Stage 2 (runtime): copies venv + app code, runs as user 1001
- Port 8080, HEALTHCHECK on `/health`
- `SETUPTOOLS_SCM_PRETEND_VERSION` build arg for hatch-vcs

## Deployment Architecture

### Kustomize Structure

```
deploy/openshift/
├── base/                          # Shared resources
│   ├── kustomization.yaml
│   ├── deployment.yaml            # 1 replica, probes, security context
│   ├── service.yaml               # ClusterIP on 8080
│   ├── configmap.yaml             # TIM_LOG_LEVEL, TIM_STRUCTURED_LOGGING
│   └── secret.yaml                # GITHUB_TOKEN placeholder
├── overlays/
│   ├── mcp-gateway/               # Behind Red Hat MCP Gateway
│   │   ├── kustomization.yaml
│   │   ├── httproute.yaml         # Gateway API HTTPRoute
│   │   ├── mcpserverregistration.yaml  # MCP Gateway CRD
│   │   └── networkpolicy.yaml     # Restrict ingress to gateway
│   └── standalone/                # Direct access (testing)
│       ├── kustomization.yaml
│       └── route.yaml             # OpenShift Route with TLS edge
```

### MCP Gateway Overlay

The `MCPServerRegistration` CRD registers TIM MCP with the gateway:
- `toolPrefix: tim_` — tools appear as `tim_search_modules`, `tim_get_module_details`,
  `tim_list_content`, `tim_get_content`
- References the HTTPRoute for traffic routing
- Path defaults to `/mcp` (the standard MCP endpoint)

A `NetworkPolicy` restricts ingress to only traffic from the MCP Gateway namespace.

### Standalone Overlay

For testing without the gateway, the standalone overlay adds an OpenShift Route
with TLS edge termination for direct HTTPS access.

## Prerequisites

- IBM Cloud OpenShift (ROKS) cluster
- OpenShift Service Mesh (Istio) installed
- Gateway API CRDs installed
- MCP Gateway deployed:
  ```bash
  kubectl apply -k 'https://github.com/Kuadrant/mcp-gateway/config/install?ref=v0.5.0'
  ```
- `oc` CLI with cluster-admin access

## Container Image Build

Images are built via GitHub Actions (`.github/workflows/build-image.yml`):
- **Trigger**: tag push (`v*`) and pull requests
- **Registry**: `ghcr.io/terraform-ibm-modules/tim-mcp`
- **Tags**: `v1.2.3` for releases, `sha-<short>` for PRs, `latest` for most recent release

## Deployment Steps

```bash
# Create namespace
oc new-project tim-mcp

# Deploy with MCP Gateway overlay
oc apply -k deploy/openshift/overlays/mcp-gateway

# Create the actual secret (replace placeholder)
oc create secret generic tim-mcp-secrets \
  --from-literal=github-token=<YOUR_TOKEN> \
  -n tim-mcp --dry-run=client -o yaml | oc apply -f -

# Verify deployment
oc get pods -n tim-mcp
oc logs -f deployment/tim-mcp -n tim-mcp

# Verify MCP Gateway discovery
oc get mcpserverregistration tim-mcp -o yaml
# Check status.discoveredTools should list 4 tools
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| No client auth in TIM MCP | Gateway handles OAuth2; TIM MCP sits behind it |
| No `credentialRef` in MCPServerRegistration | GITHUB_TOKEN is outbound server-side, not a forwarded client credential |
| `toolPrefix: tim_` | Short, distinctive, prevents naming conflicts with other backends |
| UBI9 over UBI8 | Longer support lifecycle, better security defaults |
| Port 8080 | OpenShift convention for non-root |
| Kustomize over Helm | Simpler for this use case, base+overlay pattern for gateway vs standalone |
| Disable TIM rate limiting behind gateway | Gateway (Limitador) handles rate limiting at the edge |
| `readOnlyRootFilesystem` | Security hardening; `/tmp` emptyDir + `PYTHONDONTWRITEBYTECODE=1` handles write needs |

## Verification

```bash
# Build and test container locally
docker build --build-arg VERSION=0.1.0 -t tim-mcp:test .
docker run -p 8080:8080 -e GITHUB_TOKEN=<token> tim-mcp:test
curl http://localhost:8080/health
curl -X POST http://localhost:8080/mcp -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'

# Validate K8s manifests
kubectl kustomize deploy/openshift/base
kubectl kustomize deploy/openshift/overlays/mcp-gateway

# Run tests
uv run pytest test/unit/ test/integration/
```

## Future Work (Separate Issues)

- **OpenTelemetry tracing** — Add `opentelemetry-instrumentation-httpx` and
  `opentelemetry-instrumentation-asgi` for distributed tracing through the gateway
- **Prometheus metrics** — `/metrics` endpoint for Grafana dashboards
- **MCP tool annotations** — Mark all tools as `readOnly: true`, `idempotent: true`
  for gateway routing optimization
- **HPA** — HorizontalPodAutoscaler once traffic patterns are understood
- **GitOps** — ArgoCD/OpenShift GitOps for automated deployment sync
