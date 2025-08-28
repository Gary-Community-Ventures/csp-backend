#!/bin/bash

# Monthly allocation creation helper script
# Makes it easy to create allocations from the shell

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 [current|next|YYYY-MM] [--dry-run]"
    echo ""
    echo "Examples:"
    echo "  $0                     # Create for current month"
    echo "  $0 current             # Create for current month"
    echo "  $0 next               # Create for next month"
    echo "  $0 2024-03           # Create for March 2024"
    echo "  $0 current --dry-run  # Preview what would be created for current month"
    echo ""
    exit 1
}

if [ $# -eq 0 ]; then
    # Default: current month
    echo -e "${GREEN}Creating allocations for current month...${NC}"
    docker compose exec -w /app backend python app/scripts/create_monthly_allocations.py
elif [ "$1" = "current" ]; then
    if [ "$2" = "--dry-run" ]; then
        echo -e "${YELLOW}[DRY RUN] Previewing allocations for current month...${NC}"
        docker compose exec -w /app backend python app/scripts/create_monthly_allocations.py --dry-run
    else
        echo -e "${GREEN}Creating allocations for current month...${NC}"
        docker compose exec -w /app backend python app/scripts/create_monthly_allocations.py
    fi
elif [ "$1" = "next" ]; then
    if [ "$2" = "--dry-run" ]; then
        echo -e "${YELLOW}[DRY RUN] Previewing allocations for next month...${NC}"
        docker compose exec -w /app backend python app/scripts/create_monthly_allocations.py --next-month --dry-run
    else
        echo -e "${GREEN}Creating allocations for next month...${NC}"
        docker compose exec -w /app backend python app/scripts/create_monthly_allocations.py --next-month
    fi
elif [[ "$1" =~ ^[0-9]{4}-[0-9]{2}$ ]]; then
    # Specific month format YYYY-MM
    if [ "$2" = "--dry-run" ]; then
        echo -e "${YELLOW}[DRY RUN] Previewing allocations for $1...${NC}"
        docker compose exec -w /app backend python app/scripts/create_monthly_allocations.py --month "$1" --dry-run
    else
        echo -e "${GREEN}Creating allocations for $1...${NC}"
        docker compose exec -w /app backend python app/scripts/create_monthly_allocations.py --month "$1"
    fi
elif [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    usage
else
    echo -e "${RED}❌ Invalid arguments${NC}"
    usage
fi