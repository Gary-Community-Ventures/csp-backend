#!/bin/bash

# Onboard Family Script
# Usage: ./scripts/onboard_family.sh <environment> <clerk_user_id> <family_id>
# Example: ./scripts/onboard_family.sh "dev" "user_2abc123def456" "42"
# Environments: dev, staging, prod

# Get the project root directory (parent of scripts directory)
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Load environment variables from .env.local in project root
if [ -f "$PROJECT_ROOT/.env.local" ]; then
    export $(cat "$PROJECT_ROOT/.env.local" | grep -v '^#' | xargs)
else
    echo "Error: .env.local file not found in $PROJECT_ROOT"
    echo "Please create .env.local with your API keys:"
    echo "DEV_API_KEY=your-dev-api-key"
    echo "STAGING_API_KEY=your-staging-api-key"
    echo "PROD_API_KEY=your-prod-api-key"
    exit 1
fi

# Check if required parameters are provided
if [ $# -lt 3 ]; then
    echo "Usage: $0 <environment> <clerk_user_id> <family_id>"
    echo "Environments: dev, staging, prod"
    echo "Example: $0 'dev' 'user_2abc123def456' '42'"
    exit 1
fi

# Get required parameters
ENVIRONMENT="$1"
CLERK_USER_ID="$2"
FAMILY_ID="$3"

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

echo "Onboarding family..."
echo "Environment: $ENVIRONMENT"
echo "Base URL: $BASE_URL"
echo "Clerk User ID: $CLERK_USER_ID"
echo "Family ID: $FAMILY_ID"
echo ""

curl -X POST "$BASE_URL/family/onboard" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "{
        \"clerk_user_id\": \"$CLERK_USER_ID\",
        \"family_id\": \"$FAMILY_ID\"
    }" \
    -w "\nHTTP Status: %{http_code}\n" \
    -v
