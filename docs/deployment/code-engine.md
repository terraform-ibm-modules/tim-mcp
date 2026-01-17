# Code Engine Deployment Guide

This guide provides step-by-step instructions for deploying tim-mcp to IBM Code Engine as a containerized HTTP service.

## Prerequisites

Before deploying to Code Engine, ensure you have:

1. **IBM Cloud Account** with access to Code Engine
2. **IBM Cloud CLI** installed and configured
   ```bash
   # Install IBM Cloud CLI
   curl -fsSL https://clis.cloud.ibm.com/install/linux | sh

   # Install Code Engine plugin
   ibmcloud plugin install code-engine

   # Verify installation
   ibmcloud ce version
   ```

3. **Docker** installed for building container images
   ```bash
   docker --version
   ```

4. **GitHub Personal Access Token** (optional but recommended)
   - Without token: 60 requests/hour
   - With token: 5,000 requests/hour
   - Create at: https://github.com/settings/tokens
   - Permissions: No private access scopes needed (public repositories only)

5. **IBM Cloud API Key**
   - Create at: https://cloud.ibm.com/iam/apikeys
   - Save securely (you'll need it for authentication)

## Step 1: IBM Cloud Authentication

```bash
# Login to IBM Cloud
ibmcloud login --apikey <your-api-key>

# Or use interactive login
ibmcloud login

# Target your region and resource group
ibmcloud target -r us-south -g default

# Verify you're targeting the correct region/resource group
ibmcloud target
```

## Step 2: Container Registry Setup

```bash
# Create a namespace in IBM Container Registry (if not exists)
ibmcloud cr namespace-add tim-mcp

# Verify namespace creation
ibmcloud cr namespace-list
```

## Step 3: Build and Push Container Image

### Option A: Using Code Engine Build Service (Recommended)

The Code Engine build service ensures the image is built for the correct platform (linux/amd64):

```bash
# Navigate to tim-mcp directory
cd /path/to/tim-mcp

# Create a build configuration
ibmcloud ce build create --name tim-mcp-build \
  --source https://github.com/terraform-ibm-modules/tim-mcp \
  --commit main \
  --context-dir . \
  --dockerfile Dockerfile \
  --image us.icr.io/tim-mcp/tim-mcp:latest \
  --registry-secret icr-secret \
  --size medium

# Note: First create the registry secret if it doesn't exist:
# ibmcloud ce registry create --name icr-secret \
#   --server us.icr.io \
#   --username iamapikey \
#   --password <your-ibm-cloud-api-key>

# Submit a build run
ibmcloud ce buildrun submit --build tim-mcp-build --name tim-mcp-buildrun-1

# Follow the build logs
ibmcloud ce buildrun logs -f -n tim-mcp-buildrun-1

# Verify the image
ibmcloud cr image-list --restrict tim-mcp
```

### Option B: Local Docker Build

If building locally, you must specify the platform to ensure compatibility with Code Engine:

```bash
# Navigate to tim-mcp directory
cd /path/to/tim-mcp

# Build the Docker image for linux/amd64 platform
# IMPORTANT: Code Engine requires linux/amd64 images
docker build --platform linux/amd64 -t us.icr.io/tim-mcp/tim-mcp:latest .

# Login to IBM Container Registry
ibmcloud cr login

# Push the image
docker push us.icr.io/tim-mcp/tim-mcp:latest

# Verify the image
ibmcloud cr image-list --restrict tim-mcp
```

**Platform Architecture Note**:
- Code Engine runs on AMD64/x86_64 architecture
- If building on ARM64 systems (e.g., Apple Silicon Macs), you MUST use `--platform linux/amd64`
- Without the platform flag, the image may fail to start with "no match for platform in manifest" errors
- The Code Engine build service (Option A) handles this automatically

## Step 4: Create Code Engine Project

```bash
# Create a new Code Engine project (if needed)
ibmcloud ce project create --name tim-mcp-project

# Or select existing project
ibmcloud ce project select --name tim-mcp-project
```

## Step 5: Create Secret for GitHub Token

```bash
# Create secret with your GitHub token
ibmcloud ce secret create --name tim-mcp-secrets \
  --from-literal GITHUB_TOKEN=<your-github-token>

# Verify secret creation
ibmcloud ce secret get --name tim-mcp-secrets
```

**Security Note**: Never commit your GitHub token to version control. Always store it in IBM Cloud Secrets.

## Step 6: Deploy Application

```bash
# Deploy the application
ibmcloud ce application create --name tim-mcp \
  --image us.icr.io/tim-mcp/tim-mcp:latest \
  --cpu 0.25 \
  --memory 512M \
  --min-scale 1 \
  --max-scale 3 \
  --port 8080 \
  --env-from-secret tim-mcp-secrets \
  --env TIM_LOG_LEVEL=INFO \
  --env TIM_CACHE_TTL=3600 \
  --env TIM_ALLOWED_NAMESPACES=terraform-ibm-modules \
  --probe-live /health \
  --probe-ready /health

# Get application URL
ibmcloud ce application get --name tim-mcp --output url
```

### Configuration Options Explained

| Option | Value | Description |
|--------|-------|-------------|
| `--cpu` | 0.25 | vCPU allocation (0.25 = 1/4 core) |
| `--memory` | 512M | Memory allocation (minimum for Python app) |
| `--min-scale` | 1 | Minimum instances (avoids cold starts) |
| `--max-scale` | 3 | Maximum instances (limits costs) |
| `--port` | 8080 | Container port (matches Dockerfile) |
| `--probe-live` | /health | Liveness probe endpoint |
| `--probe-ready` | /health | Readiness probe endpoint |

## Step 7: Verify Deployment

```bash
# Check application status
ibmcloud ce application get --name tim-mcp

# View application logs
ibmcloud ce application logs --name tim-mcp --follow

# Get the public URL
APP_URL=$(ibmcloud ce application get --name tim-mcp --output url)
echo "Application URL: ${APP_URL}"

# Test health endpoint
curl ${APP_URL}/health

# Test MCP protocol
curl -X POST ${APP_URL}/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

**Expected Output** (health check):
```json
{
  "status": "healthy",
  "service": "tim-mcp"
}
```

## Automated Deployment Script

For convenience, use the provided deployment script:

```bash
# Set environment variables
export GITHUB_TOKEN=<your-github-token>
export IBM_CLOUD_REGION=us-south
export IBM_CLOUD_RESOURCE_GROUP=default
export GIT_BRANCH=main  # Optional, defaults to main

# Run deployment script
./scripts/deploy-code-engine.sh

# Or deploy with specific version
./scripts/deploy-code-engine.sh v1.0.0
```

The script handles:
- Building the container image using Code Engine build service (ensures correct platform)
- Creating/updating build configuration
- Submitting build runs and monitoring progress
- Creating/updating secrets
- Deploying/updating the Code Engine application

**Note**: The deployment script uses Code Engine's build service instead of local Docker builds to ensure the image is built for the correct platform (linux/amd64), avoiding platform architecture mismatch errors.

## Updating the Application

To deploy a new version:

### Using Code Engine Build Service (Recommended)

```bash
# Update the build to point to the new version/branch
ibmcloud ce build update --name tim-mcp-build \
  --commit v1.0.1 \
  --image us.icr.io/tim-mcp/tim-mcp:v1.0.1

# Submit a new build run
ibmcloud ce buildrun submit --build tim-mcp-build

# Update application with new image
ibmcloud ce application update --name tim-mcp \
  --image us.icr.io/tim-mcp/tim-mcp:v1.0.1

# Verify update
ibmcloud ce application get --name tim-mcp
```

### Using Local Docker Build

```bash
# Build and push new image with platform flag
docker build --platform linux/amd64 -t us.icr.io/tim-mcp/tim-mcp:v1.0.1 .
ibmcloud cr login
docker push us.icr.io/tim-mcp/tim-mcp:v1.0.1

# Update application
ibmcloud ce application update --name tim-mcp \
  --image us.icr.io/tim-mcp/tim-mcp:v1.0.1

# Verify update
ibmcloud ce application get --name tim-mcp
```

## Scaling the Application

```bash
# Scale up
ibmcloud ce application update --name tim-mcp \
  --min-scale 2 --max-scale 5

# Scale to zero (when idle)
ibmcloud ce application update --name tim-mcp \
  --min-scale 0 --max-scale 3

# Manual scale
ibmcloud ce application update --name tim-mcp \
  --min-scale 3 --max-scale 3
```

## Environment Variables

Configure additional environment variables:

```bash
# Update environment variables
ibmcloud ce application update --name tim-mcp \
  --env TIM_LOG_LEVEL=DEBUG \
  --env TIM_CACHE_TTL=7200 \
  --env TIM_REQUEST_TIMEOUT=60
```

### Available Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_TOKEN` | None | GitHub PAT for API authentication |
| `PORT` | 8080 | HTTP server port (set by Code Engine) |
| `TIM_LOG_LEVEL` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `TIM_CACHE_TTL` | 3600 | Cache TTL in seconds |
| `TIM_REQUEST_TIMEOUT` | 30 | External API timeout in seconds |
| `TIM_ALLOWED_NAMESPACES` | terraform-ibm-modules | Allowed module namespaces |

## Monitoring and Logs

### View Logs

```bash
# Real-time logs
ibmcloud ce application logs --name tim-mcp --follow

# Recent logs
ibmcloud ce application logs --name tim-mcp --tail 100

# Logs for specific instance
ibmcloud ce application logs --name tim-mcp --instance <instance-name>
```

### Check Application Status

```bash
# Detailed status
ibmcloud ce application get --name tim-mcp

# List all applications
ibmcloud ce application list

# Get events
ibmcloud ce application events --name tim-mcp
```

## Troubleshooting

### Application Not Starting

**Symptom**: Application shows "Not Ready" status

**Solutions**:
```bash
# Check logs for errors
ibmcloud ce application logs --name tim-mcp

# Verify image exists
ibmcloud cr image-list --restrict tim-mcp

# Check health endpoint
curl https://<app-url>/health
```

### Health Check Failing

**Symptom**: Health probe failures in logs

**Solutions**:
- Verify `/health` endpoint returns 200 OK
- Check application is listening on port 8080
- Increase health probe timeout if needed

### Rate Limiting Errors

**Symptom**: GitHub API rate limit errors in logs

**Solutions**:
```bash
# Verify GitHub token is set
ibmcloud ce secret get --name tim-mcp-secrets

# Update token if expired
ibmcloud ce secret update --name tim-mcp-secrets \
  --from-literal GITHUB_TOKEN=<new-token>

# Restart application
ibmcloud ce application update --name tim-mcp --image us.icr.io/tim-mcp/tim-mcp:latest
```

### High Memory Usage

**Symptom**: Application restarting due to OOM

**Solutions**:
```bash
# Increase memory allocation
ibmcloud ce application update --name tim-mcp --memory 1G

# Check memory usage in logs
ibmcloud ce application logs --name tim-mcp | grep -i memory
```

### Platform Architecture Mismatch

**Symptom**: Image pull errors with "no match for platform in manifest: not found"

**Cause**: Docker image was built for the wrong CPU architecture (e.g., ARM64 instead of AMD64)

**Solutions**:

1. **Use Code Engine Build Service** (Recommended):
   ```bash
   # Create and run a build using Code Engine
   ibmcloud ce build create --name tim-mcp-build \
     --source https://github.com/terraform-ibm-modules/tim-mcp \
     --commit main \
     --dockerfile Dockerfile \
     --image us.icr.io/tim-mcp/tim-mcp:latest \
     --registry-secret icr-secret \
     --size medium

   ibmcloud ce buildrun submit --build tim-mcp-build
   ```

2. **Rebuild with Correct Platform Locally**:
   ```bash
   # Rebuild image for AMD64 platform
   docker build --platform linux/amd64 -t us.icr.io/tim-mcp/tim-mcp:latest .
   docker push us.icr.io/tim-mcp/tim-mcp:latest

   # Update application to pull new image
   ibmcloud ce application update --name tim-mcp \
     --image us.icr.io/tim-mcp/tim-mcp:latest
   ```

**Prevention**: Always build images for linux/amd64 when deploying to Code Engine, especially when building on ARM64 systems (Apple Silicon Macs)

## Cost Optimization

### Current Configuration Cost

**MVP Setup** (us-south region):
- 0.25 vCPU, 512MB RAM, min-scale=1, max-scale=3
- **Estimated cost**: ~$25-30/month for 24/7 operation

### Reduce Costs

1. **Scale to Zero** (recommended after testing):
   ```bash
   ibmcloud ce application update --name tim-mcp --min-scale 0
   ```
   - **New cost**: ~$0-5/month (only pay for active usage)
   - **Trade-off**: Cold start latency (~5-10 seconds)

2. **Reduce Resources** (if sufficient):
   ```bash
   ibmcloud ce application update --name tim-mcp \
     --cpu 0.125 --memory 256M
   ```
   - **Savings**: ~50% cost reduction
   - **Trade-off**: May impact performance

3. **Set Maximum Instances**:
   ```bash
   ibmcloud ce application update --name tim-mcp --max-scale 2
   ```
   - Prevents unexpected cost spikes

## Cleanup

To remove the application and resources:

```bash
# Delete application
ibmcloud ce application delete --name tim-mcp

# Delete secret
ibmcloud ce secret delete --name tim-mcp-secrets

# Delete project (if no longer needed)
ibmcloud ce project delete --name tim-mcp-project

# Delete container image
ibmcloud cr image-rm us.icr.io/tim-mcp/tim-mcp:latest

# Delete namespace (if no other images)
ibmcloud cr namespace-rm tim-mcp
```

## Next Steps

After successful MVP deployment:

1. **Monitor Performance**: Track response times, error rates, and resource usage
2. **Implement CI/CD**: Automate deployments with GitHub Actions
3. **Add Observability**: Integrate Prometheus metrics and Grafana dashboards
4. **Enhance Caching**: Add Redis for distributed caching
5. **Implement Rate Limiting**: Add per-IP and per-token rate limiting
6. **GitHub App Integration**: Replace PAT with GitHub App for better security

## Additional Resources

- [IBM Code Engine Documentation](https://cloud.ibm.com/docs/codeengine)
- [IBM Container Registry Documentation](https://cloud.ibm.com/docs/Registry)
- [Code Engine CLI Reference](https://cloud.ibm.com/docs/codeengine?topic=codeengine-cli)
- [Operations Runbook](../operations/runbook.md)
