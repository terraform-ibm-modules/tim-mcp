# Code Engine Deployment Guide

This guide covers deploying tim-mcp to IBM Code Engine as a containerized HTTP service.

## Prerequisites

1. **IBM Cloud Account** with Code Engine access
2. **IBM Cloud CLI** with Code Engine plugin
   ```bash
   curl -fsSL https://clis.cloud.ibm.com/install/linux | sh
   ibmcloud plugin install code-engine
   ```
3. **Terraform** >= 1.6 (for automated deployment)
4. **GitHub Personal Access Token** (optional, recommended for higher rate limits)
   - Create at: https://github.com/settings/tokens
   - No special permissions needed (public repos only)
5. **IBM Cloud API Key**
   - Create at: https://cloud.ibm.com/iam/apikeys

## Deployment

Use the provided Terraform configuration and deployment script:

```bash
# Set required environment variables
export IBM_CLOUD_API_KEY="<your-ibm-cloud-api-key>"
export GITHUB_TOKEN="<your-github-token>"

# Optional: customize region/resource group
export IBM_CLOUD_REGION="us-south"
export IBM_CLOUD_RESOURCE_GROUP="Default"

# Run deployment script
./scripts/deploy-code-engine.sh
```

The script will:
1. Initialize Terraform
2. Create Code Engine project and build configuration
3. Set up secrets for GitHub token
4. Automatically trigger the container build
5. Wait for the build to complete (up to 30 minutes for UBI8 builds)
6. Create or update the application

The deployment is fully automated and will display progress with build status updates. See [Terraform README](../../terraform/README.md) for detailed configuration options.

## Verification

After deployment, test the health endpoint:

```bash
# Get application URL
ibmcloud ce application get --name tim-mcp --output url

# Test health check
curl https://<app-url>/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "tim-mcp",
  "dependencies": {
    "github": {"status": "healthy", "rate_limit_remaining": 5000},
    "terraform_registry": {"status": "healthy"}
  }
}
```

## Configuration

Key environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_TOKEN` | - | GitHub PAT (5000 req/hr vs 60) |
| `TIM_LOG_LEVEL` | INFO | Log level (DEBUG, INFO, WARNING, ERROR) |
| `TIM_ALLOWED_NAMESPACES` | terraform-ibm-modules | Allowed module namespaces |

## Cost Optimization

Default configuration runs 24/7 (~$25-30/month). To enable scale-to-zero:

```bash
terraform apply -var="min_scale=0"
```

This reduces costs to ~$0-5/month with cold start latency.

## Troubleshooting

### Build Failures

The deployment script monitors build progress automatically. If a build fails, check the logs:

```bash
ibmcloud ce buildrun logs -n tim-mcp-buildrun-<timestamp>
```

Common issues:
- **Build timeout**: UBI8 builds can take 20-25 minutes. The script allows up to 30 minutes.
- **Registry quota**: If Container Registry exceeds 80% quota, consider cleaning old images.
- **Authentication**: Verify IBM Cloud API key has Container Registry access.

### Application Not Starting

Check application logs:
```bash
ibmcloud ce application logs --name tim-mcp
```

Verify health endpoint status shows dependency connectivity.

### Invalid GitHub Token

If the health check shows "unhealthy" status for GitHub:

```json
{
  "status": "degraded",
  "dependencies": {
    "github": {
      "status": "unhealthy",
      "error": "Invalid or expired GitHub token"
    }
  }
}
```

The GitHub token needs to be updated. Create a new token at https://github.com/settings/tokens (no special permissions needed), then update the secret:

1. Via UI: Code Engine → Projects → tim-mcp → Secrets and configmaps → tim-mcp-secrets → Edit
2. Via CLI:
   ```bash
   ibmcloud ce secret update --name tim-mcp-secrets --from-literal GITHUB_TOKEN=<new-token>
   ibmcloud ce app update --name tim-mcp
   ```
3. Or re-run the deployment script with the new token exported.

## Updates

To deploy a new version, simply re-run the deployment script:

```bash
./scripts/deploy-code-engine.sh
```

The script will automatically trigger a new build and update the application with the latest code.

## Cleanup

To remove all resources:

```bash
cd terraform
terraform destroy
```
