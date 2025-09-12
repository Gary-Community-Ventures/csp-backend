
#!/bin/bash

# Create Family Script
# Usage: ./create_family.sh <environment> [email] [supabase_id]
# Example: ./create_family.sh "dev" "family@example.com" "1abc123def456ghi789jkl"
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
    echo "Usage: $0 <environment> [email] [supabase_id]"
    echo "Environments: dev, staging, prod"
    echo "Example: $0 'dev' 'family@example.com' '1abc123def456ghi789jkl'"
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
EMAIL=${2:-"family@example.com"}
SUPABASE_ID=${3:-"1abc123def456ghi789jkl"}

echo "Creating new family..."
echo "Environment: $ENVIRONMENT"
echo "Base URL: $BASE_URL"
echo "Email: $EMAIL"
echo "Google Sheet ID: $SUPABASE_ID"
echo ""

curl -X POST "$BASE_URL/family" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "{
        \"family_id\": \"$SUPABASE_ID\",
        \"email\": \"$EMAIL\"
    }" \
    -w "\nHTTP Status: %{http_code}\n" \
    -v
