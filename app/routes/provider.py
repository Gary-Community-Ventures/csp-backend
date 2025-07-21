from clerk_backend_api import Clerk, CreateInvitationRequestBody
from flask import Blueprint, abort, jsonify, request, current_app

from app.extensions import db
from app.models.provider import Provider

from app.auth.decorators import ClerkUserType, auth_required
from datetime import datetime, timedelta
import random


bp = Blueprint("provider", __name__)


# TODO: add api key
@bp.post("/provider")
def new_provider():
    data = request.json

    # Validate required fields
    if 'google_sheet_id' not in data:
        abort(400, description="Missing required fields: google_sheet_id")

    if 'email' not in data:
        abort(400, description="Missing required field: email")

    if Provider.query.filter_by(google_sheet_id=data['google_sheet_id']).first():
        abort(409, description=f"A provider with that Google Sheet ID already exists.")

    # Create new provider
    provider = Provider.new(google_sheet_id=data["google_sheet_id"])
    db.session.add(provider)
    db.session.commit()

    # send clerk invite
    clerk: Clerk = current_app.clerk_client
    fe_domain = current_app.config.get("FRONTEND_DOMAIN")
    meta_data = {
        "types": [
            ClerkUserType.PROVIDER
        ],  # NOTE: list in case we need to have people who fit into multiple categories
        "provider_id": provider.id, 
    }

    clerk.invitations.create(
        request=CreateInvitationRequestBody(
            email_address=data["email"],
            redirect_url=f"{fe_domain}/auth/sign-up",
            public_metadata=meta_data
        )
    )

    return jsonify(data)


@bp.get("/provider")
@auth_required(ClerkUserType.PROVIDER)
def get_provider_data():
    # Generate ProviderInfo
    first_names = ["Professor", "Captain", "Doctor", "Auntie", "Uncle", "Nanny", "Sir", "Dame"]
    last_names = ["Giggles", "Sparkle", "Wobbly", "Cuddle", "Chaos", "Doo-Little", "Snuggles", "McPhee"]
    provider_info = {
        "first_name": random.choice(first_names),
        "last_name": random.choice(last_names),
    }

    # Generate Children
    children = []
    num_children = random.randint(1, 3)
    child_names = [
        {"first_name": "Alex", "last_name": "Bregman"},
        {"first_name": "Abraham", "last_name": "Toro"},
        {"first_name": "Marcelo", "last_name": "Mayer"},
        {"first_name": "Trevor", "last_name": "Story"},
        {"first_name": "Jarren", "last_name": "Duran"},
        {"first_name": "Wilyer", "last_name": "Abreu"},
        {"first_name": "Ceddanne", "last_name": "Rafaela"},
        {"first_name": "Roman", "last_name": "Anthony"},
        {"first_name": "Carlos", "last_name": "Narváez"},
        {"first_name": "Garrett", "last_name": "Crochet"},
        {"first_name": "Aroldis", "last_name": "Chapman"},
        {"first_name": "Garrett", "last_name": "Whitlock"},
        {"first_name": "Brayan", "last_name": "Bello"},
    ]
    for _ in range(num_children):
        children.append(random.choice(child_names))

    # Generate Payments
    payments = []
    num_payments = random.randint(3, 7)
    payment_providers = ["Family A", "Family B", "Family C", "Subsidy Program"]
    for _ in range(num_payments):
        payments.append(
            {
                "provider": random.choice(payment_providers),
                "amount": round(random.uniform(50.00, 500.00), 2),
                "date": (datetime.now() - timedelta(days=random.randint(1, 90))).isoformat(),
            }
        )

    # Generate Curriculum
    curriculum_descriptions = [
        "Early childhood development program focusing on play-based learning.",
        "STEM-focused curriculum with hands-on experiments.",
        "Arts and crafts integrated learning for creative expression.",
        "Outdoor education program emphasizing nature exploration.",
    ]
    curriculum = {
        "description": random.choice(curriculum_descriptions),
    }

    provider_data = {
        "provider_info": provider_info,
        "children": children,
        "payments": payments,
        "curriculum": curriculum,
    }

    return jsonify(provider_data)
