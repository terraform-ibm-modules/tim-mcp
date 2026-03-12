#!/bin/bash
set -e

# Deployment script for tim-mcp to IBM Code Engine
# Uses the TIM Code Engine module for infrastructure and build management

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/../terraform"
APP_NAME="tim-mcp"

# Validate required environment variables
for var in GITHUB_TOKEN IBM_CLOUD_API_KEY; do
  if [ -z "${!var}" ]; then
    echo "Error: $var environment variable not set"
    exit 1
  fi
done

# Check for required tools
for cmd in terraform ibmcloud; do
  if ! command -v "$cmd" &> /dev/null; then
    echo "Error: $cmd not found"
    exit 1
  fi
done

# Set Terraform variables
export TF_VAR_ibmcloud_api_key="$IBM_CLOUD_API_KEY"
export TF_VAR_github_token="$GITHUB_TOKEN"
[ -n "$IBM_CLOUD_REGION" ] && export TF_VAR_region="$IBM_CLOUD_REGION"
[ -n "$IBM_CLOUD_RESOURCE_GROUP" ] && export TF_VAR_resource_group_name="$IBM_CLOUD_RESOURCE_GROUP"
[ -n "$GIT_BRANCH" ] && export TF_VAR_git_branch="$GIT_BRANCH"

REGION=${TF_VAR_region:-us-south}
RESOURCE_GROUP=${TF_VAR_resource_group_name:-Default}

# Deploy infrastructure and run build via Terraform (TIM module handles build runs)
cd "$TERRAFORM_DIR"
[ ! -d ".terraform" ] && terraform init
echo "Deploying infrastructure and building container image..."
terraform apply -auto-approve

# Login to IBM Cloud and select project
ibmcloud login --apikey "$IBM_CLOUD_API_KEY" -r "$REGION" -g "$RESOURCE_GROUP" --quiet
ibmcloud ce project select --name "$APP_NAME"

# Get the built image reference from terraform output
BUILD_OUTPUT=$(terraform output -json build 2>/dev/null)
IMAGE_NAME=$(echo "$BUILD_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(list(d.values())[0]['output_image'])" 2>/dev/null)

if [ -z "$IMAGE_NAME" ]; then
  echo "Error: Failed to get image name from Terraform output"
  exit 1
fi

echo "Using container image: $IMAGE_NAME"

# Create or update the app
if ibmcloud ce app get --name "$APP_NAME" >/dev/null 2>&1; then
  echo "Updating existing application..."
  ibmcloud ce app update --name "$APP_NAME" --image "$IMAGE_NAME"
else
  echo "Creating new application..."
  ibmcloud ce app create \
    --name "$APP_NAME" \
    --image "$IMAGE_NAME" \
    --registry-secret "registry-access-secret" \
    --cpu 0.25 --memory 1G \
    --min-scale 1 --max-scale 3 \
    --port 8080 \
    --env-from-secret "${APP_NAME}-secrets" \
    --env TIM_LOG_LEVEL=INFO \
    --env TIM_ALLOWED_NAMESPACES=terraform-ibm-modules
fi

# Display result
APP_URL=$(ibmcloud ce app get --name "$APP_NAME" --output url 2>/dev/null || echo "")
echo ""
echo "Deployment Complete!"
echo "Application URL: $APP_URL"
echo "Health endpoint: ${APP_URL}/health"
