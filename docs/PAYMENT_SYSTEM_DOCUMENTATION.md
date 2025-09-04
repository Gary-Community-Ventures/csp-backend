# Payment System Documentation

## Overview
The CSP Backend payment system manages monthly allocations for children and facilitates payments from families to providers through the Chek payment platform. The system supports both allocated care days and lump sum payments, with payments flowing through ACH or virtual cards.

## Payment Flow Architecture

### Complete Payment Flow: Program → Family → Provider → Payment Method

```
1. Program → Family (Monthly Allocation)
   - Program allocates funds to family's Chek wallet
   - Triggered when MonthAllocation is created
   
2. Family → Provider (Care Day/Lump Sum Payment)
   - Family's wallet funds provider's wallet
   - Triggered when care days are submitted or lump sums are created
   
3. Provider Wallet → Payment Method
   - ACH: Wallet funds transferred to provider's bank account
   - Virtual Card: Wallet funds loaded onto provider's virtual card
```

## 1. MonthAllocation Creation

### How MonthAllocations are Created

MonthAllocations represent the monthly budget allocated to each child for care services. They are created through:

#### Automatic Creation (app/models/month_allocation.py:115-183)
- **Method**: `MonthAllocation.get_or_create_for_month(child_id, month_date)`
- **Process**:
  1. Normalizes date to first of month
  2. Validates not creating for past months or more than 1 month in future
  3. Gets allocation amount from Google Sheets (prorated for first month)
  4. Creates allocation record with maximum limit of $1400 (MAX_ALLOCATION_AMOUNT_CENTS)
  5. **Transfers funds from Program to Family wallet** via Chek (if allocation > 0)
  6. Stores Chek transfer ID and date for tracking

#### Manual Creation Scripts
- **create_monthly_allocations.py**: Batch creation for all children
- **create_transactions_for_allocations.py**: Creates Chek transfers for existing allocations

### Key Properties
- `allocation_cents`: Total monthly budget
- `selected_cents`: Amount promised (care days + lump sums)
- `paid_cents`: Amount actually paid out
- `remaining_unselected_cents`: Budget available for new allocations
- `remaining_unpaid_cents`: Actual remaining allocation after payments

## 2. Payment Submission Methods

### 2.1 Allocated Care Days (app/models/allocated_care_day.py)

Care days represent individual days of care provided to a child.

#### Submission Process:
1. Care days are created with date, type (FULL_DAY/HALF_DAY), and provider
2. Amount calculated based on day type and provider rates
3. Days are locked after Monday 23:59:59 of their week (business timezone)
4. Submitted care days are processed in batches by provider-child combination

#### Key Features:
- **Locking System**: Days become immutable after their week's lock date
- **Soft Delete**: Care days can be soft-deleted but remain in DB
- **Duplicate Prevention**: Unique constraint on allocation/provider/date

### 2.2 Lump Sum Payments (app/models/allocated_lump_sum.py)

Lump sums are one-time payments for services not covered by daily rates.

#### Creation Process:
1. Created via `AllocatedLumpSum.create_lump_sum()`
2. Validates amount doesn't exceed $1400 limit
3. Checks allocation has sufficient remaining budget
4. Immediately marked as submitted

## 3. Chek Payment Integration

### Payment Service Architecture (app/services/payment/payment_service.py)

The PaymentService orchestrates all payment operations through Chek:

#### Payment Processing Flow:
1. **Validation Phase**
   - Provider has payment settings configured
   - Amount doesn't exceed $1400 limit
   - Sufficient allocation and wallet balance available
   - Payment method (ACH/Card) is properly configured

2. **Intent Creation**
   - PaymentIntent captures what we're paying for
   - Links care days/lump sums to be paid
   - Stores provider and family payment settings

3. **Attempt Execution** (app/services/payment/payment_service.py:212-333)
   - Creates PaymentAttempt record
   - **Step 1**: Transfer funds Family Wallet → Provider Wallet
   - **Step 2**: Execute payment method:
     - **ACH**: Initiate Same-Day ACH from wallet to bank
     - **Card**: Transfer funds from wallet to virtual card
   - Records all Chek transaction IDs

4. **Payment Completion**
   - Creates Payment record only after successful attempt
   - Links paid items to Payment
   - Sends notification email to provider

### Chek Integration Service (app/integrations/chek/service.py)

Provides API wrapper for Chek operations:
- User management (create, get, list)
- Virtual card creation and funding
- Direct pay account (ACH) setup
- Wallet-to-wallet transfers
- ACH payment initiation

## 4. Payment Scripts

### Core Payment Scripts

1. **create_monthly_allocations.py**
   - Creates MonthAllocations for all children
   - Supports current/next/specific month
   - Includes dry-run mode
   - Automatically transfers funds to family wallets

2. **run_payment_requests.py**
   - Processes submitted care days pending payment
   - Groups by provider-child combination
   - Executes payments through PaymentService
   - Updates payment_distribution_requested flag

