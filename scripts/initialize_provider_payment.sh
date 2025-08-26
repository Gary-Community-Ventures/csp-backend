#!/bin/bash

# Script to initialize a provider's payment method (Card or ACH)
# Usage: ./scripts/initialize_provider_payment.sh <provider_id> <payment_method>
# Example: ./scripts/initialize_provider_payment.sh PROV001 card
# Example: ./scripts/initialize_provider_payment.sh PROV001 ach

# Check if provider ID and payment method are provided
if [ $# -lt 2 ]; then
    echo "Usage: $0 <provider_id> <payment_method>"
    echo "  payment_method: 'card' or 'ach'"
    echo ""
    echo "Examples:"
    echo "  $0 PROV001 card    # Initialize virtual card for provider PROV001"
    echo "  $0 PROV001 ach     # Send ACH invite to provider PROV001"
    exit 1
fi

PROVIDER_ID=$1
PAYMENT_METHOD=$2

# Validate payment method
if [[ "$PAYMENT_METHOD" != "card" && "$PAYMENT_METHOD" != "ach" ]]; then
    echo "Error: payment_method must be 'card' or 'ach'"
    exit 1
fi

# Get environment variables or use defaults
BASE_URL=${BASE_URL:-"http://localhost:5001"}
API_KEY=${API_KEY:-"your_api_key_here"}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "Initializing payment for provider: $PROVIDER_ID"
echo "Payment method: $PAYMENT_METHOD"
echo "API URL: $BASE_URL/provider/$PROVIDER_ID/initialize-payment"
echo "----------------------------------------"

# Make the API request
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
  "$BASE_URL/provider/$PROVIDER_ID/initialize-payment" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{\"payment_method\": \"$PAYMENT_METHOD\"}")

# Extract HTTP status code and response body
HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | head -n -1)

# Check response
if [ "$HTTP_CODE" -eq 200 ]; then
    echo -e "${GREEN}✓ Payment initialization successful!${NC}"
    echo ""
    echo "Response:"
    echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
    
    # Extract key information from response if available
    if command -v python3 &> /dev/null; then
        MESSAGE=$(echo "$BODY" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data.get('message', ''))" 2>/dev/null)
        if [ -n "$MESSAGE" ]; then
            echo ""
            echo -e "${GREEN}Status: $MESSAGE${NC}"
        fi
        
        # Check if already exists
        ALREADY_EXISTS=$(echo "$BODY" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data.get('already_exists', False))" 2>/dev/null)
        if [ "$ALREADY_EXISTS" == "True" ]; then
            echo -e "${YELLOW}Note: Payment method already exists for this provider${NC}"
        fi
        
        # Show relevant IDs
        if [ "$PAYMENT_METHOD" == "card" ]; then
            CARD_ID=$(echo "$BODY" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data.get('card_id', ''))" 2>/dev/null)
            if [ -n "$CARD_ID" ]; then
                echo "Card ID: $CARD_ID"
            fi
        else
            DIRECT_PAY_ID=$(echo "$BODY" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data.get('direct_pay_id', ''))" 2>/dev/null)
            INVITE_EMAIL=$(echo "$BODY" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data.get('invite_sent_to', ''))" 2>/dev/null)
            if [ -n "$DIRECT_PAY_ID" ]; then
                echo "DirectPay Account ID: $DIRECT_PAY_ID"
            fi
            if [ -n "$INVITE_EMAIL" ]; then
                echo -e "${YELLOW}ACH invite sent to: $INVITE_EMAIL${NC}"
                echo "Provider must complete setup via email invitation"
            fi
        fi
    fi
elif [ "$HTTP_CODE" -eq 400 ]; then
    echo -e "${RED}✗ Bad Request (400)${NC}"
    echo "Error: $BODY"
    exit 1
elif [ "$HTTP_CODE" -eq 404 ]; then
    echo -e "${RED}✗ Not Found (404)${NC}"
    echo "Provider $PROVIDER_ID not found in Google Sheets"
    exit 1
elif [ "$HTTP_CODE" -eq 500 ]; then
    echo -e "${RED}✗ Server Error (500)${NC}"
    echo "Error: $BODY"
    exit 1
else
    echo -e "${RED}✗ Request failed with status code: $HTTP_CODE${NC}"
    echo "Response: $BODY"
    exit 1
fi