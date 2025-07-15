from clerk_backend_api import Clerk, CreateInvitationRequestBody
from flask import Blueprint, abort, jsonify, request, current_app
from app.constants import CLERK_FAMILY_TYPE

bp = Blueprint("family", __name__)


# TODO: add api key
@bp.post("/family")
def new_family():
    data = request.json

    try:
        email = data["email"]
    except KeyError:
        abort(400)

    # TODO: create family in db

    # send clerk invite
    clerk: Clerk = current_app.clerk_client
    fe_domain = current_app.config.get("FRONTEND_DOMAIN")
    meta_data = {
        "types": [CLERK_FAMILY_TYPE],  # NOTE: list in case we need to have people who fit into multiple categories
    }

    clerk.invitations.create(
        request=CreateInvitationRequestBody(
            email_address=email, redirect_url=f"{fe_domain}/sign-up", public_metadata=meta_data
        )
    )

    return jsonify(data)
