# HTTP Deployment Guide for TIM-MCP

This guide covers deploying TIM-MCP server using HTTP transport for network access and production scenarios.

## Overview

HTTP transport mode enables TIM-MCP to run as a web service, allowing:
- Network access from remote clients
- Multiple concurrent client connections
- Integration with existing web infrastructure
- Load balancing and reverse proxy configurations

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

### Dockerfile

Create a Dockerfile for containerized deployment:

```dockerfile
FROM python:3.11-slim

# Install uv
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install dependencies
RUN uv sync --frozen

# Create non-root user
RUN useradd --create-home --shell /bin/bash tim-mcp

# Switch to non-root user
USER tim-mcp

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the server
CMD ["uv", "run", "tim-mcp", "--http", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  tim-mcp:
    build: .
    ports:
      - "8000:8000"
    environment:
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - TIM_ALLOWED_NAMESPACES=terraform-ibm-modules
      - TIM_EXCLUDED_MODULES=
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - /path/to/ssl/certs:/etc/ssl/certs:ro
    depends_on:
      - tim-mcp
    restart: unless-stopped
```

### Run with Docker

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f tim-mcp

# Stop
docker-compose down
```

## Kubernetes Deployment

### Deployment and Service

```yaml
# tim-mcp-k8s.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tim-mcp
  labels:
    app: tim-mcp
spec:
  replicas: 2
  selector:
    matchLabels:
      app: tim-mcp
  template:
    metadata:
      labels:
        app: tim-mcp
    spec:
      containers:
      - name: tim-mcp
        image: your-registry/tim-mcp:latest
        ports:
        - containerPort: 8000
        env:
        - name: GITHUB_TOKEN
          valueFrom:
            secretKeyRef:
              name: tim-mcp-secrets
              key: github-token
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5

---
apiVersion: v1
kind: Service
metadata:
  name: tim-mcp-service
spec:
  selector:
    app: tim-mcp
  ports:
  - port: 80
    targetPort: 8000
  type: ClusterIP

---
apiVersion: v1
kind: Secret
metadata:
  name: tim-mcp-secrets
type: Opaque
data:
  github-token: <base64-encoded-token>
```

### Ingress (optional)

```yaml
# tim-mcp-ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: tim-mcp-ingress
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
  - hosts:
    - tim-mcp.your-domain.com
    secretName: tim-mcp-tls
  rules:
  - host: tim-mcp.your-domain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: tim-mcp-service
            port:
              number: 80
```

## Monitoring and Logging

### Log Configuration

Configure structured logging for production:

```bash
# JSON logging for log aggregation
tim-mcp --http --log-level INFO --log-format json
```

### Health Checks

The server should provide a health endpoint at `/health` for monitoring:

```bash
# Basic health check
curl -f http://localhost:8000/health

# With timeout
curl -f --max-time 10 http://localhost:8000/health
```

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
