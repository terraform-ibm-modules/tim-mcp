# HTTP Deployment Guide for TIM-MCP

This guide covers deploying TIM-MCP server using HTTP transport for network access and production scenarios.

## Overview

HTTP transport mode enables TIM-MCP to run as a stateless web service, allowing:
- Network access from remote clients
- Multiple concurrent client connections
- Integration with existing web infrastructure
- Load balancing and reverse proxy configurations
- No session ID requirements (stateless operation)
- Horizontal scaling without session affinity

## Basic HTTP Deployment

### Local Testing

Start the server locally for testing:

```bash
# Basic HTTP mode
tim-mcp --http

# Custom port
tim-mcp --http --port 8080

# All interfaces (accessible from other machines)
tim-mcp --http --host 0.0.0.0 --port 8000

# With debug logging
tim-mcp --http --log-level DEBUG
```

The server will be available at:
- Server: `http://127.0.0.1:8000/`
- MCP endpoint: `http://127.0.0.1:8000/mcp`

**Note:** The server runs in stateless mode, so no session IDs are required. Each request is handled independently, making it perfect for load balancing and scaling.

### Environment Variables

Set environment variables for production:

```bash
export GITHUB_TOKEN="your_github_token_here"
export TIM_ALLOWED_NAMESPACES="terraform-ibm-modules"
export TIM_EXCLUDED_MODULES="terraform-ibm-modules/deprecated-module/ibm"

tim-mcp --http --host 0.0.0.0 --port 8000
```

## Production Deployment with nginx

### nginx Configuration

Create an nginx configuration to handle HTTPS and proxy to TIM-MCP:

```nginx
# /etc/nginx/sites-available/tim-mcp
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL Configuration
    ssl_certificate /path/to/your/cert.pem;
    ssl_certificate_key /path/to/your/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-SHA384;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;

    # Security Headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    # Proxy to TIM-MCP server
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (if needed in future)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        access_log off;
    }
}
```

### Enable the Configuration

```bash
# Enable the site
sudo ln -s /etc/nginx/sites-available/tim-mcp /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

## Systemd Service

Create a systemd service for automatic startup and management:

```ini
# /etc/systemd/system/tim-mcp.service
[Unit]
Description=TIM-MCP Server
After=network.target
Wants=network.target

[Service]
Type=simple
User=tim-mcp
Group=tim-mcp
WorkingDirectory=/opt/tim-mcp
Environment=GITHUB_TOKEN=your_github_token_here
Environment=TIM_ALLOWED_NAMESPACES=terraform-ibm-modules
ExecStart=/usr/local/bin/uv run tim-mcp --http --host 127.0.0.1 --port 8000 --log-level INFO
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tim-mcp

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/tim-mcp

[Install]
WantedBy=multi-user.target
```

### Service Management

```bash
# Create user and directory
sudo useradd --system --shell /bin/false tim-mcp
sudo mkdir /opt/tim-mcp
sudo chown tim-mcp:tim-mcp /opt/tim-mcp

# Install tim-mcp in the service directory
sudo -u tim-mcp -H sh -c 'cd /opt/tim-mcp && git clone https://github.com/terraform-ibm-modules/tim-mcp.git . && uv sync'

# Enable and start the service
sudo systemctl enable tim-mcp.service
sudo systemctl start tim-mcp.service

# Check status
sudo systemctl status tim-mcp.service

# View logs
sudo journalctl -u tim-mcp.service -f
```

## Docker Deployment

A production-ready `Dockerfile` is included in the repository root. It uses a
multi-stage build on Red Hat UBI9 with Python 3.12, runs as non-root user 1001,
and listens on port 8080.

### Build and Run

```bash
# Build the image (VERSION is used by hatch-vcs since .git isn't in the image)
docker build --build-arg VERSION=0.1.0 -t tim-mcp:latest .

# Run the container
docker run -p 8080:8080 -e GITHUB_TOKEN=<your_token> tim-mcp:latest

# Test health endpoint
curl http://localhost:8080/health

# Test MCP endpoint
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
```

The `PORT` environment variable controls which port the server listens on
(default: 8080 inside the container).

### Docker Compose

```yaml
# docker-compose.yml
services:
  tim-mcp:
    build:
      context: .
      args:
        VERSION: "0.1.0"
    ports:
      - "8080:8080"
    environment:
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - TIM_ALLOWED_NAMESPACES=terraform-ibm-modules
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health').read()"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    restart: unless-stopped
```

```bash
# Build and start
docker compose up -d

# View logs
docker compose logs -f tim-mcp

