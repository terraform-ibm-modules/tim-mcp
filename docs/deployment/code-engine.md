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

## Deployment Methods

### Option 1: Automated Deployment (Recommended)

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
4. Deploy the application

After the script completes, manually trigger the container build:

```bash
# Login and select project
ibmcloud login --apikey $IBM_CLOUD_API_KEY
ibmcloud target -r us-south
ibmcloud ce project select --name tim-mcp

# Trigger build
ibmcloud ce buildrun submit --build tim-mcp-build --name tim-mcp-buildrun-$(date +%s)

# Follow logs
ibmcloud ce buildrun logs -f -n tim-mcp-buildrun-<timestamp>
```

See [Terraform README](../../terraform/README.md) for detailed configuration options.

### Option 2: Manual Terraform Deployment

For more control, use Terraform directly:

```bash
cd terraform

# Set variables
export TF_VAR_ibmcloud_api_key="<your-api-key>"
export TF_VAR_github_token="<your-github-token>"

# Initialize and apply
terraform init
terraform apply

# Get outputs
terraform output
```

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

Check build logs:
```bash
ibmcloud ce buildrun logs -n tim-mcp-buildrun-<timestamp>
```

Common issues:
- Platform mismatch: Ensure using Code Engine build service or `--platform linux/amd64`
- Authentication: Verify IBM Cloud API key has Container Registry access

### Application Not Starting

Check application logs:
```bash
ibmcloud ce application logs --name tim-mcp
```

Verify health endpoint status shows dependency connectivity.

### Rate Limiting

If GitHub API rate limits are exceeded, the health check will show warnings. Ensure `GITHUB_TOKEN` is configured correctly.

## Updates

To deploy a new version:

1. Trigger a new build run
2. Wait for build to complete
3. Run `terraform apply` to update the application

## Cleanup

To remove all resources:

```bash
cd terraform
terraform destroy
```
