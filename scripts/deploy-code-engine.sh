#!/bin/bash
set -e

# Configuration
APP_NAME="tim-mcp"
IMAGE_NAME="us.icr.io/tim-mcp/tim-mcp"
VERSION=${1:-latest}
REGION=${IBM_CLOUD_REGION:-us-south}
RESOURCE_GROUP=${IBM_CLOUD_RESOURCE_GROUP:-default}

# Validate prerequisites
if [ -z "$GITHUB_TOKEN" ]; then
  echo "Error: GITHUB_TOKEN environment variable not set"
  exit 1
fi

echo "Building container image..."
docker build -t ${IMAGE_NAME}:${VERSION} .

echo "Pushing to IBM Container Registry..."
ibmcloud cr login
docker push ${IMAGE_NAME}:${VERSION}

echo "Deploying to Code Engine..."
ibmcloud target -r ${REGION} -g ${RESOURCE_GROUP}

# Create or update secret
if ibmcloud ce secret get --name ${APP_NAME}-secrets &>/dev/null; then
  echo "Updating existing secret..."
  ibmcloud ce secret update --name ${APP_NAME}-secrets \
    --from-literal GITHUB_TOKEN="${GITHUB_TOKEN}"
else
  echo "Creating secret..."
  ibmcloud ce secret create --name ${APP_NAME}-secrets \
    --from-literal GITHUB_TOKEN="${GITHUB_TOKEN}"
fi

# Create or update application
if ibmcloud ce application get --name ${APP_NAME} &>/dev/null; then
  echo "Updating existing application..."
  ibmcloud ce application update --name ${APP_NAME} \
    --image ${IMAGE_NAME}:${VERSION}
else
  echo "Creating application..."
  ibmcloud ce application create --name ${APP_NAME} \
    --image ${IMAGE_NAME}:${VERSION} \
    --cpu 0.25 \
    --memory 512M \
    --min-scale 1 \
    --max-scale 3 \
    --port 8080 \
    --env-from-secret ${APP_NAME}-secrets \
    --env TIM_LOG_LEVEL=INFO \
    --env TIM_ALLOWED_NAMESPACES=terraform-ibm-modules \
    --probe-live /health \
    --probe-ready /health
fi

echo "Deployment complete!"
ibmcloud ce application get --name ${APP_NAME} --output url
