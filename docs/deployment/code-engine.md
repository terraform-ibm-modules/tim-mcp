# Code Engine Deployment Guide

This guide covers deploying tim-mcp to IBM Code Engine as a containerized HTTP service.

## Prerequisites

1. **IBM Cloud Account** with Code Engine access
2. **IBM Cloud CLI** with Code Engine plugin
   ```bash
   curl -fsSL https://clis.cloud.ibm.com/install/linux | sh
   ibmcloud plugin install code-engine
   ```
3. **Terraform** >= 1.9
4. **GitHub Personal Access Token** (recommended)
   - For classic tokens: `public_repo` scope
   - For fine-grained tokens: `Public Repositories (read-only)` access
5. **IBM Cloud API Key** — create at https://cloud.ibm.com/iam/apikeys

## Deployment

```bash
# Set required environment variables
export IBM_CLOUD_API_KEY="<your-ibm-cloud-api-key>"
export GITHUB_TOKEN="<your-github-token>"

# Optional: customize deployment
export IBM_CLOUD_REGION="us-south"        # Default: us-south
export IBM_CLOUD_RESOURCE_GROUP="Default"  # Default: Default
export GIT_BRANCH="main"                  # Default: main

# Run deployment
./scripts/deploy-code-engine.sh
```

The script will use Terraform (with the [TIM Code Engine module](https://registry.terraform.io/modules/terraform-ibm-modules/code-engine/ibm)) to create the project, build the container, set up secrets, and deploy the application. See `terraform/variables.tf` for all configurable options.

## Verification

```bash
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

## Troubleshooting

### Build Failures

Check build logs:
```bash
ibmcloud ce buildrun logs -n <buildrun-name>
```

### Invalid GitHub Token

Update the secret and restart:
```bash
ibmcloud ce secret update --name tim-mcp-secrets --from-literal GITHUB_TOKEN=<new-token>
ibmcloud ce app update --name tim-mcp
```

## Updates

Re-run the deployment script:
```bash
./scripts/deploy-code-engine.sh
```

## Cleanup

```bash
cd terraform && terraform destroy
```
