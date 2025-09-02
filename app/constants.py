# --- Environment Constants ---
ENV_DEVELOPMENT = "development"
ENV_STAGING = "staging"
ENV_PRODUCTION = "production"
ENV_TESTING = "testing"
# --- End Environment Constants ---

# --- Business Logic Constants ---
BUSINESS_TIMEZONE = "America/Denver"  # Mountain Time for care day locking and business rules

# --- Payment Processing Constants ---
MAX_PAYMENT_AMOUNT_CENTS = 140000  # $1400 maximum per transaction
MAX_ALLOCATION_AMOUNT_CENTS = 140000  # $1400 maximum per month allocation

# --- Timing Constants ---
CHEK_STATUS_STALE_MINUTES = 1  # Minutes before Chek status is considered stale

# --- Date Calculation Constants ---
DAYS_TO_NEXT_MONTH = (
    32  # Days to add to current month to safely get into next month. Always used against first of month.
)

# --- User Restrictions ---
MAX_CHILDREN_PER_PROVIDER = 2

# --- Currency Constants ---
CENTS_PER_DOLLAR = 100

# --- Payment Rate Constants ---
MIN_PAYMENT_RATE = 1 * CENTS_PER_DOLLAR
MAX_PAYMENT_RATE = 160 * CENTS_PER_DOLLAR
