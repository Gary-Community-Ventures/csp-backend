from clerk_backend_api import Clerk, CreateInvitationRequestBody
from flask import Blueprint, abort, jsonify, request, current_app

from app.extensions import db
from app.models.family import Family

from app.auth.decorators import ClerkUserType, auth_required
from datetime import datetime, timedelta
import random


bp = Blueprint("family", __name__)


# TODO: add api key
@bp.post("/family")
def new_family():
    data = request.json

    # Validate required fields
    if 'google_sheet_id' not in data:
        abort(400, description="Missing required fields: google_sheet_id")

    if 'email' not in data:
        abort(400, description="Missing required field: email")

    if Family.query.filter_by(google_sheet_id=data['google_sheet_id']).first():
        abort(409, description=f"A family with that Google Sheet ID already exists.")

    # Create new family
    family = Family.from_dict(data)
    db.session.add(family)
    db.session.commit()

    # send clerk invite
    clerk: Clerk = current_app.clerk_client
    fe_domain = current_app.config.get("FRONTEND_DOMAIN")
    meta_data = {
        "types": [ClerkUserType.FAMILY],  # NOTE: list in case we need to have people who fit into multiple categories
        "family_id": family.id,  
    }

    clerk.invitations.create(
        request=CreateInvitationRequestBody(
            email_address=data["email"], redirect_url=f"{fe_domain}/auth/sign-up", public_metadata=meta_data
        )
    )

    return jsonify(data)


@bp.get("/family")
@auth_required(ClerkUserType.FAMILY)
def family_data():
    # Generate random caregivers
    caregivers = []
    num_caregivers = random.randint(3, 7)
    caregiver_names = [
        "The Nanny Bot",
        "Super Sitter Squad",
        "Granny Galactic",
        "Uncle Wobbly",
        "Auntie Doodle",
        "The Cuddle Crew",
        "Professor Playtime",
        "The Giggle Gang",
        "The Dream Weaver",
        "Snuggle Bear Services",
        "The Imagination Station",
    ]
    for _ in range(num_caregivers):
        caregivers.append(
            {
                "name": random.choice(caregiver_names),
                "approved": random.choice([True, False]),
            }
        )

    # Generate random transactions with random dates
    transactions = []
    num_transactions = random.randint(5, 10)
    for _ in range(num_transactions):
        transactions.append(
            {
                "provider": "",  # Placeholder
                "amount": 0.0,  # Placeholder
                "date": (datetime.now() - timedelta(days=random.randint(1, 30))).isoformat(),
            }
        )

    # Sort transactions by date (newest first)
    transactions.sort(key=lambda x: x["date"], reverse=True)

    # Apply the +--+-- pattern to the sorted transactions
    for i, transaction in enumerate(transactions):
        if i % 3 == 0:  # Positive transaction
            transaction["amount"] = 1200.00
            transaction["provider"] = "Childcare Subsidy"
        else:  # Negative transaction
            transaction["amount"] = round(random.uniform(-500.00, -50.00), 2)  # Ensure negative amounts
            transaction["provider"] = random.choice(caregiver_names)

    # Calculate balance from transactions and ensure it's positive
    total_balance = sum(t["amount"] for t in transactions)
    if total_balance <= 0:
        total_balance += random.uniform(500.00, 2000.00)  # Add a positive offset if balance is not positive

    # Generate random household info
    first_names = [
        "Captain",
        "Sparkle",
        "Professor",
        "Whimsy",
        "Ziggy",
        "Luna",
        "Pixel",
        "Gizmo",
        "Jubilee",
        "Stardust",
    ]
    last_names = [
        "Pants",
        "Sprinkles",
        "Fuzzypaws",
        "McAwesome",
        "Bubblegum",
        "Von Wigglebottom",
        "Thunderfoot",
        "Gigglesworth",
        "Moonbeam",
        "Snugglepuff",
    ]
    household_info = {
        "first_name": random.choice(first_names),
        "last_name": random.choice(last_names),
        "balance": round(total_balance, 2),
    }

    return jsonify(
        {
            "household_info": household_info,
            "caregivers": caregivers,
            "transactions": transactions,
        }
    )
