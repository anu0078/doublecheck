#!/usr/bin/env bash
# Deploy DoubleCheck to Google Cloud Run. Run this inside Google Cloud Shell:
#   git clone https://github.com/anu0078/doublecheck && cd doublecheck && bash deploy_cloudrun.sh
#
# Keys are typed in hidden prompts (not stored in your shell history).
set -euo pipefail

SERVICE="doublecheck"
REGION="${REGION:-asia-south1}"     # Mumbai

PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
if [[ -z "${PROJECT}" ]]; then
  echo "No Google Cloud project selected. Run:  gcloud config set project YOUR_PROJECT_ID"
  exit 1
fi
echo "Project: ${PROJECT}   Region: ${REGION}"

read -rsp "Paste GEMINI_API_KEY (hidden, press Enter to skip): " GEMINI_API_KEY; echo
read -rsp "Paste TELEGRAM_BOT_TOKEN (hidden, press Enter to skip): " TELEGRAM_BOT_TOKEN; echo

echo "Turning on the needed Google Cloud services (first time only)..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --quiet

echo "Building and deploying (takes 3-5 minutes)..."
# max-instances 1: rate limits and family link codes live in memory, so keep one copy.
gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --allow-unauthenticated \
  --max-instances 1 \
  --memory 512Mi \
  --quiet \
  --set-env-vars "GEMINI_API_KEY=${GEMINI_API_KEY},TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN},GEMINI_MODEL=gemini-flash-latest,TRUST_PROXY=true,ALLOWED_ORIGINS=*"

URL="$(gcloud run services describe "${SERVICE}" --region "${REGION}" --format 'value(status.url)')"

if [[ -n "${TELEGRAM_BOT_TOKEN}" ]]; then
  echo "Connecting the Telegram bot to ${URL} ..."
  gcloud run services update "${SERVICE}" --region "${REGION}" --quiet \
    --update-env-vars "PUBLIC_URL=${URL}"
fi

echo ""
echo "=============================================="
echo " DoubleCheck is live:  ${URL}"
echo " Health check:         ${URL}/api/health"
echo "=============================================="
