#!/bin/bash
set -e

# Deployment script for tim-mcp to IBM Code Engine
# This script uses Terraform for infrastructure management

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/../terraform"
APP_NAME="tim-mcp"
VERSION=${1:-latest}

# Validate prerequisites
echo "Validating prerequisites..."

if [ -z "$GITHUB_TOKEN" ]; then
  echo "Error: GITHUB_TOKEN environment variable not set"
  echo "Export it with: export GITHUB_TOKEN=<your-token>"
  exit 1
fi

if [ -z "$IBM_CLOUD_API_KEY" ]; then
  echo "Error: IBM_CLOUD_API_KEY environment variable not set"
  echo "Export it with: export IBM_CLOUD_API_KEY=<your-api-key>"
  exit 1
fi

# Check for required tools
if ! command -v terraform &> /dev/null; then
  echo "Error: terraform not found. Please install Terraform >= 1.6"
  exit 1
fi

if ! command -v ibmcloud &> /dev/null; then
  echo "Error: ibmcloud CLI not found. Please install IBM Cloud CLI"
  exit 1
fi

# Set Terraform variables
export TF_VAR_ibmcloud_api_key="$IBM_CLOUD_API_KEY"
export TF_VAR_github_token="$GITHUB_TOKEN"
export TF_VAR_image_name="us.icr.io/tim-mcp/tim-mcp:${VERSION}"

# Optional variables from environment
if [ -n "$IBM_CLOUD_REGION" ]; then
  export TF_VAR_region="$IBM_CLOUD_REGION"
fi

if [ -n "$IBM_CLOUD_RESOURCE_GROUP" ]; then
  export TF_VAR_resource_group_name="$IBM_CLOUD_RESOURCE_GROUP"
fi

if [ -n "$GIT_BRANCH" ]; then
  export TF_VAR_git_branch="$GIT_BRANCH"
fi

# Navigate to Terraform directory
cd "$TERRAFORM_DIR"

# Initialize Terraform if needed
if [ ! -d ".terraform" ]; then
  echo "Initializing Terraform..."
  terraform init
fi

# Apply Terraform configuration
echo "Deploying infrastructure with Terraform..."
terraform apply -auto-approve

# Get project name from Terraform output
PROJECT_NAME=$(terraform output -raw project_name 2>/dev/null || echo "tim-mcp")
BUILD_NAME=$(terraform output -raw build_name 2>/dev/null || echo "${APP_NAME}-build")

echo ""
echo "Infrastructure deployment complete!"
echo ""
echo "Next step: Trigger container build"
echo "======================================"
echo ""
echo "The Terraform configuration has created the build configuration,"
echo "but you need to manually trigger the first build run:"
echo ""
echo "  # Login to IBM Cloud"
echo "  ibmcloud login --apikey \$IBM_CLOUD_API_KEY"
echo ""
echo "  # Target the region and select the project"
echo "  ibmcloud target -r ${TF_VAR_region:-us-south}"
echo "  ibmcloud ce project select --name ${PROJECT_NAME}"
echo ""
echo "  # Submit build run"
echo "  ibmcloud ce buildrun submit --build ${BUILD_NAME} --name ${APP_NAME}-buildrun-\$(date +%s)"
echo ""
echo "  # Follow the build logs"
echo "  ibmcloud ce buildrun logs -f -n ${APP_NAME}-buildrun-<timestamp>"
echo ""
echo "After the build completes successfully, run 'terraform apply' again"
echo "to update the application with the new image."
echo ""
echo "Terraform Outputs:"
terraform output
