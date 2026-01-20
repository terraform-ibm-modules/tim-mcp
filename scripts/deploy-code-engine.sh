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
# Note: image_name is computed dynamically from user_name in Terraform

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

if [ -n "$NAMESPACE" ]; then
  export TF_VAR_namespace="$NAMESPACE"
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

# Get values from Terraform output
PROJECT_NAME=$(terraform output -raw project_name 2>/dev/null || echo "$APP_NAME")
BUILD_NAME=$(terraform output -raw build_name 2>/dev/null || echo "${APP_NAME}-build")
IMAGE_NAME=$(terraform output -raw image_name 2>/dev/null)
REGION=${TF_VAR_region:-us-south}
RESOURCE_GROUP=${TF_VAR_resource_group_name:-Default}

# Verify we got the image name
if [ -z "$IMAGE_NAME" ]; then
  echo "Error: Failed to get image name from Terraform output"
  exit 1
fi

echo "Using container image: $IMAGE_NAME"

echo ""
echo "Infrastructure deployment complete!"
echo ""
echo "Step 2: Building container image..."
echo "======================================"

# Login to IBM Cloud and target the project
ibmcloud login --apikey "$IBM_CLOUD_API_KEY" -r "$REGION" -g "$RESOURCE_GROUP" --quiet
ibmcloud ce project select --name "$PROJECT_NAME"

# Trigger the build
BUILDRUN_NAME="${APP_NAME}-buildrun-$(date +%s)"
echo "Submitting build run: $BUILDRUN_NAME"
ibmcloud ce buildrun submit --build "$BUILD_NAME" --name "$BUILDRUN_NAME"

# Wait for build to complete
echo "Waiting for build to complete..."
BUILD_STATUS="Unknown"
MAX_WAIT=600  # 10 minutes
ELAPSED=0
INTERVAL=10

while [ $ELAPSED -lt $MAX_WAIT ]; do
  BUILD_STATUS=$(ibmcloud ce buildrun get -n "$BUILDRUN_NAME" --output json 2>/dev/null | grep -o '"status": "[^"]*"' | cut -d'"' -f4 || echo "Unknown")

  if [ "$BUILD_STATUS" = "succeeded" ]; then
    echo "✓ Build completed successfully!"
    break
  elif [ "$BUILD_STATUS" = "failed" ]; then
    echo "✗ Build failed!"
    echo "View logs with: ibmcloud ce buildrun logs -n $BUILDRUN_NAME"
    exit 1
  fi

  MINUTES=$((ELAPSED / 60))
  SECONDS=$((ELAPSED % 60))
  echo "  Build status: $BUILD_STATUS (${MINUTES}m ${SECONDS}s elapsed)"
  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))
done

if [ "$BUILD_STATUS" != "succeeded" ]; then
  MAX_MINUTES=$((MAX_WAIT / 60))
  echo "✗ Build did not complete within ${MAX_MINUTES} minutes"
  exit 1
fi

echo ""
echo "Step 3: Creating/updating application..."
echo "=========================================="

# Create or update the app with the new image
if ibmcloud ce app get --name "$APP_NAME" >/dev/null 2>&1; then
  echo "Updating existing application..."
  ibmcloud ce app update \
    --name "$APP_NAME" \
    --image "$IMAGE_NAME"
else
  echo "Creating new application..."
  ibmcloud ce app create \
    --name "$APP_NAME" \
    --image "$IMAGE_NAME" \
    --registry-secret icr-secret \
    --cpu 0.25 \
    --memory 1G \
    --min-scale 1 \
    --max-scale 3 \
    --port 8080 \
    --env-from-secret "${APP_NAME}-secrets" \
    --env TIM_LOG_LEVEL=INFO \
    --env TIM_ALLOWED_NAMESPACES=terraform-ibm-modules
fi

# Get the application URL
APP_URL=$(ibmcloud ce app get --name "$APP_NAME" --output url 2>/dev/null || echo "")

echo ""
echo "======================================"
echo "🎉 Deployment Complete!"
echo "======================================"
echo ""
echo "Application URL: $APP_URL"
echo "Health endpoint: ${APP_URL}/health"
echo ""
echo "Test the deployment:"
echo "  curl ${APP_URL}/health"
echo ""
