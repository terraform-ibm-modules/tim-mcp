# Operations Runbook: tim-mcp on Code Engine

Essential operational procedures for tim-mcp running on IBM Code Engine.

## Quick Reference

### Essential Commands

```bash
# Application status
ibmcloud ce application get --name tim-mcp

# View logs
ibmcloud ce application logs --name tim-mcp --follow

# Get application URL
ibmcloud ce application get --name tim-mcp --output url

# Health check
curl $(ibmcloud ce application get --name tim-mcp --output url)/health
```

## Deployment

### Deploy New Version

Use Terraform for all deployments:

```bash
# Set environment variables
export IBM_CLOUD_API_KEY="<your-api-key>"
export GITHUB_TOKEN="<your-github-token>"

# Run deployment script
./scripts/deploy-code-engine.sh

# Trigger build (after script completes)
ibmcloud ce buildrun submit --build tim-mcp-build --name tim-mcp-buildrun-$(date +%s)

# Update application with new image
cd terraform && terraform apply
```

See [Code Engine Deployment Guide](../deployment/code-engine.md) for details.

### Rollback

To rollback to a previous version:

```bash
cd terraform
terraform apply -var="image_name=us.icr.io/tim-mcp/tim-mcp:<previous-version>"
```

## Monitoring

### Health Check

The `/health` endpoint validates connectivity to dependencies:

```bash
curl https://<app-url>/health
```

Expected healthy response:
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

### Logs

View application logs:
```bash
ibmcloud ce application logs --name tim-mcp --follow
```

## Troubleshooting

### Application Not Responding

1. Check application status:
   ```bash
   ibmcloud ce application get --name tim-mcp
   ```

2. View recent logs:
   ```bash
   ibmcloud ce application logs --name tim-mcp --tail 100
   ```

3. Check health endpoint for dependency issues

### Build Failures

1. View build logs:
   ```bash
   ibmcloud ce buildrun logs -n <buildrun-name>
   ```

2. Common issues:
   - Platform mismatch: Use Code Engine build service (not local Docker)
   - Registry authentication: Verify IBM Cloud API key has Container Registry access

### Rate Limiting

If GitHub rate limits are exceeded:

1. Check health endpoint - it will show rate limit status
2. Verify `GITHUB_TOKEN` secret is configured:
   ```bash
   ibmcloud ce secret get --name tim-mcp-secrets
   ```
3. Update secret if needed:
   ```bash
   cd terraform
   terraform apply -var="github_token=<new-token>"
   ```

## Maintenance

### Update Secrets

To rotate GitHub token:

```bash
export TF_VAR_github_token="<new-token>"
cd terraform
terraform apply
```

Restart application to pick up new secret:
```bash
ibmcloud ce application update --name tim-mcp --image us.icr.io/tim-mcp/tim-mcp:latest
```

### Scale Application

Modify scaling in Terraform variables:

```bash
cd terraform
terraform apply -var="min_scale=0" -var="max_scale=5"
```

## Resources

- [Code Engine Documentation](https://cloud.ibm.com/docs/codeengine)
- [IBM Cloud Support](https://cloud.ibm.com/unifiedsupport/supportcenter)
- [Terraform Configuration](../../terraform/README.md)
