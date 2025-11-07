#!/bin/bash

# Migrate Supabase IDs Script
# Usage: ./migrate_supabase_ids.sh <environment> <json_file>
# Example: ./migrate_supabase_ids.sh "staging" "mappings.json"
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
    echo "Usage: $0 <environment> [json_file]"
    echo "Environments: dev, staging, prod"
    echo "Example: $0 'staging' 'mappings.json'"
    echo "Or pipe JSON: cat mappings.json | $0 'staging'"
    echo ""
    echo "JSON file format example:"
    echo "{"
    echo "  \"mappings\": {"
    echo "    \"children\": {\"123\": \"child_abc\", \"456\": \"child_def\"},"
    echo "    \"providers\": {\"789\": \"provider_ghi\"},"
    echo "    \"families\": {\"321\": \"family_xyz\"}"
    echo "  },"
    echo "  \"dry_run\": true,"
    echo "  \"force\": false"
    echo "}"
    exit 1
fi

# Get required parameters
ENVIRONMENT="$1"
JSON_FILE="$2"

# Determine if we're reading from stdin or file
if [ -z "$JSON_FILE" ]; then
    # No file provided, check if stdin has data
    if [ -t 0 ]; then
        echo "Error: No JSON file provided and no data piped to stdin"
        echo "Usage: $0 <environment> <json_file>"
        echo "Or: cat json_file | $0 <environment>"
        exit 1
    fi
    # Reading from stdin
    JSON_SOURCE="stdin"
    JSON_CONTENT=$(cat)
else
    # Reading from file
    if [ ! -f "$JSON_FILE" ]; then
        echo "Error: JSON file '$JSON_FILE' not found"
        exit 1
    fi
    JSON_SOURCE="file"
    JSON_CONTENT=$(cat "$JSON_FILE")
fi

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

echo "Migrating Supabase IDs..."
echo "Environment: $ENVIRONMENT"
echo "Base URL: $BASE_URL"
echo "JSON Source: $JSON_SOURCE"
if [ "$JSON_SOURCE" = "file" ]; then
    echo "JSON File: $JSON_FILE"
fi
echo ""

# Show the JSON content for confirmation
echo "JSON Content:"
echo "$JSON_CONTENT"
echo ""

echo "Sending migration request..."
echo ""

curl -X POST "$BASE_URL/admin/migrate/supabase-ids" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "$JSON_CONTENT" \
    -w "\nHTTP Status: %{http_code}\n" \
    -v

echo ""
echo "Migration request completed."
