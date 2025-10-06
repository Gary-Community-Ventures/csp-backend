#!/usr/bin/env python
"""
Manual script to reclaim funds from Chek accounts back into the program wallet.

Usage:
    python app/scripts/reclaim_funds.py --amount 1000 --chek-user-id <chek_user_id>
    python app/scripts/reclaim_funds.py --amount 5000 --family-id <family_id>
    python app/scripts/reclaim_funds.py --amount 2500 --child-id <child_id>
    python app/scripts/reclaim_funds.py --amount 3000 --provider-id <provider_id>
"""

import argparse
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from flask import current_app

from app import create_app

# Create Flask app context
app = create_app()
app.app_context().push()


def reclaim_funds(amount, chek_user_id=None, family_id=None, child_id=None, provider_id=None, dry_run=False):
    """Reclaim funds from a Chek account back to the program wallet."""

    if dry_run:
        print(f"\n[DRY RUN] Would reclaim ${amount / 100:.2f}")
        if chek_user_id:
            print(f"  From Chek User ID: {chek_user_id}")
        elif family_id:
            print(f"  From Family ID: {family_id}")
        elif child_id:
            print(f"  From Child ID: {child_id}")
        elif provider_id:
            print(f"  From Provider ID: {provider_id}")
        return True

    try:
        print(f"\nReclaiming ${amount / 100:.2f} from Chek account...")

        if chek_user_id:
            print(f"  Using chek_user_id: {chek_user_id}")
            response = current_app.payment_service.reclaim_funds(chek_user_id=int(chek_user_id), amount=amount)
        elif family_id:
            print(f"  Using family_id: {family_id}")
            response = current_app.payment_service.reclaim_funds_by_family(family_id=family_id, amount=amount)
        elif child_id:
            print(f"  Using child_id: {child_id}")
            response = current_app.payment_service.reclaim_funds_by_child(child_id=child_id, amount=amount)
        elif provider_id:
            print(f"  Using provider_id: {provider_id}")
            response = current_app.payment_service.reclaim_funds_by_provider(provider_id=provider_id, amount=amount)
        else:
            print("❌ Error: No ID provided")
            return False

        print("✅ Funds reclaimed successfully!")
        print(
            f"  Transfer Source: {response.source.type} (ID: {response.source.id}), Balance After: ${response.source.balance / 100:.2f}"
        )
        print(
            f"  Transfer Destination: {response.destination.type} (ID: {response.destination.id}), Balance After: ${response.destination.balance / 100:.2f}"
        )
        print(f"  Transaction ID: {response.transfer.id}")
        print(f"  Amount: ${response.transfer.amount / 100:.2f}")
        return True

    except Exception as e:
        print(f"❌ Failed to reclaim funds: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Reclaim funds from Chek accounts back into the program wallet.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python app/scripts/reclaim_funds.py --amount 1000 --chek-user-id <chek_user_id>
  python app/scripts/reclaim_funds.py --amount 5000 --family-id <family_id>
  python app/scripts/reclaim_funds.py --amount 2500 --child-id <child_id> --dry-run
        """,
    )
    parser.add_argument("--amount", type=int, required=True, help="Amount to reclaim in cents (e.g., 1000 for $10.00)")
    parser.add_argument("--chek-user-id", type=int, help="Chek user ID")
    parser.add_argument("--family-id", type=str, help="Family Supabase ID")
    parser.add_argument("--child-id", type=str, help="Child Supabase ID")
    parser.add_argument("--provider-id", type=str, help="Provider Supabase ID")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be reclaimed without actually reclaiming"
    )

    args = parser.parse_args()

    # Validate that exactly one ID is provided
    id_count = sum(
        [
            args.chek_user_id is not None,
            args.family_id is not None,
            args.child_id is not None,
            args.provider_id is not None,
        ]
    )

    if id_count == 0:
        parser.error("Must provide exactly one of: --chek-user-id, --family-id, --child-id, --provider-id")
    elif id_count > 1:
        parser.error("Must provide exactly one ID type, not multiple")

    # Validate amount is positive
    if args.amount <= 0:
        parser.error("Amount must be greater than 0")

    try:
        # Show summary
        print("\n" + "=" * 60)
        print("Reclaim Funds Summary")
        print("=" * 60)
        print(f"Amount: ${args.amount / 100:.2f}")
        if args.chek_user_id:
            print(f"From: Chek User ID {args.chek_user_id}")
        elif args.family_id:
            print(f"From: Family ID {args.family_id}")
        elif args.child_id:
            print(f"From: Child ID {args.child_id}")
        elif args.provider_id:
            print(f"From: Provider ID {args.provider_id}")

        if args.dry_run:
            print("\n[DRY RUN MODE - No changes will be made]")
            success = reclaim_funds(
                amount=args.amount,
                chek_user_id=args.chek_user_id,
                family_id=args.family_id,
                child_id=args.child_id,
                provider_id=args.provider_id,
                dry_run=True,
            )
        else:
            # Confirm action
            confirm = input("\nAre you sure you want to reclaim these funds? (yes/no): ")
            if confirm.lower() != "yes":
                print("Aborted.")
                sys.exit(0)

            # Execute reclaim
            success = reclaim_funds(
                amount=args.amount,
                chek_user_id=args.chek_user_id,
                family_id=args.family_id,
                child_id=args.child_id,
                provider_id=args.provider_id,
            )

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
