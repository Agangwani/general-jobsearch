#!/usr/bin/env bash
# Deploy the jobsearch web UI to AWS App Runner (minimal MVP infrastructure).
#
#   build the Docker image -> push to ECR -> create/update an App Runner service
#   that serves it behind a public HTTPS URL, password-gated.
#
# Prereqs: docker, aws CLI v2, and AWS credentials in the environment
# (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION) for an IAM
# user with the policy in deploy/iam-policy.json.
#
# Usage:
#   JOBSEARCH_BASIC_AUTH_PASSWORD='choose-a-strong-one' ./deploy/aws-apprunner.sh
# (omit the password and one is generated and printed for you.)
set -euo pipefail
cd "$(dirname "$0")/.."

APP_NAME="${APP_NAME:-jobsearch-mvp}"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
ECR_REPO="${ECR_REPO:-$APP_NAME}"
SERVICE_NAME="${SERVICE_NAME:-$APP_NAME}"
ACCESS_ROLE_NAME="${ACCESS_ROLE_NAME:-AppRunnerECRAccessRole}"
CPU="${CPU:-1024}"
MEMORY="${MEMORY:-2048}"

AUTH_USER="${JOBSEARCH_BASIC_AUTH_USER:-demo}"
AUTH_PW="${JOBSEARCH_BASIC_AUTH_PASSWORD:-}"
if [ -z "$AUTH_PW" ]; then
  AUTH_PW="$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)"
  echo "· no JOBSEARCH_BASIC_AUTH_PASSWORD set — generated one:"
  echo ""
  echo "    user: $AUTH_USER"
  echo "    pass: $AUTH_PW"
  echo ""
  echo "  (save this — it's how you and anyone you share the link with log in)"
fi

echo "· resolving AWS account…"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_URI="${REGISTRY}/${ECR_REPO}"
echo "  account=${ACCOUNT_ID} region=${AWS_REGION}"

echo "· ensuring ECR repository ${ECR_REPO}…"
aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$AWS_REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$ECR_REPO" --region "$AWS_REGION" \
       --image-scanning-configuration scanOnPush=true >/dev/null

echo "· logging Docker into ECR…"
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"

echo "· building and pushing image…"
docker build -t "${ECR_URI}:latest" .
docker push "${ECR_URI}:latest"

echo "· ensuring App Runner ECR access role ${ACCESS_ROLE_NAME}…"
if ! aws iam get-role --role-name "$ACCESS_ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ACCESS_ROLE_NAME" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"build.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "$ACCESS_ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess >/dev/null
  echo "  created — waiting 15s for IAM propagation…"
  sleep 15
fi
ACCESS_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ACCESS_ROLE_NAME}"

# App Runner config. Health check is TCP on purpose: an HTTP check would hit the
# password gate, get a 401, and the service would never become healthy.
SRC_CONFIG="$(cat <<JSON
{
  "AuthenticationConfiguration": { "AccessRoleArn": "${ACCESS_ROLE_ARN}" },
  "AutoDeploymentsEnabled": false,
  "ImageRepository": {
    "ImageIdentifier": "${ECR_URI}:latest",
    "ImageRepositoryType": "ECR",
    "ImageConfiguration": {
      "Port": "8080",
      "RuntimeEnvironmentVariables": {
        "JOBSEARCH_BASIC_AUTH_USER": "${AUTH_USER}",
        "JOBSEARCH_BASIC_AUTH_PASSWORD": "${AUTH_PW}"
      }
    }
  }
}
JSON
)"
HEALTH_CONFIG='{"Protocol":"TCP","Interval":10,"Timeout":5,"HealthyThreshold":1,"UnhealthyThreshold":5}'
INSTANCE_CONFIG="{\"Cpu\":\"${CPU}\",\"Memory\":\"${MEMORY}\"}"

SERVICE_ARN="$(aws apprunner list-services --region "$AWS_REGION" \
  --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn | [0]" \
  --output text)"

if [ "$SERVICE_ARN" = "None" ] || [ -z "$SERVICE_ARN" ]; then
  echo "· creating App Runner service ${SERVICE_NAME}…"
  SERVICE_ARN="$(aws apprunner create-service --region "$AWS_REGION" \
    --service-name "$SERVICE_NAME" \
    --source-configuration "$SRC_CONFIG" \
    --instance-configuration "$INSTANCE_CONFIG" \
    --health-check-configuration "$HEALTH_CONFIG" \
    --query 'Service.ServiceArn' --output text)"
else
  echo "· updating existing App Runner service ${SERVICE_NAME}…"
  aws apprunner update-service --region "$AWS_REGION" \
    --service-arn "$SERVICE_ARN" \
    --source-configuration "$SRC_CONFIG" \
    --instance-configuration "$INSTANCE_CONFIG" \
    --health-check-configuration "$HEALTH_CONFIG" >/dev/null
fi

echo "· waiting for the service to come up (this takes a few minutes)…"
while true; do
  STATUS="$(aws apprunner describe-service --region "$AWS_REGION" \
    --service-arn "$SERVICE_ARN" --query 'Service.Status' --output text)"
  URL="$(aws apprunner describe-service --region "$AWS_REGION" \
    --service-arn "$SERVICE_ARN" --query 'Service.ServiceUrl' --output text)"
  echo "    status=${STATUS}"
  case "$STATUS" in
    RUNNING) break ;;
    CREATE_FAILED|DELETE_FAILED|PAUSED) echo "  deploy failed (status=${STATUS})"; exit 1 ;;
  esac
  sleep 15
done

echo ""
echo "✓ Deployed. Open the demo at:"
echo ""
echo "    https://${URL}/"
echo ""
echo "  Log in with user '${AUTH_USER}' and the password above."
echo "  Then go to https://${URL}/resume to upload your resume."
