# Terraform Configuration for IBM Code Engine Deployment

This directory contains Terraform configuration to deploy tim-mcp to IBM Code Engine.

## Prerequisites

1. **Terraform** >= 1.6 installed
2. **IBM Cloud CLI** with Code Engine plugin
3. **IBM Cloud API Key**
4. **GitHub Personal Access Token**

## Quick Start

### 1. Set Environment Variables

```bash
export TF_VAR_ibmcloud_api_key="<your-ibm-cloud-api-key>"
export TF_VAR_github_token="<your-github-token>"
```

### 2. Initialize Terraform

```bash
cd terraform
terraform init
```

### 3. Review Plan

```bash
terraform plan
```

### 4. Apply Configuration

```bash
terraform apply
```

### 5. Trigger Initial Build

After applying, you need to manually trigger the first build:

```bash
# Login to IBM Cloud
ibmcloud login --apikey $TF_VAR_ibmcloud_api_key

# Target the region
ibmcloud target -r us-south

# Select the Code Engine project
ibmcloud ce project select --name tim-mcp

# Submit a build run
ibmcloud ce buildrun submit --build tim-mcp-build --name tim-mcp-buildrun-1

# Follow build logs
ibmcloud ce buildrun logs -f -n tim-mcp-buildrun-1
```

### 6. Update Application

Once the build completes, update the application to use the new image:

```bash
terraform apply -auto-approve
```

## Configuration Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `ibmcloud_api_key` | IBM Cloud API key | - | Yes |
| `github_token` | GitHub Personal Access Token | - | Yes |
| `region` | IBM Cloud region | `us-south` | No |
| `resource_group_name` | Resource group name | `default` | No |
| `project_name` | Code Engine project name | `tim-mcp` | No |
| `app_name` | Application name | `tim-mcp` | No |
| `image_name` | Container image reference | `us.icr.io/tim-mcp/tim-mcp:latest` | No |
| `cpu` | CPU allocation | `0.25` | No |
| `memory` | Memory allocation | `512M` | No |
| `min_scale` | Minimum instances | `1` | No |
| `max_scale` | Maximum instances | `3` | No |
| `port` | Application port | `8080` | No |
| `git_repo` | Git repository URL | `https://github.com/terraform-ibm-modules/tim-mcp` | No |
| `git_branch` | Git branch | `main` | No |
| `allowed_namespaces` | Allowed Terraform namespaces | `terraform-ibm-modules` | No |
| `log_level` | Log level | `INFO` | No |

## Outputs

After applying, Terraform will output:

- `app_url`: The public URL of your application
- `health_endpoint`: Health check endpoint URL
- `project_id`: Code Engine project ID
- `build_name`: Build configuration name

## Customization

You can override variables in several ways:

1. **Environment Variables**: Prefix with `TF_VAR_`
   ```bash
   export TF_VAR_min_scale=0  # Enable scale-to-zero
   ```

2. **terraform.tfvars File**: Create a file with your values
   ```hcl
   region = "eu-de"
   min_scale = 0
   max_scale = 5
   ```

3. **Command Line**: Pass via `-var` flag
   ```bash
   terraform apply -var="min_scale=0" -var="max_scale=5"
   ```

## Important Notes

### Build Runs

The Terraform configuration creates the build configuration but doesn't automatically trigger builds. You must manually trigger build runs using the IBM Cloud CLI (see step 5 above).

### Scale to Zero

To enable scale-to-zero and minimize costs:

```bash
terraform apply -var="min_scale=0"
```

This will scale down to zero instances when there's no traffic.

### Updating the Application

To deploy a new version:

1. Trigger a new build (step 5)
2. Once complete, run `terraform apply` to update the application

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

**Warning**: This will delete the Code Engine project, application, secrets, and Container Registry namespace.
