#!/bin/bash

# Create Provider Script
# Usage: ./create_provider.sh <environment> [email] [google_sheet_id] [language]
# Example: ./create_provider.sh "dev" "provider@example.com" "1xyz789abc123def456ghi" "en"
# Environments: dev, staging, prod

# Load environment variables from .env.local
if [ -f ".env.local" ]; then
    export $(cat .env.local | grep -v '^#' | xargs)
else
    echo "Error: .env.local file not found"
    echo "Please create .env.local with your API keys:"
    echo "DEV_API_KEY=your-dev-api-key"
    echo "STAGING_API_KEY=your-staging-api-key" 
    echo "PROD_API_KEY=your-prod-api-key"
    exit 1
fi

# Check if required parameters are provided
if [ $# -lt 1 ]; then
    echo "Usage: $0 <environment> [email] [google_sheet_id] [language]"
    echo "Environments: dev, staging, prod"
    echo "Example: $0 'dev' 'provider@example.com' '1xyz789abc123def456ghi' 'en'"
    exit 1
fi

# Get required parameters
ENVIRONMENT="$1"

# Set BASE_URL and API_KEY based on environment
case "$ENVIRONMENT" in
    "dev")
        BASE_URL="http://localhost:5000"
        API_KEY="$DEV_API_KEY"
        ;;
    "staging")
        BASE_URL="https://csp-backend-staging-9941beb4ce92.herokuapp.com"
        API_KEY="$STAGING_API_KEY"
        ;;
    "prod")
        BASE_URL="https://csp-backend-prod-da664667e828.herokuapp.com"
        API_KEY="$PROD_API_KEY"
        ;;
    *)
        echo "Invalid environment: $ENVIRONMENT"
        echo "Valid environments: dev, staging, prod"
        exit 1
        ;;
esac

# Check if API key is set for this environment
if [ -z "$API_KEY" ]; then
    echo "Error: API key not set for $ENVIRONMENT environment"
    echo "Please add ${ENVIRONMENT^^}_API_KEY to your .env.local file"
    exit 1
fi

# Get optional parameters from command line or use defaults
EMAIL=${2:-"provider@example.com"}
GOOGLE_SHEET_ID=${3:-"1xyz789abc123def456ghi"}
LANGUAGE=${4:-"en"}

echo "Creating new provider..."
echo "Environment: $ENVIRONMENT"
echo "Base URL: $BASE_URL"
echo "Email: $EMAIL"
echo "Google Sheet ID: $GOOGLE_SHEET_ID"
echo ""

curl -X POST "$BASE_URL/provider" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "{
        \"google_sheet_id\": \"$GOOGLE_SHEET_ID\",
        \"email\": \"$EMAIL\",
        \"language\": \"$LANGUAGE\"
    }" \
    -w "\nHTTP Status: %{http_code}\n" \
    -v
