# Operations Runbook: tim-mcp on Code Engine

This runbook provides operational procedures for managing the tim-mcp service running on IBM Code Engine.

## Table of Contents

- [Quick Reference](#quick-reference)
- [Deployment Procedures](#deployment-procedures)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)
- [Incident Response](#incident-response)
- [Maintenance](#maintenance)

## Quick Reference

### Essential Commands

```bash
# Application status
ibmcloud ce application get --name tim-mcp

# View logs
ibmcloud ce application logs --name tim-mcp --follow

# Get public URL
ibmcloud ce application get --name tim-mcp --output url

# Restart application
ibmcloud ce application update --name tim-mcp --image us.icr.io/tim-mcp/tim-mcp:latest
```

### Health Check URLs

```bash
# Get application URL
APP_URL=$(ibmcloud ce application get --name tim-mcp --output url)

# Health endpoint
curl ${APP_URL}/health

# MCP protocol check
curl -X POST ${APP_URL}/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

### Key Contacts

- **Development Team**: [Your team contact]
- **IBM Cloud Support**: https://cloud.ibm.com/unifiedsupport/supportcenter
- **Code Engine Documentation**: https://cloud.ibm.com/docs/codeengine

## Deployment Procedures

### Deploy New Version

**Purpose**: Deploy a new version of tim-mcp to Code Engine

**Prerequisites**:
- New container image built and tested locally
- Access to IBM Cloud CLI
- GitHub token available

**Steps**:

1. **Build and Tag Image**:
   ```bash
   cd /path/to/tim-mcp
   docker build -t us.icr.io/tim-mcp/tim-mcp:v1.0.x .
   ```

2. **Test Image Locally**:
   ```bash
   docker run -p 8080:8080 -e GITHUB_TOKEN=<token> us.icr.io/tim-mcp/tim-mcp:v1.0.x
   curl http://localhost:8080/health
   ```

3. **Push to Registry**:
   ```bash
   ibmcloud cr login
   docker push us.icr.io/tim-mcp/tim-mcp:v1.0.x
   ```

4. **Update Code Engine Application**:
   ```bash
   ibmcloud ce application update --name tim-mcp \
     --image us.icr.io/tim-mcp/tim-mcp:v1.0.x
   ```

5. **Verify Deployment**:
   ```bash
   # Check status
   ibmcloud ce application get --name tim-mcp

   # View logs
   ibmcloud ce application logs --name tim-mcp --tail 50

   # Test health endpoint
   APP_URL=$(ibmcloud ce application get --name tim-mcp --output url)
   curl ${APP_URL}/health
   ```

**Rollback Procedure**: See [Rollback Deployment](#rollback-deployment)

### Rollback Deployment

**Purpose**: Revert to a previous working version

**When to Use**:
- New deployment causing errors
- Health checks failing
- Unexpected behavior in production

**Steps**:

1. **Identify Last Known Good Version**:
   ```bash
   # List available images
   ibmcloud cr image-list --restrict tim-mcp
   ```

2. **Rollback to Previous Version**:
   ```bash
   ibmcloud ce application update --name tim-mcp \
     --image us.icr.io/tim-mcp/tim-mcp:v1.0.previous
   ```

3. **Verify Rollback**:
   ```bash
   ibmcloud ce application get --name tim-mcp
   ibmcloud ce application logs --name tim-mcp --follow
   ```

4. **Notify Team**: Inform team of rollback and investigate root cause

### Update Environment Variables

**Purpose**: Change application configuration without redeploying

**Steps**:

```bash
# Update single variable
ibmcloud ce application update --name tim-mcp \
  --env TIM_LOG_LEVEL=DEBUG

# Update multiple variables
ibmcloud ce application update --name tim-mcp \
  --env TIM_LOG_LEVEL=DEBUG \
  --env TIM_CACHE_TTL=7200 \
  --env TIM_REQUEST_TIMEOUT=60
```

**Note**: Application will restart automatically after environment variable changes.

### Update GitHub Token (Secret Rotation)

**Purpose**: Rotate GitHub token for security

**When to Use**:
- Token expiration approaching
- Security incident
- Regular rotation (recommended: every 90 days)

**Steps**:

1. **Create New GitHub Token**:
   - Visit: https://github.com/settings/tokens
   - Create new fine-grained token with public repository access
   - Set expiration to 90 days

2. **Update Secret**:
   ```bash
   ibmcloud ce secret update --name tim-mcp-secrets \
     --from-literal GITHUB_TOKEN=<new-token>
   ```

3. **Restart Application** (to pick up new secret):
   ```bash
   ibmcloud ce application update --name tim-mcp \
     --image us.icr.io/tim-mcp/tim-mcp:latest
   ```

4. **Verify**:
   ```bash
   # Check logs for successful GitHub API calls
   ibmcloud ce application logs --name tim-mcp --tail 100 | grep -i github
   ```

5. **Revoke Old Token**: Delete old token from GitHub settings

## Monitoring

### Health Checks

**Automated Health Checks**:
- **Liveness Probe**: Code Engine checks `/health` every 30 seconds
- **Readiness Probe**: Code Engine checks `/health` before routing traffic

**Manual Health Check**:
```bash
APP_URL=$(ibmcloud ce application get --name tim-mcp --output url)
curl -s ${APP_URL}/health | jq
```

**Expected Response**:
```json
{
  "status": "healthy",
  "service": "tim-mcp"
}
```

### Log Monitoring

**View Real-Time Logs**:
```bash
ibmcloud ce application logs --name tim-mcp --follow
```

**Search Logs for Errors**:
```bash
ibmcloud ce application logs --name tim-mcp --tail 500 | grep -i error
```

**Check for API Rate Limiting**:
```bash
ibmcloud ce application logs --name tim-mcp --tail 500 | grep -i "rate limit"
```

### Application Metrics

**Check Application Status**:
```bash
ibmcloud ce application get --name tim-mcp
```

**Key Metrics to Monitor**:
- **Status**: Should be "Ready"
- **Running Instances**: Check against min/max scale settings
- **URL**: Verify application is accessible
- **Age**: Last update time

**Check Resource Usage**:
```bash
# View application details including resource allocation
ibmcloud ce application get --name tim-mcp --output json | jq '.status'
```

### Monitoring Checklist

Run this checklist daily or after deployments:

- [ ] Application status is "Ready"
- [ ] Health endpoint returns 200 OK
- [ ] No error messages in recent logs (last 100 lines)
- [ ] MCP tools endpoint is accessible
- [ ] No rate limit warnings in logs
- [ ] Application instances match expected scale (min-max)

## Troubleshooting

### Application Not Responding

**Symptoms**:
- Health check returns 5xx errors
- Application URL not accessible
- Connection timeouts

**Diagnosis**:
```bash
# Check application status
ibmcloud ce application get --name tim-mcp

# View recent logs
ibmcloud ce application logs --name tim-mcp --tail 100

# Check application events
ibmcloud ce application events --name tim-mcp
```

**Solutions**:

1. **Restart Application**:
   ```bash
   ibmcloud ce application update --name tim-mcp \
     --image us.icr.io/tim-mcp/tim-mcp:latest
   ```

2. **Check Container Image**:
   ```bash
   # Verify image exists
   ibmcloud cr image-list --restrict tim-mcp

   # Test image locally
   docker run -p 8080:8080 -e GITHUB_TOKEN=<token> us.icr.io/tim-mcp/tim-mcp:latest
   ```

3. **Increase Resources**:
   ```bash
   ibmcloud ce application update --name tim-mcp \
     --cpu 0.5 --memory 1G
   ```

### High Error Rate

**Symptoms**:
- Many error messages in logs
- Health checks passing but API calls failing
- HTTP 500 responses

**Diagnosis**:
```bash
# Count errors in recent logs
ibmcloud ce application logs --name tim-mcp --tail 1000 | grep -c ERROR

# View error details
ibmcloud ce application logs --name tim-mcp --tail 1000 | grep ERROR
```

**Common Causes & Solutions**:

1. **GitHub API Rate Limiting**:
   - **Check**: Look for "rate limit" in logs
   - **Solution**: Verify GitHub token is set correctly
   ```bash
   ibmcloud ce secret get --name tim-mcp-secrets
   ```

2. **External API Timeouts**:
   - **Check**: Look for "timeout" in logs
   - **Solution**: Increase timeout setting
   ```bash
   ibmcloud ce application update --name tim-mcp \
     --env TIM_REQUEST_TIMEOUT=60
   ```

3. **Memory Issues**:
   - **Check**: Look for "OOM" or "memory" in logs
   - **Solution**: Increase memory allocation
   ```bash
   ibmcloud ce application update --name tim-mcp --memory 1G
   ```

### Slow Response Times

**Symptoms**:
- Requests taking > 10 seconds
- Timeout errors from clients
- High latency

**Diagnosis**:
```bash
# Check application logs for timing information
ibmcloud ce application logs --name tim-mcp --tail 500 | grep duration

# Test response time manually
time curl -X POST ${APP_URL}/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

**Solutions**:

1. **Check Cache TTL**:
   ```bash
   # Increase cache duration
   ibmcloud ce application update --name tim-mcp \
     --env TIM_CACHE_TTL=7200
   ```

2. **Scale Up Resources**:
   ```bash
   ibmcloud ce application update --name tim-mcp \
     --cpu 0.5 --memory 1G --min-scale 2
   ```

3. **Check External API Performance**:
   - Test GitHub API directly: `curl -I https://api.github.com`
   - Test Terraform Registry: `curl -I https://registry.terraform.io`

### GitHub Authentication Failing

**Symptoms**:
- "401 Unauthorized" errors in logs
- Rate limit errors despite token being set
- GitHub API errors

**Diagnosis**:
```bash
# Check logs for authentication errors
ibmcloud ce application logs --name tim-mcp --tail 500 | grep -i "401\|unauthorized\|authentication"

# Verify secret exists
ibmcloud ce secret get --name tim-mcp-secrets
```

**Solutions**:

1. **Verify Token is Valid**:
   ```bash
   # Test token manually
   curl -H "Authorization: token <your-token>" https://api.github.com/user
   ```

2. **Update Secret**:
   ```bash
   ibmcloud ce secret update --name tim-mcp-secrets \
     --from-literal GITHUB_TOKEN=<new-valid-token>

   # Restart app to pick up new secret
   ibmcloud ce application update --name tim-mcp \
     --image us.icr.io/tim-mcp/tim-mcp:latest
   ```

## Incident Response

### Severity Levels

**P1 - Critical**:
- Service completely down
- All health checks failing
- No responses to any requests

**P2 - High**:
- Partial service degradation
- High error rate (>25%)
- Performance issues affecting users

**P3 - Medium**:
- Intermittent errors
- Degraded performance
- Non-critical feature failures

**P4 - Low**:
- Minor issues
- Edge case errors
- Cosmetic problems

### Incident Response Checklist

**Immediate Actions** (within 5 minutes):

1. **Assess Severity**: Determine P1-P4 level
2. **Check Status**:
   ```bash
   ibmcloud ce application get --name tim-mcp
   curl ${APP_URL}/health
   ```
3. **Review Logs**:
   ```bash
   ibmcloud ce application logs --name tim-mcp --tail 100
   ```
4. **Notify Stakeholders**: If P1/P2, notify team immediately

**Mitigation Actions** (within 15 minutes):

1. **Quick Fix Attempts**:
   - Restart application
   - Rollback to previous version if recent deployment
   - Scale up resources if performance issue

2. **Document**:
   - Screenshot errors
   - Save log output
   - Note timeline of events

**Resolution Actions** (within 1 hour for P1, 4 hours for P2):

1. **Implement Fix**:
   - Deploy corrected version
   - Update configuration
   - Scale resources appropriately

2. **Verify Resolution**:
   - Test health endpoint
   - Test MCP functionality
   - Monitor logs for 30 minutes

3. **Post-Incident**:
   - Write incident report
   - Update runbook if needed
   - Schedule post-mortem if P1/P2

## Maintenance

### Regular Maintenance Tasks

**Daily**:
- [ ] Check application status
- [ ] Review logs for errors
- [ ] Verify health endpoint

**Weekly**:
- [ ] Review application metrics
- [ ] Check for available updates
- [ ] Review cost and resource usage
- [ ] Test MCP functionality end-to-end

**Monthly**:
- [ ] Review and optimize resource allocation
- [ ] Update dependencies if security patches available
- [ ] Rotate GitHub token (every 90 days)
- [ ] Review and update documentation

**Quarterly**:
- [ ] Conduct disaster recovery test
- [ ] Review and update runbook
- [ ] Performance optimization review
- [ ] Security audit

### Scaling Procedures

**Scale Up** (increase capacity):
```bash
# Increase instances
ibmcloud ce application update --name tim-mcp \
  --min-scale 2 --max-scale 5

# Increase resources per instance
ibmcloud ce application update --name tim-mcp \
  --cpu 0.5 --memory 1G
```

**Scale Down** (reduce costs):
```bash
# Decrease instances
ibmcloud ce application update --name tim-mcp \
  --min-scale 1 --max-scale 3

# Scale to zero when idle
ibmcloud ce application update --name tim-mcp \
  --min-scale 0 --max-scale 3
```

### Backup and Recovery

**Configuration Backup**:
```bash
# Export application configuration
ibmcloud ce application get --name tim-mcp --output json > tim-mcp-config-$(date +%Y%m%d).json

# Export secret (metadata only, not values)
ibmcloud ce secret get --name tim-mcp-secrets --output json > tim-mcp-secrets-$(date +%Y%m%d).json
```

**Recovery**:
```bash
# Recreate application from backup
# Review and edit the JSON file, then use:
ibmcloud ce application create --name tim-mcp \
  --image us.icr.io/tim-mcp/tim-mcp:latest \
  --cpu 0.25 --memory 512M \
  --min-scale 1 --max-scale 3 \
  --port 8080 \
  --env-from-secret tim-mcp-secrets \
  --probe-live /health --probe-ready /health
```

### Cleanup Old Resources

**Container Images**:
```bash
# List all images
ibmcloud cr image-list --restrict tim-mcp

# Delete old images (keep last 5)
ibmcloud cr image-rm us.icr.io/tim-mcp/tim-mcp:<old-version>
```

**Code Engine Revisions**:
```bash
# List revisions
ibmcloud ce revision list --application tim-mcp

# Code Engine automatically manages revisions
# No manual cleanup needed unless experiencing issues
```

## Emergency Contacts

### IBM Cloud Support

- **Support Portal**: https://cloud.ibm.com/unifiedsupport/supportcenter
- **Emergency Phone**: Contact through support portal
- **Support Cases**: Create via IBM Cloud console

### Service Level Objectives

**MVP Targets** (no SLA):
- **Availability**: Best effort
- **Response Time**: < 5 seconds (P95)
- **Error Rate**: < 5%
- **Recovery Time**: < 1 hour for P1 incidents

**Note**: As an MVP, this service does not have formal SLAs. These are target objectives for operational excellence.

## Additional Resources

- [Code Engine Deployment Guide](../deployment/code-engine.md)
- [IBM Code Engine Documentation](https://cloud.ibm.com/docs/codeengine)
- [Code Engine CLI Reference](https://cloud.ibm.com/docs/codeengine?topic=codeengine-cli)
- [IBM Cloud Status](https://cloud.ibm.com/status)
