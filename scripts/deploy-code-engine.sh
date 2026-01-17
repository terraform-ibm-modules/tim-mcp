#!/bin/bash
set -e

# Configuration
APP_NAME="tim-mcp"
IMAGE_NAME="us.icr.io/tim-mcp/tim-mcp"
VERSION=${1:-latest}
REGION=${IBM_CLOUD_REGION:-us-south}
RESOURCE_GROUP=${IBM_CLOUD_RESOURCE_GROUP:-default}
GIT_REPO="https://github.com/terraform-ibm-modules/tim-mcp"
GIT_BRANCH=${GIT_BRANCH:-main}
BUILD_NAME="${APP_NAME}-build"
REGISTRY_SECRET="icr-secret"

# Validate prerequisites
if [ -z "$GITHUB_TOKEN" ]; then
  echo "Error: GITHUB_TOKEN environment variable not set"
  exit 1
fi

echo "Building container image using Code Engine build service..."
echo "This ensures the image is built for the correct platform (linux/amd64)"

# Check if build configuration exists, create or update
if ibmcloud ce build get --name ${BUILD_NAME} &>/dev/null; then
  echo "Updating existing build configuration..."
  ibmcloud ce build update --name ${BUILD_NAME} \
    --source ${GIT_REPO} \
    --commit ${GIT_BRANCH} \
    --image ${IMAGE_NAME}:${VERSION}
else
  echo "Creating build configuration..."
  ibmcloud ce build create --name ${BUILD_NAME} \
    --source ${GIT_REPO} \
    --commit ${GIT_BRANCH} \
    --context-dir . \
    --dockerfile Dockerfile \
    --image ${IMAGE_NAME}:${VERSION} \
    --registry-secret ${REGISTRY_SECRET} \
    --size medium \
    --timeout 900
fi

# Submit build run
BUILDRUN_NAME="${APP_NAME}-buildrun-$(date +%s)"
echo "Submitting build run: ${BUILDRUN_NAME}"
ibmcloud ce buildrun submit --build ${BUILD_NAME} --name ${BUILDRUN_NAME}

# Wait for build to complete by following logs
echo "Following build logs..."
ibmcloud ce buildrun logs -f -n ${BUILDRUN_NAME} || true

# Check build status
BUILD_STATUS=$(ibmcloud ce buildrun get -n ${BUILDRUN_NAME} --output json | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
if [ "$BUILD_STATUS" != "Succeeded" ]; then
  echo "Error: Build failed with status: ${BUILD_STATUS}"
  exit 1
fi

echo "Build completed successfully!"

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