# Stop
docker compose down
```

## Kubernetes / OpenShift Deployment

Production Kustomize manifests are provided in `deploy/openshift/`. These work
on both vanilla Kubernetes and OpenShift.

### Kustomize Structure

```
deploy/openshift/
├── base/                       # Shared resources (Deployment, Service, ConfigMap, Secret)
├── overlays/
│   ├── mcp-gateway/            # Behind Red Hat MCP Gateway (HTTPRoute, MCPServerRegistration, NetworkPolicy)
│   └── standalone/             # Direct access via OpenShift Route with TLS edge termination
```

### Deploy to OpenShift

```bash
# Create namespace
oc new-project tim-mcp

# Option A: Standalone (direct access via Route)
oc apply -k deploy/openshift/overlays/standalone

# Option B: Behind Red Hat MCP Gateway
oc apply -k deploy/openshift/overlays/mcp-gateway

# Set the GitHub token (replace placeholder secret)
oc create secret generic tim-mcp-secrets \
  --from-literal=github-token=<YOUR_TOKEN> \
  -n tim-mcp --dry-run=client -o yaml | oc apply -f -

# Verify
oc get pods -n tim-mcp
oc logs -f deployment/tim-mcp -n tim-mcp
```

### Deploy to Vanilla Kubernetes

The base manifests work on any Kubernetes cluster. For ingress, add your own
Ingress or Gateway API HTTPRoute:

```bash
kubectl create namespace tim-mcp
kubectl apply -k deploy/openshift/base
kubectl create secret generic tim-mcp-secrets \
  --from-literal=github-token=<YOUR_TOKEN> \
  -n tim-mcp --dry-run=client -o yaml | kubectl apply -f -
```

### Building on OpenShift (No External Registry)

If you don't have a container image in a registry, you can build directly on
the cluster using OpenShift's built-in build system:

```bash
# Create a binary build config
oc new-build --name=tim-mcp --binary --strategy=docker -n tim-mcp

# Upload source and build
oc start-build tim-mcp --from-dir=. --follow -n tim-mcp

# Patch the deployment to use the internal image
oc set image deployment/tim-mcp \
  tim-mcp=image-registry.openshift-image-registry.svc:5000/tim-mcp/tim-mcp:latest \
  -n tim-mcp
```

For the full MCP Gateway investigation and architecture details, see
[docs/openshift-mcp-gateway.md](../docs/openshift-mcp-gateway.md).

## Monitoring and Logging

### Log Configuration

Configure structured logging for production:

```bash
# JSON logging for log aggregation
tim-mcp --http --log-level INFO --log-format json
```

### Health Checks

The `/health` endpoint checks GitHub API and Terraform Registry connectivity:

```bash
# Basic health check
curl -f http://localhost:8080/health

# With timeout
curl -f --max-time 10 http://localhost:8080/health
```

Response:
```json
{
  "status": "healthy",
  "service": "tim-mcp",
  "dependencies": {
    "github": {
      "status": "healthy",
      "rate_limit_remaining": 4983,
      "rate_limit_total": 5000
    },
    "terraform_registry": {
      "status": "healthy"
    }
  }
}
```

Status values: `healthy` (all deps up), `degraded` (one or more deps down, still returns 200).

### Prometheus Metrics (Future Enhancement)

Consider adding Prometheus metrics for monitoring:
- Request counts and latencies
- Active connections
- Error rates
- Cache hit rates

## Security Considerations

### Access Control

- Use nginx or similar proxy for SSL termination
- Implement IP allowlisting if needed
- Consider authentication for production deployments

### Environment Security

- Store sensitive tokens in environment variables or secrets
- Use non-root users for running the service
- Apply security headers via reverse proxy
- Regular security updates for dependencies

### Network Security

- Use private networks where possible
- Configure firewall rules appropriately
- Monitor for unusual traffic patterns

## Troubleshooting

### Common Issues

1. **Port already in use**: Change port with `--port` option
2. **Permission denied**: Ensure user has permission to bind to port
3. **Connection refused**: Check if server is running and accessible
4. **SSL certificate errors**: Verify certificate paths and permissions

### Debug Mode

Enable debug logging for troubleshooting:

```bash
tim-mcp --http --log-level DEBUG
```

### Log Analysis

Monitor logs for errors and performance issues:

```bash
# Systemd logs
sudo journalctl -u tim-mcp.service -f

# Docker logs
docker-compose logs -f tim-mcp
```

This deployment guide provides comprehensive options for running TIM-MCP in HTTP mode, from simple local testing to production Kubernetes deployments.