3. **create_transactions_for_allocations.py**
   - Backfills Chek transfers for existing allocations
   - Updates allocations with transfer IDs
   - Handles specific children or all

4. **retry_failed_payments.py**
   - Lists and retries failed payment intents
   - Supports filtering by date
   - Can retry specific intent or all failures

### Onboarding Scripts

5. **onboard_providers_to_chek.py**
   - Creates Chek users for providers
   - Sets up payment methods (ACH/Card)
   - Updates ProviderPaymentSettings

6. **onboard_families_to_chek.py**
   - Creates Chek users for families
   - Sets up FamilyPaymentSettings
   - Links families to children

## 5. Database Models

### Payment Tracking Models
- **MonthAllocation**: Monthly budget per child
- **AllocatedCareDay**: Individual care day records
- **AllocatedLumpSum**: One-time payment records
- **PaymentIntent**: Captures payment request details
- **PaymentAttempt**: Records each payment try
- **Payment**: Successful payment records
- **ProviderPaymentSettings**: Provider Chek account info
- **FamilyPaymentSettings**: Family Chek account info

## 6. Identified Bugs and Issues

### 🐛 BUG #1: Incorrect Wallet-to-Wallet Transfer Configuration
**Location**: app/services/payment/payment_service.py:262-263
```python
transfer_request = TransferBalanceRequest(
    flow_direction=FlowDirection.WALLET_TO_WALLET.value,
    program_id=provider_payment_settings.chek_user_id,  # BUG: Should be family's user_id
    counterparty_id=provider_payment_settings.chek_user_id,  # BUG: Both are set to provider
    amount=intent.amount_cents,
```
**Issue**: For wallet-to-wallet transfers from family to provider, the `program_id` should be the family's Chek user ID (the sender), not the provider's. Currently both fields are set to the provider's ID, which likely causes the transfer to fail or behave incorrectly.

**Fix Required**: 
```python
program_id=family_payment_settings.chek_user_id,  # Sender (family)
counterparty_id=provider_payment_settings.chek_user_id,  # Receiver (provider)
```

### 🐛 BUG #2: Similar Issue in Family Allocation Transfer
**Location**: app/services/payment/payment_service.py:911-912
```python
transfer_request = TransferBalanceRequest(
    flow_direction=FlowDirection.PROGRAM_TO_WALLET.value,
    program_id=self.chek_service.program_id,  # Correct for program-to-wallet
    counterparty_id=self.chek_service.program_id,  # BUG: Should be family's user_id
```
**Issue**: The counterparty_id should be the family's Chek user ID (the receiver), not the program ID again.

### ⚠️ Potential Issue #3: Race Condition in Allocation Creation
**Location**: app/models/month_allocation.py:173-182
- The code handles IntegrityError for race conditions but if the allocation is not found after rollback, it raises a RuntimeError
- This could happen if the competing process also fails or rolls back

## 7. API Endpoints

### Provider Routes (app/routes/provider.py)
- Provider payment settings management
- Payment history viewing

### Payment Routes (app/routes/payments.py)
- Payment processing endpoints
- Payment status checking

### Care Day Routes (app/routes/care_day.py)
- Care day creation and submission
- Bulk care day operations

### Lump Sum Routes (app/routes/lump_sum.py)
- Lump sum creation
- Lump sum payment processing

## 8. Security Considerations

1. **Payment Limits**: Maximum payment of $1400 per transaction
2. **Allocation Validation**: Payments cannot exceed monthly allocation
3. **Wallet Balance Check**: Ensures sufficient funds before transfer
4. **Payment Method Validation**: Verifies ACH/Card setup before payment
5. **Idempotency**: Unique constraints prevent duplicate allocations/payments

## 9. Monitoring and Debugging

### Key Log Points:
- Allocation creation (with transfer IDs)
- Payment intent creation
- Payment attempt steps (wallet transfer, ACH/card transfer)
- Error tracking with Sentry integration

### Database Queries for Troubleshooting:
- Check allocation status: `MonthAllocation.query.filter_by(...)`
- Find failed payments: `PaymentIntent` with failed `PaymentAttempt`
- Track payment flow: Follow `payment_intent_id` through attempts

## 10. Testing Recommendations

1. **Fix the wallet transfer bugs** before production deployment
2. Test race condition handling in allocation creation
3. Verify payment retry logic for partial failures
4. Ensure proper cleanup of failed payment attempts
5. Validate all payment limit checks

## Summary

The payment system provides a comprehensive solution for managing childcare payments through:
- Automated monthly allocation creation with fund transfers
- Flexible payment submission via care days or lump sums  
- Robust Chek integration for wallet and payment management
- Multiple payment methods (ACH and Virtual Cards)
- Extensive scripts for operations and troubleshooting

However, critical bugs in the wallet transfer logic need immediate attention to ensure proper fund flow from families to providers.