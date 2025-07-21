from clerk_backend_api import Clerk, CreateInvitationRequestBody
from flask import Blueprint, abort, jsonify, request, current_app
from app.auth.decorators import ClerkUserType, auth_required
from datetime import datetime, timedelta
import random


bp = Blueprint("caregiver", __name__)


# TODO: add api key
@bp.post("/caregiver")
def new_caregiver():
    data = request.json

    try:
        email = data["email"]
    except KeyError:
        abort(400)

    # TODO: create caregiver in db

    # send clerk invite
    clerk: Clerk = current_app.clerk_client
    fe_domain = current_app.config.get("FRONTEND_DOMAIN")
    meta_data = {
        "types": [
            ClerkUserType.CAREGIVER
        ],  # NOTE: list in case we need to have people who fit into multiple categories
        "caregiver_id": 0,  # TODO: add
    }

    clerk.invitations.create(
        request=CreateInvitationRequestBody(
            email_address=email, redirect_url=f"{fe_domain}/auth/sign-up", public_metadata=meta_data
        )
    )

    return jsonify(data)


@bp.get("/caregiver")
# @auth_required(ClerkUserType.CAREGIVER)
def get_caregiver_data():
    # Generate CaregiverInfo
    first_names = ["Professor", "Captain", "Doctor", "Auntie", "Uncle", "Nanny", "Sir", "Dame"]
    last_names = ["Giggles", "Sparkle", "Wobbly", "Cuddle", "Chaos", "Doo-Little", "Snuggles", "McPhee"]
    caregiver_info = {
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

    caregiver_data = {
        "caregiver_info": caregiver_info,
        "children": children,
        "payments": payments,
        "curriculum": curriculum,
    }

    return jsonify(caregiver_data)
